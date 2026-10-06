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
"""Wire-level failure and disconnect regressions using explicit ASGI frames."""

import asyncio
from collections.abc import Iterator, Mapping
from contextlib import asynccontextmanager
from itertools import product

import pytest

from orbit import Application, ApplicationConfig
from orbit.asgi import ASGIApplication, Response
from orbit.asgi.request import Headers, HTTPError, Request
from orbit.container import Scope
from orbit.types import new_request_id


class _MisreportingPathParameters(Mapping[str, str]):
    """Path-parameter mapping whose false length must not disable route bounds."""

    def __init__(self, count: int) -> None:
        self._count = count

    def __getitem__(self, key: str) -> str:
        index = int(key.removeprefix("param_"))
        if 0 <= index < self._count:
            return "value"
        raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        return iter(f"param_{index}" for index in range(self._count))

    def __len__(self) -> int:
        return 0


async def call(asgi, frames, *, scope=None, send=None):
    messages = []

    async def receive():
        return frames.pop(0)

    async def capture(message):
        messages.append(message)

    await asgi(
        scope or {"type": "http", "method": "POST", "path": "/", "headers": []},
        receive,
        send or capture,
    )
    return messages


async def test_disconnect_prevents_handler_execution():
    app = Application(ApplicationConfig(name="disconnect"))
    calls = []

    @app.router.route("/", method="POST", name="root")
    async def root(request):
        calls.append(1)
        return Response.text("ok")

    async with app.running():
        messages = await call(
            ASGIApplication(app),
            [
                {"type": "http.request", "body": b"partial", "more_body": True},
                {"type": "http.disconnect"},
            ],
        )
    assert not messages and not calls


async def test_request_client_identity_is_resolved_once(monkeypatch) -> None:
    """Request parsing makes one consistent proxy-identity decision per request."""
    application = Application(ApplicationConfig(name="single-client-resolution"))
    asgi = ASGIApplication(application)
    calls = 0
    original = ASGIApplication._client

    def wrapped(_self, scope, headers):
        nonlocal calls
        calls += 1
        return original(_self, scope, headers)

    monkeypatch.setattr(ASGIApplication, "_client", wrapped)

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    request = await asgi._read_request(
        {"type": "http", "method": "GET", "path": "/", "headers": []},
        receive,
        new_request_id(),
    )
    assert calls == 1
    assert request.client_host is None


async def test_slow_client_receive_is_bounded_by_request_deadline() -> None:
    """A peer that never completes the request cannot hold the ASGI task indefinitely."""
    app = Application(ApplicationConfig(name="slow-client", request_timeout=0.01))
    messages = []

    async def receive():
        await asyncio.sleep(1)
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(message)

    async with app.running():
        await ASGIApplication(app)(
            {"type": "http", "method": "GET", "path": "/", "headers": []},
            receive,
            send,
        )
    assert messages[0]["status"] == 504


async def test_chunked_request_enforces_cumulative_limit():
    app = Application(ApplicationConfig(name="chunks", max_body_bytes=4))
    async with app.running():
        messages = await call(
            ASGIApplication(app),
            [
                {"type": "http.request", "body": b"123", "more_body": True},
                {"type": "http.request", "body": b"45", "more_body": False},
            ],
        )
    assert messages[0]["status"] == 413


async def test_oversized_request_path_is_rejected() -> None:
    app = Application(ApplicationConfig(name="path-size-validation"))
    async with app.running():
        messages = await call(
            ASGIApplication(app),
            [{"type": "http.request", "body": b"", "more_body": False}],
            scope={
                "type": "http",
                "method": "GET",
                "path": "/" + "a" * (16 * 1024),
                "headers": [],
            },
        )
    assert messages[0]["status"] == 414


async def test_oversized_raw_request_path_is_rejected() -> None:
    app = Application(ApplicationConfig(name="raw-path-size-validation"))
    decoded_path = "/" + "A" * 6000
    encoded_path = b"/" + b"%41" * 6000
    async with app.running():
        messages = await call(
            ASGIApplication(app),
            [{"type": "http.request", "body": b"", "more_body": False}],
            scope={
                "type": "http",
                "method": "GET",
                "path": decoded_path,
                "raw_path": encoded_path,
                "headers": [],
            },
        )
    assert messages[0]["status"] == 414


@pytest.mark.parametrize(
    "frame",
    [
        {"body": b""},
        {"type": "http.request", "body": "text"},
        {"type": "http.request", "more_body": 1},
    ],
)
async def test_malformed_receive_frames_are_rejected(frame):
    app = Application(ApplicationConfig(name="frame-validation"))
    async with app.running():
        messages = await call(ASGIApplication(app), [frame])
    assert messages[0]["status"] == 400


