# Optional resilience utilities

Core owns bounded lifecycle, request, cleanup, and administration timeouts. Application-level
retry, deadline, circuit-breaker, rate-limit backpressure, failure-classification, and bulkhead
policies are provided by the separately installable `orbit-resilience` repository, not imported by
Core. These optional
utilities describe behavior; they do not make an unreliable provider reliable without a suitable
timeout, capacity, retry, and recovery policy.

## Deadlines and cancellation

Install `orbit-resilience` to use `Deadline`, which composes a child operation's budget with its parent budget using a monotonic clock.
Its timeout and captured start time must both be finite numeric values.
Every adapter call should derive a child deadline instead of starting an unrelated wall-clock
timeout. When the budget expires, Core raises a timeout error and propagates cancellation. Cleanup
boundaries may shield their own finalization, but must still have a finite upper bound.

## Retry

`RetryPolicy` applies an attempt count from 1 through 1,000,000 and bounded exponential backoff. The policy object and
optional failure classifier are validated before the first attempt, and a supplied classifier remains authoritative
even if its Python truth value is false. The default failure
classifier is conservative: programming errors and explicit cancellation are not retried. Callers
should classify provider-specific transient errors explicitly and attach an idempotency key before
retrying a write. Backoff is capped at `max_delay`, including when exponentiation for an extreme
finite multiplier would overflow. A retry policy must never exceed the parent deadline.

Retries do not guarantee exactly-once delivery. Event transports, state providers, and external APIs
must document whether an operation is idempotent, deduplicated, or merely at-least-once.

## Circuit breakers and bulkheads

`CircuitBreaker` prevents repeated calls to a failing dependency and permits a single half-open
probe after a recovery delay; its failure threshold is limited to 1,000,000. `Bulkhead` bounds
concurrent operations to at most 1,000,000 and can reject waiters after
a finite queue timeout. Capacity rejection raises `BulkheadFullError`, a `TimeoutError` subclass
classified as a resource failure by the package's default classifier, so `resilient_call` does not retry
it by default. When both primitives are composed, bulkhead admission occurs before the circuit
breaker; local queue pressure therefore cannot trip the provider breaker when the provider call
never began. Their thresholds, delays, capacities, and queue policies are read-only
after construction, so the semaphore and breaker state cannot be desynchronized by assignment.
Breaker state changes also reject stale completions: a success or failure that began before newer
state changes cannot overwrite the current breaker epoch when it finishes later. A failed
half-open probe reopens the breaker immediately.
These controls are local to one process; distributed coordination belongs
to a plugin and requires an external backend when workers need a shared view.

## Rate-limit backpressure

`AsyncRateLimiter` in `orbit-resilience` waits asynchronously for per-key token-bucket capacity
before a provider operation. `orbit-security` owns HTTP rate limiting, and the optional Admin
package applies its own local limit. The resilience utility delays an outbound operation within its
caller's budget. `resilient_call` can acquire one token for every
provider attempt; configure its wait timeout and retry policy deliberately. A rate-limit wait
timeout is classified as local resource pressure and is not retried by the default classifier.
The built-in implementation is process-local and not FIFO; a shared quota requires a separately
installed adapter implementing `orbit_resilience.RateLimiter`. The capability package remains
independent of `orbit-core`.

## Failure policy

Classify failures before choosing a response:

| Class | Typical action |
| --- | --- |
| cancellation | propagate immediately |
| invalid input or programming error | fail without retry |
| transient provider failure | retry within the deadline |
| capacity exhaustion | reject or shed load |
| dependency outage | trip the circuit and report degraded health |
| cleanup failure | record, continue remaining cleanup, aggregate |

Core records bounded diagnostics and health transitions, but it does not hide failures or claim
recovery that a plugin has not confirmed.

Timeouts, attempt counts, concurrency limits, cleanup budgets, metric series and exporter values
are validated at their Core boundaries. Boolean, non-finite, unrepresentably large, and otherwise
mismatched values fail before an operation starts, rather than leaking a platform conversion error
or changing a policy through Python numeric coercion.

Security and audit timestamps use the same rule: a non-`None` `tzinfo` is insufficient when its
`utcoffset()` is `None`; such values are rejected before comparisons or trust decisions.
