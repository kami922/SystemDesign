# Schema

```sql
CREATE TABLE links (
    id              BIGSERIAL PRIMARY KEY,
    short_code      VARCHAR(16) NOT NULL UNIQUE,
    long_url        TEXT NOT NULL,
    is_custom_alias BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at      TIMESTAMPTZ NULL,
    click_count     BIGINT NOT NULL DEFAULT 0
);

CREATE TABLE click_events (
    id          BIGSERIAL PRIMARY KEY,
    short_code  VARCHAR(16) NOT NULL REFERENCES links(short_code),
    clicked_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    ip_hint     TEXT NULL
);
```

Two tables, deliberately boring - this project is about caching and write paths,
not schema modeling.

## Why `id` is not just a surrogate key

`links.id` is a `BIGSERIAL`, and it directly drives short-code generation (see
[02-short-code-strategy.md](02-short-code-strategy.md)): `short_code =
base62(id)`. That's why the column exists at all, not just as an internal
primary key.

## Counter table vs event log

`click_count` on `links` is a denormalized running total, updated on every
redirect. `click_events` is an append-only detail log of every individual
click. The stats endpoint reads `click_count` directly (cheap, O(1)); a more
detailed query (clicks per day, last N clicks) would scan `click_events`
instead. Having both side by side is a deliberate illustration of the
"counter table vs event log" tradeoff that shows up constantly in real
systems: fast aggregate reads vs full historical detail, at the cost of
maintaining two things instead of one.

## One column, two invariants

`short_code` is `UNIQUE` and holds both generated codes and custom aliases -
there's no separate `aliases` table. A single unique index enforces
uniqueness for both cases, and the redirect path doesn't need to know or
care which kind of code it's looking up.

## Physical isolation, logical identity

`fastapi-postgres` and `go-postgres` are separate Postgres containers with
separate volumes, but both get this exact same DDL (`infra/init-sql/schema.sql`,
mounted into each container's `/docker-entrypoint-initdb.d/`). Same schema,
independent instances - this is what makes the Go vs FastAPI load test
comparison fair (see [05-load-test-design.md](05-load-test-design.md)).