@pytest.mark.parametrize("path", ["/a/../secret", "/a/./secret", "/a//secret", "/a\\secret"])
async def test_ambiguous_request_paths_are_rejected(path):
    app = Application(ApplicationConfig(name="path-validation"))
    async with app.running():
        messages = await call(
            ASGIApplication(app),
            [{"type": "http.request", "body": b"", "more_body": False}],
            scope={"type": "http", "method": "GET", "path": path, "headers": []},
        )
    assert messages[0]["status"] == 400


@pytest.mark.parametrize("method", ["GET\n", "GET HTTP", "", "X" * 33])
async def test_invalid_http_methods_are_rejected(method):
    app = Application(ApplicationConfig(name="method-validation"))
    async with app.running():
        messages = await call(
            ASGIApplication(app),
            [{"type": "http.request", "body": b"", "more_body": False}],
            scope={"type": "http", "method": method, "path": "/", "headers": []},
        )
    assert messages[0]["status"] == 400
    assert app.diagnostics.collect(app).recent_requests[-1].method == "INVALID"


@pytest.mark.parametrize(
    "scope", [{"type": "http", "path": "/"}, {"type": "http", "method": "GET"}]
)
async def test_incomplete_http_scope_returns_bounded_error(scope):
    app = Application(ApplicationConfig(name="scope-validation"))
    async with app.running():
        messages = await call(
            ASGIApplication(app),
            [{"type": "http.request", "body": b"", "more_body": False}],
            scope=scope,
        )
    assert messages[0]["status"] == 400


@pytest.mark.parametrize(
    "client",
    [
        ("127.0.0.1",),
        "127.0.0.1",
        ("127.0.0.1", 70000),
        ("", 1234),
        ("bad\nhost", 1234),
        ("x" * 256, 1234),
    ],
)
async def test_malformed_client_scope_is_rejected(client):
    app = Application(ApplicationConfig(name="client-validation"))
    async with app.running():
        messages = await call(
            ASGIApplication(app),
            [{"type": "http.request", "body": b"", "more_body": False}],
            scope={
                "type": "http",
                "method": "GET",
                "path": "/",
                "headers": [],
                "client": client,
            },
        )
    assert messages[0]["status"] == 400


async def test_scoped_ipv6_client_scope_is_rejected() -> None:
    """Interface-scoped IPv6 identities cannot enter proxy trust evaluation."""
    app = Application(ApplicationConfig(name="scoped-client-validation"))
    async with app.running():
        messages = await call(
            ASGIApplication(app),
            [{"type": "http.request", "body": b"", "more_body": False}],
            scope={
                "type": "http",
                "method": "GET",
                "path": "/",
                "headers": [],
                "client": ("fe80::1%eth0", 1234),
            },
        )
    assert messages[0]["status"] == 400


@pytest.mark.parametrize("scheme", ["ftp", "", 1])
async def test_invalid_http_scheme_is_rejected(scheme):
    app = Application(ApplicationConfig(name="scheme-validation"))
    async with app.running():
        messages = await call(
            ASGIApplication(app),
            [{"type": "http.request", "body": b"", "more_body": False}],
            scope={
                "type": "http",
                "method": "GET",
                "path": "/",
                "headers": [],
                "scheme": scheme,
            },
        )
    assert messages[0]["status"] == 400


@pytest.mark.parametrize(
    "headers",
    [
        None,
        [(b"malformed",)],
        [(b"traceparent", "not-bytes")],
    ],
)
async def test_malformed_trace_scope_headers_return_bounded_error(headers) -> None:
    app = Application(ApplicationConfig(name="trace-header-validation"))
    async with app.running():
        messages = await call(
            ASGIApplication(app),
            [{"type": "http.request", "body": b"", "more_body": False}],
            scope={"type": "http", "method": "GET", "path": "/", "headers": headers},
        )
    assert messages[0]["status"] == 400


