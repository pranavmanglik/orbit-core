# API reference guide

Orbit's Python docstrings are the closest reference for individual arguments, return values,
exceptions, and lifecycle behavior. This page gives contributors and adopters a stable starting
point for finding the public Core API without pretending that every internal module is a supported
extension point.

## Stable import surface

The root package intentionally exposes only the smallest application-composition surface:

```python
from orbit import Application, ApplicationConfig, Service, ServiceDescriptor
```

Use the focused package exports for the rest of Core:

| Package | Responsibility | Typical public types |
| --- | --- | --- |
| `orbit` | Minimal application-composition import surface | `Application`, `ApplicationBuilder`, `ApplicationConfig`, `Service`, `ServiceDescriptor`, `__version__` |
| `orbit.application` | Application composition and summaries | `Application`, `ApplicationBuilder` |
| `orbit.services` | Service contracts and registration | `Service`, `ServiceContract`, `ServiceDescriptor`, `ServiceRegistry` |
| `orbit.config` | Typed settings, snapshots, secret and watcher contracts | `ApplicationConfig`, `Config`, `ConfigurationWatcher`, `load_config`, `SecretReference` |
| `orbit.container` | Dependency injection and resource ownership | `Container`, `ContainerContract`, `Provider`, `Scope`, `ProviderResolution` |
| `orbit.errors` | Structured problems and Core exception types | `OrbitProblem`, `ErrorResponse`, `OrbitError`, `ValidationError` |
| `orbit.cli` | Typer/Rich operator command entry point | `app` |
| `orbit.lifecycle` | Validated lifecycle phases and transitions | `Lifecycle`, `LifecycleObserver`, `LifecyclePhase` |
| `orbit.plugins` | Plugin metadata, discovery, and composition | `Plugin`, `PluginContract`, `PluginMetadata`, `PluginRegistry` |
| `orbit.routing` | Framework-neutral route metadata and dispatch | `Router`, `Route`, `RouteMetadata` |
| `orbit.events` | Typed in-process event delivery and storage contracts | `Event`, `EventBus`, `Delivery`, `Subscription`, `EventStore` |
| `orbit.state` | Runtime snapshots, namespaces, providers, and leases | `State`, `StateStore`, `StateProvider` |
| `orbit.health` | Component and aggregate health reporting | `HealthCheck`, `HealthService`, `HealthReport` |
| `orbit.runtime` | ASGI runtime, hosting configuration, and task supervision | `Runtime`, `HostingConfig`, `TaskSupervisor` |
| `orbit.asgi` | Core ASGI request, response, and middleware boundary | `ASGIApplication`, `Middleware`, `Headers`, typed `Request`, `Response`, ASGI message types |
| `orbit.admin` | Stable inspection-contribution contract for optional Admin consumers | `AdminContribution` |
| `orbit.security` | Authentication and authorization extension hooks | `Authenticator`, `RouteAuthorizer` |
| `orbit.diagnostics` | Logs, metrics, traces, and bounded application inspection | `Diagnostics`, `MetricsRegistry`, `Tracer`, `inspect_composition` |
| `orbit.types` | Domain-specific identifiers | `ApplicationId`, `ConfigurationId`, `EventId`, `ProviderId`, `RequestId`, `RouteId`, `ServiceId`, `SubscriptionId` |

The optional `orbit-testing` distribution provides `orbit_testing.TestClient` and
`orbit_testing.TestResponse`; Core itself does not ship test helpers.

## Contract versus implementation

Protocols, Pydantic models, enums, and exported classes define the public contract. Private modules,
underscore-prefixed members, in-memory stores, and concrete provider helpers may change as long as
the documented contract remains compatible or a deprecation path is provided.

Core's in-memory implementations are useful for deterministic tests and local development. They
are process-local reference implementations. They do not provide distributed durability, shared
coordination, production credentials, or telemetry export unless an application supplies a plugin
with those guarantees.

## Reading API documentation

For a type or callable, read in this order:

1. its package export and module docstring;
2. its class or function docstring for observable behavior and failure semantics;
3. the nearest concept guide for ownership and composition rules;
4. the relevant ADR when lifecycle, hosting, security, or dependency direction is involved;
5. tests that exercise the public contract.

The repository's documentation check validates Core and checked-out sibling Orbit package module
docstrings, public class/function/method docstrings, Markdown structure, local links, and stale-work
markers in comments. It does not replace human review: docstrings must explain why a boundary
exists when the type signature alone cannot make ownership, cancellation, redaction, or concurrency
behavior clear.
