# Stable Core release gate

Orbit Core is not expected to contain every provider integration. This gate defines when its
orchestration contracts are stable enough for plugin development and internal release. A plugin
must pass its own provider, security, and deployment evidence before it is called production-ready.

The Core release gate covers:
- dependency graph validation, scope isolation, resource cleanup and overrides;
- application and component state, concurrent lifecycle calls, timeout and cancellation;
- plugin metadata validation, explicit discovery, dependency ordering and cleanup;
- typed configuration composition, secret redaction, state validation and event delivery;
- ASGI request/response framing, disconnects, size/time limits, route dispatch and security;
- current health/readiness, diagnostics and an authenticated administrative surface;
- working CLI, examples, integration helpers, documentation and package builds;
- release archive integrity, including safe paths, importable contents, typing metadata, license
  inclusion and distribution metadata;
- module/public API docstrings, Markdown structure, local-link validation, and comment hygiene;
- lint, strict typing, behavioral tests, coverage and security automation.

Public compatibility and deprecation expectations are defined in the [API stability policy](api-stability.md).

The gate is complete only when these contracts are versioned, documented, exercised through the
public APIs, and safe under cancellation, partial failure, repeated lifecycle calls, and concurrent
use. “Complete” does not mean that Core ships a database, broker, identity provider, cloud client,
or telemetry backend.

## Orbit Core release scorecard

Day-to-day hardening progress is tracked separately using the binary checkpoints in
[`stabilization.md`](stabilization.md). That avoids mixing work in the Core worktree with
maintainer approval, GitHub configuration, deployment validation, or hosted release operations.
The weighted score below remains a release-readiness gate, not an estimate of coding progress.

Orbit uses this fixed 100-point scorecard for progress reports. It is a repository measurement
system, not a claim that a universal industry percentage exists. Each point requires current,
reviewable evidence; an unverified hosted or deployment result is not counted as passing.

| Area | Weight | What earns the points |
| --- | ---: | --- |
| Core contracts and scope | 25 | Application/service/lifecycle/DI, configuration/state/events, ASGI/routing/hosting, health/admin/security, extension contracts and public API are implemented and documented. |
| Reliability and operational behavior | 20 | Cancellation, concurrency, cleanup, protocol limits, failure injection, multi-process hosting, proxy, load and soak behavior are tested at the appropriate layer. |
| Security and supply chain | 15 | Security boundaries, redaction, scanning, dependency auditing, signed artifacts and provenance have evidence. |
| Tests and compatibility | 20 | Full behavioral suite, the declared coverage gate, supported Python versions, hosting smoke tests, lint and strict typing pass. |
| Documentation and API governance | 10 | Public docstrings, comments, guides, examples, API stability policy and ADRs are maintained. |
| Packaging and release operations | 10 | Build integrity, licenses, SBOM, checksums, hosted release workflow, rollback and release verification pass. |
| **Total** | **100** | **Stable release requires both the score threshold and every mandatory release gate.** |

The score is reported as `earned / 100`, followed by the category breakdown. A score of 90 or
more is necessary but not sufficient for a stable release. The mandatory gates are: the local Core
validation gate, hosted CI/security evidence for the release commit, deployment-level HTTP and
hosting evidence, and verified release artifacts/provenance. Plugins and community adoption are
tracked separately and do not affect this Core score.

The machine-readable source for the fixed weights and current evidence state is
[`completion-scorecard.toml`](completion-scorecard.toml). Validate and print it with
`python scripts/check-scorecard.py`; use `--require-stable` only when evaluating a release
candidate. The checker rejects category, weight, score, or gate-name drift so progress reports
cannot silently change their denominator or claim an open mandatory gate as complete.

Current evidence score: **87 / 100** — Core contracts 23/25, reliability 19/20, security and
supply chain 10/15, tests and compatibility 20/20, documentation and API governance 10/10, and
packaging and release operations 5/10. The local Core gate passes; hosted workflow results,
deployment pressure testing, and hosted release provenance remain open and therefore are not
counted as complete.

Passing local checks is evidence about the implementation, not a production certification. This
work includes separating existing integrations into local sibling package workspaces; it does not
claim that the full requested ecosystem catalog is implemented or released. Hosted repository
governance, actual security scan results and release provenance remain deployment gates.

## Verified locally on 2026-09-28

- Python 3.11.14: 1108 behavioral tests passed, 2 opt-in hosting tests skipped, 91.96% combined line/branch coverage.
- Python 3.12.14, 3.13.15, and 3.14.7: each lock-synchronized environment passed 1108 behavioral
  tests, with 2 opt-in hosting tests skipped by default; the enabled Gunicorn/Uvicorn process
  hosting smoke test also passed for each interpreter.
- The hosted quality matrix is configured to report every supported interpreter independently,
  retain one coverage XML artifact per interpreter, and bound CodeQL and Scorecard runner time.
- Ruff lint and formatting passed; strict mypy passed for 116 source files.
- Public API regression coverage verified that every documented Core package exposes unique,
  resolvable exports, with the root `__version__` export explicitly preserved.
- Documentation policy and local-link validation passed across source, tests, examples, scripts,
  and repository Markdown.
- The model-boundary audit passed: Core Pydantic models use explicit strict primitive fields,
  validate declared defaults, and regression tests reject byte-to-text coercion at event, audit,
  error, secret, and security boundaries.
- Structured mapping boundaries detach and recursively freeze nested values, reject custom mutable
  mappings that would otherwise escape protection, and fail closed on cycles or excessive nesting.
- Configuration snapshots apply the same fail-closed cycle, depth, and recursive-work guarantees
  while retaining JSON-safe immutable history.
- Configuration loading detaches explicit, file, and environment mappings during their bounded
  validation pass, so mutable custom inputs cannot change between validation and composition.
- Long-lived configuration history and in-memory state capacities are explicitly bounded to one
  million retained snapshots, entries, or namespaces at their public constructor boundaries.
- Maintained Python license-header checks, source/wheel builds and distribution-integrity checks passed.
- The frozen development/server environment installed successfully and pip-audit reported
  no known vulnerabilities; the editable Orbit package itself is excluded by that audit.
- Local release-artifact validation also generated a valid CycloneDX SBOM with 58 components and
  verified SHA-256 checksums for the source distribution and wheel; hosted provenance attestation
  remains a separate release gate. The release checker also rejects unlisted direct artifacts and
  symlinked release metadata before signing.
- Regression tests cover independent scope concurrency, singleton contention, asynchronous
  acquisition/close races, cancellation-safe cleanup, per-resource failures, atomic startup,
  shared health checks, bounded plugin activation rollback, service-owned routes, typed
  configuration/provider/request identities,
  plugin routes through lifespan, operational diagnostics, admin failure isolation and
  testing-client protocol validation, concurrent overload admission, failed-handler cleanup,
  request-capacity reuse, deterministic adversarial ASGI scope handling, and stream disconnect
  cleanup ordering for request-scoped dependencies.
- The in-process ASGI test harness now has direct regression coverage for structured lifespan
  failures, silent host termination, bounded shutdown cancellation, client disconnect frames, and
  applications that emit no response.
- The maintained `examples.minimal.app:application` target is validated through the real CLI loader,
  composition checker, dependency inspection command, and one-shot health command; its explicit
  `examples.minimal.app:runtime` target is also validated for Uvicorn/Gunicorn hosting.
- The opt-in two-worker Gunicorn smoke test passed with `uvicorn_worker.UvicornWorker` under
  Python 3.11, 3.12, 3.13, and 3.14; SIGHUP replacement workers served an HTTP route, every
  worker generation served repeated 64-request concurrent bursts, one replacement worker was
  terminated deliberately and replaced, an in-flight request completed during graceful termination,
  and every generation reached service cleanup before the Gunicorn master terminated cleanly.
- The same opt-in process suite started the supported `orbit serve --server uvicorn` development
  path on all four supported interpreters, served repeated 16-request concurrent bursts plus eight
  32-request sustained-load rounds and a bounded thirty-second request soak, rejected a stalled
  body and conflicting framing at
  the real socket boundary, rejected an oversized header with either a bounded HTTP response or
  host-level connection close, verified valid and malformed
  trusted-proxy identity through a forwarding hop in both direct Uvicorn and Gunicorn workers, and
  completed SIGINT-driven lifespan cleanup.

