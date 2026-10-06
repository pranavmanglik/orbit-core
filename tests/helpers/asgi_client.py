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
"""Minimal private in-process ASGI test client for Core-owned integration tests."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from urllib.parse import unquote, urlsplit

from orbit.asgi import (
    MAX_HEADER_BYTES,
    MAX_HEADER_COUNT,
    MAX_PATH_BYTES,
    MAX_QUERY_BYTES,
    ASGIApplication,
    Headers,
    Message,
)

_DEFAULT_LIFESPAN_TIMEOUT = 60.0
_MAX_CAPTURED_RESPONSE_BYTES = 16 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class TestResponse:
    """Captured HTTP status, validated repeated headers, and complete response body."""

    status: int
    headers: Headers
    body: bytes

    def json(self) -> Any:
        """Decode a JSON response body for test assertions."""
        return json.loads(self.body)


class TestClient:
    """Drive Core ASGI requests and lifespan in process without network dependencies.

    This helper is private to Core's test suite. It models buffered single-request HTTP messages
    and validates basic response framing; it does not test sockets, TLS, proxy behavior, or worker
    processes. Those require the separate real-host integration tests.
    """

    __test__ = False

    def __init__(
        self,
        application: ASGIApplication,
        *,
        lifespan_timeout: float = _DEFAULT_LIFESPAN_TIMEOUT,
    ) -> None:
        """Bind one ASGI application and a finite timeout for lifecycle handshakes."""
        if not isinstance(application, ASGIApplication):
            raise TypeError("Core's private TestClient requires ASGIApplication.")
        if (
            isinstance(lifespan_timeout, bool)
            or not isinstance(lifespan_timeout, (int, float))
            or not 0 < lifespan_timeout <= 300
        ):
            raise ValueError("lifespan_timeout must be greater than 0 and at most 300 seconds.")
        self.application = application
        self._timeout = float(lifespan_timeout)
        self._active = False
        self._incoming: asyncio.Queue[Message] = asyncio.Queue()
        self._outgoing: asyncio.Queue[Message] = asyncio.Queue()
        self._lifespan: asyncio.Task[None] | None = None

    async def __aenter__(self) -> TestClient:
        """Start the ASGI lifespan and fail immediately if startup is rejected."""
        if self._lifespan is not None:
            raise RuntimeError("Core's private TestClient is single-use.")
        self._lifespan = asyncio.create_task(
            self.application({"type": "lifespan"}, self._incoming.get, self._outgoing.put)
        )
        await self._incoming.put({"type": "lifespan.startup"})
        try:
            message = await self._wait_lifespan()
            if message["type"] != "lifespan.startup.complete":
                raise RuntimeError(message.get("message", "Application startup failed."))
        except BaseException:
            self._lifespan.cancel()
            await asyncio.gather(self._lifespan, return_exceptions=True)
            raise
        self._active = True
        return self

    async def __aexit__(self, *_: object) -> None:
        """Complete ASGI shutdown and ensure the lifespan task is always joined."""
        task = self._lifespan
        if task is None:
            raise RuntimeError("ASGI lifespan was not started.")
        self._active = False
        await self._incoming.put({"type": "lifespan.shutdown"})
        try:
            message = await self._wait_lifespan()
            await asyncio.wait_for(task, timeout=self._timeout)
            if message["type"] != "lifespan.shutdown.complete":
                raise RuntimeError(message.get("message", "Application shutdown failed."))
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    async def _wait_lifespan(self) -> Message:
        """Wait for one lifespan response or surface early task failure without hanging."""
        task = self._lifespan
        if task is None:
            raise RuntimeError("ASGI lifespan was not started.")
        response = asyncio.create_task(self._outgoing.get())
        try:
            done, _ = await asyncio.wait(
                (response, task), timeout=self._timeout, return_when=asyncio.FIRST_COMPLETED
            )
            if not done:
                raise TimeoutError("Timed out waiting for ASGI lifespan response.")
            if response in done:
                return response.result()
            if task.cancelled():
                raise RuntimeError("ASGI lifespan task was cancelled unexpectedly.")
            error = task.exception()
            if error is not None:
                raise error
            if not self._outgoing.empty():
                return self._outgoing.get_nowait()
            raise RuntimeError("ASGI lifespan ended without acknowledging the operation.")
        finally:
            if not response.done():
                response.cancel()
            await asyncio.gather(response, return_exceptions=True)

    async def request(
        self,
        method: str,
        path: str,
        *,
        body: bytes = b"",
        headers: Mapping[str, str] | Sequence[tuple[str, str]] | None = None,
    ) -> TestResponse:
        """Send one complete buffered HTTP message and verify response framing and bounds."""
        if not self._active:
            raise RuntimeError("Send requests inside the TestClient context manager.")
        if not isinstance(method, str) or not method:
            raise TypeError("Request method must be a nonempty string.")
        if not isinstance(path, str):
            raise TypeError("Request path must be a string.")
        if not isinstance(body, bytes):
            raise TypeError("Request body must be bytes.")
        url = urlsplit(path)
        raw_path = url.path or "/"
        try:
            raw_path_bytes = raw_path.encode("utf-8")
            query_bytes = url.query.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ValueError("Request URL must contain valid Unicode text.") from exc
        if len(raw_path_bytes) > MAX_PATH_BYTES:
            raise ValueError("Request path exceeds Core's supported maximum.")
        if len(query_bytes) > MAX_QUERY_BYTES:
            raise ValueError("Request query exceeds Core's supported maximum.")

        pairs = headers.items() if isinstance(headers, Mapping) else headers or ()
        encoded_headers: list[tuple[bytes, bytes]] = []
        header_bytes = 0
        for name, value in pairs:
            if not isinstance(name, str) or not isinstance(value, str):
                raise TypeError("Request header names and values must be strings.")
            try:
                encoded_name, encoded_value = name.encode("latin-1"), value.encode("latin-1")
            except UnicodeEncodeError as exc:
                raise ValueError("Request headers must be Latin-1 encodable.") from exc
            header_bytes += len(encoded_name) + len(encoded_value) + 2
            if len(encoded_headers) >= MAX_HEADER_COUNT or header_bytes > MAX_HEADER_BYTES:
                raise ValueError("Request headers exceed Core's supported maximum.")
            encoded_headers.append((encoded_name, encoded_value))

        messages: list[Message] = []
        request_sent = False
        response_bytes = 0

        async def receive() -> Message:
            """Provide one request frame followed by a client disconnect."""
            nonlocal request_sent
            if request_sent:
                return {"type": "http.disconnect"}
            request_sent = True
            return {"type": "http.request", "body": body, "more_body": False}

        async def send(message: Message) -> None:
            """Check start/body ordering and bound the response retained by this test helper."""
            nonlocal response_bytes
            if not messages:
                if message["type"] != "http.response.start":
                    raise AssertionError("ASGI response body preceded response start.")
            elif message["type"] != "http.response.body":
                raise AssertionError("Unexpected ASGI response frame.")
            elif messages[-1].get("type") == "http.response.body" and not messages[-1].get(
                "more_body", False
            ):
                raise AssertionError("ASGI response sent a frame after its final body.")
            if message["type"] == "http.response.body":
                response_bytes += len(message.get("body", b""))
                if response_bytes > _MAX_CAPTURED_RESPONSE_BYTES:
                    raise AssertionError("Test response exceeded the 16 MiB capture limit.")
            messages.append(message)

        await self.application(
            {
                "type": "http",
                "asgi": {"version": "3.0"},
                "method": method.upper(),
                "path": unquote(raw_path, encoding="utf-8", errors="strict"),
                "raw_path": raw_path_bytes,
                "scheme": url.scheme or "http",
                "http_version": "1.1",
                "root_path": "",
                "client": ("127.0.0.1", 54321),
                "query_string": query_bytes,
                "headers": encoded_headers,
            },
            receive,
            send,
        )
        if not messages or messages[0]["type"] != "http.response.start":
            raise AssertionError("ASGI application did not start an HTTP response.")
        if messages[-1]["type"] != "http.response.body" or messages[-1].get("more_body", False):
            raise AssertionError("ASGI response stream did not finish.")
        status = messages[0].get("status")
        if isinstance(status, bool) or not isinstance(status, int) or not 200 <= status <= 599:
            raise AssertionError("ASGI application returned an invalid final status.")
        try:
            response_headers = Headers(
                [
                    (name.decode("latin-1"), value.decode("latin-1"))
                    for name, value in messages[0]["headers"]
                ]
            )
        except (KeyError, TypeError, UnicodeDecodeError) as exc:
            raise AssertionError("ASGI application returned invalid response headers.") from exc
        response_body = b"".join(frame.get("body", b"") for frame in messages[1:])
        return TestResponse(status, response_headers, response_body)


__all__ = ["TestClient", "TestResponse"]