async def test_adversarial_http_scope_corpus_stays_inside_bounded_error_responses() -> None:
    """Malformed ASGI scope combinations must not escape the runtime as arbitrary exceptions."""
    app = Application(ApplicationConfig(name="scope-corpus"))
    invalid_methods = [None, "", "GET\n", "X" * 33]
    invalid_paths = [None, "", "relative", "/a//b", "/a/../b", "/a?query"]
    invalid_clients = [
        None,
        ("", 1234),
        ("127.0.0.1", 70000),
        ("bad\nhost", 1234),
        ("x" * 256, 1234),
        ("127.0.0.1",),
    ]
    malformed_scopes = [
        {
            "type": "http",
            "method": method,
            "path": path,
            "headers": [],
            "client": client,
        }
        for method, path, client in product(invalid_methods, invalid_paths, invalid_clients)
    ]
    malformed_scopes.extend(
        [
            {"type": "http", "method": "GET", "path": "/", "headers": None},
            {"type": "http", "method": "GET", "path": "/", "headers": [(b"x",)]},
            {
                "type": "http",
                "method": "GET",
                "path": "/",
                "headers": [("x", b"value")],
            },
            {
                "type": "http",
                "method": "GET",
                "path": "/",
                "headers": [(b"x", b"\x00")],
            },
            {
                "type": "http",
                "method": "GET",
                "path": "/",
                "headers": [(b"x-field", b"value")] * 1_001,
            },
        ]
    )

    async with app.running():
        for scope in malformed_scopes:
            messages = await call(
                ASGIApplication(app),
                [{"type": "http.request", "body": b"", "more_body": False}],
                scope=scope,
            )
            assert messages and messages[0]["status"] in {400, 413, 431}


def test_trace_id_requires_nonzero_trace_and_parent_span() -> None:
    valid = [(b"traceparent", b"00-" + b"1" * 32 + b"-" + b"2" * 16 + b"-01")]
    assert ASGIApplication._trace_id({"headers": valid}) == "1" * 32
    assert (
        ASGIApplication._trace_id(
            {"headers": [(b"traceparent", b"00-" + b"0" * 32 + b"-" + b"2" * 16 + b"-01")]}
        )
        is None
    )


def test_trace_id_does_not_scan_beyond_request_header_limit() -> None:
    valid = (b"traceparent", b"00-" + b"1" * 32 + b"-" + b"2" * 16 + b"-01")
    headers = [(b"x-field", b"value")] * 1_000 + [valid]
    assert ASGIApplication._trace_id({"headers": headers}) is None


@pytest.mark.parametrize(
    "trace_headers",
    [
        [
            (b"traceparent", b"00-" + b"1" * 32 + b"-" + b"2" * 16 + b"-01"),
            (b"traceparent", b"00-" + b"3" * 32 + b"-" + b"4" * 16 + b"-01"),
        ],
        [
            (b"traceparent", b"00-" + b"1" * 32 + b"-" + b"2" * 16 + b"-01"),
            (b"traceparent", b"malformed"),
        ],
    ],
)
def test_duplicate_traceparent_fields_fail_closed(trace_headers) -> None:
    """A later traceparent cannot overwrite or be ignored after a valid first field."""
    assert ASGIApplication._trace_id({"headers": trace_headers}) is None


async def test_websocket_upgrade_is_rejected_by_the_http_core() -> None:
    app = Application(ApplicationConfig(name="websocket-policy"))
    messages = await call(ASGIApplication(app), [], scope={"type": "websocket"})
    assert messages == [{"type": "websocket.close", "code": 1003}]


async def test_unsupported_scope_type_error_is_bounded() -> None:
    """Unsupported host scope types cannot inject unbounded data into runtime errors."""
    app = Application(ApplicationConfig(name="unsupported-scope"))
    with pytest.raises(RuntimeError, match="Unsupported ASGI scope type") as error:
        await ASGIApplication(app)(
            {"type": "unsupported-" + "x" * 1_000_000},
            lambda: None,
            lambda message: None,
        )
    assert len(str(error.value)) < 100


async def test_response_boundary_honors_case_insensitive_head_semantics() -> None:
    """Overload and draining paths cannot emit a body for a lowercase HEAD method."""
    messages = []

    async def send(message):
        messages.append(message)

    await ASGIApplication._send(Response.text("hidden"), "head", send)

    assert messages[0]["type"] == "http.response.start"
    assert messages[1] == {"type": "http.response.body", "body": b"", "more_body": False}


@pytest.mark.parametrize(
    "root_path,path",
    [
        ("/api/", "/api/items"),
        ("/api//internal", "/api/items"),
        ("/api/../internal", "/api/items"),
        ("/api", "/other"),
    ],
)
async def test_noncanonical_root_paths_are_rejected(root_path, path):
    app = Application(ApplicationConfig(name="root-path-validation"))
    async with app.running():
        messages = await call(
            ASGIApplication(app),
            [{"type": "http.request", "body": b"", "more_body": False}],
            scope={
                "type": "http",
                "method": "GET",
                "path": path,
                "root_path": root_path,
                "headers": [],
            },
        )
    assert messages[0]["status"] == 400


