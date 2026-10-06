# Plugin authoring guide

This guide defines the minimum contract for an Orbit plugin that can be installed and tested
independently of Orbit Core. A plugin is an extension package, not a patch to Core. Keep provider
SDKs, credentials, migrations, network clients, and vendor-specific error handling outside Core.
Depending on the capability, the ecosystem may add a separately installable capability package
between Core contracts and a provider-specific adapter/plugin, so applications have a consistent
API across providers. The capability package owns the shared API; the provider adapter owns the
vendor SDK, credentials, transport, and provider-specific behavior. This is a design direction, not
a universal plugin-to-plugin contract supplied by Core. The project catalog provides planned
package names; it does not by itself define their APIs or mean they are implemented.

## Package shape

The current Core host supports Python plugins: use a dedicated distribution and declare the
`orbit.plugins` entry point in its package metadata. Pin the supported Core API range, expose a
typed configuration model, and keep the import path free of network or filesystem side effects.
Discovery imports code, so the deployment environment must treat enabled plugin packages as
trusted code. If a capability package defines a separate provider-adapter contract, document that
contract and its version range independently; Core's plugin API version does not version
capability-specific APIs.

For an opt-in local process plugin, install `orbit-core[process-plugins]` and construct
`orbit.plugins.process.ProcessPlugin` with a validated `PluginMetadata`, an absolute executable and
argument sequence, and bounded JSON-object configuration bytes. Core launches the child without a
shell and completes a versioned gRPC handshake before activation. Capability adapters can use
`invoke()` with their generated Protocol Buffer request/response types; capability repositories own
those types and the typed API presented to application code.

The host includes generated Python bindings and the versioned `.proto` source. Capability-owned
Rust stream and Go Kubernetes packages include focused SDK/runtime implementations and Core-host
checks; they are package-specific examples, not general SDK support for every capability. TypeScript
process support and broader conformance suites remain open. The process host does not expose the
Python `setup(application)` hook to the child; use a small
capability adapter in the host language to make Core registrations. Process plugins are trusted
code, not sandboxed code. They run as the application user and receive the configuration passed to
them. The current local gRPC channel uses plaintext loopback plus a one-use token, so it is not for
remote or mutually untrusted plugins. Never pass secrets in command arguments or error/health text.

## Registration and setup

Implement `PluginContract` and provide stable metadata: name, identifier, plugin API version,
semantic version, capabilities, required dependencies, optional dependencies, and required
capabilities. `activate()` and `deactivate()` are required lifecycle hooks. The synchronous
`setup(application)` hook is optional: implement it only when the plugin contributes providers,
services, routes, event handlers, health checks, or admin views. Setup must be deterministic and
must not open connections or launch tasks; defer resource acquisition to lifecycle hooks. The
convenience `Plugin` base class supplies a no-op setup hook for subclasses to override. A
provider-specific integration should also state which capability-level adapter contract it
implements and how compatibility is tested.

## Lifecycle

Activation occurs after composition validation and before service initialization. Acquire resources
through Core's container so ownership and reverse cleanup are visible. Every task and connection must
have a finite timeout and an explicit cancellation path. Cleanup must attempt all owned resources,
remain bounded by the application deadline, and preserve the original startup failure when rollback
also reports errors.

## Configuration and secrets

Register a namespaced Pydantic model with explicit limits. Use secret references rather than placing
credentials in ordinary strings or diagnostics. Document precedence, reload behavior, validation,
rotation, and what happens to in-flight requests during a change. Never include submitted secret
values in exceptions, logs, metrics, or admin responses.

## Health, resilience, and observability

Expose liveness and readiness checks that reflect the provider's actual ability to serve requests.
Core bounds its own lifecycle and request work. Application-level retry, deadline,
circuit-breaker, and bulkhead policies are optional in the separate `orbit-resilience` package.
Classify transient failures without retrying cancellation or non-idempotent writes blindly.
Register bounded metrics and spans with stable names and low-cardinality labels; export them
through a telemetry plugin.

For process plugins, use capability-specific message schemas and wrappers, bound each request,
preserve cancellation and deadlines, and map provider failures to stable codes without returning
secrets or raw provider diagnostics.

## Required tests

Each plugin should run Core's contract tests plus provider tests covering startup rollback, repeated
shutdown, cancellation, timeouts, capacity exhaustion, credential errors, health degradation,
process restart, and upgrade compatibility. Add integration tests against the real provider and a
failure-injection suite before calling the plugin production-ready.
