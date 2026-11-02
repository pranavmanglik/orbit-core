# Core and Orbit plugin ownership

This page records the ownership of implementations currently in Core and the local sibling package
workspaces. It distinguishes implemented local packages from the larger requested catalog; no
local workspace described here should be mistaken for a published or stable release. Core keeps
the orchestration contracts and provider-neutral runtime behavior used by optional integrations.

## Current implementation map

| Existing implementation | Keep in Core or move? | Reason |
| --- | --- | --- |
| Application, service, lifecycle, dependency-injection, configuration, runtime, and plugin registry | Keep in Core | These are the shared orchestration foundation and plugin execution contracts. |
| ASGI server, router, request/response types, health, Core Admin foundation, and CLI | Keep in Core | These form Orbit's supported application and operator surfaces. Core Admin is a protected overview plus typed inspection/control APIs, not the planned general CRUD/analytics dashboard. Preserve Uvicorn for development and Gunicorn with Uvicorn workers for production. |
| ASGI middleware protocol and registration point | Keep in Core | These are the composition contract for native ASGI middleware, independent of optional policies. |
| In-process ASGI `TestClient` and `TestResponse` | Extracted to the separate `orbit-testing` workspace | These are test-only tools, not runtime orchestration. The package depends on Core's public ASGI contracts and introduces no separate web framework or network client. |
| CORS policy and gzip response compression | Extracted to the separate `orbit-gateway` workspace | These are useful but optional HTTP policies; the package implements Core's middleware contract without making them part of every Core installation. |
| General HTTP `RateLimitMiddleware` | Extracted to the separate `orbit-security` workspace | Request throttling is opt-in middleware over Core's ASGI contracts. Core keeps the bounded local `RateLimiter` needed for its own Admin surface, but does not bundle this general policy or imply that its per-process quotas are distributed. |
| Identity, Principal, security context, authorization policy, `Authenticator`, `Token`, and `TokenVerifier` contracts | Keep in Core | They are provider-neutral security boundaries consumed by the runtime. |
| `SQLDatabase`, `SQLTransaction`, immutable SQL results, and `SQLiteDatabase` | Keep in Core | The common async SQL contract is a baseline capability, and stdlib SQLite is useful for local development and embedded applications without adding a runtime dependency. Server database adapters implement this contract outside Core. |
| Generic repository and Unit-of-Work contracts | Extracted to sibling repository `orbit-data` | The Pydantic-independent protocols define typed CRUD and async transaction-scope behavior without choosing persistence or a driver. |
| Provider-neutral asynchronous cache contract | Extracted to sibling repository `orbit-cache` | Cache is an optional capability; applications that do not need caching should not gain a Core or Redis dependency. |
| Provider-neutral object storage contract | Separate sibling package `orbit-storage` | It defines bounded object metadata, pagination, closeable async download streams, normalized failures, and an async store protocol without selecting a filesystem, cloud SDK, bucket, or provider. Provider adapters remain separate. |
| S3 object storage adapter and Core plugin | Separate sibling package `orbit-s3` | It implements `orbit-storage`, owns aiobotocore client configuration and lifecycle, supports bounded multipart upload and closeable downloads, and registers through the capability key. Credentials remain with the SDK chain; no S3 dependency enters Core or `orbit-storage`. |
| Google Cloud Storage adapter and Core plugin | Separate sibling package `orbit-gcs` | It implements `orbit-storage`, owns the gcloud-aio client and credential-file configuration, bounds streamed upload buffering and concurrency, pins streamed reads to the listed object generation, and closes its client through the Core plugin lifecycle. No Google SDK or cloud credentials enter Core or `orbit-storage`. |
| Azure Blob Storage adapter and Core plugin | Separate sibling package `orbit-azure-storage` | It implements `orbit-storage`, owns Azure Identity and the async Blob SDK lifecycle, streams async uploads through bounded provider block transfers, and pins downloads to the looked-up ETag. No Azure SDK or credentials enter Core or `orbit-storage`. |
| Redis cache adapter and Core plugin bridge | Extracted to sibling repository `orbit-redis` | It adapts the separate `orbit-cache` contract and owns redis-py, connection settings, credentials, pool limits, provider failures, and an opt-in Core plugin that registers the cache and closes it on shutdown. Redis is not built into Core or the generic cache capability. |
| SQL repository implementation, Unit of Work, and adapter registry | Extracted to sibling repository `orbit-sql` | It consumes `orbit-data` contracts and Core's `SQLDatabase`/SQLite capability; it validates identifiers, binds values, and explicitly selects trusted SQL adapters. |
| PostgreSQL pool, driver integration, and Core plugin bridge | Extracted to sibling repository `orbit-sql-postgres` | It owns asyncpg, provider configuration, and pool lifecycle while implementing Core's `SQLDatabase` contract. Its optional plugin lazily registers the capability using `orbit-sql`'s shared container key, leaving resource cleanup to Core. |
| Explicit SQL schema migration runner | Separate optional `orbit-migrations` workspace | It runs ordered async callbacks inside Core `SQLDatabase` transactions, tracks applied versions, and adds no database driver, ORM, or startup-time migration behavior. |
| MongoDB document repositories and client lifecycle | Separate optional `orbit-mongo` workspace | It implements `orbit-data.Repository`, owns PyMongo Async configuration, and contributes a Core plugin that registers a lazy database resource. Core and `orbit-data` remain driver-independent. |
| `BearerAuthenticator`, token validation/revocation, role policy, and bounded in-process rate limiting | Keep in Core | Core needs provider-neutral auth contracts and a safe local limiter for its own Admin Panel and ASGI baseline. This limiter is process-local; distributed/shared rate limiting remains an optional capability/adapter. |
| `PyJWTVerifier` | Extracted to the separate `orbit-jwt` repository | It directly integrates the external PyJWT implementation. The adapter implements Core's `TokenVerifier` contract and owns its PyJWT dependency; Core no longer imports or exports the verifier. |
| OAuth/OIDC/JWK models and provider protocols | Keep the provider-neutral contracts in Core | The current code validates standard protocol data but does not fetch keys, call an issuer, or implement an identity-vendor integration. Concrete issuer/network behavior belongs in Orbit plugins. |
| `MetricsRegistry`, metric instruments, snapshots, diagnostic models, `Tracer`, and `TelemetrySink` contracts | Keep in Core | These are bounded, backend-neutral runtime diagnostics and extension points. |
| Prometheus text rendering and `/metrics` handler | Extracted to the separate `orbit-prometheus` repository | The adapter consumes Core metric snapshots and contributes its route without making Prometheus formatting mandatory for Core users. It depends on the `orbit-metrics` capability package, following Core → capability → adapter layering. |
| `InMemoryTracer` and in-memory diagnostics | Keep in Core | These are bounded local implementations useful for tests and development; they do not integrate with an external telemetry backend. |
| OpenTelemetry SDK implementation of Core's `Tracer` contract | Separate sibling package `orbit-tracing` | It owns the isolated SDK provider, bounded batch processor, injected exporter lifecycle, and OTLP optional extras. Core remains usable with its in-memory tracer and does not install OpenTelemetry. Inbound W3C context extraction is opt-in through an outer ASGI wrapper; outbound injection is explicit. No automatic HTTP-client instrumentation is installed. |
| `SecretReference`, redacted `SecretValue`, and `SecretManager` protocol | Keep in Core | They define safe, provider-neutral secret contracts. No remote secrets backend is implemented here. |
| `StateProvider`, `EventStore`, `EventTransport`, and their in-memory implementations | Keep in Core | These are contracts and process-local defaults/test implementations, not Redis, SQL, or broker integrations. Do not move them merely because plugins may implement them. |
| Typed event definitions and application-facing event client | Separate sibling package `orbit-events` | It validates Pydantic payloads and exact schema versions over Core's `EventTransport`. Core retains the event envelope, in-process bus/store, transport contract, and lifecycle. Broker adapters remain independent, optional packages; this layer does not provide a second bus or schema registry. |
| `AdminTransport` protocol | Keep in Core | It is an injectable transport boundary; Core does not include a concrete outbound HTTP client. |
| Configuration observer lifecycle contract | Keep in Core | Applications need one stable lifecycle hook to own optional configuration watchers without depending on their filesystem or transport implementations. |
| TOML file polling and hot-reload watcher | Extracted to the separate `orbit-devtools` workspace | Filesystem polling is optional development tooling; its package consumes Core's public `Config`, `load_config`, and lifecycle protocol. |
| Retry, deadline, circuit-breaker, bulkhead, and asynchronous rate-limit controls | Extracted to the separate `orbit-resilience` repository | Core's own lifecycle, request, cleanup, and administrative deadlines plus its nonblocking local HTTP/Admin limiter remain Core-owned; optional service-call backpressure and resilience policy are not required by every application. `orbit-resilience` defines an adapter protocol for shared quotas without binding it to a vendor. |
| Core diagnostic collection and correlation context | Keep in Core | These are backend-neutral runtime primitives. |
| JSON logging formatter | Extracted to the separate `orbit-logging` workspace | Structured log output is optional and consumes Core correlation context without making presentation part of the orchestration package. |

