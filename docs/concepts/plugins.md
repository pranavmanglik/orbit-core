# Plugins and adapters

Plugins extend the orchestrator without moving provider knowledge into Core. Orbit uses a layered
arrangement: Core provides lifecycle and resource ownership; capability packages define uniform
user-facing contracts; provider packages implement those contracts using vendor SDKs and settings.
Install only capabilities and providers an application uses.

```text
Core (orchestration, lifecycle, DI, generic extension contracts)
├── orbit-data (common database-neutral repository contracts)
│   ├── orbit-sql (SQL types, repositories, transactions, adapter contract)
│   │   ├── orbit-sql-sqlite (SQLite)
│   │   ├── orbit-sql-mysql (MySQL)
│   │   └── orbit-sql-postgres (PostgreSQL)
│   └── orbit-nosql (NoSQL resource/repository capability)
│       └── orbit-nosql-mongo (MongoDB provider adapter)
├── orbit-auth (authentication, authorization, identity, and protocol contracts)
│   ├── orbit-auth-jwt (PyJWT verifier)
│   ├── orbit-auth-oauth2 (OAuth2/OIDC flow)
│   └── orbit-auth-rbac (role-to-permission evaluator)
├── orbit-security (cross-cutting security controls such as HTTP rate limiting)
└── other capability and provider packages
```

`orbit-data` is shared by SQL and NoSQL repository implementations. `orbit-sql` and `orbit-nosql`
define family-specific behavior; neither selects or imports a provider. Provider adapters own
drivers, connection settings, credentials, transport, resource cleanup and provider-specific error
mapping. SQL and NoSQL systems do not imply identical transaction, query, consistency or indexing
behavior. Redis remains a cache provider through `orbit-cache`; it may implement `orbit-nosql` only
where the data contract is semantically correct for Redis.

The target boundary keeps authentication, database, and Admin implementations out of Core. SQLite
and authentication implementations now live in their capability/provider packages. Core retains an
opaque request-authentication context, route-authorizer and Admin-contribution contracts, and bounded
route requirement metadata. The Python `orbit-admin` package owns the operations API, CRUD plugin,
HTTP client, audit sinks, and its process-local limiter, with direct dependencies on the capability
packages it uses. See [ADR 0022](../architecture/adr/0022-extract-database-and-authentication.md)
, [ADR 0025](../architecture/adr/0025-admin-capability-boundary.md), and [ADR 0026](../architecture/adr/0026-auth-capability-boundary.md) for the accepted boundaries.

The Core container remains a generic resource owner. A provider plugin may register an async
resource factory at a package-owned key. Core resolves and closes that resource without importing the
provider package or knowing its driver. Capability registries are explicit: they never scan entry
points or import arbitrary installed packages.

This layering is not a claim that Core defines one universal provider protocol. Each capability
package must version its own adapter contract, provider selection and conflict rules, and
compatibility tests. Core's plugin metadata, dependency ordering, setup and lifecycle hooks supply
the generic runtime boundary.

## Python and process plugins

Core's in-process Python plugin path remains available. The optional
`orbit-core[process-plugins]` extra also provides a versioned local gRPC/Protocol Buffers process
boundary for separately packaged JavaScript/TypeScript, Go and Rust implementations. The wire
schema is in `orbit.plugins.v1.process_plugin.proto`; capability packages own their messages, typed
SDKs and cross-language conformance tests.

The process host supervises trusted local executables. It requires an absolute executable path and
argument vector, does not invoke a shell, bounds configuration and messages, passes a one-use
authentication token through stdin, binds only to loopback, and reaps the child during rollback and
shutdown. Its plaintext loopback transport is not a sandbox: the child runs with the application's
operating-system privileges. Use OS/container isolation when plugins need reduced privileges. Never
send secrets in command arguments, environment variables, logs or health/error messages.
