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
"""Core enforces the bounded stable AdminContribution inspection contract."""

import asyncio

import pytest
from pydantic import BaseModel

from orbit import Application, ApplicationConfig


@pytest.mark.parametrize(
    "contribution",
    [object(), type("MissingInspect", (), {"name": "bad"})()],
)
def test_admin_registration_rejects_invalid_contracts(contribution) -> None:
    """Invalid extensions fail during composition instead of leaking attribute errors."""
    app = Application(ApplicationConfig(name="admin-contract"))
    with pytest.raises(TypeError, match="Admin contribution"):
        app.register_admin(contribution)  # type: ignore[arg-type]


async def test_concurrent_extension_inspections_do_not_duplicate_provider_work() -> None:
    """Concurrent admin requests fail closed instead of replacing one inspection task."""
    started = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    class View(BaseModel):
        status: str

    class Extension:
        name = "backend"

        async def inspect(self):
            nonlocal calls
            calls += 1
            started.set()
            if release.is_set():
                return View(status="recovered")
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                await release.wait()
                return View(status="recovered")

    app = Application(ApplicationConfig(name="admin-concurrent", health_timeout=0.01))
    extension = Extension()
    app.register_admin(extension)
    first = asyncio.create_task(app.inspect_admin_contribution("backend"))
    await started.wait()
    second = asyncio.create_task(app.inspect_admin_contribution("backend"))

    assert await asyncio.gather(first, second) == [None, None]
    assert calls == 1
    release.set()
    for _ in range(20):
        await asyncio.sleep(0)
        if not app._detached_admin_inspections:  # noqa: SLF001 - wait for test-owned cleanup.
            break
    assert not app._detached_admin_inspections  # noqa: SLF001 - verify one late task retired.
    recovered = await app.inspect_admin_contribution("backend")
    assert isinstance(recovered, View)


async def test_completed_extension_inspection_is_reused_before_owner_retires(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A completed inspection cannot be replaced during its first waiter's completion gap."""
    import orbit.application.application as application_module

    original_wait = asyncio.wait
    owner_paused = asyncio.Event()
    allow_owner = asyncio.Event()
    first_wait = True
    calls = 0

    async def wait_with_completion_gap(tasks, *, timeout):
        nonlocal first_wait
        done, pending = await original_wait(tasks, timeout=timeout)
        if first_wait:
            first_wait = False
            owner_paused.set()
            await allow_owner.wait()
        return done, pending

    monkeypatch.setattr(application_module.asyncio, "wait", wait_with_completion_gap)

    class View(BaseModel):
        status: str

    class Extension:
        name = "backend"

        async def inspect(self):
            nonlocal calls
            calls += 1
            return View(status="ready")

    app = Application(ApplicationConfig(name="admin-completion-gap"))
    extension = Extension()
    app.register_admin(extension)
    first = asyncio.create_task(app.inspect_admin_contribution("backend"))
    await owner_paused.wait()
    second = asyncio.create_task(app.inspect_admin_contribution("backend"))
    await asyncio.sleep(0)
    allow_owner.set()

    first_view, second_view = await asyncio.gather(first, second)
    assert calls == 1
    assert isinstance(first_view, View)
    assert isinstance(second_view, View)


async def test_application_cleanup_retires_running_extension_inspection() -> None:
    """Application cleanup transfers active extension work into detached ownership."""
    started = asyncio.Event()
    release = asyncio.Event()
    finished = asyncio.Event()

    class View(BaseModel):
        status: str

    class Extension:
        name = "backend"

        async def inspect(self):
            started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                await release.wait()
                finished.set()
                return View(status="closed")

    app = Application(ApplicationConfig(name="admin-cleanup"))
    extension = Extension()
    app.register_admin(extension)
    inspection = asyncio.create_task(app.inspect_admin_contribution("backend"))
    await started.wait()
    app._cancel_pending_admin_inspections()  # noqa: SLF001 - exercise shutdown ownership.
    assert app._detached_admin_inspections  # noqa: SLF001 - verify transferred ownership.
    release.set()
    assert isinstance(await inspection, View)
    await asyncio.wait_for(finished.wait(), timeout=0.1)
    assert not app._running_admin_inspections  # noqa: SLF001 - verify active task retirement.
    assert not app._detached_admin_inspections  # noqa: SLF001 - verify detached cleanup.
