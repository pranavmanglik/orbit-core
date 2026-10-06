# HTTP and ASGI operation

Expose `Runtime(application).asgi` or `ASGIApplication(application)` to a lifespan-enabled
ASGI server. Application composition owns router freezing after plugin setup; lifespan does
not freeze plugin-contributed routes prematurely.

## Unified hosting model

Orbit uses Uvicorn and Gunicorn together. Uvicorn is the ASGI worker and protocol layer in every
environment. Gunicorn is the optional process manager for managed multi-worker execution. The
Orbit runtime owns application startup, readiness, request draining and resource cleanup; the
host owns sockets, worker processes and operating-system signals.

Use Uvicorn directly for local development and reload:

```bash
orbit serve app:runtime --server uvicorn --reload
```

Use Gunicorn with the `uvicorn-worker` package for managed workers:

```bash
orbit serve app:runtime --server gunicorn --workers 4
```

Orbit disables Uvicorn's host-level proxy identity rewriting in both modes. Core therefore
receives the direct ASGI peer and applies `trust_forwarded_headers` plus `trusted_proxies`
itself. Manual Gunicorn/Uvicorn deployments must keep `forwarded_allow_ips` empty; otherwise
the host may rewrite a malformed forwarded identity before Core can reject it.

Managed hosting also exposes validated worker controls: `--worker-timeout`, `--keep-alive`,
`--max-requests`, and `--max-requests-jitter`. These map to Gunicorn's silence timeout,
HTTP keep-alive, and bounded worker recycling. Direct Uvicorn receives the keep-alive setting;
worker recycling is a Gunicorn concern.

Hosting numeric limits are strict integers and reload is a strict boolean at the typed Core
boundary; strings, booleans, and floats are rejected instead of being silently coerced into worker,
timeout, or source-reload policy.

Gunicorn targets must expose a `Runtime` so every worker receives the same ASGI boundary. Orbit
does not preload application resources in the Gunicorn master. Each worker composes and starts
its own application during lifespan. Gunicorn handles worker replacement, signal delivery and
graceful worker termination; the Orbit lifecycle handles component cleanup inside each worker.

`Runtime` and `ASGIApplication` validate their application, hosting, router, authenticator, and
tracer objects at construction. Invalid composition fails before a host process or lifecycle hook
is started, rather than becoming a later attribute or protocol error.
`Runtime.info` exposes an immutable inspection model: application identity follows the bounded
application-name contract, and service/task/child counts are non-negative strict integers.

Gunicorn and Uvicorn do not provide distributed coordination. Multiple workers must use external
adapters for shared locks, durable state, event delivery and scheduled work. Do not put singleton
resources in module import side effects or rely on in-memory state across workers.

