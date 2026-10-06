# Observability

`application.diagnostics` owns request diagnostics and a backend-neutral `MetricsRegistry`.
Counters, gauges and histograms validate names and labels, reject non-finite values, and cap
the number of metric definitions, histogram buckets, and label series to prevent unbounded
cardinality. `MetricSnapshot` repeats the metric kind, value, count, sum, label, and bucket
validation when an exporter or adapter constructs a snapshot directly; labels and buckets are
detached while validating, so inaccurate custom mapping lengths cannot bypass the caps. Call
`snapshots()` to obtain detached, recursively read-only values for a Prometheus, OpenTelemetry or other exporter;
diagnostic status-count mappings follow the same immutable snapshot contract.
Histogram snapshots also require cumulative, nondecreasing bucket counts that do not exceed the
total count. Exporter-specific label rules are enforced by the selected adapter.
Label values must already be strings; Core does not silently coerce arbitrary objects into
observable labels. Request status codes, durations, latency bounds and diagnostic counters are
strictly typed at the model boundary, so booleans and numeric strings cannot become telemetry
values through implicit coercion.
Metric updates also reject overflow-sized integers and cumulative totals that would become
non-finite, so exporters cannot silently receive `Infinity` from local arithmetic.
Request diagnostics perform the same cumulative-duration preflight before retaining history or
updating counters, so a rejected record cannot partially mutate the diagnostic snapshot.
`DiagnosticSnapshot` also applies Core's capacity policy to direct request-history and
latency-bucket construction, keeping detached operator payloads bounded even when they do not
originate from `Diagnostics.collect()`.
`DiagnosticSnapshot` also validates that aggregate request, error, cancellation, disconnection,
and per-status totals are nonnegative and internally coherent before the snapshot is retained or
serialized.

Request diagnostics automatically publish `orbit_http_requests_total` and
`orbit_http_request_duration_seconds`. Core does not ship an exporter or network endpoint;
separately installed adapters own exposition, transport, batching, retention and backpressure.
The `orbit-metrics-prometheus` adapter adds a `/metrics` route to an application when explicitly
registered. Protect it with route roles and deployment network policy when the output is not
intended to be public.

`orbit_http_responses_total` adds the bounded `method`, `status`, and `outcome` dimensions for
request analysis. The aggregate counter remains available for low-cardinality dashboards.

The runtime also publishes `orbit_services_registered`, `orbit_tasks_registered`,
`orbit_tasks_failed`, and `orbit_plugins_enabled` gauges. They are refreshed when diagnostics are
collected; exporter plugins can refresh them before collecting snapshots.

Event delivery publishes `orbit_events_published`, `orbit_event_delivery_failures`, and
`orbit_events_deduplicated` gauges from the bus's cumulative counters. Delivery history remains
bounded separately, so these values do not depend on the diagnostic retention window.

Container construction publishes `orbit_container_resolutions_total` and
`orbit_container_resolution_failures_total`. Only outcome counts are retained; provider keys,
values and exception messages stay outside the metrics payload.

`orbit_service_health{service,status}` and `orbit_plugin_health{plugin,status}` are one-hot
health gauges. Status values are limited to Core's four health states, and plugin names are
namespaced, so a component's current health can be queried without unbounded status labels.

`Diagnostics.subscribe()` requires a sink with a callable `record()` method; sink failures are
logged with a constant message and isolated from request processing, so provider exception text
does not enter Core's default diagnostic log. The optional `orbit-logging` package formats
standard-library records with application, request, correlation, trace and span IDs while
excluding exception messages and arbitrary record extras. Core retains the backend-neutral
context and diagnostics contracts.
Install it separately with `pip install orbit-logging`; it does not configure the root logger.
The ASGI boundary binds a request correlation ID and span, and accepts a valid W3C
`traceparent` trace ID; malformed or untrusted trace headers are ignored. Context variables are
restored after every request so concurrent work cannot leak identity between requests.

`InMemoryTracer` and the `Tracer`/`Span` protocols provide a bounded adapter-neutral tracing
surface. Pass a tracer to `Runtime(..., tracer=tracer)` or `ASGIApplication` to create an HTTP
span per request. Nested spans inherit the W3C trace ID and parent span ID, capture bounded
printable attributes (at most 128 attributes per span), and record `ok` or `error` status on
completion. `SpanRecord` validates bounded printable IDs, finite nonnegative timing, and allowed
statuses at the public snapshot boundary. Retained span attributes are detached from caller-owned
mappings while validating and recursively frozen so exporters cannot mutate diagnostic history.
HTTP spans use the matched route template for `http.route`, never the concrete request path or
dynamic path parameters; unmatched requests and Core-owned endpoints omit that attribute. This
prevents user-controlled path values from being copied into tracing exporters as route metadata.
OpenTelemetry and other exporters can implement the
same protocols without adding a backend dependency to Core. Span history sizes, span names, and
attribute names are validated at construction or use so malformed diagnostic metadata cannot leak
incidental Python type errors.

`Diagnostics.export(application, indent=2)` serializes the same detached snapshot as JSON for
incident artifacts or transport adapters. It is bounded by the configured request history and
contains no raw request bodies, credentials, exception messages, or provider values. The optional
indent is a strict integer from 0 through 8. Request and span history, metric definitions, and
metric series accept explicit capacities no greater than 1,000,000.
Setting request or span `history_size` to zero disables local retention while cumulative counters
remain available.