async def test_oversized_root_path_is_rejected() -> None:
    app = Application(ApplicationConfig(name="root-path-size-validation"))
    async with app.running():
        messages = await call(
            ASGIApplication(app),
            [{"type": "http.request", "body": b"", "more_body": False}],
            scope={
                "type": "http",
                "method": "GET",
                "path": "/",
                "root_path": "/" + "a" * (16 * 1024),
                "headers": [],
            },
        )
    assert messages[0]["status"] == 414


async def test_canonical_root_path_is_removed_before_route_dispatch() -> None:
    app = Application(ApplicationConfig(name="root-path"))

    @app.router.route("/items", name="items")
    async def items(request):
        return Response.json({"path": request.path, "root_path": request.root_path})

    async with app.running():
        messages = await call(
            ASGIApplication(app),
            [{"type": "http.request", "body": b"", "more_body": False}],
            scope={
                "type": "http",
                "method": "GET",
                "path": "/api/items",
                "root_path": "/api",
                "headers": [],
            },
        )
    assert messages[0]["status"] == 200
    assert messages[1]["body"] == b'{"path":"/items","root_path":"/api"}'


@pytest.mark.parametrize("scope", [{}, None, []])
async def test_invalid_asgi_scope_is_rejected_explicitly(scope):
    app = Application(ApplicationConfig(name="scope-type-validation"))
    with pytest.raises(RuntimeError, match="ASGI scope"):
        await ASGIApplication(app)(scope, lambda: None, lambda message: None)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "query_string, status",
    [("bad", 400), (b"x=" + b"a" * (64 * 1024), 414)],
)
async def test_query_string_is_bounded_and_typed(query_string, status):
    app = Application(ApplicationConfig(name="query-validation"))
    async with app.running():
        messages = await call(
            ASGIApplication(app),
            [{"type": "http.request", "body": b"", "more_body": False}],
            scope={
                "type": "http",
                "method": "GET",
                "path": "/",
                "query_string": query_string,
                "headers": [],
            },
        )
    assert messages[0]["status"] == status


async def test_request_frame_count_is_bounded(monkeypatch) -> None:
    """Zero-byte request frames cannot consume unbounded parser work."""
    monkeypatch.setattr("orbit.asgi.application._MAX_REQUEST_FRAMES", 2)
    app = Application(ApplicationConfig(name="frame-count"))
    messages = await call(
        ASGIApplication(app),
        [
            {"type": "http.request", "body": b"", "more_body": True},
            {"type": "http.request", "body": b"", "more_body": True},
            {"type": "http.request", "body": b"", "more_body": False},
        ],
        scope={"type": "http", "method": "POST", "path": "/", "headers": []},
    )
    assert messages[0]["status"] == 400
    assert b"request.protocol" in messages[1]["body"]


async def test_request_header_count_is_bounded(monkeypatch) -> None:
    """Many tiny header fields cannot bypass the aggregate request-header boundary."""
    monkeypatch.setattr("orbit.asgi.application._MAX_REQUEST_HEADERS", 2)
    app = Application(ApplicationConfig(name="header-count"))
    messages = await call(
        ASGIApplication(app),
        [{"type": "http.request", "body": b"", "more_body": False}],
        scope={
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [(b"x-one", b"1"), (b"x-two", b"2"), (b"x-three", b"3")],
        },
    )
    assert messages[0]["status"] == 431
    assert b"request.headers-too-many" in messages[1]["body"]


async def test_header_section_is_bounded_and_frames_are_validated():
    limited = Application(ApplicationConfig(name="headers", max_header_bytes=1024))
    async with limited.running():
        oversized = await call(
            ASGIApplication(limited),
            [{"type": "http.request", "body": b"", "more_body": False}],
            scope={
                "type": "http",
                "method": "GET",
                "path": "/",
                "headers": [(b"x-large", b"x" * 1020)],
            },
        )
        malformed = await call(
            ASGIApplication(limited),
            [{"type": "http.request", "body": b"", "more_body": False}],
            scope={"type": "http", "path": "/", "headers": [("x", b"value")]},
        )
    assert oversized[0]["status"] == 431
    assert malformed[0]["status"] == 400


async def test_duplicate_content_type_headers_are_rejected() -> None:
    app = Application(ApplicationConfig(name="duplicate-content-type"))
    async with app.running():
        messages = await call(
            ASGIApplication(app),
            [{"type": "http.request", "body": b"{}", "more_body": False}],
            scope={
                "type": "http",
                "method": "POST",
                "path": "/",
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-type", b"text/plain"),
                ],
            },
        )
    assert messages[0]["status"] == 400