## Follow-up branch revalidation on 2026-10-01

Commit `7651129` and the current uncommitted follow-up changes were revalidated on Python 3.11.14
after being based on the current upstream `main`. Ruff lint and formatting, strict mypy,
documentation and license-header checks, workflow and model-boundary validation, a fresh source and
wheel build with package-integrity checks, and the scorecard checker all passed. The
scorecard remains **87/100** with the hosted CI/security, deployment, and release-provenance gates
open.

The locked transitive dependency `urllib3` was updated from 2.7.0 to 2.8.0 after the live audit
reported advisories affecting the earlier version. The frozen lockfile check passed, and a
subsequent `pip-audit --skip-editable --progress-spinner off` run reported no known vulnerabilities
in the installed dependency set. As with the documented audit policy, the editable Orbit package
itself is excluded; this local result does not replace hosted scanning of the release artifact.

The full behavioral suite passed with **1,110 passed, 2 opt-in hosting tests skipped, and 92.00%
coverage**. With local socket access enabled, both opt-in real-process hosting tests also passed:
the direct Uvicorn development path and the Gunicorn `uvicorn_worker.UvicornWorker` path. This is
local evidence for the follow-up branch, not a replacement for hosted checks or deployment-level
load and proxy validation.

The latest local follow-up makes `AdminClient` event-loop ownership explicit and tests both
sequential reuse and concurrent first-use races: one instance binds atomically to one loop and
rejects use from another. Additional admin-client tests now cover health refresh routing, malformed
adapter results, non-mapping response bodies, and recovery after synchronous transport exceptions.
Authorization helpers now require the validated Core `Principal` type, rejecting role-shaped
objects that have not crossed Core's identity boundary.
Token, policy, JWKS, and revocation expiry comparisons now use exact UTC instants through daylight-
saving folds. Revocation cleanup is indexed by an expiry heap rather than scanning the entire store.
Repository workflow policy now also requires explicit token permissions, rejects global write
permissions in block and flow-style YAML, and ensures checkout actions do not retain their
credentials after use. Before the latest state-expiry-index change, the full suite passed with
**1,122 passed and 2 opt-in hosting tests skipped** on Python 3.11.14 (92.20% coverage), 3.12.14
(92.17%), 3.13.15 (92.17%), and 3.14.7 (92.14%). The opt-in real-process tests were not enabled
in those cross-version behavioral runs; their previously recorded separate hosting results remain
distinct evidence.

## State expiry index update on 2026-10-01

Namespaced in-memory state now uses a min-heap to inspect only due TTL deadlines instead of
scanning every retained key on each operation. Unique refresh tokens prevent stale deadlines from
expiring newer values; periodic compaction bounds obsolete index records. Tests cover refresh and
expiry ordering plus bounded compaction. The tox matrix also now installs the `server` extra needed
by CLI host tests and isolates coverage files per interpreter. All four environments passed with
**1,126 passed and 2 opt-in hosting tests skipped**: Python 3.11.14 at **92.16%**, 3.12.14 at
**92.21%**, 3.13.15 at **92.21%**, and 3.14.7 at **92.18%** coverage. The opt-in real-process
hosting suite also passed **2 tests per interpreter** across all four versions after this change.
The latest source and wheel build passed the archive-integrity checker, `uv lock --check` passed,
and `pip-audit --skip-editable` reported no known vulnerabilities in the installed dependency set.

## Candidate revalidation on 2026-10-04

After moving file polling, CORS, and gzip policy to separate packages, the current Core source passed
**1,054 behavioral tests** on Python 3.11.14, 3.12.14, 3.13.15, and 3.14.7, with two opt-in real-host tests skipped
by default on each interpreter. Branch coverage remained above **91.7%** on every interpreter,
above the 90% gate. Ruff, documentation/workflow/license checks, scorecard validation, and strict
mypy passed. The matrix ran in isolated `uv` project environments using the frozen lockfile,
keeping the shared workspace environment untouched and ensuring the current worktree was tested.
The opt-in Uvicorn/Gunicorn worker-process suite also passed **2 tests on each interpreter**.

The `orbit-devtools`, `orbit-logging`, and `orbit-gateway` wheels installed together with the current
Core wheel in a clean target directory; their combined **52 tests passed** against those installed
wheels. The devtools suite passed on Python 3.11–3.14 (**10 tests each**), as did the gateway suite
(**39 tests each**). The earlier combined
Core/data/SQL/PostgreSQL/JWT/metrics/Prometheus/resilience package validation remains separate
evidence for its own candidate; this check does not claim a live PostgreSQL service or deployment.

On the immediately preceding Core candidate, the Core, data contracts, SQL capability, PostgreSQL
adapter, JWT, metrics, Prometheus, and resilience wheel artifacts built successfully. All eight
installed together in a clean Python 3.11 environment with dependency checks passing. The seven
optional-package suites ran against those installed distributions (**137 passed** after the JWT,
Prometheus, resilience, PostgreSQL, and repository-conflict hardening below), and module-origin
checks confirmed imports resolved from the installed wheels. This earlier run does not include the
latest Core wheel. It verifies local packaging/composition only, not live PostgreSQL or deployment.

Core's focused packaging-boundary, rate-limiter, ASGI middleware, and Admin rate-limit checks passed
**24 tests**. The rebuilt `orbit-sql` wheel's suite includes task-cancellation rollback, conflict
translation, and Unit-of-Work reuse (**12 passed**). The PostgreSQL adapter suite passes **21 tests
on each of Python 3.11, 3.12, 3.13, and 3.14**, covering transaction cancellation/release, bounded
pool shutdown, fail-fast constructor validation, immediate conflict mapping, and deferred commit
conflicts.
These focused runs supplement but do not replace the four-interpreter full Core matrix recorded above.

The optional `orbit-resilience` package provides an async token-bucket backpressure capability with
an adapter protocol for future shared quota providers. Its previous 67-test suite passed on Python
3.11–3.14. After the eager configuration-validation change below, the expanded **72-test** suite
passed against the installed rebuilt wheel on Python 3.12, 3.13, and 3.14, and against source plus
wheel on Python 3.11. Each isolated environment passed dependency checks; Ruff, format, and strict
mypy passed on the updated source. This is a per-process implementation, not a distributed quota
service.

The optional `orbit-prometheus` exporter now rejects metric-family collisions with histogram-
generated sample names and caps each encoded exposition at 8 MiB. The expanded **8-test** suite
passes against both the source tree and rebuilt wheel; the combined seven-package installed-wheel
suite then totaled **122 passed**. Ruff, format, and strict mypy checks pass. The cap bounds one scrape
response; it does not replace deployment-level scrape and cardinality planning.

The optional `orbit-jwt` adapter rejects algorithm allowlists that mix HMAC and asymmetric families,
avoiding an unsafe key-family configuration. Its base install keeps cryptography optional: HMAC works
without that dependency, while configuring RSA, ECDSA, PSS, or EdDSA without the
`orbit-jwt[asymmetric]` extra fails immediately with an install hint. The **24-test** suite passes,
including real HS256/RS256 verification; Ruff, format, and strict mypy pass. A clean Python 3.11
base-wheel install was verified without cryptography, and the asymmetric extra was separately
installed and smoke-tested. This adapter remains outside Core and depends on Core's token contract.

The general HTTP `RateLimitMiddleware` moved from Core to the separately installable
`orbit-security` package. Core retains its bounded local limiter for built-in Admin protection, but
no longer bundles general request-throttling policy. The package reuses Core's ASGI types and
bounded local `RateLimiter`, documents that limits are per-process rather than distributed, and has integration
coverage for allowed/rejected requests, headers, callable validation, and falsey key providers.

