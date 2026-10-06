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
"""ASGI framing, middleware, authentication, readiness and resource integration."""

import asyncio
from contextlib import asynccontextmanager

import pytest
from pydantic import BaseModel, SecretStr

from orbit import Application, ApplicationConfig, Service, ServiceDescriptor
from orbit.asgi import ASGIApplication, Response
from orbit.asgi.request import Headers, HTTPError, Request
from orbit.container import Scope
from orbit.diagnostics import InMemoryTracer
from orbit.health import HealthReport, HealthStatus
from tests.helpers.asgi_client import TestClient
from tests.helpers.auth_value import AuthTestIdentity, AuthTestPrincipal


def compose(**config):
    app = Application(ApplicationConfig(name="http-tests", **config))
    return app, ASGIApplication(app)


def test_raw_path_validation_rejects_encoded_traversal_bytes() -> None:
    with pytest.raises(HTTPError, match="canonical"):
        ASGIApplication._validate_raw_path(b"/users/%2e%2e/private")
    for raw_path in (
        b"relative",
        b"/users/%2",
        b"/users/%zz",
        b"/users/%2fprivate",
        b"/users/%5cprivate",
        b"/users/%3fprivate",
        b"/users/%23private",
        b"/users/%01private",
        b"/users//private",
    ):
        with pytest.raises(HTTPError, match="canonical"):
            ASGIApplication._validate_raw_path(raw_path)


@pytest.mark.parametrize("raw_path", [b"/file%2Etxt", b"/v1/%C3%A9", b"/items/42"])
def test_raw_path_validation_preserves_safe_encoded_segments(raw_path: bytes) -> None:
    """Encoded ordinary characters remain valid while routing boundaries stay protected."""
    ASGIApplication._validate_raw_path(raw_path)


@pytest.mark.parametrize("raw_path", [b"/invalid/\xff", b"/invalid/%FF"])
def test_raw_path_validation_rejects_invalid_utf8(raw_path: bytes) -> None:
    with pytest.raises(HTTPError, match="canonical"):
        ASGIApplication._validate_raw_path(raw_path)


async def test_raw_path_must_match_decoded_scope_path() -> None:
    app, asgi = compose()
    async with app.running():
        messages = []

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            messages.append(message)

        await asgi(
            {
                "type": "http",
                "method": "GET",
                "path": "/expected",
                "raw_path": b"/different",
                "headers": [],
            },
            receive,
            send,
        )
    assert messages[0]["status"] == 400


async def test_forwarded_headers_require_a_trusted_proxy():
    app, asgi = compose(
        trust_forwarded_headers=True,
        trusted_proxies=("127.0.0.1/32",),
    )

    @app.router.route("/request", name="request")
    async def request_info(request):
        return Response.json({"host": request.client_host, "scheme": request.scheme})

    async with TestClient(asgi) as client:
        response = await client.request(
            "GET",
            "/request",
            headers={"x-forwarded-for": "203.0.113.4", "x-forwarded-proto": "https"},
        )
    assert response.json() == {"host": "203.0.113.4", "scheme": "https"}


async def test_malformed_forwarded_client_port_is_not_trusted():
    app, asgi = compose(
        trust_forwarded_headers=True,
        trusted_proxies=("127.0.0.1/32",),
    )

    @app.router.route("/request", name="request")
    async def request_info(request):
        return Response.json({"host": request.client_host})

    async with TestClient(asgi) as client:
        response = await client.request(
            "GET", "/request", headers={"forwarded": "for=203.0.113.4:bad"}
        )
    assert response.json() == {"host": "127.0.0.1"}


@pytest.mark.parametrize("forwarded", ["for=fe80::1%eth0", "for=[fe80::1%25eth0]"])
async def test_scoped_forwarded_ipv6_is_not_trusted(forwarded: str) -> None:
    """Interface-scoped IPv6 literals cannot become trusted client identities."""
    app, asgi = compose(
        trust_forwarded_headers=True,
        trusted_proxies=("127.0.0.1/32",),
    )

    @app.router.route("/request", name="request")
    async def request_info(request):
        return Response.json({"host": request.client_host})

    async with TestClient(asgi) as client:
        response = await client.request("GET", "/request", headers={"forwarded": forwarded})
    assert response.json() == {"host": "127.0.0.1"}


def test_scoped_ipv6_addresses_are_never_trusted() -> None:
    """The trust helper rejects Python's interface-scoped IPv6 extension explicitly."""
    assert not ASGIApplication._trusted("fe80::1%eth0", ("fe80::/64",))