## Implementations not present in this repository

Core provides asynchronous SQLite through a single dedicated worker thread, bounded row reads,
serialized transactions, and structured errors that omit raw SQL and driver details. It does not
provide connection pooling, distributed coordination, or a server-database implementation.

Core includes opt-in, static-user Basic Auth; it has no account lifecycle, federation, or
credential persistence. The current source has no general outbound HTTP or
gRPC client, broker client, remote secret backend, OpenTelemetry exporter, identity-provider
integration, or Docker/Kubernetes deployment engine. The in-memory state and event stores are not
database integrations. Do not add these as part of this sorting task or document them as existing
features; they need separate scope and design.

## Local optional package workspaces

The following sibling workspaces currently contain code. Every row is a separately installable
optional distribution; none is bundled into `orbit-core` or required as a Core dependency. They are
not yet published releases or stable APIs:

| Workspace | Implemented boundary |
| --- | --- |
| `orbit-data` | Generic typed repository and Unit-of-Work contracts. |
| `orbit-cache` | Provider-neutral async bytes-cache contract and normalized capability errors. |
| `orbit-storage` | Provider-neutral async object-store protocol, byte/stream uploads, explicitly closeable download streams, bounded typed metadata/pagination, and capability errors; no provider SDK or Core dependency. |
| `orbit-s3` | Optional aiobotocore `ObjectStore` implementation with bounded sequential multipart upload, paginated listing, lazy client lifecycle, sanitized errors, and a Core plugin; no live S3 validation is claimed. |
| `orbit-gcs` | Optional gcloud-aio `ObjectStore` implementation with bounded async-stream buffering and concurrency, generation-pinned streamed reads, paginated listing, sanitized errors, and a Core plugin; no live GCS validation is claimed. |
| `orbit-azure-storage` | Optional Azure async Blob SDK `ObjectStore` implementation with `DefaultAzureCredential`, bounded concurrent block transfers, ETag-conditional streamed downloads, paginated listing, sanitized errors, and a Core plugin; no live account or emulator validation is claimed. |
| `orbit-redis` | Optional standalone Redis adapter for `orbit-cache`, with redis-py and client lifecycle; includes a Core plugin bridge, all opt-in. |
| `orbit-sql` | SQL CRUD repositories and transaction scope over Core SQL, plus explicit adapter selection. |
| `orbit-sql-postgres` | asyncpg provider implementation of Core SQL and the `orbit-sql` adapter contract; its optional Core plugin registers a lazy, container-managed SQL resource. |
| `orbit-migrations` | Forward-only migration runner over Core's asynchronous SQL contract; explicit deployment invocation, transactional history, and no cross-process migration lock. |
| `orbit-mongo` | PyMongo Async adapter for typed `orbit-data.Repository` CRUD, with a lazy Core-managed database resource; Mongo multi-operation Unit of Work is not implemented. |
| `orbit-vector` | Provider-neutral Pydantic vector, record, query, and score types plus an async `VectorStore` protocol; no database SDK or vendor adapter is included. |
| `orbit-tracing` | OpenTelemetry implementation of Core's `Tracer` contract; owns an isolated SDK provider and exporter lifecycle, with optional OTLP HTTP/gRPC extras. It supports opt-in inbound W3C context extraction through an ASGI wrapper and explicit outbound header injection, but no automatic HTTP-client instrumentation. |
| `orbit-kafka` | Optional aiokafka adapter for Core `EventTransport`, with manual commits after handler success, bounded retries, redacted errors, and Core-owned plugin shutdown. It does not claim exactly-once delivery or broker-backed test evidence. |
| `orbit-rabbitmq` | Optional aio-pika adapter for Core `EventTransport`, with durable topic routing, publisher confirms, manual acknowledgements, bounded retries, optional dead-letter exchange, and Core-owned connection cleanup. No live-broker test is claimed. |
| `orbit-nats` | Optional nats.py JetStream adapter for Core `EventTransport`, with durable explicit-ack consumers, bounded local pending buffers, server-limited redelivery, and Core-owned connection draining. It requires a pre-provisioned JetStream stream; no live-server test is claimed. |
| `orbit-jwt` | PyJWT implementation of Core's `TokenVerifier` contract. |
| `orbit-security` | Optional provider-neutral security-policy package. Its current implementation is request-level rate-limit middleware using Core's ASGI and local limiter contracts; new optional policies belong here when they do not require a vendor adapter. It does not duplicate Core's Basic Auth baseline. |
| `orbit-testing` | Optional in-process ASGI client and response assertions for Core applications and plugin tests. |
| `orbit-metrics` | Provider-neutral exporter contract over Core metric snapshots. |
| `orbit-prometheus` | Prometheus renderer and optional `/metrics` route plugin. |
| `orbit-resilience` | Optional process-local retry, deadline, circuit-breaker, bulkhead, and async rate-limit backpressure utilities. |
| `orbit-logging` | Optional stdlib JSON formatter enriched with Core request and trace context. |
| `orbit-devtools` | Optional TOML configuration watcher for validated extension-section reloads. |
| `orbit-gateway` | Optional CORS and gzip middleware for Core's ASGI application. |