`resilient_call` now validates its operation and supplied deadline, retry, circuit, and bulkhead
objects before acquiring rate-limit capacity. Five regressions cover malformed policy objects and
non-callable operations leaving limiter state untouched. The expanded **72-test** resilience suite
passes on Python 3.11–3.14 against the rebuilt wheel, and also passes from source on Python 3.11.
All seven optional-package suites passed in the combined-wheel environment (**137 passed**, Python
3.11).

Unique and primary-key violations now have a stable SQL error code across built-in SQLite and the
PostgreSQL adapter; `orbit-sql` maps it to `orbit_data.RepositoryConflictError` for repository
writes; PostgreSQL deferred uniqueness violations at commit follow the same path. The focused Core
database suite passed **18 tests**, `orbit-sql` passed **12 tests**, and the PostgreSQL adapter
passed **21 tests on Python 3.11–3.14**. The Core database, SQL repository, and PostgreSQL adapter
suite passed **51 tests per interpreter** across that matrix. A new installed-wheel composition test
exercises adapter registration, a typed repository read/write, and a repository-bound unit of work
through the Core SQL contract. The final combined seven-package wheel suite passed **137 tests** on
Python 3.11. [ADR 0008](../architecture/adr/0008-sql-repository-conflicts.md) records the conflict
contract and compatibility behavior.

Ruff lint and format checks, strict mypy, workflow policy, scorecard, Pydantic model-boundary,
documentation, license-header, and `uv lock --check` validations passed. A fresh source distribution
and wheel built under `/tmp`; the package-integrity checker accepted both artifacts. A current
`pip-audit --skip-editable --progress-spinner off` run, with the unrelated inherited `VIRTUAL_ENV`
unset and Orbit's `.venv` selected explicitly, reported **no known vulnerabilities** in the
installed third-party dependencies. The editable Orbit distribution remains excluded, so this is
dependency evidence rather than an audit of the built artifact. In addition, strict `pip-audit`
against the clean combined-wheel environment used the OSV vulnerability service because the local,
unpublished Orbit distributions are not resolvable from PyPI. A subsequent `pip-audit --path`
scan of that combined Python 3.11 environment reported no known vulnerabilities among **28
auditable third-party distributions** and skipped **15 local Orbit distributions**; those Orbit
packages are not covered by this advisory scan. `uv pip check` confirmed all **43 installed
distributions** have compatible dependencies. This is installed-environment evidence, not a
live-provider or hosted release scan. Release readiness remains **87/100**, and external release
gates remain open.

The plugin contract follow-up clarified that `setup(application)` is optional while metadata and
activation/deactivation hooks form the minimal `PluginContract`. A regression test verifies that a
lifecycle-only plugin can be registered and composed without a setup hook. The focused plugin suite
passed **23 tests**, and the full suite count above includes these regressions. Core rejects
coroutine setup hooks during registration and rejects awaitables returned by synchronous setup
callables during composition, closing native coroutines and cancelling returned asyncio futures
or tasks rather than silently dropping setup work. Registry composition is explicitly one-shot: a
second `setup()` call fails before rerunning hooks, even if an earlier hook raised after possibly
making partial changes. GZip middleware also skips `206 Partial Content` responses so its body
transformation cannot contradict byte-range and `Content-Range` semantics. The ASGI response
contract now also prohibits content in `205 Reset Content`, and compression cannot turn its empty
body into a gzip payload. The remote admin client now treats only 2xx responses as success;
redirect and cache statuses are reported through the structured error boundary rather than being
mistaken for completed operations. Bulkhead admission now occurs before circuit evaluation when
both are composed; capacity timeouts raise `BulkheadFullError`, classify as resource failures, and
do not trip the provider circuit or retry by default. An already-expired `Deadline.scope()` now
raises before entering a synchronous operation, preventing work from starting after its budget.

## Optional cache capability and Redis adapter on 2026-10-04

The sibling `orbit-cache` package now defines a provider-neutral async contract for byte values,
non-empty string keys, explicit seconds-based TTLs, normalized errors, cancellation propagation,
and resource shutdown. It has no runtime dependencies and does not depend on Core. The sibling
`orbit-redis` package implements that contract with redis-py, bounded connection settings, redacted
configuration/errors, and explicit client cleanup. Its opt-in `RedisCachePlugin` registers the
capability in the Core container under the published dependency key and closes the client through
the Core plugin lifecycle. Neither package is bundled into Core; the plugin does not connect to
Redis until the first operation.

The combined capability and adapter suites passed **22 tests on each of Python 3.11, 3.12, 3.13,
and 3.14** using local editable package installs. Ruff, formatting, and strict mypy passed on
Python 3.13 and 3.14; suite validation on 3.11 and 3.12 also passed. Both wheels then installed into
a clean Python 3.11 environment and all **22 tests passed against those installed artifacts**;
module-origin checks confirmed imports came from site-packages. A separate capability-only
installation confirmed `orbit-cache` installs without Core or Redis. Tests cover plugin/container
composition and cleanup, no-server operation using a fake provider, TTL and byte semantics,
argument validation, credential redaction, cancellation, closed-client behavior, and Redis client
factory options. The following standalone Redis smoke does not prove compatibility with every
Redis server/provider version. In addition, the installed adapter wheel completed local
round-trip, binary-value, delete, TTL-expiration, and async-close smoke checks against a temporary
Redis 8.0.1 server, which was stopped after verification. This is one local standalone-server
version, not a production topology or broad Redis compatibility matrix. The Core release-readiness
score remains **87/100** and the separate external release gates remain open; this ecosystem work
does not increase the Core stabilization score.

## SQL provider plugin bridge on 2026-10-04

The `orbit-sql` capability now exports `SQL_DATABASE_KEY` as the shared dependency-injection key
for a `SQLDatabase`. `orbit-sql-postgres` adds an optional `PostgresPlugin` that registers a lazy
resource factory under that key. It performs no connection work during plugin setup, opens its pool
on first asynchronous resolution, and relies on Core's container cleanup to drain the pool during
application shutdown. The existing explicit `SQLAdapterRegistry` path remains available. The
change is limited to the existing sibling package repositories; Core's database API, default
SQLite implementation, and runtime dependencies are unchanged.

The expanded PostgreSQL adapter suite passed **22 tests on each of Python 3.11, 3.12, 3.13, and
3.14**; `orbit-sql` passed **12 tests per interpreter**. Ruff and strict mypy passed for both source
packages on Python 3.11. Their current data, SQL, and PostgreSQL wheels were built and installed
together with Core in a clean Python 3.11 environment; the installed SQL suite passed **12 tests**
and the installed PostgreSQL suite passed **22 tests**, including lazy pool acquisition, SQL
contract resolution, and Core-owned shutdown. The fake asyncpg pool tests do not establish
connectivity or compatibility with a live PostgreSQL deployment. The Core release-readiness score
remains **87/100**; external gates remain open.

## Optional dependency-boundary regression on 2026-10-04

The Core packaging-boundary tests now enumerate the full requested Orbit package catalog, not just
the packages already checked out locally, when checking that Core has no optional Orbit runtime
dependencies. They also parse Core's Python source and reject direct imports from the current
provider-SDK denylist, while retaining the wheel-package allowlist that limits the Core artifact to
`src/orbit`. The focused boundary suite passed **3 tests**, and its Ruff lint/format checks passed.
This is a static import guard rather than proof against dynamic imports or every future SDK name.

The scan found no current provider SDK imports in Core. The test-only ASGI harness has now moved to
the separately installable `orbit-testing` workspace; its contract tests moved with it, and Core
tests and existing gateway, Prometheus, and security package tests now import `orbit_testing`.
Core's ASGI exports now include the `Headers`, message, and request-limit contracts required by the
external test utility, without exposing Core's private limits module. The Core wheel remains
limited to `orbit`; the complete post-extraction test evidence is recorded below. Core release
readiness remains **87/100**; this boundary change adds no scorecard points.

## Combined Core and local plugin-wheel verification on 2026-10-04

