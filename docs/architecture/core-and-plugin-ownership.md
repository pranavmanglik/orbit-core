# Core and Orbit plugin ownership

This page records the ownership of implementations currently in Core and the local sibling package
workspaces. It distinguishes implemented local packages from the larger requested catalog; no
local workspace described here should be mistaken for a published or stable release. Core keeps
the orchestration contracts and provider-neutral runtime behavior used by optional integrations.

## Current implementation map

| Existing implementation | Keep in Core or move? | Reason |
| --- | --- | --- |
| Application, service, lifecycle, dependency-injection, configuration, runtime, and plugin registry | Keep in Core | These are the shared orchestration foundation and plugin execution contracts. |
| ASGI server, router, request/response types, health, CLI, and stable extension contracts | Keep in Core | These form Orbit's supported application surface. Admin routes and user-facing operations belong to `orbit-admin`. Preserve Uvicorn for development and Gunicorn with Uvicorn workers for production. |
| ASGI middleware protocol and registration point | Keep in Core | These are the composition contract for native ASGI middleware, independent of optional policies. |
| Core's own ASGI integration-test harness | Private implementation under `tests/helpers` | Core CI must test Core without a dependency cycle or inaccessible sibling checkout. This helper is test-only and is not included in the Core wheel or public API. |
| Reusable ASGI `TestClient` and `TestResponse` for downstream tests | Separate `orbit-testing` workspace | Plugin authors can opt in to shared test utilities that depend on Core's public ASGI contracts; Core's own test suite does not depend on this package. |
| CORS policy and gzip response compression | Extracted to the separate `orbit-gateway` workspace | These are useful but optional HTTP policies; the package implements Core's middleware contract without making them part of every Core installation. |
| Authentication and authorization contracts and implementations | Separate `orbit-auth` capability and focused auth packages | Core retains generic request-context and extension contracts. `orbit-auth` owns authenticators, principals, tokens, authorization policy, and provider-neutral OAuth/OIDC contracts; adapters implement JWT, OAuth flows, and optional RBAC behavior. |
| `SQLDatabase`, `SQLTransaction`, immutable SQL results, and `SQLiteDatabase` | Move to `orbit-sql` plus `orbit-sql-sqlite` | SQL contracts belong with the SQL capability; SQLite is a provider and is installed separately. Core's container still owns the selected resource lifecycle. |
| Generic repository and Unit-of-Work contracts | Extracted to sibling repository `orbit-data` | The Pydantic-independent protocols define typed CRUD and async transaction-scope behavior without choosing persistence or a driver. |
| Provider-neutral asynchronous cache contract | Extracted to sibling repository `orbit-cache` | Cache is an optional capability; applications that do not need caching should not gain a Core or Redis dependency. |
| Provider-neutral object storage contract | Separate sibling package `orbit-storage` | It defines bounded object metadata, pagination, closeable async download streams, normalized failures, and an async store protocol without selecting a filesystem, cloud SDK, bucket, or provider. Provider adapters remain separate. |
| S3 object storage adapter and Core plugin | Separate sibling package `orbit-storage-s3` | It implements `orbit-storage`, owns aiobotocore client configuration and lifecycle, supports bounded multipart upload and closeable downloads, and registers through the capability key. Credentials remain with the SDK chain; no S3 dependency enters Core or `orbit-storage`. |
| Google Cloud Storage adapter and Core plugin | Separate sibling package `orbit-storage-gcs` | It implements `orbit-storage`, owns the gcloud-aio client and credential-file configuration, bounds streamed upload buffering and concurrency, pins streamed reads to the listed object generation, and closes its client through the Core plugin lifecycle. No Google SDK or cloud credentials enter Core or `orbit-storage`. |
| Azure Blob Storage adapter and Core plugin | Separate sibling package `orbit-storage-azure` | It implements `orbit-storage`, owns Azure Identity and the async Blob SDK lifecycle, streams async uploads through bounded provider block transfers, and pins downloads to the looked-up ETag. No Azure SDK or credentials enter Core or `orbit-storage`. |
| Redis cache adapter and Core plugin bridge | Extracted to sibling repository `orbit-cache-redis` | It adapts the separate `orbit-cache` contract and owns redis-py, connection settings, credentials, pool limits, provider failures, and an opt-in Core plugin that registers the cache and closes it on shutdown. Redis is not built into Core or the generic cache capability. |
| Remote service discovery contract and static resolver | Separate sibling package `orbit-discovery` with generated Go client/server bindings in `orbit-discovery-go` | It defines immutable, validated service-instance snapshots and a bounded static resolver for local use. Core's service registry remains local to one application; no network or vendor discovery client is installed. |
| SQL repository implementation, Unit of Work, SQL contracts, and adapter registry | `orbit-sql` | It consumes `orbit-data`, defines async SQL behavior, validates identifiers, binds values, and explicitly selects trusted SQL adapters. |
| SQLite driver, MySQL driver, PostgreSQL pool, and their Core plugin bridges | `orbit-sql-sqlite`, `orbit-sql-mysql`, `orbit-sql-postgres` | Each package owns its SDK/driver, provider settings, connection/pool lifecycle, sanitized failures, and optional Core resource registration. |
| NoSQL database-family capability | `orbit-nosql` | It layers family-level repository/resource semantics over `orbit-data` without pretending that providers share transactions, queries, indexing, or consistency. |
| Explicit SQL schema migration runner | Separate optional `orbit-migrations` workspace | It runs ordered async callbacks inside `orbit-sql` transactions, tracks applied versions, and adds no database driver, ORM, or startup-time migration behavior. |
| MongoDB document repositories and client lifecycle | Separate optional `orbit-nosql-mongo` workspace | It implements `orbit-data.Repository`, owns PyMongo Async configuration, and contributes a Core plugin that registers a lazy database resource. Core and `orbit-data` remain driver-independent. |
| Basic/bearer authentication, identity and principal models, token validation/revocation, JWKS, and generic role/policy authorization | Extracted to `orbit-auth` | It implements Core's `RouteAuthorizer` extension contract. Core transports an opaque value and validates route requirement metadata, but does not construct principals or evaluate roles or policies. |
| `PyJWTVerifier` | Extracted to the separate `orbit-auth-jwt` repository | It directly integrates the external PyJWT implementation. The adapter implements `orbit-auth`'s `TokenVerifier` contract and owns its PyJWT dependency; neither Core nor `orbit-security` installs PyJWT. |
| OAuth/OIDC/JWK models and provider-neutral protocols | Separate capability `orbit-auth` | `orbit-auth-oauth2` and provider adapters own their flows, transports, storage, credentials, and vendor behavior. Core does not validate identity data. |
| `MetricsRegistry`, metric instruments, snapshots, diagnostic models, `Tracer`, and `TelemetrySink` contracts | Keep in Core | These are bounded, backend-neutral runtime diagnostics and extension points. |
| Prometheus text rendering and `/metrics` handler | Extracted to the separate `orbit-metrics-prometheus` repository | The adapter consumes Core metric snapshots and contributes its route without making Prometheus formatting mandatory for Core users. It depends on the `orbit-metrics` capability package, following Core → capability → adapter layering. |
| `InMemoryTracer` and in-memory diagnostics | Keep in Core | These are bounded local implementations useful for tests and development; they do not integrate with an external telemetry backend. |
| OpenTelemetry SDK implementation of Core's `Tracer` contract | Separate sibling package `orbit-tracing` | It owns the isolated SDK provider, bounded batch processor, injected exporter lifecycle, and OTLP optional extras. Core remains usable with its in-memory tracer and does not install OpenTelemetry. Inbound W3C context extraction is opt-in through an outer ASGI wrapper; outbound injection is explicit. No automatic HTTP-client instrumentation is installed. |
| `SecretReference`, redacted `SecretValue`, and `SecretManager` protocol | Keep in Core | They define safe, provider-neutral secret contracts. No remote secrets backend is implemented here. |
| `StateProvider`, `EventStore`, `EventTransport`, and their in-memory implementations | Keep in Core | These are contracts and process-local defaults/test implementations, not Redis, SQL, or broker integrations. Do not move them merely because plugins may implement them. |
| Typed event definitions and application-facing event client | Separate sibling package `orbit-events` | It validates Pydantic payloads and exact schema versions over Core's `EventTransport`. Core retains the event envelope, in-process bus/store, transport contract, and lifecycle. Broker adapters remain independent, optional packages; this layer does not provide a second bus or schema registry. |
| Configuration observer lifecycle contract | Keep in Core | Applications need one stable lifecycle hook to own optional configuration watchers without depending on their filesystem or transport implementations. |
| TOML file polling and hot-reload watcher | Extracted to the separate `orbit-devtools` workspace | Filesystem polling is optional development tooling; its package consumes Core's public `Config`, `load_config`, and lifecycle protocol. |
| Retry, deadline, circuit-breaker, bulkhead, and asynchronous rate-limit controls | Split between Core lifecycle deadlines and optional packages | Core owns runtime cleanup deadlines. `orbit-security` owns HTTP rate limiting, and `orbit-resilience` owns service-call policies and shared-quota adapter contracts. |
| Fixed-delay interval scheduling | Separate optional `orbit-scheduler` package | It provides a bounded process-local async scheduler with fixed-delay runs and explicit shutdown. Core retains application lifecycle supervision; the scheduler does not persist jobs or coordinate workers. |
| Queue-backed job handling contract and runner | Separate optional `orbit-workers` package | It owns bounded worker concurrency and acknowledges only successful handlers; adapters provide queue leases, retry settlement, durable storage, and transport lifecycle. Core can supervise the worker coroutine but does not bundle a broker. |
| Server-Sent Events framing and response helper | Separate optional `orbit-realtime` package | It frames bounded SSE events over Core's native async streaming `Response` and closes the upstream iterator with the HTTP response lifecycle. It does not add a web framework, WebSocket support, or shared pub/sub. |
| Provider-neutral bounded text search contract | Separate optional `orbit-search` package | It defines explicit field paths, exact scalar filters, opaque pagination, immutable bounded results, and an async adapter protocol. Search SDKs, credentials, transport, collection setup, and provider failures remain adapter-owned; no OpenSearch or Elasticsearch adapter is included. |
| Core diagnostic collection and correlation context | Keep in Core | These are backend-neutral runtime primitives. |
| JSON logging formatter | Extracted to the separate `orbit-logging` workspace | Structured log output is optional and consumes Core correlation context without making presentation part of the orchestration package. |

