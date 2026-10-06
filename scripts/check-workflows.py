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
"""Validate the repository's GitHub Actions supply-chain conventions."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_ROOT = ROOT / ".github" / "workflows"
JOB_HEADER = re.compile(r"^  ([A-Za-z0-9_-]+):\s*$")
PINNED_ACTION = re.compile(r"^\s*(?:-\s+)?uses:\s+([^@\s]+)@([0-9a-f]{40})\s+#\s+v\S+\s*$")
CHECKOUT_STEP = re.compile(r"^(\s*)-\s+uses:\s+actions/checkout@")
PERSIST_CREDENTIALS_FALSE = re.compile(r"^\s+persist-credentials:\s*false\s*$")


def workflow_files() -> list[Path]:
    """Return maintained GitHub Actions workflow files in deterministic order."""
    return sorted(WORKFLOW_ROOT.glob("*.yml"))


def job_ranges(lines: list[str]) -> list[tuple[str, int, int]]:
    """Return the line ranges belonging to each top-level job in a workflow."""
    jobs_line = next((index for index, line in enumerate(lines) if line.strip() == "jobs:"), None)
    if jobs_line is None:
        return []
    headers = [
        (match.group(1), index)
        for index, line in enumerate(lines[jobs_line + 1 :], jobs_line + 1)
        if (match := JOB_HEADER.match(line)) is not None
    ]
    return [
        (name, start, headers[index + 1][1] if index + 1 < len(headers) else len(lines))
        for index, (name, start) in enumerate(headers)
    ]


def errors_for(path: Path) -> list[str]:
    """Return workflow policy violations for one file."""
    lines = path.read_text(encoding="utf-8").splitlines()
    errors: list[str] = []
    if not any(line.startswith("permissions:") for line in lines):
        errors.append(f"{path}: workflow must declare explicit top-level permissions")
    else:
        permissions_index = next(
            index for index, line in enumerate(lines) if line.startswith("permissions:")
        )
        inline_permissions = lines[permissions_index].partition(":")[2]
        if re.search(r""":\s*["']?write["']?\s*[,}]""", inline_permissions):
            errors.append(
                f"{path}:{permissions_index + 1}: workflow-level write permissions must be "
                "scoped to individual jobs"
            )
        for line_number, line in enumerate(lines[permissions_index + 1 :], permissions_index + 2):
            if line.strip() and not line.startswith(" "):
                break
            if re.fullmatch(r"  [A-Za-z0-9_-]+:\s*write\s*", line):
                errors.append(
                    f"{path}:{line_number}: write permissions must be scoped to individual jobs"
                )

    for line_number, line in enumerate(lines, 1):
        if "uses:" not in line:
            if line.strip() == "write-all" or re.match(r"^\s*permissions:\s*write-all\s*$", line):
                errors.append(f"{path}:{line_number}: broad write-all permissions are forbidden")
            continue
        if PINNED_ACTION.fullmatch(line) is None:
            errors.append(
                f"{path}:{line_number}: actions must use a 40-character SHA and version comment"
            )

        checkout = CHECKOUT_STEP.match(line)
        if checkout is not None:
            step_indent = len(checkout.group(1))
            step_lines: list[str] = []
            for following_line in lines[line_number:]:
                if len(following_line) - len(
                    following_line.lstrip()
                ) == step_indent and following_line.lstrip().startswith("-"):
                    break
                step_lines.append(following_line)
            if not any(PERSIST_CREDENTIALS_FALSE.fullmatch(step_line) for step_line in step_lines):
                errors.append(f"{path}:{line_number}: checkout must set persist-credentials: false")

    for name, start, end in job_ranges(lines):
        block = lines[start:end]
        if not any(line.strip().startswith("runs-on:") for line in block):
            continue
        if not any(line.strip().startswith("timeout-minutes:") for line in block):
            errors.append(f"{path}:{start + 1}: job {name!r} has no timeout-minutes")

    if path.name in {"ci.yml", "release.yml"} and any("orbit-testing" in line for line in lines):
        errors.append(
            f"{path}: Core CI and release must not depend on a separate orbit-testing checkout"
        )

    if path.name == "ci.yml":
        text = "\n".join(lines)
        if "fail-fast: false" not in text:
            errors.append(f"{path}: the Python matrix must set fail-fast: false")
        if re.search(r"^\s+path: (?:[^\s]*/)?coverage\.xml\s*$", text, re.MULTILINE) is None:
            errors.append(f"{path}: the quality job must retain coverage.xml")
    if path.name == "release.yml":
        text = "\n".join(lines)
        required_release_markers = {
            "scripts/check-scorecard.py": "release validation must verify the fixed scorecard",
            "scripts/check-release.py": "release validation must verify checksums and the SBOM",
            "dependencies.cdx.json": "release validation must generate a CycloneDX SBOM",
            "actions/attest-build-provenance@": "release artifacts must receive build provenance",
            "actions/upload-artifact@": "release artifacts must be uploaded",
            "id-token: write": "release signing requires the OIDC identity permission",
            "attestations: write": "release provenance requires the attestation permission",
        }
        for marker, message in required_release_markers.items():
            if marker not in text:
                errors.append(f"{path}: {message}")
        if "! -name SHA256SUMS" not in text:
            errors.append(f"{path}: checksum generation must exclude SHA256SUMS")
        if "sha256sum dist/* > dist/SHA256SUMS" in text:
            errors.append(f"{path}: checksum generation must not hash dist/* including itself")
        if "sigstore/gh-action-sigstore-python@" not in text:
            errors.append(f"{path}: release artifacts must receive Sigstore signatures")
        if "inputs: dist/*" not in text:
            errors.append(f"{path}: Sigstore must sign the complete dist artifact set")
    return errors


def main() -> int:
    """Validate least-privilege permissions, checkout credentials, pins, timeouts, and releases."""
    errors = [error for path in workflow_files() for error in errors_for(path)]
    if errors:
        print("GitHub Actions workflow policy violations:", file=sys.stderr)
        print("\n".join(f"  {error}" for error in errors), file=sys.stderr)
        return 1
    print("Workflow checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
