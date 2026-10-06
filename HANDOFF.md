# Orbit Core handoff

## Current state

Orbit Core is a pre-alpha custom Python framework. The repository currently contains the foundational
runtime and cross-cutting contracts, but it is not certified for commercial production use. Work is
local and uncommitted; it has not been pushed to GitHub. Preserve the user's root `app.py` state if
present and do not reset or clean the worktree without explicit instruction.

Hardening progress is tracked as separate binary local and external checkpoints in
[`docs/development/stabilization.md`](docs/development/stabilization.md); do not report a blended
percentage. The weighted release-readiness scorecard in
[`docs/development/completion.md`](docs/development/completion.md) is a separate gate. The local
Core validation gate passes; hosted CI/security results, deployment pressure testing, and hosted
release provenance remain unverified.

The current Core CI and release workflows also check out `orbit-projects/orbit-testing` at `main`.
That repository is not publicly accessible at the configured URL, and the local sibling workspace has
no Git remote. Therefore hosted checks cannot be considered runnable until that package repository
is available to the workflow token at the expected path, or the maintainer supplies its correct
repository and access arrangement. Keep `orbit-testing` separate; do not copy it back into Core to
hide this prerequisite.

## Hosting decision

The authoritative hosting model is:

```text
Reverse proxy/load balancer -> Gunicorn -> uvicorn_worker.UvicornWorker -> Orbit ASGI application
```

`orbit serve` defaults to direct Uvicorn for development. Production uses:

```bash
uv run orbit serve app:runtime --server gunicorn --workers 4
```

The project also supports direct Uvicorn, `orbit run`, and `orbit start`. The accepted architecture
decision is to keep Orbit's native ASGI and routing boundary; do not add FastAPI, Starlette,
Litestar, or another web framework. Because Orbit owns HTTP/routing code, future work must emphasize
protocol security, fuzzing, load testing, and maintenance discipline. See
[ADR 0005](docs/architecture/adr/0005-native-asgi-boundary.md), which resolves the earlier FastAPI
wording in the project prompt.

## Implemented areas

- Application lifecycle phases, nested applications, task supervision with bounded cancellation
  drains, graceful cleanup, service start/stop/restart/reload, explicit failed-restart state
  transitions, application context propagation, and hosting inspection.
- Dependency injection scopes, factories, async providers, resources, aliases, introspection, and
  resolution telemetry.
- Service descriptors, dependency ordering, capabilities, health, readiness, and admin controls.
- Plugin registration/discovery, API compatibility, dependency ordering, enable/disable semantics,
  optional dependencies, capabilities, required-capability validation, and bounded activation/
  deactivation cleanup.
- Layered configuration, snapshots, diffs, reload observers, TOML watching, secret references,
  redacted secret values, secret-manager contracts, and explicit one-million-entry history caps.
- State namespaces, TTL, transactions, optimistic versions, async providers, lease coordination,
  and explicit one-million-entry/namespace capacity caps.
- Events with metadata, retries, backoff, dead letters, filters, priorities, concurrency limits,
  failure-safe deduplication before durable persistence, durable store contracts, replay, and
  application-owned event-store shutdown, with explicit one-million in-memory capacity ceilings.
- ASGI request context, validation, streaming, aggregate inbound/outbound header and body limits,
  cancellation/disconnect handling, cookies,
  compression, strict CORS, canonical path and method validation, trusted proxy handling, RFC 7239
  `Forwarded`, and optional tracing spans.
- Routing groups, middleware, route API-version metadata, OpenAPI generation, and shared error schema.
- Security policies, opt-in static-user Basic Auth, bearer authentication contracts, revocation,
  Admin rate limiting, OAuth/OIDC/JWKS contracts, and token validation policies. The separately
  installable `orbit-auth-jwt` repository owns `PyJWTVerifier` and the PyJWT dependency.
  General request-level rate limiting now lives in the separately installable `orbit-security`
  package and reuses Core's bounded in-process limiter; Core no longer exports that middleware.
- Structured Core mappings are detached and recursively immutable with explicit cycle, nesting, and
  container-work limits; direct HTTP request models enforce aggregate header, body, and query caps.
- Admin API, audit records, service/task operations, remote `AdminClient`, bounded Core metric
  instruments/snapshots, structured logging, tracing, and diagnostics export. Prometheus exposition
  and its `/metrics` route live in the separate `orbit-metrics` and `orbit-metrics-prometheus` repositories;
  application-level resilience utilities live in `orbit-resilience`.
- Optional caching is split into `orbit-cache` (provider-neutral async bytes-cache contract) and
  `orbit-cache-redis` (redis-py adapter plus an opt-in Core plugin that registers the capability and owns
  client shutdown). Neither package is bundled into Core; Redis is not installed unless the
  application chooses the adapter.
- The SQL capability publishes a shared container key; `orbit-sql-postgres` offers both explicit
  adapter-registry use and a plugin that lazily registers a PostgreSQL pool as a Core-managed
  resource. Its setup phase performs no database I/O.
- The packaging-boundary regression checks the full requested optional-package catalog and
  statically rejects known provider-SDK imports from Core. The in-process ASGI test client now lives
  in the separately installable `orbit-testing` repository and depends on Core's public ASGI
  contracts; Core's tests import it as `orbit_testing`.
- All 14 checked-out optional sibling wheels plus the Core wheel were installed together in a fresh
  Python 3.14 environment. The current Core suite and all 14 package suites passed **1,274 tests**
  combined, with two default-skipped host tests. Import-origin checks resolved all 15 Orbit modules
  to `site-packages`, and dependency consistency passed across 45 distributions. Separately, the
  Core suite passes 1,028 tests on Python 3.11–3.14 through tox; details are in the
  [completion report](docs/development/completion.md).