@pytest.mark.parametrize(
    "forwarded",
    [
        "for=203.0.113.4;for=198.51.100.4;proto=https",
        "for=203.0.113.4;proto=https;proto=http",
    ],
)
async def test_duplicate_forwarded_parameters_fail_closed(forwarded: str) -> None:
    """Repeated identity or scheme parameters cannot overwrite trusted proxy metadata."""
    app, asgi = compose(
        trust_forwarded_headers=True,
        trusted_proxies=("127.0.0.1/32",),
    )

    @app.router.route("/request", name="request")
    async def request_info(request):
        return Response.json({"host": request.client_host, "scheme": request.scheme})

    async with TestClient(asgi) as client:
        response = await client.request(
            "GET",
            "/request",
            headers={"forwarded": forwarded},
        )
    assert response.json() == {"host": "127.0.0.1", "scheme": "http"}


@pytest.mark.parametrize(
    "header_name",
    ["forwarded", "x-forwarded-for", "x-forwarded-proto"],
)
async def test_duplicate_forwarding_headers_fail_closed(header_name: str) -> None:
    """Conflicting proxy fields must not override the direct socket identity or scheme."""
    app, asgi = compose(
        trust_forwarded_headers=True,
        trusted_proxies=("127.0.0.1/32",),
    )

    @app.router.route("/request", name="request")
    async def request_info(request):
        return Response.json({"host": request.client_host, "scheme": request.scheme})

    async with TestClient(asgi) as client:
        response = await client.request(
            "GET",
            "/request",
            headers=[
                (
                    header_name,
                    "for=203.0.113.4;proto=https" if header_name == "forwarded" else "203.0.113.4",
                ),
                (
                    header_name,
                    "for=198.51.100.4;proto=http" if header_name == "forwarded" else "198.51.100.4",
                ),
            ],
        )
    assert response.json() == {"host": "127.0.0.1", "scheme": "http"}


async def test_runtime_tracer_records_http_span():
    app = Application(ApplicationConfig(name="trace-tests"))
    tracer = InMemoryTracer()
    asgi = ASGIApplication(app, tracer=tracer)

    @app.router.route("/trace", name="trace")
    async def trace(request):
        return Response.text("ok")

    async with TestClient(asgi) as client:
        response = await client.request("GET", "/trace")
    assert response.status == 200
    span = next(item for item in tracer.history if item.name == "http.get")
    assert span.attributes["http.route"] == "/trace"
    assert span.attributes["http.status_code"] == 200
    assert span.status == "ok"


async def test_runtime_tracer_records_route_template_not_sensitive_path_parameter():
    app = Application(ApplicationConfig(name="trace-route-template"))
    tracer = InMemoryTracer()
    asgi = ASGIApplication(app, tracer=tracer)

    @app.router.route("/users/{user_id}", name="user-detail")
    async def user_detail(request):
        return Response.text("ok")

    sensitive_identifier = "credential-like-path-segment"
    async with TestClient(asgi) as client:
        response = await client.request("GET", f"/users/{sensitive_identifier}")

    assert response.status == 200
    span = next(item for item in tracer.history if item.name == "http.get")
    assert span.attributes["http.route"] == "/users/{user_id}"
    assert sensitive_identifier not in repr(span.attributes)


async def test_runtime_tracer_omits_route_for_unmatched_path():
    app = Application(ApplicationConfig(name="trace-unmatched-route"))
    tracer = InMemoryTracer()
    asgi = ASGIApplication(app, tracer=tracer)

    async with TestClient(asgi) as client:
        response = await client.request("GET", "/unmatched/sensitive-segment")

    assert response.status == 404
    span = next(item for item in tracer.history if item.name == "http.get")
    assert "http.route" not in span.attributes


async def test_runtime_enforces_outbound_header_budget_after_runtime_headers() -> None:
    app, asgi = compose()

    @app.router.route("/headers", name="headers")
    async def headers(request):
        return Response(status=200, headers=[("x-test", "ok")] * 999)

    async with TestClient(asgi) as client:
        response = await client.request("GET", "/headers")
    assert response.status == 500
    assert response.json()["code"] == "runtime.internal"


async def test_runtime_owned_response_headers_cannot_be_overridden() -> None:
    app, asgi = compose()

    @app.router.route("/headers", name="headers")
    async def headers(request):
        return Response(
            body=b"ok",
            headers={
                "x-request-id": "attacker-controlled",
                "x-content-type-options": "unsafe",
            },
        )

    async with TestClient(asgi) as client:
        response = await client.request("GET", "/headers")
    assert len(response.headers.getall("x-request-id")) == 1
    assert len(response.headers.getall("x-content-type-options")) == 1
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-request-id"] != "attacker-controlled"


