# Architecture overview

Orbit Core is the Python orchestrator. It owns application composition, lifecycle, dependency
injection, configuration, state, events, health, ASGI/routing, CLI, generic runtime primitives and
stable extension contracts. Authentication and database capabilities are optional packages.

Orbit uses Uvicorn and Gunicorn together across environments. Uvicorn supplies the ASGI worker and
protocol implementation. Gunicorn supplies pre-fork process management, signal handling, worker
supervision and graceful replacement. Local reload and single-worker execution use Uvicorn
directly; managed multi-worker execution uses Gunicorn with the `uvicorn-worker` package.

The target database package chain is:

```text
orbit-data (shared database-neutral repositories)
├── orbit-sql (SQL contract, repositories, units of work)
│   ├── orbit-sql-sqlite
│   ├── orbit-sql-mysql
│   └── orbit-sql-postgres
└── orbit-nosql (NoSQL capability)
    └── provider adapters such as orbit-nosql-mongo
```

The authentication chain puts opt-in Basic Auth and provider-neutral authorization in
`orbit-auth`; `orbit-auth-jwt`, `orbit-auth-oauth2`, and `orbit-auth-rbac` are optional child packages.
`orbit-security` owns cross-cutting security controls such as HTTP rate limiting. Core provides generic
request and plugin extension points but no authentication implementation or database implementation.

The `orbit-admin` repository contains the TypeScript dashboard and a separately buildable Python
operations/CRUD capability. The Python package depends directly on the capability packages it uses;
database providers are selected explicitly by the application. Package availability and maturity
are per-repository. Do not infer an installed feature from this architecture diagram; check each
package's status, tests, and documented provider coverage.

Core may include in-memory implementations for deterministic local runtime needs. They are
process-local and do not silently become production defaults for durable state, event delivery,
credentials or telemetry.

`HostingConfig` is the shared validated model for host selection, bind address, port, worker count,
reload policy and graceful timeout. It can be supplied to `Runtime` and reused by deployment
tooling so configuration validation does not depend on a particular CLI invocation.
