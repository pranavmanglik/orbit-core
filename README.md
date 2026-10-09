# Orbit Core

Orbit Core is the **orchestrator** for service-based Python applications. It owns composition,
dependency lifetimes, lifecycle transitions, the ASGI boundary, health, diagnostics, and operator
inspection. It deliberately does not own databases, brokers, identity providers, cloud clients, or
telemetry vendors. Those capabilities are installed as plugins and adapters against Core contracts.

The project's complete architectural direction is recorded in the [project charter](docs/architecture/project-charter.md).
Orbit Core provides the web runtime and operator CLI. Admin routes, CRUD, audit storage, and the
TypeScript dashboard belong to the separately installed `orbit-admin` repository, whose Python
package depends directly on Core, Security, Data, and SQL capability contracts. Admin is not
activated by Core configuration. The Admin package is pre-alpha and still has open durability and
live-provider release gates. Orbit owns a small provider-neutral ASGI
and routing boundary. Development uses Uvicorn directly; production uses Gunicorn with the Uvicorn worker.
The [native ASGI decision](docs/architecture/adr/0005-native-asgi-boundary.md) records why Core
owns this boundary rather than depending on another web framework.

Optional capability packages and provider adapters are separate distributions and repositories:
they are not bundled into the `orbit-core` package, installed as its dependencies, or activated
implicitly. Install only the packages an application chooses to use. Core contains orchestration,
generic runtime behavior, and stable extension contracts. Database and security capabilities,
including SQLite and Basic Auth, are separately installed packages.

This boundary is the central design constraint: Core coordinates a capability, while a plugin owns
the provider-specific implementation. A deployment can therefore replace a provider without
changing application lifecycle or business code.

## Development

Python 3.11–3.14 is supported by the configured CI matrix. Core's own integration tests use a
private ASGI harness under `tests/helpers`, so the Core test and release workflows have no
cross-repository test dependency. Plugin authors can install the separately maintained
`orbit-testing` package for reusable ASGI contract tests; it is not a runtime dependency of
`orbit-core`.

Then create the environment from the committed lockfile:

```bash
python -m pip install uv==0.12.23
uv sync --frozen --extra dev --extra development-server --extra process-plugins
uv lock --check
uv run --no-sync pytest --cov=orbit
uv run --no-sync ruff check src tests scripts examples
uv run --no-sync mypy src/orbit
```

## Application composition

```python
from orbit import Application, ApplicationConfig
from orbit.asgi import Response
from orbit.runtime import Runtime

application = Application(ApplicationConfig(name="orders"))


@application.router.route("/version", method="GET", name="version")
async def version(request):
    return Response.json({"service": "orders", "version": "1"})


runtime = Runtime(application)
```

Save this as `app.py`, then run `uv run --no-sync orbit serve app:runtime`.
The runtime owns startup and shutdown through ASGI lifespan. The hosting server owns sockets,
TLS and worker processes. Routes and providers contributed by plugin setup are included before
composition freezes. Production deployments should instead install the `server` extra to add
Gunicorn and `uvicorn-worker` for supervised multi-worker hosting.

## What Core guarantees

- Complete startup is serialized against shutdown. Partial startup rolls back entered
  service hooks, plugin activation and managed resources.
- Scoped providers are isolated across requests. Singleton providers share application
  ownership. Resource exits run in reverse acquisition order with individual deadlines.
- Requests have body, time and concurrency limits. Streaming retains its dependency scope.
  Overload responses and interrupted requests are included in operational diagnostics.
- Health probes share concurrent work, and component health is reflected in application state.
- Protected application routes require an authenticator and a configured `RouteAuthorizer`, such as
  `orbit-auth`'s `RoleAuthorizer`. Configuration secrets represented by Pydantic secret types
  are masked in inspection.
- The CLI inspects Core composition and state. Install `orbit-admin` for operator routes.

These are orchestration guarantees, not a claim that an in-memory reference backend is durable or
that a deployment has been load-tested. Production behavior comes from the selected plugins,
their provider contracts, and the host's deployment evidence.

## Plugin boundary