All twelve existing sibling package wheels plus the current Core wheel were installed together in a
fresh Python 3.11 environment with no Orbit editable installs. The 12 installed-package suites
passed **212 tests** in total; module-origin checks confirmed each of the 13 top-level Orbit
packages came from `site-packages`, and `uv pip check` found no conflicts among the **38** installed
distributions.
Core's full suite then passed in that same environment with **1,055 passed and 2 opt-in host tests
skipped**. The tests were launched from the Core repository root so its documented `examples.*`
targets were available; `orbit.__file__` still resolved to the installed Core wheel. The separate
real-process Uvicorn/Gunicorn worker suite passed **2 tests** in the same environment. Together the
local package and Core runs account for **1,267 passed tests**, plus the 2 intentionally skipped
host tests, and the additional 2 opt-in host tests passed separately. This is Python 3.11 local
wheel-composition evidence only; it is not hosted CI, a live PostgreSQL deployment, production
load validation, or release provenance.

## Post-extraction Core and ecosystem verification on 2026-10-04

After extracting the in-process ASGI test client to the separate `orbit-testing` repository, Core's
full suite passed **1,027 tests with two opt-in host tests skipped** on Python 3.11, 3.12, 3.13, and
3.14. The `orbit-testing` contract suite passed **29 tests** on all four versions. The two opt-in
Gunicorn/Uvicorn worker-process tests passed on each version as well. Core, `orbit-testing`, and
`orbit-security` wheels were rebuilt; a clean Python 3.11 environment installed the current Core,
test utility, and 13 other checked-out optional package wheels. All 14 optional package suites
passed **246 tests**, and Core passed its 1,027-test suite in that environment. Together, the Core
and optional-package suites total **1,273 passing tests**. Core's SQLite suite now also exercises
cancellation during an in-flight worker operation, proving the transaction rolls back before its
serialization lock is released to another task. `uv pip check` reported no conflicts
among 43 installed distributions, and import-origin checks confirmed the
Orbit packages came from installed distributions rather than editable worktrees. This is local
wheel-composition evidence, not hosted CI, live provider interoperability, or deployment/load
validation.

Ruff, Ruff formatting, strict Core mypy, documentation, scorecard, workflow-policy, model-boundary,
license-header, wheel-integrity, lockfile, and `git diff --check` validations passed after the
final documentation/workflow edits. The `orbit-testing` GitHub repository does not yet have a
confirmed remote; hosted CI checkout cannot be validated until the user creates and publishes that
repository on `main`. Core's release-readiness score remains **87/100**; external gates remain open.

## Latest Core and package-documentation revalidation on 2026-10-04

After adding a regression test that enforces the sibling `orbit-testing` checkout in CI/release
workflows, the complete Core suite passed **1,028 tests with two opt-in hosting tests skipped** on
Python 3.11, 3.12, 3.13, and 3.14. The full `tox -p auto` matrix also passed its lint and strict
mypy environments. Current isolated coverage is 91.6534% on 3.11, 91.6733% on 3.12, 91.6932% on
3.13, and 91.6683% on 3.14. The run exposed and fixed a tox install-order issue: tox now installs
the local Core and sibling test utility together, rather than trying to resolve the unpublished
Core dependency from the package index. Repository documentation, workflow, license, scorecard,
and diff checks passed. The combined optional-package wheel count above remains the earlier
verified run and was not repeated for this workflow-only regression.

A follow-up static audit covered the 14 currently checked-out optional package workspaces. Ruff
lint and format checks pass for every package; strict mypy passes for all 14 after making the
provider libraries declared by `orbit-jwt` and `orbit-redis` available in the shared disposable
Python 3.14 environment. This found and fixed one import-order issue in `orbit-prometheus` tests.
Then all 14 package test suites passed against their current workspace source trees in that
environment: **246 tests passed**. Core was the installed tox package; optional package imports
were resolved from local source paths, so this is not a fresh all-wheels origin check. The earlier
combined-wheel evidence above remains separate.

## Current Python 3.14 wheel-composition validation on 2026-10-04

Built fresh wheels for Core and all 14 checked-out optional packages into an isolated wheelhouse,
then installed all 15 Orbit distributions into a newly created Python 3.14 environment alongside
their third-party runtime/test dependencies. Import-origin checks for all 15 top-level Orbit
modules resolved to that environment's `site-packages`, and `uv pip check` found no conflicts among
45 installed distributions. Running the Core suite and each sibling package suite in that one
environment produced **1,274 passed, 2 skipped** (Core 1,028 passed; optional packages 246 passed).
The two skips are opt-in real hosting tests, not package failures. This validates the local wheel
composition and provider-neutral package contracts; it does not test live Redis/PostgreSQL services,
hosted CI, production deployment, or release provenance.

All 14 checked-out optional package repositories have a root README referenced by their
distribution metadata. The `orbit-cache` and `orbit-metrics` READMEs now explain their contracts,
installation, usage, lifecycle/encoding responsibilities, and layered adapter boundaries; the
`orbit-security` README explicitly distinguishes its rate-limit middleware from Core Basic Auth and
optional identity integrations. Core's architecture guide records that package documentation is
owned alongside each implementation. These package suites pass locally: 2 cache, 1 metrics, and 3
security tests.
OpenAPI generation and the default `/openapi.json` endpoint remain in Core by maintainer decision;
ADR 0014 records that `orbit-docs`, if created, is optional and may add documentation presentation
or integrations without replacing Core's route contract. ADR 0015 records the current security
boundary: Core retains opt-in Basic Auth, `orbit-security` currently provides optional
provider-neutral rate-limit policy, and concrete identity integrations remain separate adapters.
ADR 0016 clarifies that the requested `orbit-sec` basic/professional variants are planned
optional additions above Core, but are not implemented and their package split remains undecided.
The `orbit-security` package suite passed 3 tests after its README was aligned with this boundary.
Its wheel now advertises the provider-neutral security-policy scope in package metadata and embeds
the README; wheel build, Ruff, strict package mypy, and all 3 tests pass. Release readiness remains
**87/100**;
local stabilization checkpoints remain **7/7**, while external release gates remain **0/4**.

The ownership audit found that an earlier ADR incorrectly rejected the requested basic/professional
`orbit-sec` variants. ADR 0016 now preserves the user-requested direction without claiming that
the current rate-limit package implements either variant or choosing an unapproved distribution
layout. Core's built-in Basic Auth and provider-neutral contracts remain the baseline; advanced
identity integrations stay optional. The Core and `orbit-security` package guides now state the
same current implementation status, and the cross-workspace documentation/link check passes.

## Security package direction updated on 2026-10-05

The security package decision has since been clarified: keep Core's built-in security baseline and
use one optional `orbit-security` package; do not create separate Basic and Professional security
variants. ADR 0017 supersedes the undecided variant proposal in ADR 0016. The Core ownership and
security guides and the `orbit-security` README now reflect this direction. The optional package's
implemented scope remains request-level rate limiting; this documentation change does not imply a
complete security suite.

To close this pass over the 14 existing local packages, reran every package's source tests in its
own repository context. All **247 tests passed on each supported Python version (3.11–3.14)**.
Running `orbit-sql` from the Core directory initially failed collection because its example import
requires the package root on the module path; rerunning in the package context passed all 13 SQL
tests on all four interpreters. The current documentation/link policy also passes across Core and
all checked-out sibling workspaces. The older all-package wheel run recorded 246 package tests and
predates this latest source suite count. No package was created, committed, or pushed in this pass.

As a fresh cross-version source check, all 14 checked-out optional package suites passed on Python
3.11, 3.12, 3.13, and 3.14 (**246 tests per interpreter**). The runs import the current sibling
`src` trees plus Core source; they verify package behavior and compatibility, not published wheels
or live provider services.

Core's packaging-boundary regression now builds a wheel from the current source into pytest's
temporary directory and inspects the produced archive, requiring exactly the `orbit/` import tree
plus its single `.dist-info` metadata root. This replaces the earlier manifest-only test as direct
evidence that optional sibling implementations are absent from the Core artifact. The updated
Core suite passes **1,036 tests and 2 opt-in host tests skipped** on Python 3.11–3.14; Ruff,
documentation/link, workflow, scorecard, model-boundary, license, and strict mypy gates pass.

The Admin Basic Auth integration test now uses the documented `Runtime(..., authenticator=...)`
composition path instead of constructing `ASGIApplication` directly. It verifies anonymous HTTPS
access receives the configured challenge and a credential with explicit Admin roles is accepted.

