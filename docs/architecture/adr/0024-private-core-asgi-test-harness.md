# Private ASGI harness for Core integration tests

- Status: Accepted
- Date: 2026-10-05

## Context

Core's integration tests used the separately installable `orbit-testing` package. That made the
Core test workflow depend on a sibling checkout that was unavailable to hosted GitHub Actions, and
created a development dependency cycle: the test utility depends on Core's public ASGI contracts,
while Core's tests depended on the utility.

Core needs direct protocol-level integration coverage without adding another runtime framework or
making its own testability depend on a separately released package.

## Decision

Core's integration tests use a small private ASGI harness in `tests/helpers/asgi_client.py`. It
implements only the request/response and lifespan behavior needed by Core's tests, with bounded
response capture and protocol validation. It is not exported from `orbit`, not included in the Core
wheel, and is not a supported application API.

The independently installable `orbit-testing` package remains available for plugin and application
authors who want reusable test utilities. Core CI and release workflows must not check it out or
install it.

## Consequences

- Core tests and release checks can install and run from the Core repository alone.
- Core owns a small amount of test-only protocol code, which is isolated under `tests/helpers` and
  covered by Core integration tests.
- The reusable `orbit-testing` package continues to be tested and released independently; it is
  not validated by Core's test workflow.
- The implementation does not add a web framework, socket server, or production dependency.

## Evidence

- `tests/helpers/asgi_client.py`
- `tests/integration/test_admin_extensions.py`
- `tests/integration/test_http_runtime.py`
- `tests/integration/test_operational_runtime.py`
- `tests/unit/test_workflow_policy.py`