async def test_duplicate_cookie_headers_are_rejected() -> None:
    app = Application(ApplicationConfig(name="duplicate-cookie"))
    async with app.running():
        messages = await call(
            ASGIApplication(app),
            [{"type": "http.request", "body": b"", "more_body": False}],
            scope={
                "type": "http",
                "method": "GET",
                "path": "/",
                "headers": [(b"cookie", b"session=one"), (b"cookie", b"session=two")],
            },
        )
    assert messages[0]["status"] == 400


@pytest.mark.parametrize(
    "header", [(b"bad name", b"value"), (b"x-test", b"bad\r\nvalue"), (b"x-test", b"bad\x01value")]
)
async def test_inbound_header_injection_is_rejected(header):
    app = Application(ApplicationConfig(name="header-validation"))
    async with app.running():
        messages = await call(
            ASGIApplication(app),
            [{"type": "http.request", "body": b"", "more_body": False}],
            scope={"type": "http", "method": "GET", "path": "/", "headers": [header]},
        )
    assert messages[0]["status"] == 400


@pytest.mark.parametrize(
    "host",
    ["example.com", "localhost:8000", "127.0.0.1", "[::1]:443", "service_name"],
)
def test_valid_host_authority_values_are_accepted(host: str) -> None:
    ASGIApplication._validate_host_header(Headers({"host": host}))


@pytest.mark.parametrize(
    "headers",
    [
        [("host", "one.example"), ("Host", "two.example")],
        {"host": "example.com:bad"},
        {"host": "example.com:65536"},
        {"host": "[::1"},
        {"host": "[fe80::1%25eth0]:443"},
        {"host": "127.0.0.1:80:90"},
        {"host": "2001:db8::1"},
        {"host": "user@example.com"},
        {"host": "example.com/path"},
        {"host": "é.example"},
    ],
)
def test_invalid_host_authority_values_fail_closed(headers) -> None:
    with pytest.raises(HTTPError, match="Host"):
        ASGIApplication._validate_host_header(Headers(headers))


def test_response_header_budget_is_bounded():
    with pytest.raises(ValueError, match="safety limit"):
        Response(headers={"x-large": "x" * (64 * 1024)})
    with pytest.raises(ValueError, match="safety limit"):
        Response(headers=[("x-header", "v")] * 1001)
    with pytest.raises(ValueError, match="header value"):
        Response(headers={"x-test": "bad\x7fvalue"})


def test_response_header_budget_includes_runtime_content_length() -> None:
    """The generated framing header must fit inside the final response budget."""
    with pytest.raises(ValueError, match="safety limit"):
        Response(headers=[("x-header", "v")] * Response.MAX_HEADER_COUNT)

    header_name = "x-large"
    value_size = Response.MAX_HEADER_BYTES - len(header_name) - 2
    with pytest.raises(ValueError, match="safety limit"):
        Response(headers={header_name: "x" * value_size})


def test_response_rejects_invalid_status_and_body_framing() -> None:
    with pytest.raises(ValueError, match="final"):
        Response(status=200.0)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="body"):
        Response(status=204, body=b"unexpected")
    with pytest.raises(ValueError, match="body"):
        Response(status=304, stream=iter(()))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="body"):
        Response(status=205, body=b"unexpected")
    with pytest.raises(ValueError, match="body"):
        Response(status=205, stream=iter(()))  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="asynchronous"):
        Response(stream=iter(()))  # type: ignore[arg-type]

    class InvalidIterator:
        def __aiter__(self):
            return object()

    class InvalidCleanup:
        aclose = False

        def __aiter__(self):
            return self

        async def __anext__(self):
            raise StopAsyncIteration

    with pytest.raises(TypeError, match="asynchronous"):
        Response(stream=InvalidIterator())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="cleanup"):
        Response(stream=InvalidCleanup())  # type: ignore[arg-type]

    class SynchronousCleanup:
        def __aiter__(self):
            return self

        async def __anext__(self):
            raise StopAsyncIteration

        def aclose(self):
            return None

    with pytest.raises(TypeError, match="async callable"):
        Response(stream=SynchronousCleanup())  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"method": "GET\n"},
        {"path": "/a/../secret"},
        {"body": "text"},
        {"query_string": "x=1"},
        {"client_port": 70000},
        {"scheme": "ftp"},
        {"root_path": "/" + "a" * (16 * 1024)},
    ],
)
def test_direct_request_rejects_invalid_contract_values(kwargs: dict[str, object]) -> None:
    with pytest.raises((TypeError, ValueError)):
        Request("GET", "/", **kwargs)  # type: ignore[arg-type]