A fresh installed-wheel composition used wheels built from the current Core and all 14 sibling
workspaces. The Core wheel and source archive passed `check-package.py`; archive inspection showed
each wheel contains only its own top-level Orbit import package, and all 15 imports resolved from
the installed wheel target. Core's wheel-backed suite passed **1,036 tests with 2 opt-in host tests
skipped**, and the 14 optional package wheel-backed suites passed **246 tests**. In the all-package
environment, `pip check` reported no broken requirements. This validates local artifact composition,
not live Redis/PostgreSQL providers or deployment behavior.

`orbit-sql` now owns a runnable Notes API example composing Core's SQLite resource/lifecycle, the
`orbit-data` repository protocol, and `orbit-sql`'s SQL repository. The package README documents
installation, Uvicorn startup, and local requests; it clearly labels the sample's in-memory default
and lack of authentication/migrations as development-only. Its ASGI/TestClient integration test
covers schema startup, POST/GET persistence, and resource shutdown. The complete SQL package suite
passes **13 tests** on Python 3.11–3.14; Ruff, format, and strict package mypy checks also pass.

## Optional package development-extra matrix on 2026-10-04

Created clean Python 3.11, 3.12, 3.13, and 3.14 environments, then installed Core and all 14
checked-out optional packages as editable local projects with every package's own `dev` extra.
Dependency checks passed in all four environments. The `orbit-gateway`, `orbit-security`, and
`orbit-prometheus` test suites import the separate `orbit-testing` utility; their manifests now
declare it only under the `dev` extra, and their READMEs document the local workspace setup. A clean
install of those extras and their required local capability packages succeeded. This keeps the test
harness out of runtime dependency sets while making a package's declared development setup complete.

Each package suite was run separately from its own repository to avoid pytest module-name clashes
between repositories that contain identically named test files. All 14 suites passed **246 tests
per interpreter** on Python 3.11, 3.12, 3.13, and 3.14 (984 passing test executions in total), with
`pip check` clean for every environment. Separately, Ruff lint, Ruff format, and strict mypy passed
for all 14 package workspaces in the fresh development environment. An AST audit found and fixed
three undocumented methods on Orbit SQL's internal executor protocol; every checked-out package's
source modules and public declarations now have docstrings, and each package README passes Ruff
format checking. This is editable-workspace compatibility evidence, distinct from the Python 3.14
wheel-composition run above; it does not certify hosted CI, live providers, or deployment behavior.

## Current all-version wheel-composition matrix on 2026-10-04

Rebuilt a fresh wheelhouse from the current Core and all 14 checked-out optional package trees.
Installed those 15 Orbit wheels into clean Python 3.11, 3.12, 3.13, and 3.14 environments, including
Core's `dev` and `server` extras and every optional package's `dev` extra. This covers the ASGI host
dependencies exercised by Core's CLI tests while preserving the separate optional-package
boundaries. Each environment passed `pip check`, and import-origin assertions confirmed all 15
Orbit top-level modules came from `site-packages`, not the source worktrees.

In each environment, the Core suite passed **1,028 tests**, with two opt-in real-host tests skipped;
the 14 package suites, run separately from their repositories, passed **246 tests**. Thus the wheel
matrix records **1,274 passed and 2 expected skips per Python version** (5,096 passed and 8 skips
across the four environments). The real Uvicorn/Gunicorn process tests have separate passing tox
evidence for all four versions. These are locally built wheels and local interpreter runs, not
hosted CI, live Redis/PostgreSQL interoperability, production deployment validation, or release
provenance.

Built source distributions for the same 15 projects as well. Archive inspection confirmed that
each source distribution contains its package's import module, `README.md`, `LICENSE`, and
`pyproject.toml`, with no sibling Orbit package source included. This provides package-owned
documentation and licensing in both binary and source release artifacts; it is a local packaging
check, not a publication or signature/provenance check. Then rebuilt a wheel from each source
archive; all 15 builds succeeded, and wheel inspection confirmed the package files and embedded
README match the direct wheel build byte-for-byte.

An OSV-backed `pip-audit` scan was also run in each installed wheel-matrix environment. Python
3.12–3.14 reported no known vulnerabilities. Python 3.11 initially reported an advisory for the
environment's otherwise-unrequired `setuptools 79.0.1`; this was test/build tooling in the
disposable `.tox` environment, not a declared Orbit runtime dependency. After upgrading that
environment to `setuptools 84.0.0`, the repeat audit reported no known vulnerabilities and
`pip check` remained clean. The PyPI-backed audit endpoint was unreliable during this run, so the
recorded result uses OSV; this local dependency scan does not replace hosted security scanning of
the release commit or certify Orbit code against vulnerabilities not represented in the advisory
database.

## Package documentation consistency update on 2026-10-04

Reviewed the 14 optional package workspaces currently checked out beside Core. Their package-owned
`README.md` files now state the pre-alpha/API stability status, Python 3.11–3.14 support, local
development and test commands, and Apache-2.0 licensing. Existing usage examples and package
boundary guidance were retained. Each package README is included in its own source distribution;
none of these workspaces is bundled into the Core distribution.

Validation against the current package source trees passed Ruff and all **246 package tests**
across the 14 workspaces. The Core lint target also passed documentation, local-link, workflow,
scorecard, model-boundary, and license-header checks; `git diff --check` was clean. These are local
workspace checks, not published-package or hosted CI evidence. Fresh wheels and source distributions
were built for Core and all 14 package workspaces. For every project, the wheel's embedded long
description and the source archive's root `README.md` matched the current package README byte for
byte.

## Core install-boundary smoke on 2026-10-04

Installed the newly built Core wheel into separate clean targets on Python 3.11, 3.12, 3.13, and
3.14, resolving only its base requirements. Each environment contained exactly 13 distributions:
Core, Pydantic, Typer, Rich, and their transitive dependencies. None contained optional Orbit
distributions, FastAPI, Uvicorn, Gunicorn, `uvicorn-worker`, or development tools. In each target,
isolated imports resolved to the installed wheel, and CLI, Basic Auth, and SQLite imports succeeded.
An in-memory SQLite create/insert/read/close smoke test passed on all four interpreters.

Installed the same wheel with its `server` extra into a separate clean Python 3.14 target. Uvicorn,
Gunicorn, and `uvicorn-worker` imported successfully, while FastAPI and development tools remained
absent. The separate four-version functional and real-worker test matrix remains the evidence for
hosted runtime behavior.

Installed the five current layered package chains from fresh wheels into additional isolated
targets: Core → cache contract → Redis, Core → data contracts → SQL capability → PostgreSQL adapter,
Core → metrics capability → Prometheus, Core → JWT verifier adapter, and Core → optional security
middleware. For each target, the installed Orbit distributions were exactly the expected chain and
the public package imports succeeded; unrelated Orbit packages, server extras, and development
tools were absent. These local composition checks do not imply that the remaining catalog packages
or live provider services are implemented. An OSV-backed `pip-audit --path` scan of each of those
five exact Python 3.14 installed targets reported no known vulnerabilities at scan time. This is
local advisory-database evidence, not hosted scanning or a guarantee about future disclosures.

## Core database and Admin security integration revalidation on 2026-10-04