## Implementations not present in this repository

Core does not provide SQL/NoSQL contracts, a database driver, or authentication implementations.
Those features are installed from the corresponding capability/provider packages. The current
source has no general outbound HTTP or
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
| `orbit-storage-s3` | Optional aiobotocore `ObjectStore` implementation with bounded sequential multipart upload, paginated listing, lazy client lifecycle, sanitized errors, and a Core plugin; no live S3 validation is claimed. |
| `orbit-storage-gcs` | Optional gcloud-aio `ObjectStore` implementation with bounded async-stream buffering and concurrency, generation-pinned streamed reads, paginated listing, sanitized errors, and a Core plugin; no live GCS validation is claimed. |
| `orbit-storage-azure` | Optional Azure async Blob SDK `ObjectStore` implementation with `DefaultAzureCredential`, bounded concurrent block transfers, ETag-conditional streamed downloads, paginated listing, sanitized errors, and a Core plugin; no live account or emulator validation is claimed. |
| `orbit-cache-redis` | Optional standalone Redis adapter for `orbit-cache`, with redis-py and client lifecycle; includes a Core plugin bridge, all opt-in. |
| `orbit-sql` | Provider-neutral SQL contracts, typed CRUD repositories, bounded values/results, transaction scope, and explicit adapter selection. |
| `orbit-sql-sqlite` | Standard-library SQLite provider behind a dedicated worker thread, with bounded reads and cancellation-safe transactions; local SQLite tests pass. |
| `orbit-sql-mysql` | Asyncmy MySQL provider, typed TLS/pool settings, parameter adaptation, sanitized failures, and managed transaction/resource scope; fake-client tests only, no live MySQL evidence. |
| `orbit-sql-postgres` | asyncpg PostgreSQL provider implementing the shared Orbit SQL contract; local fake-pool tests only, no live service validation. |
| `orbit-nosql` | Provider-neutral NoSQL database resource contract built on `orbit-data`; local structural contract test passes. |
| `orbit-migrations` | Forward-only migration runner over the `orbit-sql` asynchronous SQL contract; explicit deployment invocation, transactional history, duplicate/oversized history rejection, and no cross-process migration lock. |
| `orbit-nosql-mongo` | PyMongo Async adapter for typed `orbit-data.Repository` CRUD; currently being aligned with `orbit-nosql`; Mongo multi-operation Unit of Work is not implemented. |
| `orbit-vector` | Provider-neutral Pydantic vector, record, query, and score types plus an async `VectorStore` protocol; no database SDK or vendor adapter is included. |
| `orbit-tracing` | OpenTelemetry implementation of Core's `Tracer` contract; owns an isolated SDK provider and exporter lifecycle, with optional OTLP HTTP/gRPC extras. It supports opt-in inbound W3C context extraction through an ASGI wrapper and explicit outbound header injection, but no automatic HTTP-client instrumentation. |
| `orbit-events-kafka` | Optional aiokafka adapter for Core `EventTransport`, with manual commits after handler success, bounded retries, redacted errors, and Core-owned plugin shutdown. It does not claim exactly-once delivery or broker-backed test evidence. |
| `orbit-events-rabbitmq` | Optional aio-pika adapter for Core `EventTransport`, with durable topic routing, publisher confirms, manual acknowledgements, bounded retries, optional dead-letter exchange, and Core-owned connection cleanup. No live-broker test is claimed. |
| `orbit-events-nats` | Optional nats.py JetStream adapter for Core `EventTransport`, with durable explicit-ack consumers, bounded local pending buffers, server-limited redelivery, and Core-owned connection draining. It requires a pre-provisioned JetStream stream; no live-server test is claimed. |
| `orbit-auth` | Provider-neutral authentication and authorization capability: Basic/bearer authenticators, identity/principal/token models, validation and revocation contracts, JWKS/OAuth/OIDC contracts, and generic role/policy authorization. |
| `orbit-auth-jwt` | PyJWT implementation of `orbit-auth`'s `TokenVerifier` contract. |
| `orbit-auth-oauth2` | Authorization-code and PKCE flow integration over the `orbit-auth` OAuth/OIDC contracts, with transaction persistence delegated to a selected store. |
| `orbit-auth-rbac` | Optional exact role-to-permission evaluator over a trusted structural `RoleSubject`; no identity provider, persistent role store, or wildcard policy is included. |
| `orbit-security` | Optional cross-cutting security controls, currently bounded in-process token-bucket rate limiting and HTTP middleware. It does not own authentication or authorization contracts. |
| `orbit-testing` | Optional in-process ASGI client and response assertions for Core applications and plugin tests. |
| `orbit-metrics` | Provider-neutral exporter contract over Core metric snapshots. |
| `orbit-metrics-prometheus` | Prometheus renderer and optional `/metrics` route plugin. |
| `orbit-resilience` | Optional process-local retry, deadline, circuit-breaker, bulkhead, and async rate-limit backpressure utilities. |
| `orbit-logging` | Optional stdlib JSON formatter enriched with Core request and trace context. |
| `orbit-devtools` | Optional TOML configuration watcher for validated extension-section reloads. |
| `orbit-gateway` | Optional CORS and gzip middleware for Core's ASGI application. |
| `orbit-search` | Provider-neutral async full-text search contract with bounded immutable query/result models; no provider adapter is included. |
| `orbit-email` | Provider-neutral bounded email message and async sender contracts. Provider SDKs, credentials, delivery guarantees, and transport lifecycle remain adapter-owned. |