The [ASGI HTTP specification](https://asgi.readthedocs.io/en/latest/specs/www.html) defines
the host/framework boundary. The host supplies decoded paths and body chunks, and owns
HTTP parsing, transfer encoding, TLS and worker processes. Core never decodes the path twice.
ASGI scopes must be dictionary mappings with a string `type`; malformed scope objects fail with
an explicit bounded protocol error before request state or diagnostics are created. Unsupported
scope types are rejected with a constant diagnostic, so host-provided scope text cannot become an
unbounded exception or log payload.
The ASGI `path` and `raw_path` are both validated: dot segments, repeated slashes, backslashes,
query/fragment delimiters, controls, malformed escapes, and encoded separators are rejected.
Ordinary encoded characters remain valid, including a dot inside a name such as `file%2Etxt`.
When `raw_path` is supplied, its UTF-8-decoded value must exactly match `path`; mismatched or
invalid-UTF-8 scope pairs are rejected before routing.
The ASGI `root_path` is validated as a canonical path and removed before route dispatch, so
mounted applications receive the same route paths locally and behind a proxy.

The shared router applies the same canonical-path rules when used directly by Core callers, so
programmatic dispatch cannot bypass the ASGI path boundary. Optional Admin routes set their own
`no-store` headers inside `orbit-admin`.
The runtime owns `X-Request-ID` and `X-Content-Type-Options`; handler-supplied values for those
headers are removed before canonical values are emitted, preventing ambiguous duplicate security
or correlation headers.

Lifespan frames are validated before their protocol fields are read. A malformed startup or
shutdown frame produces an explicit protocol error; a malformed post-startup frame still runs
the normal application shutdown path before the error is propagated to the host.

## Request contract

HTTP headers are bounded by `max_header_bytes` (64 KiB by default), by a 1,000-field count, and
decoded and mounted root paths are bounded by 16 KiB; malformed header frames are rejected before
dispatch. A request may contain at most 100,000 ASGI `http.request` frames, including empty body frames. Response headers use the same
64 KiB safety budget and a 1000-field
cap, including the runtime-generated `Content-Length` on buffered responses. When a `Host` header is supplied, malformed ports,
unbracketed IPv6, unsafe authority delimiters, and non-ASCII values fail closed. HTTP bodies are buffered up to `max_body_bytes`, and buffered or streamed responses are
bounded by `max_response_bytes` (16 MiB by default). Both declared Content-Length and cumulative
received bytes are checked. Conflicting, malformed, or ASGI-preserved repeated Content-Length
fields are rejected; an HTTP host may normalize identical wire fields before Core receives the
scope, as permitted by the HTTP framing rules. Extreme numeric values cannot become an internal
integer-conversion error. Repeated headers remain distinct. The
single-valued `Content-Type` and `Cookie` fields are rejected when repeated, and duplicate cookie
names within one field are rejected, so conflicting media-type or session interpretations fail
closed at the request boundary; response `Content-Type` is also single-valued. The
`max_concurrent_requests` defaults to 1,000 and is capped at one million; deployments must tune it
with `max_body_bytes` against the worker's memory budget. The shared `Headers` model applies the same field-name, Latin-1, control-character, 1,000-field and
16 MiB aggregate limits to direct Core model construction; `Request` also rejects bodies above the
1 GiB Core ceiling and query strings above 64 KiB before they reach parsing or dispatch.
Query parsing preserves repeated values and caps field count. A client that stalls while sending
headers or body frames remains inside the finite `request_timeout`; it cannot hold a request task
indefinitely.

Handlers may raise `HTTPError` for intentional client-facing failures. Its final `4xx–5xx` status,
lowercase error code, and printable message are bounded at construction so malformed or unsafe
error data cannot destabilize response serialization.

`Response` accepts only final integer status codes and validates asynchronous stream iteration and
optional asynchronous cleanup at construction. Statuses 204 and 304 are required to have no body
or stream, so invalid HTTP framing fails before response headers are sent.
`Response.text()` requires a string before UTF-8 encoding, while `Response.json()` rejects values
that the strict JSON serializer cannot represent.
The separate `orbit-testing` package provides `orbit_testing.TestClient` and validated
`TestResponse` values using Core's public `Headers` contract. This keeps test-only code out of the
Core distribution while sharing the same status, header, and body validation.
HEAD responses retain the GET content length while suppressing the body. The final response
boundary canonicalizes the method too, so overload, draining, and other early responses cannot
emit a body when an ASGI server supplies a lowercase method token.

Handlers receive `Request`, with headers, JSON/schema validation, path parameters, query
data and a scoped dependency container. Core generates a typed `RequestId`; client-supplied
IDs do not become trusted correlation identity. `current_request_id()` exposes the typed value to
nested code, while HTTP headers, JSON errors, and structured logs serialize it as a UUID string.
Directly constructed `Request` values enforce the same method, canonical-path, body, query,
scheme, client-address, request-ID and path-parameter contracts as ASGI-created requests. Direct
path-parameter mappings are bounded, identifier-keyed, and limited to canonical nonempty path
segments, so callers cannot bypass route or path safety by constructing a `Request` directly.
ASGI peer host values are bounded and reject empty, whitespace, and control-character text before
they can affect client identity or become an internal model error.
Malformed ASGI header scopes are rejected through the normal bounded request error path before
dispatch; trace-context extraction applies the same header-count bound before scanning fields.
Duplicate or invalid optional `traceparent` values are ignored, while only one nonzero W3C trace
and parent-span ID is propagated into tracing context.

`request_timeout` bounds buffered reading, authentication, dispatch and response delivery.
Error response delivery is also bounded. Once response headers have started, a stream failure
propagates to the host instead of attempting a second HTTP response.

Request diagnostics retain only a bounded HTTP method token. If a malformed scope is rejected
before method validation, the diagnostic record uses `INVALID` rather than copying untrusted
control characters or arbitrary text into logs and inspection exports.

General request-level rate limiting is optional middleware in `orbit-security`. It uses Core's
bounded in-process token bucket and emits `x-ratelimit-limit`, `x-ratelimit-remaining`, and
`retry-after` headers. Its default key is the validated client host; deployments may provide an
explicit bounded identity or tenant key. Each worker has a separate bucket, so this is not a
distributed quota. Admin operations use the limiter owned by the optional `orbit-admin` package.

## Routing and middleware

Routes are associated with optional service identities and required roles. HEAD uses GET
when no explicit HEAD route exists and sends no body. OPTIONS and 405 expose allowed methods.
Middleware executes in registration order, with the first middleware outermost.
Route-specific middleware can wrap one handler after routing, authorization, and request-model
validation. Declared Pydantic request and response models are enforced by the runtime, and
validated request data is available as `request.validated_body`.

The health paths and admin namespace are reserved. Live reports process responsiveness;
ready reflects current application and service health. Authentication is supplied through
the provider-neutral authenticator contract. Application and principal context are restored
on every request exit.

## Ownership and shutdown

A request scope remains alive for the entire streamed response. A send-side OSError indicates
a disconnect; stream and dependency cleanup still run. Disconnects encountered while sending
an error response are handled the same way. If stream cleanup fails after another response error,
the primary transport or application error is preserved and the cleanup failure is logged; when
there is no earlier error, cleanup failure remains observable to the caller.
The regression suite verifies the cleanup order as well: a streamed iterator closes before its
request-scoped dependency resources exit.

At shutdown, the runtime rejects new work, waits for active requests for the lifecycle
timeout, then cancels unfinished requests and waits for their cleanup before stopping Core.
Shutdown itself is shared and shielded against caller cancellation. Handlers cannot await
runtime shutdown because that would wait on themselves.

Overload responses return 503 with correlation headers and contribute to diagnostics.
The request timeout and shutdown deadlines require cooperative async extension code.

`Runtime.info` exposes the current lifecycle phase plus registered service and supervised-task
counts, including failed tasks, without acquiring resources or mutating the application.

WebSocket upgrades are explicitly rejected by this Core HTTP release. The testing client
exercises real ASGI messages; socket, proxy and worker behavior requires deployment tests.

The protocol regression suite also runs a deterministic adversarial scope corpus covering malformed
methods, paths, client addresses, schemes, header shapes, and oversized header lists. This is
bounded input coverage, not a substitute for deployment-level fuzzing or proxy testing.

Shutdown drains active requests up to `lifecycle_timeout`, then cancels and performs a bounded
cancellation grace drain. A handler that suppresses cancellation is reported as a cleanup failure
rather than being allowed to hang worker termination; such handlers must release their
request-scoped resources.

Set `trust_forwarded_headers=True` with explicit `trusted_proxies` CIDR networks to accept
`X-Forwarded-For` and `X-Forwarded-Proto`. The immediate ASGI peer must match a configured
network; otherwise forwarded values are ignored and the socket peer remains authoritative.
Invalid forwarded addresses and schemes are discarded. Host authorities and ASGI client
identities also reject interface-scoped IPv6 literals, so Python-specific zone identifiers cannot
enter proxy trust evaluation.

Cross-origin policy and response compression are optional middleware in the separate
`orbit-gateway` distribution. Install it with `pip install orbit-gateway` and attach
`CORSMiddleware` or `GZipMiddleware` explicitly through `ASGIApplication.add_middleware()`.
Core provides only the middleware contract and ASGI registration point; applications that do not
need these HTTP policies do not carry their implementation in `orbit-core`. See the separate
`orbit-gateway` package README for exact CORS and gzip policy behavior.

`Request.cookies` parses a bounded Cookie header into a detached mapping and rejects duplicate
cookie names instead of selecting the last parser value. `Response.with_cookie`
builds a validated `Set-Cookie` value and appends it without folding existing repeated cookies;
cookie names/values and attributes are safe text without semicolon attribute injection,
`secure`/`httponly` are strict booleans,
`SameSite=None` requires `Secure`, and `max_age` must be a nonnegative integer;
cookie parsing or attribute errors become explicit request/configuration errors before bytes are
sent.

Middleware may optionally implement async `startup()` and `shutdown()` hooks. ASGI lifespan runs
startup hooks in registration order after application startup, and shutdown hooks in reverse order
before application cleanup. If a middleware startup hook fails, already-started middleware is
cleaned up and the application is stopped before lifespan failure is reported; rollback attempts
every already-started hook and preserves the original startup failure. Each asynchronous hook is
given the application lifecycle deadline. A hook that suppresses cancellation is detached and its
late result is consumed, so a stubborn extension cannot prevent remaining middleware or Core
resources from being released. A shutdown hook that raises `CancelledError` is also retained as a
cleanup failure while application cleanup continues. During shutdown, middleware and application
cleanup failures are reported together so an operator can diagnose the complete cleanup outcome.

When forwarded headers are trusted, Core also accepts the first RFC 7239 `Forwarded` element.
Its validated `for` and `proto` parameters take precedence over their `X-Forwarded-*`
counterparts; malformed values are ignored and the direct socket peer remains authoritative. Core
also rejects repeated `Forwarded`, `X-Forwarded-For`, or `X-Forwarded-Proto` fields, and duplicate
`for` or `proto` parameters within one `Forwarded` element, as ambiguous; one field may still
contain a validated comma-separated proxy chain. Interface-scoped IPv6 literals are rejected in
forwarded `for` values; only address literals without a zone identifier can affect client identity.

`orbit-security.RateLimitMiddleware` validates its key provider during construction. The provider
must return a bounded string key; the middleware preserves callable objects even when their boolean
value is false. Allowed responses include `Vary: Origin`, and rejected requests return a structured
429 without reflecting attacker-controlled policy input.