## Remaining requested catalog

These catalog entries have no separate local package. Where Core already provides a baseline, it is
named explicitly; that baseline does not imply the separate package or advanced integration exists.

| Requested package | Current evidence and status |
| --- | --- |
| `orbit-events` | Implemented as a separate typed schema/client capability over Core `EventTransport`; Core continues to own the in-process event bus/store. `orbit-kafka`, `orbit-rabbitmq`, and `orbit-nats` remain independent optional broker adapters. No schema registry, schema migration system, or exactly-once guarantee is claimed. |
| `orbit-health` | Core has health checks plus liveness/readiness endpoints. No separate health package exists. |
| `orbit-admin` | Core has authenticated Admin APIs and an overview. The general dashboard, CRUD, and analytics package is not implemented. |
| `orbit-docs` | Core owns OpenAPI generation from Core route contracts and serves `/openapi.json`. No separate package exists; a future `orbit-docs` package may add optional rendered documentation or external documentation integrations without replacing this Core behavior. |
| `orbit-streams` | No stream-processing package exists; Core's in-process event bus is not a substitute for stream-processing integrations. |
| `orbit-cloud`, `orbit-kubernetes`, `orbit-discovery`, `orbit-config-server` | No cloud, orchestration, service-discovery, or centralized-configuration integration exists. |
| `orbit-oauth2`, `orbit-rbac` | Core has provider-neutral OAuth/OIDC data and role/policy primitives; no separate provider or RBAC package exists. |
| `orbit-observability` | Core has local diagnostic/metric/tracing primitives; `orbit-tracing` exports Core spans through OpenTelemetry. No unified observability capability joining metrics, logs, and traces exists. |
| `orbit-scheduler`, `orbit-workers`, `orbit-lock` | Core supervises application-owned tasks; no scheduled-job, background-worker, or distributed-lock package exists. |
| `orbit-storage` | Provider-neutral object-store capability implemented separately; no concrete backend is included. |
| `orbit-graphql`, `orbit-realtime` | No GraphQL, WebSocket, or Server-Sent Events integration exists. Core's current HTTP runtime does not claim WebSocket support. |
| `orbit-email`, `orbit-notifications` | No email, SMS, or push-notification integration exists. |
| `orbit-search` | No Elasticsearch/OpenSearch integration exists. |