## Requested catalog packages not implemented or deferred

The rows below have no implementation in a separate local package. Where Core already provides a
baseline, it is named explicitly; that baseline does not imply the separate package or advanced
integration exists.

| Requested package | Current evidence and status |
| --- | --- |
| `orbit-events` | Implemented as a separate typed schema/client capability over Core `EventTransport`; Core continues to own the in-process event bus/store. `orbit-events-kafka`, `orbit-events-rabbitmq`, and `orbit-events-nats` remain independent optional broker adapters. No schema registry, schema migration system, or exactly-once guarantee is claimed. |
| `orbit-health` | No separate checkout or package is maintained: intentionally deferred because Core already owns health-check contracts, aggregation, and liveness/readiness endpoints. |
| `orbit-admin` | Python package owns protected operations routes, explicit CRUD resources, audit sinks, and a typed remote client; the TypeScript dashboard remains a separate UI package. |
| `orbit-streams` | Separate Python bounded batch pipeline and typed process capability; optional `orbit-streams-rust` SDK/runtime uses the same schema. Neither package supplies durable broker delivery or checkpoints. |
| `orbit-cloud` and `orbit-cloud-aws`, `orbit-cloud-gcp`, `orbit-cloud-azure` | `orbit-cloud` defines a bounded read-only inventory contract; the three provider adapters map it to AWS Resource Explorer, Google Cloud Asset Inventory, and Azure Resource Graph. Tests use fake SDK clients; live provider coverage, permissions, and consistency remain unverified release gates. The adapters remain outside Core. |
| `orbit-kubernetes`, `orbit-kubernetes-go` | Python and Go adapters implement Kubernetes EndpointSlice service discovery. They do not provision or manage clusters. |
| `orbit-config-server` | A provider-neutral, versioned full-snapshot capability exists; no configuration server or remote provider adapter is included. |
| `orbit-auth-oauth2` | Separate provider-neutral authorization-code/PKCE flow exists; no transaction-store, identity-provider, or live OIDC integration is included. |
| `orbit-observability` | Core has local diagnostic/metric/tracing primitives; `orbit-tracing` exports Core spans through OpenTelemetry. No unified observability capability joining metrics, logs, and traces exists. |
| `orbit-lock` | Provider-neutral expiring lease contract with fencing tokens. Redis implementation is optional through `orbit-cache-redis[lock]`; Redis failover may roll back fencing counters. |
| `orbit-storage` | Provider-neutral object-store capability implemented separately; no concrete backend is included. |
| `orbit-graphql` | No GraphQL server framework or integration exists. |
| `orbit-realtime` | SSE framing is implemented separately; WebSockets and shared pub/sub are not implemented. Core's current HTTP runtime does not claim WebSocket support. |
| `orbit-notifications` | No cross-channel delivery, SMS/push integration, notification preference, or idempotency contract exists. `orbit-email` supplies only a provider-neutral email message/sender contract and has no delivery adapter. |

