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
"""Guard the separately installable capability and provider package boundary."""

from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path
from zipfile import ZipFile

_ROOT = Path(__file__).resolve().parents[2]
_OPTIONAL_ORBIT_PACKAGES = {
    "orbit-data",
    "orbit-sql",
    "orbit-sql-postgres",
    "orbit-nosql-mongo",
    "orbit-cache-redis",
    "orbit-vector",
    "orbit-migrations",
    "orbit-events",
    "orbit-events-kafka",
    "orbit-events-rabbitmq",
    "orbit-events-nats",
    "orbit-streams",
    "orbit-cloud",
    "orbit-cloud-aws",
    "orbit-cloud-gcp",
    "orbit-cloud-azure",
    "orbit-kubernetes",
    "orbit-discovery",
    "orbit-gateway",
    "orbit-config-server",
    "orbit-security",
    "orbit-auth-oauth2",
    "orbit-auth-jwt",
    "orbit-auth-rbac",
    "orbit-observability",
    "orbit-logging",
    "orbit-metrics",
    "orbit-metrics-prometheus",
    "orbit-tracing",
    "orbit-health",
    "orbit-cache",
    "orbit-scheduler",
    "orbit-workers",
    "orbit-resilience",
    "orbit-lock",
    "orbit-storage",
    "orbit-storage-s3",
    "orbit-storage-gcs",
    "orbit-storage-azure",
    "orbit-testing",
    "orbit-devtools",
    "orbit-graphql",
    "orbit-realtime",
    "orbit-email",
    "orbit-notifications",
    "orbit-search",
    "orbit-admin",
}
_WEB_FRAMEWORK_DISTRIBUTIONS = {"fastapi", "litestar", "starlette"}
_PROCESS_HOST_IMPORTS = {
    Path("src/orbit/plugins/process.py"): {"grpc", "google"},
    Path("src/orbit/plugins/v1/process_plugin_pb2.py"): {"google"},
    Path("src/orbit/plugins/v1/process_plugin_pb2_grpc.py"): {"grpc"},
}
_PROVIDER_IMPORT_ROOTS = {
    "aioboto3",
    "aiobotocore",
    "aiohttp",
    "aiokafka",
    "aiomysql",
    "aiosqlite",
    "aio_pika",
    "aiosmtplib",
    "apscheduler",
    "arq",
    "asyncpg",
    "authlib",
    "azure",
    "boto3",
    "botocore",
    "celery",
    "chromadb",
    "confluent_kafka",
    "docker",
    "dramatiq",
    "elasticsearch",
    "google",
    "graphql",
    "grpc",
    "httpx",
    "jwt",
    "kafka",
    "keycloak",
    "kubernetes",
    "motor",
    "nats",
    "opensearchpy",
    "opentelemetry",
    "pika",
    "pinecone",
    "psycopg",
    "pymongo",
    "prometheus_client",
    "qdrant_client",
    "redis",
    "requests",
    "requests_oauthlib",
    "sentry_sdk",
    "sendgrid",
    "sqlalchemy",
    "strawberry",
    "structlog",
    "temporalio",
    "weaviate",
    "websockets",
    "fastapi",
    "litestar",
    "starlette",
}


def _distribution_name(requirement: str) -> str:
    """Extract and normalize a distribution name from a PEP 508 requirement string."""
    match = re.match(r"\s*([A-Za-z0-9_.-]+)", requirement)
    assert match is not None, f"Invalid dependency declaration: {requirement!r}"
    return re.sub(r"[-_.]+", "-", match.group(1)).lower()


def test_core_does_not_depend_on_optional_capability_or_provider_packages() -> None:
    """Core excludes optional packages and external web frameworks from every install extra."""
    with (_ROOT / "pyproject.toml").open("rb") as manifest_file:
        manifest = tomllib.load(manifest_file)

    project = manifest["project"]
    declared = list(project.get("dependencies", []))
    for requirements in project.get("optional-dependencies", {}).values():
        declared.extend(requirements)

    bundled = _OPTIONAL_ORBIT_PACKAGES.intersection(
        _distribution_name(requirement) for requirement in declared
    )
    assert not bundled, f"Optional Orbit packages must not be Core dependencies: {sorted(bundled)}"
    frameworks = _WEB_FRAMEWORK_DISTRIBUTIONS.intersection(
        _distribution_name(requirement) for requirement in declared
    )
    assert not frameworks, f"Orbit owns its ASGI framework boundary: {sorted(frameworks)}"


