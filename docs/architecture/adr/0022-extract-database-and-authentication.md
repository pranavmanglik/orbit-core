# ADR 0022: Move database and authentication capabilities out of Core


> The authentication package ownership decision in this ADR was superseded by [ADR 0026](0026-auth-capability-boundary.md). Its Core extraction and database decisions remain in effect.
- Status: Accepted; implementation complete locally; external release gates remain
- Date: 2026-10-05
- Supersedes: database and security ownership decisions in ADRs 0007, 0015, 0017, and 0018

## Context

Core previously included SQLite and several authentication, authorization, token, and rate-limit
implementations. That mixes optional application capabilities with the Python orchestration runtime
and makes Core's Admin surface depend on security behavior that belongs in an independently
installable package. The Orbit workspace now has capability repositories for SQL, NoSQL, data
repositories, and security, plus provider adapters.

The user selected one `orbit-security` distribution with Basic and Professional installation extras,
and asked that both the TypeScript Admin dashboard and a Python Admin package live in `orbit-admin`.
The Python Admin package now depends directly on `orbit-security`, `orbit-data`, and `orbit-sql`,
alongside Core runtime contracts that it uses.

## Decision

- Core owns orchestration, lifecycle, dependency injection, configuration, in-memory state and
  events, health, ASGI/routing, CLI, generic runtime primitives, and stable extension contracts.
- Core does not own authentication/authorization implementations, database capability contracts,
  database drivers, or database providers.
- `orbit-data` defines common provider-neutral data/repository contracts. `orbit-sql` and
  `orbit-nosql` define their family capabilities. Provider packages own drivers, provider settings,
  credentials, transport, transactions/consistency, provider failures, and resource lifecycle.
- `orbit-sql-sqlite`, `orbit-sql-mysql`, and `orbit-sql-postgres` are separately installable SQL
  providers. MongoDB is a NoSQL provider. Redis remains a cache integration unless a separately
  documented adapter implements meaningful NoSQL repository semantics.
- `orbit-security` owns the opt-in Basic Auth baseline and provider-neutral authentication and
  authorization features. Basic Auth uses salted adaptive password hashes, has no built-in
  credentials, requires TLS by default, and is disabled unless explicitly configured. Advanced
  JWT, OAuth2/OIDC, and identity-provider integrations remain optional packages.
- Keep Core extension points generic. Core must not import capability packages or vendor SDKs.
  Retire Core security callers coherently as the Python Admin package takes ownership of Admin
  authentication, authorization, and database dependencies.
- The existing TypeScript dashboard remains in `orbit-admin`; the same repository gains an
  independently buildable Python Admin package.

## Alternatives considered

- Keep SQLite and Basic Auth in Core as convenience baselines: rejected because the user selected
  separately installed database and security capabilities and direct Admin dependencies.
- Move only vendor drivers while retaining Core's SQL/auth models: rejected because those models
  are capability contracts and would keep Core responsible for database and identity behavior.
- Put all Admin UI and server behavior in Core: rejected because it forces optional data and
  security concerns into every Core application and prevents independent package releases.

## Consequences and migration

- Existing Basic Auth imports and Core SQLite imports were removed. Applications install
  `orbit-security` and `orbit-sql-sqlite` explicitly.
- `orbit-sql` owns SQL contracts and repository behavior; adapters depend on it rather than on
  removed Core database modules.
- Core no longer contains its authentication, identity/principal models, token lifecycle/revocation
  store, token validation policy, JWKS contracts, role checks, policy registry, or rate limiter;
  those implementations are separately installable. Core keeps only generic request-authentication
  transport and the `RouteAuthorizer` extension hook.
- `orbit-admin` contains the TypeScript dashboard and Python package for the operations API, CRUD,
  client, and audit sinks, with direct capability-package dependencies. Core retains only the
  `AdminContribution` protocol and bounded inspection API. See ADR 0025 for the Admin ownership
  decision and its local evidence.
- `basic` and `professional` extras are package variants, not claims of completed feature sets.
  Declare and document each only when code, dependency metadata, installation checks, and user docs
  match.

## Evidence

- [Core and plugin ownership](../core-and-plugin-ownership.md)
- [Database package boundary](../../concepts/database.md)
- [Orbit Security](../../security/overview.md)
- [Orbit ecosystem goal](../../../../ORBIT_ECOSYSTEM_GOAL.md)
- Local workspace checkouts: `../orbit-data`, `../orbit-sql`, `../orbit-nosql`,
  `../orbit-sql-sqlite`, `../orbit-sql-mysql`, `../orbit-sql-postgres`, `../orbit-security`, and
  `../orbit-admin`. `../orbit-auth-jwt` now imports `Token` and `TokenVerifier` from `orbit-security`.

### Implementation follow-up (2026-10-06)

Core no longer has its Admin HTTP dispatcher, `admin_enabled` setting, Admin audit ring, or rate
limiter. Its `orbit.admin` module contains only the stable `AdminContribution` extension contract
and Core retains bounded inspection ownership for registered contributions. `orbit-security` now
owns the token-bucket implementation and HTTP middleware. `orbit-admin` owns the operations routes,
CRUD plugin, audit sinks, and typed remote client, with direct dependencies on Core, Security, Data,
and SQL. `AdminPlugin` installs operations by default; applications may select CRUD-only or
operations-only mode. Focused local tests and packaging pass; provider release, hosted CI, live
MySQL/PostgreSQL audit evidence, atomic resource/audit writes, and deployment review remain open.
