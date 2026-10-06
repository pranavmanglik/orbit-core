# Orbit roadmap

This roadmap turns the [project charter](docs/architecture/project-charter.md) into an honest,
reviewable sequence of work. Dates are intentionally omitted while the project is pre-alpha;
scope and evidence matter more than calendar promises.

The current development phase hardens Orbit Core and organizes integrations that already exist
outside it into separately installable packages. Core's plugin registry and extension contracts
remain part of Core. This phase does not imply that every package in the requested ecosystem catalog
has been implemented or released.

## Current foundation

Orbit Core currently provides the provider-neutral orchestration foundation for:

- typed application configuration, state, identifiers, services, providers, and events;
- dependency injection with scopes, overrides, graph validation, and resource cleanup;
- explicit lifecycle transitions, nested applications, health/readiness, diagnostics, and tasks;
- ASGI request/response handling, routing metadata, limits, security primitives, and hosting;
- plugin contracts, metadata, dependency ordering, capabilities, and lifecycle integration;
- authenticated Admin Panel foundations and a Typer/Rich operator CLI;
- documentation, tests, type checks, coverage, repository security automation, and release checks.

The current plugin host loads allowlisted Python entry points in-process. A cross-language plugin
protocol and native/process host are longer-term work, not part of the current implementation.

These are Core contracts and reference implementations. They do not include provider SDKs or claim
durability, distributed coordination, load-test evidence, or production certification. Optional
workspace packages currently include `orbit-data`, `orbit-cache`, `orbit-cache-redis`, `orbit-sql`,
`orbit-sql-postgres`, `orbit-auth-jwt`, `orbit-security`, `orbit-testing`, `orbit-metrics`,
`orbit-metrics-prometheus`, `orbit-resilience`, `orbit-logging`, `orbit-devtools`, `orbit-gateway`,
`orbit-events-kafka`, `orbit-migrations`, `orbit-nosql-mongo`, `orbit-events-nats`, `orbit-events-rabbitmq`, and `orbit-vector`.
They are local workspaces, not published releases. See the
[Core/plugin ownership map](docs/architecture/core-and-plugin-ownership.md).

## Next Core work

1. Harden the Orbit-owned ASGI and router boundary while preserving the single Core graph,
   lifecycle ownership, routing metadata, dependency contracts, and Uvicorn/Gunicorn hosting model.
2. Stabilize the public Core API through compatibility policy, deprecations, migration notes, and
   clear extension-contract versioning for future adapter authors.
3. Harden the custom and integrated HTTP boundaries with protocol, fuzzing, slow-client, proxy,
   WebSocket, load, race, and failure-injection tests.
4. Expand remote operational workflows for the Admin Panel and CLI without coupling business logic
   to command handlers or exposing unauthenticated worker state.
5. Publish executable examples and contract-test templates for service, plugin, authentication,
   health, observability, and configuration integrations.

## Ecosystem work

Continue organizing the implementations that exist, then build the requested plugin catalog
incrementally. Do not create empty repositories to imply progress. Each implemented package must be
independently installable, documented, tested against its capability/Core contracts, and clear
about its provider, credential, durability, and operational assumptions. The requested catalog
names and package status are tracked in the ownership map; names do not imply that a contract or
implementation already exists.

After the Orbit-maintained foundations, support community adapters for messaging, storage, cloud
providers, service discovery, observability systems, and developer workflows. Plugin quality must
not be measured only by whether it imports: lifecycle rollback, readiness, security, redaction,
upgrade, migration, and failure behavior are part of the contract.

## Long-term direction

- Establish a stable cross-language plugin protocol for components where Python is not the right
  implementation language, with explicit versioning, serialization, security, and process
  ownership rules.
- Improve OpenSSF Best Practices maturity toward Silver and Gold where the project can provide real
  evidence, including signed releases, SBOMs, provenance, vulnerability response, and reproducible
  release checks.
- Grow governance and maintainership across organizations and evaluate CNCF Sandbox readiness only
  after the project has demonstrated reusable software, community adoption, transparent governance,
  and sustained release operations.

## Out of scope for Core

Orbit Core will not absorb vendor SDKs, a mandatory database or broker, a fixed identity provider,
cloud-specific deployment logic, a telemetry backend, or hot package installation into a running
application. Those capabilities may be excellent plugins; keeping them outside Core is what lets a
minimal Orbit application remain small and lets operators choose the right provider.
