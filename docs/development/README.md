# Development

Track stabilization work using the evidence-based local and external checkpoints in
[`stabilization.md`](stabilization.md). Keep these pass counts separate from the weighted stable
release gate in [`completion.md`](completion.md).

Orbit Core changes are changes to a public orchestration contract. Identify the owning boundary
before editing (application, container, plugin, adapter, ASGI, or observability), document lifecycle
and failure semantics, and keep provider SDKs in plugin packages.

Core's own ASGI integration tests use a private harness in `tests/helpers`, avoiding a cycle where
Core tests depend on an optional package that itself depends on Core. The independent
`orbit-testing` distribution remains available to plugin authors for reusable ASGI contract tests;
Core CI and release jobs do not check out that sibling repository.

Install the locked development environment and run the same checks as CI. It includes the
production `server` extra so the opt-in Gunicorn/Uvicorn worker tests can run. For ordinary local
development outside this full test environment, use `--extra development-server` to install only
Uvicorn.

```bash
uv sync --frozen --extra dev --extra server --extra process-plugins
uv lock --check
uv run --no-sync ruff check src tests scripts examples
uv run --no-sync ruff format --check src tests scripts examples
uv run --no-sync mypy src/orbit
uv run --no-sync python scripts/check-workflows.py
uv run --no-sync python scripts/check-scorecard.py
uv run --no-sync python scripts/check-model-boundaries.py
uv run --no-sync pytest --cov=orbit --cov-report=term-missing
uv run --no-sync python scripts/check-documentation.py
uv run --no-sync python scripts/check-license-headers.py
uv run --no-sync python scripts/generate-process-plugin-protocol.py
uv run --no-sync python -m build --no-isolation
uv run --no-sync python scripts/check-package.py dist
uv run --no-sync pip-audit --skip-editable --progress-spinner off
```

Run the managed hosting test when changing worker, signal, reload, or process-lifecycle behavior:

```bash
ORBIT_RUN_HOSTING_TESTS=1 uv run --no-sync pytest -q tests/integration/test_gunicorn_host.py
```

## Local release-candidate integrity

The pull-request gate verifies the source tree and distributable archives. A release candidate
also needs its generated dependency inventory and checksum manifest before the repository-owned
release-integrity checker can run. After the development gate and package build above, run:

```bash
uv run --no-sync pip-audit --skip-editable --format cyclonedx-json --output dist/dependencies.cdx.json
python -m json.tool dist/dependencies.cdx.json > /dev/null
find dist -maxdepth 1 -type f ! -name SHA256SUMS -print0 \
  | sort -z \
  | xargs -0 --no-run-if-empty sha256sum > dist/SHA256SUMS
sha256sum --check dist/SHA256SUMS
uv run --no-sync python scripts/check-release.py dist
```

This reproduces the local artifact portion of the release workflow. Sigstore signing, GitHub build
provenance, artifact upload, and their verification require the hosted workflow identity and
services; they cannot be established by a local command.

At the release decision, run `uv run --no-sync python scripts/check-scorecard.py
--require-stable`. It intentionally fails until the current score threshold *and* every mandatory
hosted and deployment gate has evidence recorded in the scorecard; a locally valid wheel is not a
release authorization.

`check-package.py` validates the built wheel and source archive before release artifacts are
attested. It checks safe paths and regular archive members, matching project/version filenames,
importable package files, the PEP 561 typing marker, license inclusion, and the metadata that
identifies the supported Orbit Core distribution.

The release workflow then runs `check-release.py` after generating `SHA256SUMS` and the CycloneDX
dependency inventory. That repository-owned check verifies that every direct release file is
covered exactly once, rejects unsafe paths, symlinked metadata, and duplicate entries, validates
digests and required distribution archives, and checks the SBOM shape before hosted signing runs.

The authoritative package version is `src/orbit/_version.py`; Hatchling reads that declaration for
distribution metadata, and the package checker compares built artifacts against the same source.
Do not update a second version field in `pyproject.toml` because the project intentionally uses a
single version source.

Concurrency regressions use synchronization events to establish races and bounded test
deadlines to detect deadlocks. Do not rely on large sleeps to make a race likely.

Every behavior change should include a focused regression test for cancellation, timeout, partial
startup, resource cleanup, concurrency, or redaction when those guarantees are affected. Run the
real hosting test when changing worker, signal, or reload behavior.

For plugin and application tests, install the separate `orbit-testing` distribution and use
`orbit_testing.TestClient` as an async context manager around a freshly composed application. It
owns real startup/shutdown messages, validates response framing, preserves repeated request
headers, applies Core's public request/header/path/query limits, and translates encoded paths as an
ASGI host would. Each client is single-use. `lifespan_timeout` bounds protocol waits; failures
surface immediately. Core itself uses its private test harness under `tests/helpers`.

See [operations](operations.md) for hosting and observability, [documentation conventions](documentation.md)
for source and Markdown standards, [public API stability](api-stability.md) for compatibility and
deprecation policy, and [completion criteria](completion.md) for release gates.