def test_direct_request_normalizes_safe_values_and_bounds_query_parsing() -> None:
    request = Request("get", "/", scheme="HTTPS", path_parameters={"id": "42"})
    assert request.method == "GET"
    assert request.scheme == "https"
    assert request.path_parameters["id"] == "42"
    with pytest.raises(ValueError, match="query string"):
        Request("GET", "/", query_string=b"x=" + b"a" * (64 * 1024))
    with pytest.raises(ValueError, match="maximum supported length"):
        Request("GET", "/" + "a" * (16 * 1024))


def test_direct_http_boundaries_reject_oversized_headers_and_body(monkeypatch) -> None:
    import orbit.asgi.request as request_module

    monkeypatch.setattr(request_module, "MAX_BODY_BYTES", 4)
    with pytest.raises(ValueError, match="aggregate size"):
        Headers({"x-large": "a" * (16 * 1024 * 1024)})
    with pytest.raises(ValueError, match="field count"):
        Headers([(f"x-{index}", "value") for index in range(1_001)])
    with pytest.raises(ValueError, match="body"):
        Request("POST", "/", body=b"12345")


@pytest.mark.parametrize(
    "parameters",
    [
        [("id", "42")],
        {"bad-name": "42"},
        {"id": ""},
        {"id": "a/b"},
        {"id": "a\n b"},
        {"id": "\ud800"},
        {"x" * 128: "42"},
        {"id": "a" * (16 * 1024 + 1)},
    ],
)
def test_direct_request_rejects_unsafe_path_parameters(parameters: object) -> None:
    """Direct request construction cannot bypass route-derived segment boundaries."""
    with pytest.raises((TypeError, ValueError)):
        Request("GET", "/", path_parameters=parameters)  # type: ignore[arg-type]


def test_direct_request_bounds_path_parameter_cardinality() -> None:
    parameters = {f"param_{index}": "value" for index in range(129)}
    with pytest.raises(ValueError, match="safety limit"):
        Request("GET", "/", path_parameters=parameters)

    with pytest.raises(ValueError, match="safety limit"):
        Request("GET", "/", path_parameters=_MisreportingPathParameters(129))


@pytest.mark.parametrize(
    "kwargs",
    [
        {"status": True, "code": "request.invalid", "message": "Invalid request."},
        {"status": 200, "code": "request.invalid", "message": "Invalid request."},
        {"status": 399, "code": "request.invalid", "message": "Invalid request."},
        {"status": 600, "code": "request.invalid", "message": "Invalid request."},
        {"status": 400, "code": "Request.Invalid", "message": "Invalid request."},
        {"status": 400, "code": "request.invalid", "message": "bad\nmessage"},
        {"status": 400, "code": "request.invalid", "message": "x" * 1025},
    ],
)
def test_http_error_rejects_malformed_wire_contract_values(kwargs: dict[str, object]) -> None:
    with pytest.raises((TypeError, ValueError)):
        HTTPError(**kwargs)  # type: ignore[arg-type]


async def test_lifespan_failure_terminates_without_second_completion():
    from orbit import Service, ServiceDescriptor

    class Bad(Service):
        descriptor = ServiceDescriptor(name="bad")

        async def configure(self):
            raise ValueError("secret")

    app = Application(ApplicationConfig(name="lifespan"))
    app.register(Bad())
    messages = await call(
        ASGIApplication(app), [{"type": "lifespan.startup"}], scope={"type": "lifespan"}
    )
    assert [m["type"] for m in messages] == ["lifespan.startup.failed"]
    assert "secret" not in messages[0]["message"]


async def test_stream_disconnect_closes_iterator():
    app = Application(ApplicationConfig(name="stream-disconnect"))
    closed = []

    @app.router.route("/", method="POST", name="root")
    async def root(request):
        async def stream():
            try:
                yield b"one"
                yield b"two"
            finally:
                closed.append(True)

        return Response.streaming(stream())

    async def send(message):
        if message["type"] == "http.response.body":
            raise OSError("peer disconnected")

    async with app.running():
        await call(ASGIApplication(app), [{"type": "http.request", "body": b""}], send=send)
    assert closed == [True]


