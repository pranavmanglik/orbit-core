# ADR 0020: Local gRPC process plugin host

Status: Accepted for the pre-release Core. Date: 2026-10-05.

## Context

Orbit Core is a Python orchestrator. Its existing `PluginContract` is an in-process Python
protocol, which cannot be implemented directly in another language. The ecosystem selected gRPC
with Protocol Buffers for a typed, generated cross-language boundary. A host must preserve Core
lifecycle ownership, bound messages, identify the expected plugin, and keep provider contracts
outside Core.

## Decision

Keep the current Python entry-point and in-process plugin path unchanged. Add an opt-in process host
in `orbit.plugins.process`, installed through the `process-plugins` extra. Core supervises one
local child executable over the bidirectional gRPC stream defined by
`src/orbit/plugins/v1/process_plugin.proto`.

The child receives a one-use 256-bit token and an ephemeral `127.0.0.1` endpoint through a bounded
stdin bootstrap record. It authenticates with the token and sends a protocol/version and complete
metadata handshake before Core activates it. Configuration is sent only after the handshake.
Protocol messages support activate, deactivate, health, and capability calls. Capability packages
own their typed Protocol Buffer schemas, compatibility policy, and user-facing adapters; Core
transports `Any` payloads and does not interpret capability data.

Core executes an explicit absolute command vector without a shell, passes only a small baseline
environment plus explicit overrides, redirects child output, limits configuration/message sizes,
and bounds startup, calls, and shutdown. Failure or cancellation must close the stream, stop the
server, and reap or terminate the child. The process host is not a sandbox: plugins execute with
the application's OS privileges. The current transport is plaintext loopback with bearer-token
authentication and is only intended for trusted same-user processes. Remote execution, reduced
privileges, automatic restart, and process-level resource quotas are outside this first host
milestone.

The Python `setup(application)` hook is not available across the process boundary. A capability
package may provide a Python adapter that registers Core services/routes and delegates capability
calls to the process plugin. Core lifecycle commands are separate from capability-specific
contract versions.

## Alternatives considered

- Keep Python-only: preserves in-process composition but does not meet the selected polyglot goal.
- Add native ABI loading: couples runtimes and memory models and increases crash/security impact.
- Framed JSON-RPC on stdio: simpler bootstrap, but would require a custom typed schema, streaming,
  backpressure, and code-generation system.
- Bind a plugin server to a plugin-selected local port: adds endpoint discovery and a startup race;
  Core-owned loopback server plus a child connection avoids this race.

## Consequences

The optional dependency keeps Core's default installation small. The protocol is versioned
independently from the Python Core API. Generated Python bindings and a process host are present;
focused Go Kubernetes and Rust streams SDK/runtime paths exercise the protocol. TypeScript support,
broader conformance tests, capability migrations, security review, and realistic performance
measurements remain release gates. Process isolation does not imply
performance improvement: IPC and serialization must be included in workload benchmarks.

## Validation

`tests/integration/test_process_plugins.py` and `orbit-streams/tests/test_process_rust.py` exercise
separately launched children through the real gRPC stream, including lifecycle, health, typed
Protobuf calls, configuration, error sanitization, and shutdown. These local tests do not establish
OS sandboxing, live provider behavior, or release readiness.
