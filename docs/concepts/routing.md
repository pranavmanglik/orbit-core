# Routing

Orbit's router maps an HTTP method and canonical path to a handler during application composition.
It is provider-neutral and intentionally independent of Starlette, Litestar, or another web
framework. The router is part of Core's orchestration boundary: plugins may contribute routes, but
Core validates and freezes the complete route table before serving requests.

## Matching rules

Static segments take precedence over parameter segments. Parameters use `{name}` and are returned
in the request path-parameter mapping. A route may declare at most 128 parameters, and each name
uses the same bounded identifier contract as direct `Request` construction. Trailing slashes are
significant, paths must be absolute, and equivalent method/path templates are rejected at
registration time. `HEAD` is derived from a
`GET` route, and `OPTIONS` reports the methods allowed by the best path match.
Direct `Router.match()` calls normalize method case and accept only Core's supported HTTP methods;
invalid method types and unsupported methods fail as routing contract errors before path lookup.
Direct dispatch also applies the 16 KiB UTF-8 path bound, so programmatic callers cannot bypass the
ASGI request limit with an oversized or non-encodable path.

Core indexes route patterns in a static-first segment trie. Dispatch explores matching static and
parameter branches instead of scanning every registered route; route names, identifiers, and
method/template duplicates use dedicated indexes during composition. The ordered route list remains
available for inspection and OpenAPI generation.

A missing path produces `routing.route-not-found`. A known path with a disallowed method produces
`routing.method-not-allowed` and an `Allow` value. This distinction is stable for clients and
observability. Route matching does not perform a second percent-decoding pass; malformed escapes,
encoded separators, and dot-segment traversal are rejected by the ASGI request boundary.

## Groups and metadata

`Router.group()` composes prefixes, name prefixes, and roles for related endpoints. Route metadata
can declare an owning `ServiceId`, request and response Pydantic models, API versions, middleware,
roles, and summaries. Pass `service_id=service.descriptor.id` to `Router.route()` or
`RouteGroup.route()` when a service owns an endpoint. Application composition rejects a route that
references an unregistered service before lifecycle startup begins.
Group prefixes are validated as bounded canonical paths at composition time, and group name
prefixes are bounded printable text. Grouped route paths must be strings and absolute; route
metadata also rejects non-UTF-8 text and implicit coercion of route names or role labels before it
can reach OpenAPI generation or dispatch. Role collections are normalized to immutable sets when a
group is created or extended, so malformed nested-group inputs fail during composition rather than
later while routes are being combined.
Plugins should use a group to make ownership and route-requirement boundaries visible in inspection.
Core stores role labels as metadata but does not evaluate them. If a route declares roles, the ASGI
runtime delegates them to the configured `RouteAuthorizer`; without one the request is denied. The
`orbit-security` package supplies `RoleAuthorizer` and policy implementations.

## Validation and OpenAPI

Request models are validated before handler execution and response models after handler execution.
Validation failures use Core's structured error response and never expose internal exception text.
`OrbitProblem` and `ErrorResponse` bound public text and reject control characters, so reusable
errors remain safe when they cross HTTP, OpenAPI, Admin, logging, or telemetry boundaries.
`Router.openapi()` emits a deterministic OpenAPI 3.1 document from the frozen route metadata,
including Core error responses and role requirements. It describes the contract; a plugin or host
may publish the document through its own documentation endpoint.
OpenAPI title and version values are bounded printable text before they are included in the
generated document.

`Route` validates its binding metadata, handler, Pydantic request/response model classes, and
middleware tuple at construction time; each route may contain at most 1,024 middleware layers.
Router registration repeats those checks before adding
anything to the router, so malformed composition fails before dispatch or OpenAPI generation.
Paths are bounded to 2 KiB, summaries to 1 KiB, API
version labels to 32 characters, and summaries must be printable before they reach OpenAPI or
administrative inspection.

## Handler responsibilities

Handlers should resolve request-scoped dependencies through `request.container`, propagate
cancellation, and return `Response` or a supported structured value. Streaming handlers retain
their dependency scope until the final response frame, disconnect, or cancellation. Blocking
provider calls belong behind plugin adapters and must not block the event loop.