Core's opt-in static-user Basic Auth remains the built-in baseline; it does not provide account
management, federation, credential persistence, or a full security suite. Orbit has one optional
`orbit-security` package for additional provider-neutral security policies. Its current
implementation is request-level rate limiting only. There are no separate Basic or Professional
security package variants; Core's baseline and the single optional package have distinct scopes.
Concrete identity providers and vendor integrations remain separate packages such as `orbit-jwt`
and the planned `orbit-oauth2`; they are not silently pulled in by `orbit-security`.

Each implemented sibling package owns its user documentation in that repository, beginning with
the root `README.md` included in its distribution metadata. The README must explain its scope,
installation, public usage, lifecycle/security limits, and which adjacent capabilities remain
optional; API docstrings and package tests stay with the implementation. Core's catalog records
ownership and status but does not replace package-maintained usage documentation.

These database workspace names now follow the requested `orbit_data → orbit_sql → provider adapter`
layers. Every planned package remains a separate deliverable until its contract, implementation,
tests, documentation, and packaging exist.

The built-in exceptions are intentionally narrow: Core-owned, provider-neutral security and
capability contracts; stdlib-backed SQLite for local/embedded SQL; and opt-in static-user Basic
Auth. They are not a reason to pull database vendors, auth providers, security suites, or telemetry
backends into Core. In particular, the optional packages listed above must be explicitly installed
by an application, while Core continues to work without them.

## Extraction constraints

- Extracted integrations must live in separately installable repositories, depend on public Core
  contracts, and include tests against those contracts before Core removes its implementation.
- The capability package owns its uniform application-facing API and adapter selection/conflict
  rules. An adapter owns its provider SDK, configuration, credentials, transport, and provider-
  specific failures. Core's plugin registry does not define those capability-specific rules.
- Keep Orbit Core installable without optional providers. Do not add provider SDKs to Core.
- Do not create plugin implementations inside the `orbit-core` package. The destination plugin
  package/workspace must be available before physically moving the two concrete integrations.
