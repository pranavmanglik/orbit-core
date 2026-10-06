# Background tasks

Applications own background work through `application.tasks`. Register tasks during
composition, before `configure()` freezes the application:

```python
async def refresh_cache() -> None:
    while True:
        await cache.refresh()
        await asyncio.sleep(30)


application.tasks.register("cache-refresh", refresh_cache)
```

Tasks start after all services have started and stop before service cleanup. Shutdown
cancels every task and drains cancellation within `lifecycle_timeout`. A task that suppresses
cancellation is marked failed and logged as abandoned once the deadline expires; Python cannot
forcefully terminate such a task, so task code must cooperate with cancellation.

Task names are bounded lowercase identifiers (`[a-z][a-z0-9_.-]{0,126}`). Restart policies, numeric
limits, delays, factories and observers are validated at registration. Retained failure history and
restart budgets are each capped at 1,000,000; history retains only the newest configured number of
failures in chronological order, and `history_size=0` disables retention. String,
boolean, non-finite or otherwise mismatched values are rejected before application startup, keeping
task supervision failures out of the worker lifecycle and making Admin task paths unambiguous.

Use `RestartPolicy.ON_FAILURE` with a finite budget for work that can recover from a
transient failure:

```python
application.tasks.register(
    "poller",
    poll,
    policy=RestartPolicy.ON_FAILURE,
    max_restarts=3,
    restart_delay=1.0,
)
```

Task failures are isolated from unrelated services, retained as bounded metadata in
`application.tasks.history` and emitted as `orbit.task.failed`. The optional `orbit-admin` package
exposes task state at an authenticated `/admin/tasks` endpoint.

`TaskFailure` and `TaskInfo` are validated immutable snapshots. Names, attempt counters,
exception-type identifiers, lifecycle states and elapsed timing are checked at construction, so
operator-facing diagnostics retain the same bounded contract whether they came from the
supervisor or an adapter.

If an asynchronous failure observer is configured, its execution is bounded by the
supervisor's `observer_timeout` (one second by default). Observer exceptions and timeouts are
logged and do not prevent the task's failure state, restart budget, or shutdown from progressing.
Task specifications share Core's one-million registration ceiling. At most one
cancellation-resistant observer is retained after a timeout; later failures skip a
new observer invocation until it exits, preventing orphan-task accumulation. Observers should
still avoid blocking synchronous work and should treat the failure payload as diagnostic metadata
rather than a retry or durability guarantee.

A task that terminates after exhausting its restart policy is reported as an unhealthy
`task:<name>` component and makes application readiness fail. Restartable tasks remain eligible
for readiness while they are running or within their configured restart budget.

While the application is running, operators can explicitly restart a task through
`await application.restart_task("poller")` or the authenticated `POST
/admin/tasks/poller/restart` operation when `orbit-admin` is installed. The supervisor joins the old task before creating its
replacement and retains the prior failure history for diagnostics. The intentional cancellation
does not create a synthetic `CancelledError` failure or invoke the failure observer. The join is
bounded by the supervisor shutdown timeout; a task that suppresses cancellation is marked failed
and no duplicate replacement is created.