The database guide described direct container ownership, but `SQLiteDatabase` did not yet implement
the async context-manager protocol required by Core's `register_resource`. Added `__aenter__` and
`__aexit__`, retaining lazy connection creation and delegating teardown to `aclose`. A regression
resolves the public `SQLDatabase` contract through a container, exercises the resource, closes the
container, then confirms the database rejects later operations with `database.closed`. The database
suite passed **20 tests**. The Admin guide now demonstrates wiring environment-supplied Basic
credentials into `Runtime`; an integration regression checks anonymous challenge and authenticated
read-role access over HTTPS. Basic Auth verification now retains its concurrency permit until
already-running PBKDF2 work completes, even if its request task is cancelled repeatedly; a
thread-controlled regression verifies a second hash cannot start early. The database suite passed
**20 tests** and the Basic Auth suite passed **9 tests**. A follow-up regression then exposed that
concurrent SQLite `aclose()` callers could return before the first caller had finished closing the
connection. Close now has one shared cleanup task; concurrent callers await it, and cancellation
of a waiter is deferred until cleanup completes. A thread-controlled test verifies both properties.
The worker-operation drain also tolerates repeated cancellation; a transaction regression cancels
twice and verifies the next operation cannot interleave before worker completion. The SQLite suite
passes **21 tests**. The full Core suite passed **1,032 tests with two opt-in
hosting tests skipped** on each supported interpreter: Python 3.11, 3.12, 3.13, and 3.14. Tox
installs Core editably, and import-origin checks confirmed each tox environment runs the current
source tree rather than a stale installed copy. Ruff, strict mypy, documentation, model-boundary,
workflow, scorecard, and license-header checks also passed. The SQL baseline ADR and database usage
guide describe managed resource ownership and concurrent/cancellation-safe close behavior; the
security guide documents the Basic Auth cancellation bound. The two opt-in Uvicorn/Gunicorn
worker-process tests passed on each of Python 3.11, 3.12, 3.13, and 3.14. Actual reverse-proxy/load
and hosted-release evidence remain open.

## Hosting extra ownership on 2026-10-04

The CLI previously directed both Uvicorn development and Gunicorn production users to the same
`server` extra, unnecessarily installing Gunicorn and its worker for local-only hosting. Added a
`development-server` extra containing only Uvicorn; `server` remains the production combination of
Uvicorn, Gunicorn, and `uvicorn-worker`. The CLI now reports the selected extra, and manifest tests
pin the exact dependency sets. Updated the root README, CLI and development guides, and changelog.
The full Core suite passed
**1,034 tests with 2 opt-in hosting tests skipped** on each supported Python version (3.11–3.14),
and lock, lint, documentation, and strict typing checks passed. Production hosting is unchanged;
external proxy/load and hosted-release validation are still open.

## Core and package API documentation audit on 2026-10-04

An AST audit over Core and all 14 checked-out optional package source trees found one undocumented
public async handler: the Prometheus plugin's nested `/metrics` route function. Added a docstring
describing its runtime snapshot refresh and exposition response. A repeat audit found module
docstrings and public class/function/async-function docstrings across all 15 source trees, with no
remaining omissions. `orbit-prometheus` passed Ruff checks and all **8 package tests**. This audit
covers source docstrings; it does not substitute for review of examples, design explanations, or
API stability.

The automated documentation policy now follows that audit boundary: it checks module and public
callable docstrings, Python comment hygiene, Markdown structure, and local links in Core and every
checked-out sibling `orbit-*` workspace beside the Core repository. This keeps future package
changes from silently falling outside the documentation checks. The new discovery and public
docstring-policy regression tests pass (**3 passed**); the full Core matrix passed on Python
3.11–3.14 with **1,036 passed and 2 opt-in hosting tests skipped on each interpreter**, and strict
mypy plus the complete lint/documentation/license gate passed.

A cross-page architecture review found the overview and ADR 0006 diagrams blurred the capability
package and provider adapter into one layer, unlike the implemented SQL workspaces. Clarified the
extension direction versus package-dependency direction in the overview, ADR 0006, and plugin
authoring guide. The docs now show the concrete `orbit-core → orbit-data → orbit-sql →
orbit-sql-postgres → asyncpg` extension chain, SQLite-only and direct-plugin alternatives, and
the reverse dependency edges from adapters to their contracts.

## Evidence still required for a stable release

- Maintainers approve the first stable public-API baseline after compatibility review, record
  accepted exceptions or deprecations, and authorize a release version/tag.
- Hosted CI, CodeQL, and OpenSSF Scorecard runs are successful for public `main` commit
  `aaf49f27ad34eed130ebdcf13e5bec624fecfb5d` as of 2026-09-28, but those runs predate the current
  unpushed Core tree; rerun and review them after push, then verify repository protection and
  code-owner membership.
- The current CI and release workflows check out `orbit-projects/orbit-testing@main`, but that
  repository is not publicly accessible at the configured URL and the local sibling workspace has
  no remote. Make the separate package repository available to the workflow token, or provide its
  correct repository/access arrangement, before expecting hosted checks to start. Do not fold its
  test client back into Core to bypass this dependency.
- The active `main-protection` ruleset still has an empty required-status-check list, so the exact
  matrix contexts must be added after a successful pull request.
- The public release-workflow history has no runs; execute it and verify artifact upload, SBOM,
  checksums, Sigstore signing artifacts, and build-provenance attestations.
- Deployment-level testing against the selected host and actual proxy under representative load,
  slow clients, protocol fuzzing, upstream failure, cancellation, and worker termination. Existing
  process tests are smoke evidence; they do not verify a deployment's TLS/HTTP2 or proxy setup.
- Execute the protected release workflow and verify uploaded artifacts, SBOM, checksums, signing,
  build provenance, publication, and rollback evidence.

These gates do not require adding provider implementations to Core. Distributed persistence,
identity administration, telemetry exporters and hot package installation are not silently
substituted with in-memory implementations. Core provides the orchestration and extension
contracts; plugins and deployments select and validate the corresponding adapters.

## First remaining-catalog package: orbit-migrations (2026-10-05)

Started the next catalog item in its own local `orbit-migrations` workspace after closing the
14-package organization pass. The package provides a forward-only runner for explicit asynchronous
migration callbacks on Core's `SQLDatabase` contract. Each callback and its history write share a
transaction; unknown history fails closed; cancellation propagates through Core's rollback path.
The package adds no SQL driver, ORM, web framework, or Core dependency on an optional package.
Migrations are an explicit deployment step, and distributed locking and downgrades are clearly
outside its current scope.

Its six SQLite-backed tests pass on Python 3.11–3.14. Ruff, strict mypy against the current Core
source, the cross-workspace documentation gate, wheel/sdist builds, wheel-root inspection, and
verification of the wheel's `py.typed` marker and Apache license all pass. The Core scorecard
remains **87/100** and stable-release gates remain open; this package is pre-alpha and does not
claim live PostgreSQL migration validation. The local catalog now has 15 optional package
workspaces; the other catalog entries remain unimplemented until their own contracts and packages
are built.

## Next database adapter: orbit-mongo (2026-10-05)

