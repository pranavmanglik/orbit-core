# Contributing to Orbit Core

Thank you for contributing. Orbit Core is a contract-driven orchestration library, so changes are
reviewed for API clarity, lifecycle behavior, failure semantics, and compatibility with the
architecture documented in `docs/`.

## Before you change code

Read the [architecture overview](docs/architecture/overview.md), the relevant concept guide, and
any applicable [architecture decision record](docs/architecture/adr/README.md). Establish which
boundary owns the change before implementing it:

- Core owns orchestration rules and provider-neutral contracts.
- Capability adapters define reusable integration contracts.
- Provider plugins own SDKs, credentials, network clients, and vendor-specific behavior.

Repository protection and CI expectations are documented in the
[repository governance guide](docs/development/repository-governance.md). Public compatibility
and deprecation expectations are documented in the [API stability policy](docs/development/api-stability.md).
Changes to branch
protection, required checks, or release evidence should be reviewed as supply-chain changes.

Do not add a provider SDK to Core or introduce a second lifecycle, state, or hosting abstraction.
If a change establishes or revises an architectural convention, include an ADR.

## Development environment

Orbit supports Python 3.11 through 3.14. Core's development dependency group uses the separately
maintained `orbit-testing` package through the sibling path `../orbit-testing`; check out both
repositories side by side before syncing. The test package is not a runtime dependency and is not
bundled into the Core wheel. Hosted CI checks it out into the same sibling path. Then use the
committed lockfile:

```bash
python -m pip install uv==0.12.23
uv sync --frozen --extra dev --extra server
uv lock --check
```

Run the complete local gate before submitting a pull request:

```bash
uv run --no-sync ruff check src tests scripts examples
uv run --no-sync ruff format --check src tests scripts examples
uv run --no-sync mypy src/orbit
uv run --no-sync python scripts/check-workflows.py
uv run --no-sync python scripts/check-scorecard.py
uv run --no-sync python scripts/check-model-boundaries.py
uv run --no-sync pytest --cov=orbit
uv run --no-sync python scripts/check-documentation.py
uv run --no-sync python scripts/check-license-headers.py
uv run --no-sync python -m build --no-isolation
uv run --no-sync python scripts/check-package.py dist
uv run --no-sync pip-audit --skip-editable --progress-spinner off
```

`check-scorecard.py` keeps the published stable-release assessment tied to explicit, reviewable
evidence. It is a validation check, not a substitute for the hosted release gates. For a release
candidate, also follow the artifact-integrity procedure in the
[development guide](docs/development/README.md#local-release-candidate-integrity).

The same documentation, license, model-boundary, and formatting checks are available through the
repository's local pre-commit hooks.

The real Gunicorn/Uvicorn process test is opt-in because it starts worker processes:

```bash
ORBIT_RUN_HOSTING_TESTS=1 uv run --no-sync pytest -q tests/integration/test_gunicorn_host.py
```

## Change requirements

Every behavior change should include a focused regression test. Cover cancellation, timeout,
partial startup, cleanup, concurrency, redaction, or protocol framing when the change affects
those guarantees. Update the relevant guide, README, changelog, or ADR when a public contract,
operator behavior, or architectural decision changes.

Public classes, functions, and methods must have precise type annotations and docstrings. Module
docstrings should state the module's responsibility and boundary. Comments should explain an
invariant, ownership rule, or non-obvious compatibility constraint; do not narrate the syntax.
Avoid credentials, request bodies, exception messages, and provider values in documentation,
diagnostics, logs, and examples.

Each Python file must retain the repository's full Apache-2.0 header. Keep formatting, imports,
local links, and Markdown structure compatible with the repository checks.

## Pull requests

Describe the behavior and the owning boundary in the pull request summary. Include validation
commands and call out any unverified deployment, security, or multi-process assumptions. Keep
commits focused and do not include generated environments, coverage artifacts, credentials, or
unrelated formatting churn.
