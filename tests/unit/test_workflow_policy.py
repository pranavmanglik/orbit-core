# Copyright 2026-present Orbit Contributors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Regression tests for the repository GitHub Actions policy checker."""

import importlib.util
from pathlib import Path


def _checker_module():
    path = Path(__file__).parents[2] / "scripts" / "check-workflows.py"
    spec = importlib.util.spec_from_file_location("orbit_check_workflows", path)
    if spec is None or spec.loader is None:
        raise AssertionError("Unable to load workflow checker.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_workflow_checker_accepts_pinned_timed_job(tmp_path: Path) -> None:
    workflow = tmp_path / "valid.yml"
    workflow.write_text(
        "\n".join(
            (
                "permissions:",
                "  contents: read",
                "jobs:",
                "  build:",
                "    runs-on: ubuntu-latest",
                "    timeout-minutes: 20",
                "    steps:",
                "      - uses: actions/checkout@0123456789abcdef0123456789abcdef01234567 # v4",
                "        with:",
                "          persist-credentials: false",
                "",
            )
        ),
        encoding="utf-8",
    )

    assert _checker_module().errors_for(workflow) == []


def test_workflow_checker_rejects_unpinned_action_and_missing_timeout(tmp_path: Path) -> None:
    workflow = tmp_path / "invalid.yml"
    workflow.write_text(
        "\n".join(
            (
                "jobs:",
                "  build:",
                "    runs-on: ubuntu-latest",
                "    steps:",
                "      - uses: actions/checkout@v4",
                "",
            )
        ),
        encoding="utf-8",
    )

    errors = _checker_module().errors_for(workflow)
    assert any("40-character SHA" in error for error in errors)
    assert any("timeout-minutes" in error for error in errors)
    assert any("explicit top-level permissions" in error for error in errors)


def test_workflow_checker_requires_version_comment_for_pinned_action(tmp_path: Path) -> None:
    """A raw commit hash must retain a human-readable action version for review."""
    workflow = tmp_path / "missing-version.yml"
    workflow.write_text(
        "\n".join(
            (
                "jobs:",
                "  build:",
                "    runs-on: ubuntu-latest",
                "    timeout-minutes: 20",
                "    steps:",
                "      - uses: actions/checkout@0123456789abcdef0123456789abcdef01234567",
                "",
            )
        ),
        encoding="utf-8",
    )

    errors = _checker_module().errors_for(workflow)
    assert any("version comment" in error for error in errors)


def test_workflow_checker_rejects_persisted_checkout_credentials_and_write_all(
    tmp_path: Path,
) -> None:
    workflow = tmp_path / "unsafe.yml"
    workflow.write_text(
        "\n".join(
            (
                "permissions:",
                "  write-all",
                "jobs:",
                "  build:",
                "    runs-on: ubuntu-latest",
                "    timeout-minutes: 20",
                "    steps:",
                "      - uses: actions/checkout@0123456789abcdef0123456789abcdef01234567 # v4",
                "        with:",
                "          persist-credentials: true",
                "",
            )
        ),
        encoding="utf-8",
    )

    errors = _checker_module().errors_for(workflow)
    assert any("write-all permissions are forbidden" in error for error in errors)
    assert any("persist-credentials: false" in error for error in errors)


def test_workflow_checker_requires_write_permissions_to_be_job_scoped(tmp_path: Path) -> None:
    workflow = tmp_path / "broad-write.yml"
    workflow.write_text(
        "\n".join(
            (
                "permissions:",
                "  contents: read",
                "  security-events: write",
                "jobs:",
                "  analyze:",
                "    runs-on: ubuntu-latest",
                "    timeout-minutes: 20",
                "",
            )
        ),
        encoding="utf-8",
    )

    errors = _checker_module().errors_for(workflow)
    assert any("write permissions must be scoped to individual jobs" in error for error in errors)


def test_workflow_checker_rejects_inline_workflow_level_write_permission(tmp_path: Path) -> None:
    workflow = tmp_path / "inline-write.yml"
    workflow.write_text(
        "\n".join(
            (
                'permissions: { contents: read, security-events: "write" }',
                "jobs:",
                "  analyze:",
                "    runs-on: ubuntu-latest",
                "    timeout-minutes: 20",
                "",
            )
        ),
        encoding="utf-8",
    )

    errors = _checker_module().errors_for(workflow)
    assert any("workflow-level write permissions" in error for error in errors)


def test_core_workflows_reject_the_sibling_orbit_testing_checkout(tmp_path: Path) -> None:
    """Keep Core test and release workflows independent of a downstream test package."""
    workflow = tmp_path / "ci.yml"
    workflow.write_text(
        "\n".join(
            (
                "permissions:",
                "  contents: read",
                "jobs:",
                "  test:",
                "    runs-on: ubuntu-latest",
                "    timeout-minutes: 20",
                "    steps:",
                "      - uses: actions/checkout@0123456789abcdef0123456789abcdef01234567 # v4",
                "        with:",
                "          persist-credentials: false",
                "          repository: orbit-projects/orbit-testing",
                "          path: orbit-testing",
                "      - run: pytest",
                "      - uses: actions/upload-artifact@"
                "0123456789abcdef0123456789abcdef01234567 # v4",
                "        with:",
                "          path: coverage.xml",
                "",
            )
        ),
        encoding="utf-8",
    )

    errors = _checker_module().errors_for(workflow)
    assert any("must not depend" in error for error in errors)


def test_workflow_checker_requires_release_signing_and_complete_inputs(tmp_path: Path) -> None:
    """Release policy requires Sigstore coverage for every generated artifact."""
    workflow = tmp_path / "release.yml"
    workflow.write_text(
        "\n".join(
            (
                "jobs:",
                "  build:",
                "    runs-on: ubuntu-latest",
                "    timeout-minutes: 20",
                "    steps:",
                "      - run: echo release",
                "",
            )
        ),
        encoding="utf-8",
    )

    errors = _checker_module().errors_for(workflow)
    assert any("Sigstore signatures" in error for error in errors)
    assert any("complete dist artifact set" in error for error in errors)
    assert any("fixed scorecard" in error for error in errors)
    assert any("checksums and the SBOM" in error for error in errors)
    assert any("CycloneDX SBOM" in error for error in errors)
    assert any("build provenance" in error for error in errors)
    assert any("uploaded" in error for error in errors)
