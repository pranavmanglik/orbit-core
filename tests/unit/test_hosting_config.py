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
"""Tests for unified hosting configuration."""

import pytest
from pydantic import ValidationError

import orbit.runtime as runtime_module
from orbit import Application, ApplicationConfig
from orbit.asgi import ASGIApplication, Response
from orbit.runtime import HostingConfig, HostServer, Runtime


def test_hosting_config_validates_shared_worker_policy() -> None:
    config = HostingConfig(
        server=HostServer.GUNICORN,
        workers=4,
        graceful_timeout=45,
        worker_timeout=60,
        keep_alive=10,
        max_requests=1000,
        max_requests_jitter=100,
    )
    runtime = Runtime(Application(ApplicationConfig(name="hosting")), hosting=config)
    assert runtime.hosting.workers == 4
    assert runtime.hosting.server is HostServer.GUNICORN
    assert runtime.hosting.worker_timeout == 60
    assert runtime.hosting.max_requests_jitter == 100
    assert runtime.hosting.bind == "127.0.0.1:8000"
    with pytest.raises(ValidationError):
        HostingConfig(server="gunicorn", reload=True)
    with pytest.raises(ValidationError, match="multiple workers"):
        HostingConfig(server="uvicorn", reload=True, workers=2)
    with pytest.raises(ValidationError):
        HostingConfig(max_requests_jitter=1)
    with pytest.raises(ValidationError):
        HostingConfig(max_requests=10, max_requests_jitter=11)
    with pytest.raises(ValidationError, match="booleans"):
        HostingConfig(workers=True)
    with pytest.raises(ValidationError):
        HostingConfig(reload="true")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        HostingConfig(workers="4")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        HostingConfig(worker_timeout=30.0)  # type: ignore[arg-type]
    assert HostingConfig(max_requests=10).max_requests_jitter == 0
    assert HostingConfig(host="::1", port=9000).bind == "[::1]:9000"
    assert HostingConfig(host="[::1]", port=9000).bind == "[::1]:9000"
    with pytest.raises(ValidationError):
        HostingConfig(host="bad:host")
    with pytest.raises(ValidationError):
        HostingConfig(host="bad host")
    with pytest.raises(ValidationError):
        HostingConfig(host="bad\x7fhost")
    with pytest.raises(ValidationError):
        HostingConfig(host="[bad]")
    with pytest.raises(ValidationError, match="server"):
        HostingConfig(server=b"uvicorn")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        HostingConfig(host=b"127.0.0.1")  # type: ignore[arg-type]
    with pytest.raises(AttributeError):
        getattr(runtime_module, "missing_" + "runtime_symbol")


def test_runtime_info_rejects_untrusted_identity_and_counts() -> None:
    """Runtime inspection cannot expose malformed names or negative/coerced counts."""
    info = runtime_module.RuntimeInfo(application_name="contracts", phase="created")
    assert info.service_count == 0
    with pytest.raises(ValueError):
        runtime_module.RuntimeInfo(application_name="bad name", phase="created")
    with pytest.raises(ValueError):
        runtime_module.RuntimeInfo(application_name="contracts", phase="created", child_count=-1)
    with pytest.raises(ValueError):
        runtime_module.RuntimeInfo(application_name="contracts", phase="created", task_count="1")  # type: ignore[arg-type]


def test_runtime_and_asgi_boundaries_reject_invalid_constructor_objects() -> None:
    app = Application(ApplicationConfig(name="constructor-contracts"))
    with pytest.raises(TypeError, match="Application"):
        Runtime(object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="HostingConfig"):
        Runtime(app, hosting=object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="Router"):
        ASGIApplication(app, router=object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="Authenticator"):
        ASGIApplication(app, authenticator=object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="RouteAuthorizer"):
        ASGIApplication(app, authorizer=object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="Tracer"):
        ASGIApplication(app, tracer=object())  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_runtime_delegates_asgi_calls() -> None:
    app = Application(ApplicationConfig(name="runtime-call"))

    @app.router.route("/", name="root")
    async def root(request):
        return Response.text("ok")

    runtime = Runtime(app)
    messages = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(message)

    async with app.running():
        await runtime({"type": "http", "method": "GET", "path": "/", "headers": []}, receive, send)
    assert messages[0]["status"] == 200
