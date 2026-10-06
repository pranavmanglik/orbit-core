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
"""Cross-process tests for the optional gRPC process-plugin host."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest
from google.protobuf.wrappers_pb2 import StringValue

pytest.importorskip("grpc")

from orbit.health.models import HealthStatus  # noqa: E402
from orbit.plugins.metadata import PluginMetadata  # noqa: E402
from orbit.plugins.process import ProcessPlugin  # noqa: E402
from orbit.plugins.registry import PluginRegistry  # noqa: E402

_ROOT = Path(__file__).resolve().parents[2]
_CHILD = _ROOT / "tests" / "helpers" / "process_plugin_child.py"


def _plugin(*, configuration_json: bytes = b"{}") -> ProcessPlugin:
    return ProcessPlugin(
        PluginMetadata(
            name="orbit-process-fixture",
            version="1.0.0",
            capabilities=frozenset({"test.echo"}),
        ),
        (sys.executable, str(_CHILD)),
        configuration_json=configuration_json,
        env={"PYTHONPATH": str(_ROOT / "src")},
        startup_timeout=5,
        command_timeout=2,
        shutdown_timeout=1,
    )


@pytest.mark.asyncio
async def test_process_plugin_lifecycle_health_and_typed_capability_call() -> None:
    plugin = _plugin(configuration_json=b'{"secret":"never expose"}')
    registry = PluginRegistry()
    registry.register(plugin)
    await registry.activate()
    process = plugin._process  # noqa: SLF001 - verify owned process is reaped after shutdown.
    try:
        health = await plugin.health()
        assert health.status is HealthStatus.HEALTHY
        assert health.message == "Plugin process is healthy."
        assert "secret" not in (health.message or "")

        async def echo(value: str) -> str:
            response = StringValue()
            await plugin.invoke(
                "/orbit.test.v1.Echo/Call",
                StringValue(value=value),
                response,
            )
            return response.value

        assert await asyncio.gather(*(echo(str(index)) for index in range(8))) == [
            f"echo:{index}" for index in range(8)
        ]
    finally:
        await registry.deactivate()
    assert registry.active_names == ()
    assert process is not None and process.returncode is not None
    assert plugin._process is None  # noqa: SLF001 - assert process ownership was released.
    assert plugin._server is None  # noqa: SLF001 - assert listener ownership was released.


@pytest.mark.asyncio
async def test_process_plugin_sanitizes_child_failure_and_reaps_process() -> None:
    secret = "credential-never-leak"
    plugin = _plugin(configuration_json=(f'{{"fail_activate":true,"secret":"{secret}"}}').encode())
    with pytest.raises(Exception) as caught:
        await plugin.activate()
    assert secret not in str(caught.value)
    assert plugin._process is None  # noqa: SLF001 - activation rollback must reap the child.
    assert plugin._server is None  # noqa: SLF001 - activation rollback must close the listener.


def test_process_plugin_rejects_shell_strings_and_unbounded_configuration() -> None:
    metadata = PluginMetadata(name="orbit-process-fixture", version="1.0.0")
    with pytest.raises(TypeError):
        ProcessPlugin(metadata, "echo unsafe")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="absolute path"):
        ProcessPlugin(metadata, ("python", "worker.py"))
    with pytest.raises(ValueError, match="JSON object"):
        ProcessPlugin(metadata, (sys.executable, str(_CHILD)), configuration_json=b"[]")
    with pytest.raises(ValueError, match="1 MiB"):
        ProcessPlugin(
            metadata, (sys.executable, str(_CHILD)), configuration_json=b" " * (1024 * 1024 + 1)
        )


def test_process_plugin_repr_does_not_expose_arguments_or_configuration() -> None:
    plugin = _plugin(configuration_json=b'{"secret":"do-not-print"}')
    assert repr(plugin) == "ProcessPlugin(name='orbit-process-fixture', version='1.0.0')"
