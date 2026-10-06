# ADR 0014: Keep OpenAPI generation in Core

- Status: Accepted
- Date: 2026-10-04

## Context

Orbit Core owns its native ASGI router, typed route metadata, request validation, and HTTP runtime.
The router currently generates an OpenAPI 3.1 document, and the ASGI application serves that
document at `/openapi.json`. Package documentation belongs beside each package's code, so the
ownership of schema generation and serving needs to be explicit.

## Decision

Keep OpenAPI generation from Core route contracts and the default `/openapi.json` endpoint in
Core. These are part of the framework's routing and application contract, not a third-party
documentation backend. Each repository owns its user and developer documentation alongside its
implementation; no separate documentation runtime package is part of the ecosystem.

## Alternatives considered

- Move generation and serving to an optional documentation package: rejected because Core's own
  route contract should remain inspectable without an optional package, and this would make a
  foundational routing surface contingent on a sibling distribution.
- Keep only the schema model in Core and require an optional plugin to serve it: rejected because
  the current built-in endpoint is part of the default native ASGI runtime and has no external
  provider dependency.

## Consequences

- Core continues to expose `Router.openapi()` and serves `/openapi.json` by default.
- Core retains responsibility for validating route metadata and producing a deterministic schema.
- Package documentation stays in each package repository; this decision adds no documentation UI,
  generator backend, hosting integration, or runtime dependency.
- This decision does not add a web framework or another runtime dependency.

## Evidence

- `src/orbit/routing/router.py`
- `src/orbit/asgi/application.py`
- `tests/integration/test_operational_runtime.py`
- `docs/concepts/routing.md`
- `docs/architecture/core-and-plugin-ownership.md`