async def test_stream_disconnect_closes_request_scope_after_iterator() -> None:
    """A transport disconnect must close the stream before its request scope exits."""
    app = Application(ApplicationConfig(name="stream-scope-disconnect"))
    calls: list[str] = []

    @asynccontextmanager
    async def resource(container):
        calls.append("resource-open")
        try:
            yield object()
        finally:
            calls.append("resource-closed")

    app.container.register_resource("request", resource, scope=Scope.SCOPED)

    @app.router.route("/", method="GET", name="root")
    async def root(request):
        async def stream():
            await request.container.aresolve("request")
            try:
                yield b"one"
            finally:
                calls.append("stream-closed")

        return Response.streaming(stream())

    async def send(message):
        if message["type"] == "http.response.body":
            raise OSError("peer disconnected")

    async with app.running():
        await call(
            ASGIApplication(app),
            [{"type": "http.request", "body": b"", "more_body": False}],
            scope={"type": "http", "method": "GET", "path": "/", "headers": []},
            send=send,
        )
    assert calls == ["resource-open", "stream-closed", "resource-closed"]


async def test_stream_response_limit_closes_iterator_after_partial_send():
    app = Application(ApplicationConfig(name="stream-limit", max_response_bytes=1024))
    closed = []

    @app.router.route("/", method="GET", name="root")
    async def root(request):
        async def stream():
            try:
                yield b"x" * 1024
                yield b"y"
            finally:
                closed.append(True)

        return Response.streaming(stream())

    async with app.running():
        with pytest.raises(ValueError, match="Response stream"):
            await call(
                ASGIApplication(app),
                [{"type": "http.request", "body": b"", "more_body": False}],
                scope={"type": "http", "method": "GET", "path": "/", "headers": []},
            )
    assert closed == [True]


async def test_stream_cleanup_is_bounded_when_aclose_suppresses_cancellation():
    class StubbornStream:
        def __init__(self):
            self.release = asyncio.Event()

        def __aiter__(self):
            return self

        async def __anext__(self):
            raise StopAsyncIteration

        async def aclose(self):
            while not self.release.is_set():
                try:
                    await asyncio.sleep(0)
                except asyncio.CancelledError:
                    continue

    stream = StubbornStream()

    async def send(message):
        return None

    await asyncio.wait_for(
        ASGIApplication._send(Response.streaming(stream), "GET", send, cleanup_timeout=0.01),
        0.05,
    )
    stream.release.set()
    await asyncio.sleep(0)


async def test_stream_cleanup_does_not_mask_primary_send_failure() -> None:
    """A cleanup failure must not hide the disconnect or send error that caused cleanup."""

    class FailingCloseStream:
        def __aiter__(self):
            return self

        async def __anext__(self):
            raise StopAsyncIteration

        async def aclose(self):
            raise RuntimeError("cleanup failed")

    async def send(message):
        raise OSError("peer disconnected")

    with pytest.raises(OSError, match="peer disconnected"):
        await ASGIApplication._send(Response.streaming(FailingCloseStream()), "GET", send)


async def test_stream_cleanup_failure_is_visible_after_successful_response() -> None:
    """A cleanup failure remains observable when no earlier response error exists."""

    class FailingCloseStream:
        def __aiter__(self):
            return self

        async def __anext__(self):
            raise StopAsyncIteration

        async def aclose(self):
            raise RuntimeError("cleanup failed")

    async def send(message):
        return None

    with pytest.raises(RuntimeError, match="cleanup failed"):
        await ASGIApplication._send(Response.streaming(FailingCloseStream()), "GET", send)


async def test_buffered_response_limit_is_checked_before_response_start():
    app = Application(ApplicationConfig(name="response-limit", max_response_bytes=1024))

    @app.router.route("/", method="GET", name="root")
    async def root(request):
        return Response.text("x" * 1025)

    async with app.running():
        messages = await call(
            ASGIApplication(app),
            [{"type": "http.request", "body": b"", "more_body": False}],
            scope={"type": "http", "method": "GET", "path": "/", "headers": []},
        )
    assert messages[0]["status"] == 500


@pytest.mark.parametrize(
    "headers",
    [
        {"x-bad": "line\r\ninjected"},
        {"bad name": "x"},
        {"transfer-encoding": "chunked"},
        {"connection": "close"},
    ],
)
def test_response_header_validation(headers):
    with pytest.raises(ValueError):
        Response(headers=headers)


def test_response_rejects_duplicate_content_type() -> None:
    with pytest.raises(ValueError, match="duplicate Content-Type"):
        Response(
            headers=[
                ("content-type", "application/json"),
                ("content-type", "text/plain"),
            ]
        )