Plugins register services, routes, providers, configuration, health checks, event handlers, and
stable extension contributions during composition. Core validates plugin identity, API compatibility, dependencies,
capabilities, enablement, and cleanup before the application enters its serving phase. See the
[plugin contract](docs/concepts/plugins.md) before implementing an integration.

Python plugins remain in-process. For trusted local plugins implemented in another language,
install the optional `process-plugins` extra to supervise a gRPC/Protocol Buffers process plugin.
The host supports bounded lifecycle, health, and typed capability calls; it is not a sandbox. A
separate Go Kubernetes provider and Rust stream SDK exercise the host through typed capability
contracts. Broader cross-language conformance, performance benchmarks, and TypeScript process support
remain in progress. See the
[process plugin contract](docs/concepts/plugins.md#plugins-and-adapters) and
[host decision](docs/architecture/adr/0020-local-grpc-process-plugin-host.md).

`orbit-core` does not bundle optional packages. Current local workspaces include `orbit-data`,
`orbit-sql`, `orbit-nosql`, `orbit-sql-sqlite`, `orbit-sql-mysql`, `orbit-nosql-mongo`, `orbit-cache-redis`, `orbit-vector`, `orbit-migrations`, `orbit-cloud`, `orbit-events`,
`orbit-events-kafka`, `orbit-events-rabbitmq`, `orbit-events-nats`, `orbit-gateway`, `orbit-auth`, `orbit-security`, `orbit-auth-oauth2`,
`orbit-auth-jwt`, `orbit-auth-rbac`, `orbit-logging`, `orbit-metrics`, `orbit-tracing`, `orbit-cache`,
`orbit-resilience`, `orbit-lock`, `orbit-storage`, `orbit-storage-s3`, `orbit-storage-gcs`, `orbit-storage-azure`, `orbit-testing`,
`orbit-devtools`, `orbit-metrics-prometheus`, `orbit-sql-postgres`, `orbit-scheduler`, `orbit-discovery`,
`orbit-discovery-go`,
`orbit-cloud-aws`, `orbit-cloud-gcp`, `orbit-cloud-azure`, `orbit-kubernetes`, `orbit-kubernetes-go`, `orbit-workers`, `orbit-realtime`, `orbit-webrtc`, `orbit-webrtc-go`, `orbit-sockets`, `orbit-sockets-go`, `orbit-sockets-rust`, `orbit-email`,
`orbit-notifications`, `orbit-search`, `orbit-streams`, `orbit-streams-rust`, `orbit-config-server`, `orbit-graphql`,
`orbit-observability`, `orbit-admin`, `orbit-search-elasticsearch`, and `orbit-search-opensearch`. They are installed separately and remain
pre-alpha. The three cloud adapters implement read-only inventory APIs with fake-client coverage;
live provider compatibility and release readiness remain open. See
[Core and plugin ownership](docs/architecture/core-and-plugin-ownership.md)
for the explicit Core exceptions and package status.

See [architecture](docs/architecture/overview.md), [dependency injection](docs/concepts/dependency-injection.md),
[lifecycle](docs/concepts/lifecycle.md), [HTTP operation](docs/runtime/asgi.md),
[admin](docs/admin/README.md), [CLI](docs/cli/README.md), and
[release gates](docs/development/completion.md).

The [public roadmap](ROADMAP.md) distinguishes implemented Core contracts from planned hardening,
ecosystem plugins, cross-language plugin transport, and long-term CNCF readiness.

## Community and governance

Contributions follow [CONTRIBUTING.md](CONTRIBUTING.md), the [Code of Conduct](CODE_OF_CONDUCT.md),
and the [governance policy](GOVERNANCE.md). The [maintainer directory](MAINTAINERS.md) records
release and Core-contract responsibility. Report vulnerabilities privately under
[SECURITY.md](SECURITY.md).

## Release status

The package remains pre-release (`0.1.0a1`). Local behavioral tests and static checks establish
specific guarantees; hosted CI, security scans and deployment-specific load testing are separate
release evidence. [Production operations](docs/development/operations.md) describes those boundaries.

Source: [orbit-projects/orbit-core](https://github.com/orbit-projects/orbit-core).
Licensed under Apache-2.0; maintained Python files carry the full license notice.
