# ADR 0007: Core SQL capability and SQLite baseline

- Status: Superseded by [ADR 0022](0022-extract-database-and-authentication.md)
- Date: 2026-10-04

## Context

Orbit needs a useful built-in database baseline for local development and simple embedded
applications, while keeping server database drivers and provider-specific concerns out of Core.
Application code should have one typed async SQL boundary so database adapters can be selected
without teaching Core about every database vendor. Redis and similar stores have key-value
semantics and should use a distinct capability rather than pretending to be SQL.

## Decision

Core defines `SQLDatabase`, `SQLTransaction`, bounded immutable result types, and a built-in
`SQLiteDatabase` that wraps stdlib `sqlite3` on one dedicated worker thread per instance. Calls on
an instance are serialized; transaction scopes reserve that serialization boundary until commit or
rollback. The portable scalar contract includes common text, numeric, byte, date/time, and UUID
values; SQLite binds the extended date/time, decimal, and UUID values as text and returns text on
reads. Core adds no database driver dependency.

Server SQL adapters live outside the Core package and implement the shared contract. Their
capability package owns uniform application-facing selection rules; each adapter owns its driver,
configuration, pooling, and provider-specific semantics. Non-SQL stores such as Redis use a
separate key-value capability.

## Alternatives considered

- Keep all database support outside Core: rejected because a lightweight local baseline is useful
  for development and basic applications.
- Add a third-party async SQLite driver: rejected because stdlib SQLite avoids a new mandatory
  runtime dependency and worker isolation keeps its blocking calls off the event loop.
- Model Redis through SQL: rejected because key-value operations have different semantics and
  should not inherit SQL's query/transaction abstraction.

## Consequences

SQLite is explicitly a local embedded baseline, not a server database or distributed store. The
common protocol intentionally avoids dialect-specific migrations, pooling, retries, and advanced
database features. Those require adapter-specific documentation and tests. The worker thread and
connection are resources owned by the `SQLiteDatabase` instance. Its async context-manager protocol
allows the Core container to manage the resource directly; concurrent `aclose` callers share one
cancellation-resistant shutdown operation. Callers outside a resource scope must close it with
`aclose`.