@pytest.mark.parametrize(
    "headers",
    [
        {"bad name": "value"},
        {"x-test": "bad\r\nvalue"},
        {"x-test": "bad\x01value"},
        {"x-test": "€"},
    ],
)
def test_shared_headers_reject_invalid_field_syntax(headers):
    with pytest.raises(ValueError):
        Headers(headers)


def test_shared_headers_preserve_valid_repeated_values_and_validate_lookup_type():
    headers = Headers([("Set-Cookie", "a=1"), ("set-cookie", "b=2")])
    assert headers.getall("set-cookie") == ("a=1", "b=2")
    with pytest.raises(TypeError):
        headers.getall(None)  # type: ignore[arg-type]


@pytest.mark.parametrize("status", [0, 100, 199, 600])
def test_response_status_validation(status):
    with pytest.raises(ValueError):
        Response(status=status)


@pytest.mark.parametrize("body", [b"NaN", b"Infinity", b"\xff", b"{"])
def test_invalid_json_documents(body):
    with pytest.raises(HTTPError):
        Request("POST", "/", {"content-type": "application/json"}, body).json()


def test_request_json_rejects_duplicate_content_type() -> None:
    request = Request(
        "POST",
        "/",
        Headers(
            [
                ("content-type", "application/json"),
                ("content-type", "application/json"),
            ]
        ),
        b"{}",
    )
    with pytest.raises(HTTPError, match="Duplicate Content-Type"):
        request.json()


def test_strict_response_json_does_not_stringify_arbitrary_objects():
    with pytest.raises(TypeError):
        Response.text(42)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        Response.json(object())
    with pytest.raises(ValueError):
        Response.json(float("nan"))


def test_request_cookies_and_response_set_cookie_preserve_contracts():
    request = Request("GET", "/", headers={"cookie": "session=abc; theme=dark"})
    assert dict(request.cookies) == {"session": "abc", "theme": "dark"}
    response = Response.text("ok").with_cookie("session", "abc", httponly=True)
    assert response.headers.getall("set-cookie") == ("session=abc; HttpOnly; Path=/; SameSite=lax",)


def test_request_cookies_reject_duplicate_fields() -> None:
    request = Request(
        "GET",
        "/",
        headers=Headers([("cookie", "session=one"), ("cookie", "session=two")]),
    )
    with pytest.raises(HTTPError, match="Duplicate Cookie"):
        _ = request.cookies


def test_request_cookies_reject_duplicate_names_in_one_field() -> None:
    """Cookie parsing cannot select a session value based on pair order."""
    request = Request("GET", "/", headers={"cookie": "session=one; theme=dark; session=two"})
    with pytest.raises(HTTPError, match="Duplicate cookie names"):
        _ = request.cookies


def test_response_cookie_enforces_secure_samesite_and_lifetime() -> None:
    with pytest.raises(TypeError, match="samesite"):
        Response.text("ok").with_cookie("session", "abc", samesite=1)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="Secure"):
        Response.text("ok").with_cookie("session", "abc", samesite="none")
    with pytest.raises(ValueError, match="max_age"):
        Response.text("ok").with_cookie("session", "abc", max_age=-1)
    secure = Response.text("ok").with_cookie(
        "session", "abc", samesite="none", secure=True, max_age=0
    )
    assert "SameSite=none" in secure.headers["set-cookie"]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"name": "bad name"},
        {"name": 1},
        {"value": 1},
        {"secure": 1},
        {"httponly": "true"},
        {"path": 1},
        {"expires": "bad\r\nvalue"},
        {"expires": "Wed, 09 Jun 2021 10:18:14 GMT; Secure"},
        {"path": "/; Secure"},
        {"domain": "example.com; Secure"},
    ],
)
def test_response_cookie_rejects_malformed_attribute_types(kwargs: dict[str, object]) -> None:
    with pytest.raises((TypeError, ValueError)):
        Response.text("ok").with_cookie("session", "abc", **kwargs)  # type: ignore[arg-type]


async def test_overload_rejects_instead_of_waiting_without_bound():
    app = Application(ApplicationConfig(name="overload", max_concurrent_requests=1))
    entered, release = asyncio.Event(), asyncio.Event()

    @app.router.route("/", method="POST", name="root")
    async def root(request):
        entered.set()
        await release.wait()
        return Response.text("done")

    asgi = ASGIApplication(app)
    async with app.running():
        task = asyncio.create_task(call(asgi, [{"type": "http.request", "body": b""}]))
        await entered.wait()
        rejected = await call(asgi, [{"type": "http.request", "body": b""}])
        assert rejected[0]["status"] == 503
        release.set()
        await task