Created a separate local `orbit-mongo` workspace implementing `orbit_data.Repository` with a typed
Pydantic model mapping and bounded `_id`-ordered reads. Its `MongoPlugin` lazily provides a
Core-managed Mongo database resource, validates and redacts the connection URI, checks readiness
when first resolved, and closes the async client through Core container cleanup. The adapter uses
PyMongo's native async API, consistent with [MongoDB's migration guidance](https://www.mongodb.com/docs/languages/python/pymongo-driver/current/reference/migration/);
Motor is not added. Duplicate keys map to `orbit_data.RepositoryConflictError`; provider and
document-validation failures avoid exposing URI, driver, or record details.

Five fake-driver tests pass on Python 3.11–3.14; they cover repository CRUD, aliases, error
redaction, config validation, plugin registration, and resource closure. Ruff, strict mypy, wheel
and sdist builds, wheel-backed tests, wheel-root/license/typing-marker inspection, and the
cross-workspace documentation gate pass. No live MongoDB service was available or tested, and
`orbit_data.UnitOfWork`/multi-operation Mongo transactions are not implemented. The catalog now
has 16 local optional package workspaces; 27 requested catalog packages remain unimplemented.
Core's readiness score remains **87/100**; external release gates remain open.

## Provider-neutral vector capability: orbit-vector (2026-10-05)

Added `orbit-vector` as its own optional workspace. It defines immutable Pydantic embedding, record,
query, and result values plus an async `VectorStore` protocol for upsert/get/search/delete. Embeddings
and scores reject non-finite values, search limits are bounded, and score records distinguish raw
similarity from distance without pretending providers share a common scale. It intentionally has no
embedding model, index/filter dialect, database driver, or vendor adapter; those remain separately
installable integrations. Core does not depend on this package.

Six tests pass on Python 3.11–3.14. Ruff, strict mypy, formatting, wheel/sdist builds, wheel-root
inspection, and installed-wheel tests pass. The cross-workspace documentation checker discovers its
README and public API docstrings. The local catalog now has 17 optional package workspaces; 26
requested catalog packages remain unimplemented. Core's readiness score remains **87/100** and the
stable-release gate remains open.

## Kafka event transport adapter: orbit-kafka (2026-10-05)

Added a separate optional `orbit-kafka` package implementing Core's typed `EventTransport` contract.
It maps event names to prefixed topics, serializes Core event envelopes as JSON, applies a bounded
encoded-message limit, lazily owns an aiokafka producer, and offers one consumer handler per event
name. Consumers disable auto-commit and commit only after handler completion; bounded retries leave
a failed record uncommitted, and sanitized diagnostics expose failed subscription IDs. The Core
plugin registers the transport and closes resources on shutdown. This is at-least-once, not
exactly-once, and no live Kafka broker test has been run. Core does not depend on aiokafka.

Five fake-client tests pass on Python 3.11–3.14. Ruff, strict mypy, formatting, wheel/sdist builds,
wheel-root/license/typing-marker inspection, and installed-wheel tests pass. Installed aiokafka
0.14.0 constructor and partition-seek signatures were checked. No live broker was available or tested.
The local catalog now has 18 optional package workspaces; 25 requested catalog packages remain
unimplemented. Core's readiness score remains **87/100** and the stable-release gate remains open.

## RabbitMQ event transport adapter: orbit-rabbitmq (2026-10-05)

Added `orbit-rabbitmq` as a separate optional aio-pika adapter for Core `EventTransport`. It uses a
durable topic exchange, durable per-event queues, publisher confirms, persistent JSON messages, and
manual acknowledgements after handler success. Bounded in-callback retries reject exhausted
deliveries without requeue; operators must configure a dead-letter exchange if rejected events need
to be retained. A Core plugin registers the transport and closes the robust connection at shutdown.
This adapter is at-least-once, not exactly-once, and does not create broker infrastructure or claim
live RabbitMQ validation.

Five fake-client tests pass on Python 3.11–3.14. Ruff, strict mypy, formatting, and cross-workspace
documentation checks pass. Wheel/sdist and installed-wheel checks remain pending. The local catalog
now has 19 optional package workspaces; 24 requested packages remain unimplemented. Core's
readiness score remains **87/100** and the stable-release gate remains open.

## NATS JetStream event transport adapter: orbit-nats (2026-10-05)

Added `orbit-nats` as a separate optional nats.py adapter for Core's `EventTransport`. It requires an
operator-provisioned JetStream stream, maps event names to concrete subjects, uses event IDs as
JetStream publish message IDs, and waits for JetStream publish acknowledgements. Durable push
consumers use explicit acknowledgements, bounded client-side pending buffers, bounded server-side
delivery attempts, delayed NAKs, synchronous handler-success acknowledgements, and terminal handling
after delivery exhaustion. TLS can be required and customized with an SSL context; token and
username/password authentication are validated and represented as secrets. Core owns client drain
and shutdown through the optional plugin. This is at-least-once; duplicate suppression depends on the
server's configured JetStream duplicate window, and there is no live NATS server test.

Five fake-client tests pass on Python 3.11–3.14. Ruff, strict mypy, formatting, cross-workspace
documentation checks, wheel/sdist builds, wheel-root/license/typing-marker inspection, and
installed-wheel tests pass. Installed nats.py 2.16.0 APIs for connect, JetStream publish/subscribe,
ack, NAK, and term were checked. No live NATS server was available or tested. The local catalog now
has 20 optional package workspaces; 23 requested packages remain unimplemented. Core's readiness
score remains **87/100** and the stable-release gate remains open.

## Typed event capability: orbit-events (2026-10-05)

Added a separate `orbit-events` capability package with Pydantic-backed event definitions, explicit
positive schema versions, duplicate-name protection in an event catalog, and a client facade over
Core's `EventTransport`. Publishing validates and JSON-serializes payloads into Core event envelopes;
subscribers require an exact schema-version match and receive validated typed payloads. The client
does not own or close the transport, leaving shutdown with the selected broker adapter's Core
plugin. Core keeps its event envelope, in-process bus/store, transport contract, and lifecycle. This
does not add a competing bus, schema registry, schema migration mechanism, or exactly-once guarantee.

Four fake-transport tests pass on Python 3.11–3.14. Ruff, strict mypy, formatting, and wheel/sdist
build checks pass. The package's public README documents the Core/capability/adapter boundary and
explicit delivery/schema limits. The workspace then contained 21 optional package repositories; 22
requested catalog packages remain unimplemented (the separate Prometheus and PostgreSQL adapter
repositories are additional to the requested catalog). Core's readiness score remains **87/100**
and the stable-release gate remains open.

## Object storage capability: orbit-storage (2026-10-05)

Added `orbit-storage` as a standalone capability package with a typed async `ObjectStore` protocol,
bounded object metadata and listing pagination, opaque key validation, normalized error types, and a
shared container dependency key for adapters. It has no Core or provider-SDK dependency. `orbit-s3`,
`orbit-gcs`, and `orbit-azure-storage` remain separate and are not implemented by this work. The
README documents adapter ownership, lifecycle, and provider-specific consistency, encryption,
versioning, and conditional-write limits.

Five contract tests cover key and metadata validation, immutable-but-serializable metadata,
closeable streamed downloads, and bounded pagination. Ruff, formatting, strict mypy, tests on Python
3.11–3.14, sdist/wheel builds, and installed-wheel tests pass. The workspace now contains 22 package
repositories; 21 of the 41 requested catalog packages remain unimplemented. Core's readiness score
remains **87/100** and the stable-release gate remains open.

## S3 object storage adapter: orbit-s3 (2026-10-05)

Added a separate `orbit-s3` adapter for `orbit-storage` using aiobotocore. It lazily owns an async
S3 client, follows the SDK credential chain, maps normalized object metadata and ListObjectsV2
continuation tokens, streams downloads with explicit close behavior, and sends async uploads as
sequential bounded multipart parts. Failed or cancelled multipart operations attempt an abort;
provider error strings are sanitized. The Core plugin registers the adapter using the shared storage
dependency key and closes the client at shutdown. Custom endpoint HTTP requires an explicit
development-only opt-in. Default streamed upload capacity is bounded by part size times part count;
it does not claim S3's full maximum object size. No live AWS or S3-compatible service was available
or tested.

Six fake-client tests cover configuration, CRUD, streaming/multipart behavior, pagination, error
redaction, and Core lifecycle ownership. Ruff, formatting, strict mypy, tests on Python 3.11–3.14,
wheel/sdist builds, and installed-wheel tests pass. The workspace contains 23
package repositories; 20 of the 41 requested catalog packages remain unimplemented. Core's
readiness score remains **87/100** and the stable-release gate remains open.

## Cross-workspace validation on 2026-10-05

The Projects directory currently contains 23 separate optional package workspaces (the earlier
“14 workspaces” count in this log refers to an older checkpoint). In one isolated Python 3.11
environment, all 23 editable distributions and their declared development extras installed together
alongside the current Core checkout. Running each repository's test suite independently passed
**294 package tests**. Ruff lint, Ruff format checks, and strict mypy passed for every package. The
`orbit-sql` example test was run with its repository root explicitly on `PYTHONPATH`, as required
for its local example module. These runs used fake provider clients and did not contact live
database, broker, cache, or object-storage services.

The current Core source then passed **1,037 tests, with 2 opt-in process-host tests skipped**, on
Python 3.11. Ruff lint and formatting passed for source, tests, scripts, and examples; strict mypy
passed for 111 source files; documentation/link checks, license-header checks, and scorecard
validation passed. Core readiness remains **87/100**. The four-interpreter Core evidence and the
earlier 20-package matrix remain recorded above; this latest combined 23-package run was on Python
3.11 only. Of 41 catalog names, 21 currently have a local implementation package (including the
two additional `orbit-prometheus` and `orbit-sql-postgres` workspaces), leaving 20 not yet created.
The single optional security package remains `orbit-security`; Core retains its built-in Basic Auth
and security baseline. No Basic/Professional security variants were created.

## Google Cloud Storage adapter: orbit-gcs (2026-10-05)

Created `orbit-gcs` as a separate provider adapter over the existing `orbit-storage` capability.
It owns gcloud-aio, optional service-account-file configuration, provider error normalization, and
an opt-in Core plugin that registers the shared object-store key and closes the SDK client. Byte
uploads and async streams are accepted; streams are buffered only up to a configurable per-upload
ceiling and the adapter limits concurrent uploads to bound aggregate memory. Downloads remain
streamed, are explicitly closeable, and include the GCS generation precondition from the metadata
request so a concurrent replacement fails rather than returning mixed-version data. gcloud-aio
documents the async stream API and managed client lifecycle ([API reference](https://talkiq.github.io/gcloud-aio/autoapi/storage/index.html)); the generation condition follows [Cloud Storage request preconditions](https://cloud.google.com/storage/docs/request-preconditions). No live project or emulator was available or tested.

Seven fake-client tests pass on Python 3.11. Ruff, formatting, and strict mypy pass. Fresh wheel and
source distributions build; the wheel includes its Apache license and `py.typed`, and all seven
tests pass against the installed `orbit-gcs` and `orbit-storage` wheels in the isolated validation
environment. The local workspace now contains 24 optional package repositories. Of the 41
requested catalog packages, 22 are represented locally (the separate Prometheus and PostgreSQL
adapter repos are extra to that catalog), leaving 19 not yet implemented. Core remains **87/100**
on the separate release-readiness scorecard; stable release gates remain open.

## Azure Blob Storage adapter: orbit-azure-storage (2026-10-05)

Created `orbit-azure-storage` as a separate provider adapter over `orbit-storage`. It uses the
Azure async Blob SDK and `DefaultAzureCredential`, keeping Azure identity, endpoint and container
configuration, and SDK resource cleanup outside Core. Async iterable uploads pass through the
provider's block-transfer support with configurable block size and bounded transfer concurrency;
download reads are ETag-conditional so metadata and bytes cannot silently cross object versions.
Only local HTTP emulator endpoints are accepted when the explicit insecure-HTTP option is enabled.
The official [Azure async SDK guide](https://learn.microsoft.com/en-us/azure/storage/blobs/storage-blob-python-get-started)
and [async API reference](https://learn.microsoft.com/en-us/python/api/azure-storage-blob/azure.storage.blob.aio?view=azure-python)
document the asynchronous client lifecycle, uploads, listings, and chunked downloads. No live Azure
account or Azurite test was available or run.

Eight tests pass on Python 3.11, including a no-network construction/close smoke test using the real
SDK client with an injected test credential. Ruff, formatting, and strict mypy pass. The Core
documentation gate, including public protocol-method docstrings in this adapter, passes. Fresh wheel
and source distributions build; installed-wheel tests pass, `pip check` is clean, and the wheel
contains the Apache license and `py.typed`. The Projects directory now contains 25 sibling package
repositories. Of 41 requested catalog packages, 23 are represented locally (the Prometheus and
PostgreSQL adapter repos are additional catalog-external workspaces), leaving 18 not yet created.
Core remains **87/100** on the separate release-readiness scorecard; hosted, live-provider, and
deployment gates remain open.

## Current sibling-package regression sweep (2026-10-05)

Re-ran every checked-out `orbit-*` workspace in the shared Python 3.11 validation environment.
All **25 package suites passed (309 tests)**, together with Ruff, formatting, strict mypy, and
`git diff --check`. The first sweep exposed that the `orbit-sql` example test could not import its
repository-owned `examples` package under a plain `pytest` invocation. Its pytest configuration now
adds the repository root and `src` to the test import path, so the documented development command
works without a task-specific `PYTHONPATH`. The rerun passed all 13 SQL package tests and checks.
This is local fake-client/SQLite evidence only; it does not represent live cloud, broker, or database
provider validation, nor hosted CI or release approval.

## Fresh wheel composition and hosting-extra smoke (2026-10-05)

Built Core and all 25 checked-out sibling packages as wheels, then installed all **26 Orbit
distributions** together into a fresh Python 3.11 virtual environment. The dependency resolver
completed successfully, `pip check` reported no broken requirements, and import-origin checks
confirmed every Orbit package loaded from that environment's `site-packages`, not a source checkout.
Installing Core's `development-server` and `server` extras resolved Uvicorn, Gunicorn, and
`uvicorn-worker`; both server version commands and the worker-module import succeeded. This confirms
package metadata and local wheel composition only. It is not an end-to-end production deployment or
live-provider test.

## Current Core source and host-process revalidation (2026-10-05)

The current Core source suite passed on Python 3.11: **1,037 passed and 2 opt-in hosting tests
skipped** in the default run. Running `tests/integration/test_gunicorn_host.py` with
`ORBIT_RUN_HOSTING_TESTS=1` then passed both real-process tests: direct Uvicorn development serving
and graceful Gunicorn shutdown/reload with two Uvicorn workers. Ruff, formatting, strict mypy,
license-header checks, and the Core documentation/boundary tests passed on this candidate. This is
local host-process evidence, not a substitute for deployment behind the selected production proxy,
representative external load, hosted CI, or release provenance. Core's release-readiness score
remains **87/100**.

## OpenTelemetry tracing adapter: orbit-tracing (2026-10-05)

Implemented `orbit-tracing` as a separate optional package over Core's `Tracer` contract. It owns
an isolated OpenTelemetry SDK provider, bounded batch processing, exporter lifecycle, and optional
OTLP HTTP/gRPC dependencies. An opt-in outer ASGI wrapper extracts bounded W3C `traceparent` and
`tracestate` context before Core creates its request span; applications may explicitly inject
context into their own outbound request headers. It does not install automatic client
instrumentation or change OpenTelemetry's global provider. Tests use the in-memory exporter and do
not contact a collector or live telemetry backend.

All seven package tests pass against both the source checkout and freshly installed wheel. Ruff,
formatting, and strict mypy pass; wheel and source distributions build; the isolated install with
both OTLP extras passes `pip check`, and import-origin checks resolve Core, testing, and tracing
from `site-packages`. Core documentation, license-header, and package-boundary checks pass with the
updated ownership entry. No live collector or telemetry backend was exercised. The local workspace
now contains 26 sibling package repositories; 24 of the 41 requested catalog packages have a local
package (the additional Prometheus and PostgreSQL adapter workspaces are not in that catalog),
leaving 17 catalog entries without a local implementation. Core's separate release-readiness score
remains **87/100**; external CI, release provenance, live-provider, and target-environment
deployment gates remain outstanding.

## Pull-request CI dependency and locked audit remediation (2026-10-05)

Inspection of recent hosted PR runs showed all four Python matrix jobs failing on the second
`actions/checkout` step, before dependency installation or tests. That step requests the separate
`orbit-projects/orbit-testing` repository, which currently returns HTTP 404. The local sibling
workspace exists and the frozen Core environment resolves against it, but hosted CI cannot use it
until that repository is available at the configured public URL and `main` ref. Hosted PR CI is
therefore still an external blocker; local green checks are not represented as hosted CI success.

The same Core lockfile's audit environment resolved `urllib3 2.7.0` through the development-only
`pip-audit` dependency chain (`pip-audit → cachecontrol → requests`). `uv.lock` now pins `urllib3`
2.8.0, the fixed version reported by the audit feed. With that lock, a fresh frozen sync passes
`uv lock --check`, `pip-audit --skip-editable` reports no known vulnerabilities, and `pip check`
passes. Core's current Python 3.11 suite passes **1,037 tests at 91.70% coverage** (two opt-in
hosting tests skipped in the default run); the opt-in Uvicorn/Gunicorn host tests pass **2/2**.
Ruff, format, strict mypy, workflow/scorecard/model-boundary/documentation/license checks, wheel and
source builds, and package-integrity checks pass locally. These results do not substitute for the
unavailable hosted checkout or the other external release gates. The independent release-readiness
score remains **87/100** and its stable-release gate remains open.