Core no longer contains its former Basic Auth module, SQLite implementation, bearer authenticator,
token lifecycle, token validation policy, or JWKS contract modules. The wider security extraction is
complete for runtime auth and rate-limit implementation ownership. Core retains only opaque request
context and route requirement contracts. `orbit-admin` is a separate consumer of those contracts.
The security distribution may add Professional extras only when each extra has an implementation,
declared dependencies, tests, and documentation. Authentication contracts stay in `orbit-auth`; JWT verification stays in `orbit-auth-jwt`; OAuth2/OIDC
flows stay in `orbit-auth-oauth2`; cross-cutting HTTP rate limiting stays in `orbit-security`. No extra or feature is claimed complete until those gates pass.

Each implemented sibling package owns its user documentation in that repository, beginning with
the root `README.md` included in its distribution metadata. The README must explain its scope,
installation, public usage, lifecycle/security limits, and which adjacent capabilities remain
optional; API docstrings and package tests stay with the implementation. Core's catalog records
ownership and status but does not replace package-maintained usage documentation.

These database workspace names now follow the requested `orbit_data → orbit_sql → provider adapter`
layers. Every planned package remains a separate deliverable until its contract, implementation,
tests, documentation, and packaging exist.

Core's in-memory state and event implementations remain process-local runtime primitives; they are
not databases or durable broker integrations. The former Core SQLite provider and Basic Auth
implementation have been removed. Optional database and security packages must be explicitly
installed by an application, while Core remains installable without them.

## Extraction constraints

- Extracted integrations live in separately installable repositories and depend only on public Core
  runtime contracts plus their capability package. The former Core SQLite and Basic Auth
  implementations have already been removed; the remaining auth extraction requires package tests
  and coordinated caller/API updates before this boundary is complete.
- The capability package owns its uniform application-facing API and adapter selection/conflict
  rules. An adapter owns its provider SDK, configuration, credentials, transport, and provider-
  specific failures. Core's plugin registry does not define those capability-specific rules.
- Keep Orbit Core installable without optional providers. Do not add provider SDKs to Core.
- Do not create plugin implementations inside the `orbit-core` package. The destination plugin
  package/workspace must be available before physically moving the two concrete integrations.
