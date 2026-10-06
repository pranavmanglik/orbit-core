# ADR 0012: Keep general HTTP rate-limiting middleware optional

- Status: Superseded by [ADR 0025](0025-admin-capability-boundary.md)
- Date: 2026-10-04

## Context

Core used to export a general-purpose HTTP `RateLimitMiddleware` alongside its ASGI protocol. The
framework also needs a small bounded in-process limiter to protect its built-in Admin surface.
Those needs do not make a separately configured middleware policy necessary for every application.
The Admin-specific limiter subsequently moved to `orbit-admin`; see ADR 0025.

## Decision

Move the general HTTP middleware to the separately installable `orbit-security` package. It
continues to implement Core's `Middleware`, `Request`, and `Response` contracts and uses the
limiter implementation from `orbit-security`; keep the middleware
composition protocol and registration API in Core. The middleware is opt-in and does not provide a
distributed quota backend.

## Consequences

- Applications that use `RateLimitMiddleware` install `orbit-security` and import it from
  `orbit_security`.
- `orbit-core` includes no HTTP rate-limit implementation; `orbit-admin` owns its operator API
  policy and uses the separately installable implementation from `orbit-security`.
- Each worker has an independent in-memory bucket. Shared quotas and provider-backed security
  remain optional capability/adapter work.
- This is a pre-release public API relocation; the former `orbit.asgi.RateLimitMiddleware` import is
  removed rather than retained as a Core implementation shim.

## Evidence

- `orbit-security/tests/test_ratelimit.py`
- `docs/runtime/asgi.md`
- `docs/architecture/core-and-plugin-ownership.md`