def test_host_extras_keep_development_and_production_dependencies_distinct() -> None:
    """Local Uvicorn use stays light while managed production includes Gunicorn workers."""
    with (_ROOT / "pyproject.toml").open("rb") as manifest_file:
        manifest = tomllib.load(manifest_file)

    extras = manifest["project"]["optional-dependencies"]
    development = {_distribution_name(requirement) for requirement in extras["development-server"]}
    production = {_distribution_name(requirement) for requirement in extras["server"]}

    assert development == {"uvicorn"}
    assert production == {"gunicorn", "uvicorn", "uvicorn-worker"}


def test_requested_orbit_catalog_is_documented_with_current_boundary_status() -> None:
    """Every requested optional distribution has an explicit current ownership entry."""
    ownership = (_ROOT / "docs" / "architecture" / "core-and-plugin-ownership.md").read_text(
        encoding="utf-8"
    )
    status_rows = [line for line in ownership.splitlines() if line.startswith("|")]
    documented = {name for row in status_rows for name in re.findall(r"`(orbit-[a-z0-9-]+)`", row)}
    missing = sorted(_OPTIONAL_ORBIT_PACKAGES - documented)
    assert not missing, f"Requested Orbit packages are missing ownership status: {missing}"


def test_built_core_wheel_contains_only_the_core_python_package(tmp_path: Path) -> None:
    """The artifact installed by users must not bundle sibling package implementations."""
    with (_ROOT / "pyproject.toml").open("rb") as manifest_file:
        manifest = tomllib.load(manifest_file)

    packages = manifest["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"]
    assert packages == ["src/orbit"]

    subprocess.run(
        [
            sys.executable,
            "-m",
            "build",
            "--wheel",
            "--no-isolation",
            "--outdir",
            str(tmp_path),
            str(_ROOT),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    wheels = list(tmp_path.glob("*.whl"))
    assert len(wheels) == 1
    with ZipFile(wheels[0]) as wheel:
        roots = {
            member.split("/", maxsplit=1)[0]
            for member in wheel.namelist()
            if not member.endswith("/")
        }
    metadata_roots = {name for name in roots if name.endswith(".dist-info")}
    assert roots == {"orbit"} | metadata_roots
    assert len(metadata_roots) == 1


def test_core_sources_do_not_import_provider_sdks() -> None:
    """Provider SDKs and competing web frameworks must not enter the Core source boundary."""
    source_root = _ROOT / "src" / "orbit"
    violations: list[tuple[str, str]] = []
    for source in sorted(source_root.rglob("*.py")):
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported = (alias.name.split(".", maxsplit=1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                imported = iter((node.module.split(".", maxsplit=1)[0],))
            else:
                continue
            violations.extend(
                (str(source.relative_to(_ROOT)), module)
                for module in imported
                if module in _PROVIDER_IMPORT_ROOTS
                and module not in _PROCESS_HOST_IMPORTS.get(source.relative_to(_ROOT), set())
            )

    assert not violations, (
        f"Provider SDK and web-framework imports must remain outside Core: {violations}"
    )


def test_base_core_import_does_not_load_optional_process_plugin_dependencies() -> None:
    """Installing Core without the process extra keeps gRPC out of ordinary startup imports."""
    code = (
        "import sys; import orbit; "
        "assert 'grpc' not in sys.modules; "
        "assert 'google.protobuf' not in sys.modules"
    )
    subprocess.run(
        [sys.executable, "-c", code],
        cwd=_ROOT,
        env={**os.environ, "PYTHONPATH": str(_ROOT / "src")},
        check=True,
        capture_output=True,
        text=True,
    )
