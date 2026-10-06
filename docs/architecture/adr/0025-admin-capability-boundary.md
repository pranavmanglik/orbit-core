# ADR 0025: Keep Admin HTTP behavior in the optional package

- Status: Accepted and implemented locally
- Date: 2026-10-06
- Supersedes: Core Admin dispatch and rate-limit placement in ADRs 0001 and 0012

## Context

Core previously mounted an operations console directly, stored its rate-limit policy and audit
ring, and exposed configuration flags for the endpoint. That made Admin unavoidable Core surface
area even though the Admin package already depends directly on the security and data capabilities
it needs. The user clarified that all Admin behavior should live in `orbit-admin`.

## Decision

- Core owns no Admin HTTP routes, dashboard, client, audit sink, Admin-specific limiter, or
  `admin_enabled` configuration. Its `orbit.admin.AdminContribution` protocol and bounded
  `Application.inspect_admin_contribution()` behavior remain stable extension contracts.
- `orbit-security` owns the provider-neutral bounded token-bucket limiter and optional HTTP
  middleware. Core owns only opaque request authentication context and role-label authorization
  hooks.
- `orbit-admin-python` owns the operations routes, explicit CRUD resources, audit sinks, and typed
  remote client. It depends directly on Core, Security, Data, and SQL. Provider drivers remain
  separate packages.
- `AdminPlugin(resources)` installs operations and CRUD by default. `operations=False` selects
  CRUD only; `AdminOperationsPlugin` selects the operations console without CRUD resources.
- Every protected route uses Core's route-role metadata and requires an explicitly configured
  authenticator and `RouteAuthorizer`. The operations package applies a bounded local rate limit,
  safe no-store headers, explicit mutation authorization checks, and payload-free audit records.

## Alternatives considered

- Keep the `/admin` dispatcher in Core but make security and storage optional: rejected because it
  would preserve an Admin implementation and configuration surface in the orchestrator.
- Remove Core's admin contribution contract too: rejected because bounded extension inspection is
  a stable runtime hook with Core-owned cancellation and lifecycle behavior; it does not mount HTTP
  routes or select presentation.

## Consequences

Core applications do not expose Admin endpoints unless they install an Admin plugin. The Admin
package can release independently and choose whether it installs operations routes, CRUD, and SQL
audit storage. Process-local rate limits and in-memory audit history are not shared across workers;
SQL CRUD and audit writes are not atomic under the current repository contract. Those limits are
documented and remain production release gates where the deployment requires stronger guarantees.

Local evidence: the Core HTTP suite verifies `/admin` is not mounted by Core; the Admin suite tests
authenticated operations views, rate limiting, CRUD field allowlists, audit behavior, and SQLite
sink lifecycle. Hosted CI, live PostgreSQL/MySQL audit tests, and deployment/security review remain
external release gates.
