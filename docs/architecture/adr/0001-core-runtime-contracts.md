# ADR 0001: Core runtime contracts

Status: Accepted for the pre-release Core. Date: 2026-09-13.

## Decision
Preserve the requested package boundaries. File length is not a quality criterion:
a module owns one cohesive responsibility, and its public behavior must be implemented,
documented, and exercised, including failure paths.

One Application owns the service graph, provider container, event bus, router,
plugin registry, lifecycle, configuration and state. Runtime, CLI and admin use these
same objects. Composition freezes before resource acquisition; no implicit module
scanning or plugin import occurs during construction.

Startup is transactional. Every component whose resource hook has been entered is
eligible for reverse-order cleanup, including the failing component. Cancellation
must propagate after cleanup. Shutdown attempts all cleanup and aggregates failures.
Applications cannot restart after stopping; build a new application.

Dependency factories declare dependency keys. SINGLETON resources live at application
scope, SCOPED resources at an explicit request/task scope, and TRANSIENT values are
created per resolution. Async resource providers use async context managers with LIFO
exit. Singleton-to-scoped dependencies are rejected. No automatic annotation injection.

HTTP supports bounded buffered requests, repeated headers, HEAD/OPTIONS, route parameters,
middleware, authentication, request scopes, JSON validation, structured errors, and
streaming responses. WebSocket support is outside this HTTP Core release; reject upgrades
explicitly. The host owns sockets, HTTP parsing, TLS and worker processes.

The admin panel is opt-in and authenticated. Inspection requires orbit.admin.read;
mutations require orbit.admin.write and a non-cookie request authorization mechanism.
Provider code is trusted code: discovery requires an explicit allowlist. At the time of this
decision, the plugin host was Python-only and imported Python entry points into the application
process. ADR 0020 adds an optional versioned local gRPC process host; it does not load arbitrary
native libraries or sandbox plugin code. Cross-language SDKs, conformance, security review, and
performance evidence remain separate ecosystem gates.

## Consequences
No provider integrations are required for the Core tests. Health, plugin and event
backends remain external implementations of these contracts. Operational safety is
tested locally; claims about OpenSSF badges, branch protection, production deployment
or signed published releases require evidence from the hosted project.
