# Short-code generation

**Chosen approach: base62-encode the Postgres `BIGSERIAL` id.** Not random
generation with a collision-retry loop.

## Why

This is the canonical TinyURL-style approach - the one every "design a URL
shortener" writeup uses - so it directly maps this exercise onto the classic
system-design interview problem.

It's collision-free *by construction*: Postgres guarantees `id` is unique, so
`base62(id)` is automatically unique too. No retry loop, no probability
argument about collision rates at scale needed.

It also cleanly separates two things that are easy to conflate:

- **Generated codes** - derived from `id`, so uniqueness is free.
- **Custom aliases** - an arbitrary user-supplied string, which needs an
  explicit uniqueness check because nothing else guarantees it.

Implementing both paths side by side, with visibly different uniqueness
strategies, is itself the lesson: not every "make this unique" problem needs
the same tool.

## Mechanics

1. Reserve an id: `SELECT nextval('links_id_seq')`.
2. Compute `short_code = base62(id)` in application code.
3. Insert `id` and `short_code` together in one statement.

Reserving the id first (rather than inserting-then-updating) avoids a
two-step write and avoids ever having a row with a null/placeholder
`short_code`.

Base62 alphabet: `0-9A-Za-z` (62 characters). No padding - `id=1` → `"1"`,
`id=61` → `"z"`, `id=62` → `"10"` (rolls over exactly like decimal rolls over
at 10, just in base 62).

## Custom alias path

1. Validate charset/length (`^[A-Za-z0-9_-]{4,16}$`).
2. Insert directly with the user's string as `short_code`.
3. **Catch the unique-violation, don't just pre-check.** A `SELECT ... WHERE
   short_code = $1` before the insert has an inherent race: two concurrent
   requests for the same alias can both pass the check before either
   commits. The unique index is the actual source of truth; the application
   catches the resulting constraint violation (Postgres error code `23505`)
   and returns `409 Conflict`. This is implemented identically in both
   services (`fastapi-service/app/routers/links.py`,
   `go-service/internal/handlers/links.go`) - it's a good concrete example
   of "the database is the only place that can actually enforce this."

## The alternative not taken

Random generation + collision-retry (generate a random string, check if it
exists, retry if taken) is the more production-grade approach at very high
write volume - it avoids sequential-id enumeration/guessing and avoids the
auto-increment sequence as a single point of write contention. It's not
implemented here to keep scope on the caching/analytics lessons that are the
actual point of this project, but it's worth knowing as the next step up in
sophistication.