- Remote admin transports have bounded synchronous worker and asynchronous operation budgets; timed
  out calls retain their capacity until the underlying adapter actually returns.
- CLI inspection/health/diagnostics commands, bounded `health-watch`, plus `serve`, `run`, and
  `start` hosting commands.
- CI matrix now runs every supported interpreter independently, retains per-interpreter coverage
  artifacts, and bounds hosted security analysis; architecture/concepts/runtime/security/operations
  documentation is updated alongside it.
- Production deployment runbook covering the Gunicorn/Uvicorn worker topology, proxy trust,
  health probes, resource ownership, graceful shutdown, and network-level release checks.

## Validation

The latest full validation passed:

```bash
.venv/bin/uv run --no-sync ruff format src tests
.venv/bin/uv run --no-sync ruff check src tests
.venv/bin/uv run --no-sync mypy src
.venv/bin/uv run --no-sync python scripts/check-workflows.py
.venv/bin/uv run --no-sync python scripts/check-model-boundaries.py
.venv/bin/uv run --no-sync pytest -q
.venv/bin/uv run --no-sync python scripts/check-documentation.py
.venv/bin/uv run --no-sync python scripts/check-license-headers.py
.venv/bin/uv run --no-sync python -m build --no-isolation
.venv/bin/uv run --no-sync python scripts/check-package.py dist
git diff --check
```

The current Core suite passed **1,028 tests with two default-skipped opt-in host tests** on Python
3.11, 3.12, 3.13, and 3.14 through tox. A fresh Python 3.14 wheel environment ran Core and all 14
installed optional-package suites: **1,274 tests passed**, with two opt-in host tests skipped.
Wheel-origin and dependency checks passed. The two real-process Uvicorn/Gunicorn worker tests passed
separately on each interpreter in prior local validation. Ruff, strict mypy, documentation,
workflow, scorecard, model-boundary, license, lockfile, and package-integrity checks passed. This is
local validation, not hosted CI, live provider interoperability, production load validation, or
release provenance; details and older evidence remain in the [completion report](docs/development/completion.md).

The real-process tests exercise Uvicorn development hosting and the two-worker Gunicorn/
`uvicorn_worker.UvicornWorker` production topology, including graceful worker replacement and
shutdown. Enable them with
`ORBIT_RUN_HOSTING_TESTS=1 uv run --no-sync pytest -q tests/integration/test_gunicorn_host.py`.
The completion log records the detailed scenarios and historical test runs so this handoff remains
focused on the latest candidate rather than repeating stale counts.

The 2026-10-04 source distribution and wheel passed the package-integrity checker. The latest
combined-environment `pip-audit` found no known vulnerabilities in **28 auditable third-party
distributions** and skipped **15 unpublished Orbit distributions**; those local packages were not
covered by the advisory scan. `uv pip check` verified all 43 installed distributions were
compatible. Earlier SBOM and checksum results are historical local artifact evidence, not hosted
release provenance; signing, attestation, and publication remain open gates.

The public repository status was checked on 2026-09-28 through GitHub's public API. CI, CodeQL, and
OpenSSF Scorecard completed successfully on public `main` commit
`aaf49f27ad34eed130ebdcf13e5bec624fecfb5d`; those runs predate the current unpushed Core changes.
The active `main-protection` ruleset targets the default branch and requires one approving review,
code-owner review, linear history, CodeQL scanning, code-quality errors, and 80% coverage, but its
required status-check list is empty. After the Core changes are committed and pushed, an
authenticated maintainer must open a pull request, verify the new matrix results, and add the exact
reported status contexts to the ruleset. The public release-workflow history currently has no runs,
so hosted artifact upload and build-provenance attestation remain unverified.

## Highest-priority remaining work

1. Approve the first stable public-API baseline: review exported APIs and compatibility guarantees,
   record accepted exceptions/deprecations, and authorize the version/tag. This is a maintainer
   decision, not something local tests can decide.
2. Make the `orbit-testing` source available to the Core workflows, then verify hosted CI, CodeQL,
   and OpenSSF Scorecard on the release commit; confirm code-owner access, secret scanning, branch
   protection, and required status contexts in the protected-main ruleset.
3. Exercise the selected production host and actual reverse proxy with representative sustained
   load, TLS/HTTP2 configuration, slow clients, protocol fuzzing, upstream failures, cancellation,
   and worker termination. The existing multi-worker and direct-Uvicorn process suite is a smoke
   test, not deployment certification.
4. Run the protected release workflow and verify artifact upload, SBOM, checksums, Sigstore
   signatures, build provenance, publication, and rollback evidence.

Additional database and messaging adapters, expanded CLI streaming, and cloud-specific operations
remain separate ecosystem or roadmap work; they are not prerequisites for declaring the
provider-neutral Core boundary stable. The initial `orbit-cache → orbit-cache-redis` capability/adapter/
plugin chain is implemented locally but is not published or certified as stable.

## Working rules

- Do not claim Orbit Core is complete or commercially production-ready based only on unit tests.
- Do not replace the Gunicorn + Uvicorn-worker hosting decision.
- Keep the native ASGI boundary; do not add FastAPI, Starlette, Litestar, or another web framework
  unless the user explicitly changes this decision.
- Keep docs and tests aligned with every implementation change.
- Do not commit, push, create or merge PRs, or change GitHub settings; the user handles those steps.
