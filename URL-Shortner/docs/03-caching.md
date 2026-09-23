# Caching: cache-aside on the redirect hot path

This is the single most important system-design concept in this project.

## What's cached

Only what the redirect path needs to decide "redirect or 410" - not the
whole `links` row:

```
key:   link:{short_code}
value: {"long_url": "...", "expires_at": "..." | null}
```

Keeping the cached payload minimal matters on a hot path: less to serialize,
less to deserialize, smaller network payload to/from Redis, per request,
multiplied by however many redirects per second a hot code gets.

## TTL

`ttl = min(default_ttl (24h), time_until_expires_at)` - if a link has no
`expires_at`, it just gets the flat default. If it does, the cache entry is
set to expire at (or before) the link itself does.

## Read path

```
GET link:{code}
  hit  -> check expires_at in the cached value
            expired?     -> 410, don't touch Postgres
            still valid? -> redirect
  miss -> SELECT long_url, expires_at FROM links WHERE short_code = $1
            not found?   -> 404
            expired?     -> 410, don't cache (nothing gained from
                             remembering a dead entry)
            valid?       -> write-through into Redis with the TTL rule
                             above, then redirect
```

## Invalidation - or rather, the lack of it

This is worth stating explicitly because it's easy to assume you need more
machinery than you actually do:

- **Custom alias creation**: nothing to invalidate. The code didn't exist
  before, so there's no stale cache entry to worry about - the first read
  populates the cache exactly like a generated code would.
- **Expiration**: no active invalidation job needed. The Redis TTL is set to
  match (or precede) `expires_at`, so the entry falls out of cache on its
  own schedule. Once it's gone, the next read hits Postgres, sees
  `expires_at < now()`, returns 410, and (per the read path above) doesn't
  recache it.
- **Update/delete**: there are no update or delete endpoints in this
  project's scope, so "invalidate on update" simply doesn't apply here.

## What's *not* done (on purpose)

**Negative caching** (caching 404s for nonexistent codes) is not
implemented. It would protect Postgres from repeated lookups of codes that
don't exist, at the cost of extra cache-management complexity. Left as a
stretch extension - not needed to make the Zipfian load test in
[05-load-test-design.md](05-load-test-design.md) meaningful, since that test
only exercises real, seeded codes.

## Proof, not just description

Run this yourself (see the Milestone 2 section of the project history, or
just try it):

1. Redirect through a code once (cache miss → populated).
2. Stop the stack's Postgres container.
3. Redirect through that same code again - it still works. A never-hit code
   fails, because it was never cached.

That's cache-aside actually removing the database from the request path for
hot keys, observed directly rather than just asserted.