@pytest.mark.parametrize(
    "method,status,body",
    [
        ("GET", 200, b"42"),
        ("HEAD", 200, b""),
        ("POST", 405, b""),
        ("OPTIONS", 204, b""),
    ],
)
async def test_http_method_semantics(method, status, body):
    app, asgi = compose()

    @app.router.route("/users/{id}", name="user")
    async def user(request):
        return Response.text(request.path_parameters["id"])

    async with TestClient(asgi) as client:
        response = await client.request(method, "/users/42")
        assert response.status == status
        assert response.body == body
        if method in {"POST", "OPTIONS"}:
            assert "HEAD" in response.headers["allow"]
        if method == "HEAD":
            assert response.headers["content-length"] == "2"


async def test_json_validation_and_request_error_redaction():
    app, asgi = compose()

    class Payload(BaseModel):
        number: int
        secret: SecretStr

    @app.router.route("/json", method="POST", name="json")
    async def process(request):
        return Response.json(request.validate(Payload))

    async with TestClient(asgi) as client:
        good = await client.request(
            "POST",
            "/json",
            body=b'{"number":2,"secret":"private"}',
            headers={"content-type": "application/json"},
        )
        assert good.status == 200
        assert b"private" not in good.body
        bad = await client.request(
            "POST",
            "/json",
            body=b'{"number":"private"}',
            headers={"content-type": "application/json"},
        )
        assert bad.status == 422 and b"private" not in bad.body
        malformed = await client.request(
            "POST", "/json", body=b"{", headers={"content-type": "application/json"}
        )
        assert malformed.status == 400
        assert (await client.request("POST", "/json")).status == 415


@pytest.mark.parametrize(
    "body,headers,status",
    [
        (b"12345", {}, 413),
        (b"1", {"content-length": "9"}, 413),
        (b"1", {"content-length": "2"}, 400),
        (b"1", {"content-length": "-1"}, 400),
    ],
)
async def test_body_limits_and_length_validation(body, headers, status):
    app, asgi = compose(max_body_bytes=4)
    async with TestClient(asgi) as client:
        response = await client.request("POST", "/missing", body=body, headers=headers)
        assert response.status == status


async def test_middleware_order_and_scope_resource_cleanup():
    app, asgi = compose()
    calls = []

    @asynccontextmanager
    async def resource(container):
        calls.append("open")
        try:
            yield object()
        finally:
            calls.append("close")

    app.container.register_resource("request", resource, scope=Scope.SCOPED)

    async def outer(request, next_handler):
        calls.append("before")
        response = await next_handler(request)
        calls.append("after")
        return response

    asgi.add_middleware(outer)

    @app.router.route("/scope", name="scope")
    async def handler(request):
        one = await request.container.aresolve("request")
        assert one is await request.container.aresolve("request")
        return Response.text("ok")

    async with TestClient(asgi) as client:
        assert (await client.request("GET", "/scope")).status == 200
    assert calls == ["before", "open", "after", "close"]


async def test_streaming_preserves_resource_scope_and_repeated_headers():
    app, asgi = compose()
    calls = []

    @asynccontextmanager
    async def resource(container):
        try:
            yield "resource"
        finally:
            calls.append("closed")

    app.container.register_resource("stream", resource, scope=Scope.SCOPED)

    @app.router.route("/stream", name="stream")
    async def handler(request):
        async def chunks():
            try:
                assert await request.container.aresolve("stream") == "resource"
                yield b"one"
                assert not calls
                yield b"two"
            finally:
                calls.append("stream-closed")

        return Response(stream=chunks(), headers=[("set-cookie", "a=1"), ("set-cookie", "b=2")])

    async with TestClient(asgi) as client:
        result = await client.request("GET", "/stream")
        assert result.body == b"onetwo"
        assert result.headers.getall("set-cookie") == ("a=1", "b=2")
        assert "content-length" not in result.headers
    assert calls == ["stream-closed", "closed"]


async def test_current_readiness_reflects_changed_health():
    class Switch(Service):
        descriptor = ServiceDescriptor(name="switch")
        status = HealthStatus.HEALTHY

        async def health(self):
            return HealthReport(status=self.status)

    app, asgi = compose()
    service = Switch()
    app.register(service)
    async with TestClient(asgi) as client:
        assert (await client.request("GET", "/health/ready")).status == 200
        service.status = HealthStatus.UNHEALTHY
        assert (await client.request("GET", "/health/ready")).status == 503
        assert (await client.request("GET", "/health/live")).status == 200


