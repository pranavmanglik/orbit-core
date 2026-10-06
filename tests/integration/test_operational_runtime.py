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
"""Real ASGI lifespan, plugin composition and operational failure behavior."""

import asyncio
from contextlib import asynccontextmanager

from pydantic import BaseModel

from orbit import Application, ApplicationConfig
from orbit.asgi import ASGIApplication, Response
from orbit.container import Scope
from orbit.plugins import Plugin, PluginMetadata
from orbit.runtime.context import current_request_id
from tests.helpers.asgi_client import TestClient


async def test_plugin_routes_are_composed_before_runtime_freezes():
    class Extension(Plugin):
        metadata = PluginMetadata(name="orbit-routes", version="1.0.0")

        def setup(self, app):
            @app.router.route("/plugin", method="GET", name="plugin")
            async def route(request):
                return Response.text("plugin")

    app = Application(ApplicationConfig(name="plugin-runtime"))
    app.register_plugin(Extension())
    async with TestClient(ASGIApplication(app)) as client:
        assert (await client.request("GET", "/plugin")).body == b"plugin"


async def test_openapi_endpoint_exposes_composed_routes():
    app = Application(ApplicationConfig(name="openapi"))

    @app.router.route("/hello/{name}", method="GET", name="hello")
    async def hello(request):
        return Response.text(request.path_parameters["name"])

    async with TestClient(ASGIApplication(app)) as client:
        response = await client.request("GET", "/openapi.json")
    assert response.status == 200
    assert response.json()["paths"]["/hello/{name}"]["get"]["operationId"] == "hello"


async def test_metrics_endpoint_is_not_installed_by_core():
    app = Application(ApplicationConfig(name="metrics"))

    @app.router.route("/", name="root")
    async def root(request):
        return Response.text("ok")

    async with TestClient(ASGIApplication(app)) as client:
        response = await client.request("GET", "/metrics")
    assert response.status == 404


async def test_route_models_validate_request_and_response():
    class Input(BaseModel):
        value: int

    class Output(BaseModel):
        doubled: int

    app = Application(ApplicationConfig(name="validation"))

    @app.router.route(
        "/double", method="POST", name="double", request_model=Input, response_model=Output
    )
    async def double(request):
        return Response.json(Output(doubled=request.validated_body.value * 2))

    async with TestClient(ASGIApplication(app)) as client:
        valid = await client.request(
            "POST", "/double", body=b'{"value": 4}', headers={"content-type": "application/json"}
        )
        invalid = await client.request(
            "POST",
            "/double",
            body=b'{"value": "bad"}',
            headers={"content-type": "application/json"},
        )
    assert valid.status == 200 and valid.json() == {"doubled": 8}
    assert invalid.status == 422


async def test_route_middleware_wraps_only_selected_route():
    calls = []

    async def middleware(request, next_handler):
        calls.append("before")
        response = await next_handler(request)
        calls.append("after")
        return response

    app = Application(ApplicationConfig(name="route-middleware"))

    @app.router.route("/selected", name="selected", middleware=(middleware,))
    async def selected(request):
        calls.append("handler")
        return Response.text("selected")

    @app.router.route("/plain", name="plain")
    async def plain(request):
        return Response.text("plain")

    async with TestClient(ASGIApplication(app)) as client:
        await client.request("GET", "/selected")
        await client.request("GET", "/plain")
    assert calls == ["before", "handler", "after"]


async def test_overload_has_correlation_and_is_counted():
    app = Application(ApplicationConfig(name="overload", max_concurrent_requests=1))
    entered, release = asyncio.Event(), asyncio.Event()

    @app.router.route("/", method="GET", name="root")
    async def route(request):
        entered.set()
        await release.wait()
        return Response.text("ok")

    async with TestClient(ASGIApplication(app)) as client:
        first = asyncio.create_task(client.request("GET", "/"))
        await entered.wait()
        overloaded = await client.request("GET", "/")
        assert overloaded.status == 503
        assert overloaded.headers["x-request-id"]
        release.set()
        await first
        snapshot = app.diagnostics.collect(app)
        assert snapshot.request_count == 2
        assert snapshot.error_count == 1
        assert snapshot.status_counts == {503: 1, 200: 1}


async def test_concurrent_admission_reuses_capacity_and_closes_failed_scopes():
    """Bounded admission must preserve cleanup when accepted work fails concurrently."""
    app = Application(ApplicationConfig(name="concurrent-cleanup", max_concurrent_requests=2))
    entered = asyncio.Event()
    release = asyncio.Event()
    started = 0
    active = 0
    closed = 0

    @asynccontextmanager
    async def request_resource(container):
        nonlocal active, closed
        active += 1
        try:
            yield object()
        finally:
            active -= 1
            closed += 1

    app.container.register_resource("request", request_resource, scope=Scope.SCOPED)

    @app.router.route("/work", method="GET", name="work")
    async def work(request):
        nonlocal started
        started += 1
        sequence = started
        await request.container.aresolve("request")
        if sequence == 2:
            entered.set()
        await release.wait()
        if sequence == 2:
            raise RuntimeError("synthetic handler failure")
        return Response.text(str(sequence))

    async with TestClient(ASGIApplication(app)) as client:
        first = asyncio.create_task(client.request("GET", "/work"))
        second = asyncio.create_task(client.request("GET", "/work"))
        await entered.wait()

        rejected = await client.request("GET", "/work")
        assert rejected.status == 503
        assert active == 2

        release.set()
        successful, failed = await asyncio.gather(first, second)
        assert successful.status == 200
        assert failed.status == 500
        assert active == 0
        assert closed == 2

        reusable = await client.request("GET", "/work")
        assert reusable.status == 200

    assert active == 0
    assert closed == 3


async def test_request_context_is_isolated():
    app = Application(ApplicationConfig(name="correlation"))

    @app.router.route("/", method="GET", name="root")
    async def route(request):
        await asyncio.sleep(0)
        request_id = current_request_id()
        assert request_id == request.request_id
        return Response.json({"request_id": str(request_id)})

    async with TestClient(ASGIApplication(app)) as client:
        first, second = await asyncio.gather(client.request("GET", "/"), client.request("GET", "/"))
        assert first.json()["request_id"] != second.json()["request_id"]
    assert current_request_id() is None


async def test_error_response_disconnect_does_not_escape_runtime():
    app = Application(ApplicationConfig(name="disconnect-error"))

    async def receive():
        return {"type": "http.request", "body": b""}

    async def send(message):
        raise OSError("disconnected")

    async with app.running():
        await ASGIApplication(app)(
            {
                "type": "http",
                "method": "GET",
                "path": "/",
                "headers": [(b"content-length", b"invalid")],
            },
            receive,
            send,
        )
    assert app.diagnostics.collect(app).recent_requests[-1].outcome == "disconnected"


async def test_oversized_content_length_is_client_error():
    app = Application(ApplicationConfig(name="length"))
    async with TestClient(ASGIApplication(app)) as client:
        response = await client.request("GET", "/", headers={"content-length": "9" * 5000})
        assert response.status == 413