class Auth:
    """Deterministic test authentication, never a production credential implementation."""

    async def authenticate(self, request):
        token = request.headers.get("authorization", "")
        roles = {
            "Bearer reader": {"orbit.admin.read"},
            "Bearer writer": {"orbit.admin.read", "orbit.admin.write"},
        }.get(token)
        return (
            AuthTestPrincipal(
                identity=AuthTestIdentity(subject="test", provider="test"), roles=frozenset(roles)
            )
            if roles
            else None
        )


async def test_admin_package_is_opt_in_and_protected_user_route():
    app, asgi = compose()

    @app.router.route("/private", name="private", roles=frozenset({"private"}))
    async def private(request):
        return Response.text("private")

    async with TestClient(asgi) as client:
        assert (await client.request("GET", "/admin")).status == 404
        assert (await client.request("GET", "/private")).status == 401


async def test_authenticated_route_fails_closed_without_authorizer():
    app, _ = compose()

    @app.router.route("/private", name="private", roles=frozenset({"private"}))
    async def private(request):
        return Response.text("private")

    class Auth:
        async def authenticate(self, request):
            return AuthTestPrincipal(
                identity=AuthTestIdentity(subject="user", provider="test"),
                roles=frozenset({"private"}),
            )

    async with TestClient(ASGIApplication(app, authenticator=Auth())) as client:
        response = await client.request("GET", "/private")
    assert response.status == 403
    assert b"private" not in response.body


async def test_internal_error_never_leaks_exception_details():
    app, asgi = compose()

    @app.router.route("/fail", name="fail")
    async def fail(request):
        raise ValueError("private-database-password")

    async with TestClient(asgi) as client:
        response = await client.request("GET", "/fail")
        assert response.status == 500
        assert b"private-database-password" not in response.body
        assert response.headers["x-request-id"] == response.json()["request_id"]


async def test_request_deadline_cleans_scope():
    app, asgi = compose(request_timeout=0.01)
    calls = []

    @asynccontextmanager
    async def resource(container):
        try:
            yield 1
        finally:
            calls.append("closed")

    app.container.register_resource("r", resource, scope=Scope.SCOPED)

    @app.router.route("/slow", name="slow")
    async def slow(request):
        await request.container.aresolve("r")
        await asyncio.Event().wait()

    async with TestClient(asgi) as client:
        assert (await client.request("GET", "/slow")).status == 504
        assert calls == ["closed"]


async def test_duplicate_headers_and_query_parameters():
    headers = Headers([("X-Test", "one"), ("x-test", "two")])
    assert headers.getall("X-Test") == ("one", "two")
    assert headers["X-TEST"] == "one"
    assert len(headers) == 1 and list(headers) == ["x-test"]
    request = Request("GET", "/", headers, query_string=b"x=1&x=2&blank=")
    assert request.query_parameters == {"x": ["1", "2"], "blank": [""]}
    with pytest.raises(KeyError):
        _ = headers["absent"]


@pytest.mark.parametrize("values", [{1: "value"}, {"name": 1}, [(1, "value")]])
def test_headers_reject_non_string_pairs(values):
    with pytest.raises(TypeError, match="strings"):
        Headers(values)


async def test_middleware_lifecycle_is_ordered_and_failure_safe():
    app = Application(ApplicationConfig(name="middleware-lifecycle"))
    asgi = ASGIApplication(app)
    calls: list[str] = []

    class Managed:
        async def startup(self):
            calls.append("start")

        async def shutdown(self):
            calls.append("stop")

        async def __call__(self, request, next_handler):
            return await next_handler(request)

    asgi.add_middleware(Managed())
    async with TestClient(asgi):
        assert calls == ["start"]
    assert calls == ["start", "stop"]


async def test_forwarded_header_is_supported_only_from_trusted_proxy():
    app = Application(
        ApplicationConfig(
            name="forwarded-rfc",
            trust_forwarded_headers=True,
            trusted_proxies=("127.0.0.1/32",),
        )
    )
    asgi = ASGIApplication(app)

    @app.router.route("/request", name="request")
    async def request_info(request):
        return Response.json({"host": request.client_host, "scheme": request.scheme})

    async with TestClient(asgi) as client:
        trusted = await client.request(
            "GET", "/request", headers={"forwarded": "for=203.0.113.8;proto=https"}
        )
        assert trusted.json() == {"host": "203.0.113.8", "scheme": "https"}
