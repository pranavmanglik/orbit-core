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
"""HTTP ASGI runtime with bounded requests, scoped dependencies and authenticated dispatch."""

from __future__ import annotations

import asyncio
import inspect
import logging
import re
import sys
from dataclasses import replace
from functools import partial
from ipaddress import ip_address, ip_network
from time import monotonic
from typing import TYPE_CHECKING, Any, Literal
from urllib.parse import unquote_to_bytes
from uuid import uuid4

from pydantic import ValidationError

from orbit._limits import _MAX_CORE_CAPACITY, safe_exception_type_name
from orbit.asgi.lifespan import handle_lifespan
from orbit.asgi.middleware import Middleware, NextHandler
from orbit.asgi.request import MAX_PATH_BYTES, Headers, HTTPError, Request
from orbit.asgi.response import Response
from orbit.asgi.types import Receive, Scope, Send
from orbit.diagnostics.models import RequestRecord
from orbit.diagnostics.tracing import Tracer
from orbit.errors import ErrorCategory, OrbitProblem, RoutingError, SecurityError
from orbit.lifecycle import LifecyclePhase
from orbit.routing import Router
from orbit.security.context import bind_principal, current_principal, reset_principal
from orbit.security.contracts import Authenticator, RouteAuthorizer
from orbit.types import RequestId, new_request_id

if TYPE_CHECKING:
    from orbit.application import Application
_LOG = logging.getLogger(__name__)
_MAX_REQUEST_FRAMES = 100_000
_MAX_REQUEST_HEADERS = 1_000


class _Disconnected(Exception):
    """Internal control flow: the peer disconnected before request processing."""


class ASGIApplication:
    """Serve HTTP and lifespan using one composed Core application.

    The host must support lifespan. Requests are bounded by size, duration and concurrency.
    Authentication and route authorization are explicit extension hooks; there is no permissive
    fallback for protected routes. Request scopes live through streaming responses and close on
    success, failure or disconnect.
    """

    def __init__(
        self,
        application: Application,
        router: Router | None = None,
        *,
        authenticator: Authenticator | None = None,
        authorizer: RouteAuthorizer | None = None,
        tracer: Tracer | None = None,
    ) -> None:
        from orbit.application import Application

        if not isinstance(application, Application):
            raise TypeError("ASGIApplication requires an Application instance.")
        if router is not None and not isinstance(router, Router):
            raise TypeError("ASGIApplication router must be a Router instance.")
        if authenticator is not None and not isinstance(authenticator, Authenticator):
            raise TypeError("ASGIApplication authenticator must implement Authenticator.")
        if authorizer is not None and not isinstance(authorizer, RouteAuthorizer):
            raise TypeError("ASGIApplication authorizer must implement RouteAuthorizer.")
        if tracer is not None and not isinstance(tracer, Tracer):
            raise TypeError("ASGIApplication tracer must implement Tracer.")
        self._application = application
        self._router = router if router is not None else application.router
        self._authenticator = authenticator
        self._authorizer = authorizer
        self._tracer = tracer
        self._middleware: list[Middleware] = []
        self._requests: set[asyncio.Task[Any]] = set()
        self._detached_middleware_hooks: set[asyncio.Task[Any]] = set()
        self._draining = False
        self._shutdown_task: asyncio.Task[None] | None = None

    @property
    def router(self) -> Router:
        """Expose the application's shared router."""
        return self._router

    def add_middleware(self, middleware: Middleware) -> None:
        """Append middleware during composition; first registered executes outermost."""
        self._application.lifecycle.require(LifecyclePhase.CREATED)
        if not callable(middleware):
            raise TypeError("Middleware must be callable.")
        if any(
            getattr(middleware, hook_name, None) is not None
            and not callable(getattr(middleware, hook_name))
            for hook_name in ("startup", "shutdown")
        ):
            raise TypeError("Middleware lifecycle hooks must be callable.")
        if len(self._middleware) >= _MAX_CORE_CAPACITY:
            raise RuntimeError("Middleware capacity reached.")
        self._middleware.append(middleware)

    async def shutdown(self) -> None:
        """Reject new work, drain bounded requests, then close application resources."""
        if asyncio.current_task() in self._requests:
            raise RuntimeError("Request handlers cannot await runtime shutdown.")
        if self._shutdown_task is None:
            self._draining = True
            self._shutdown_task = asyncio.create_task(self._shutdown())
        cancelled = False
        while not self._shutdown_task.done():
            try:
                await asyncio.shield(self._shutdown_task)
            except asyncio.CancelledError:
                cancelled = True
        self._shutdown_task.result()
        if cancelled:
            raise asyncio.CancelledError

    async def _startup(self) -> None:
        """Start the application, then middleware resources in registration order."""
        await self._application.startup()
        started: list[Middleware] = []
        try:
            for middleware in self._middleware:
                started.append(middleware)
                hook = getattr(middleware, "startup", None)
                if hook is not None:
                    await self._call_middleware_hook(hook)
        except BaseException:
            cleanup_failures: list[BaseException] = []
            for middleware in reversed(started):
                hook = getattr(middleware, "shutdown", None)
                if hook is not None:
                    try:
                        await self._call_middleware_hook(hook)
                    except BaseException as exc:
                        # Rollback is best effort, but every already-started middleware
                        # still receives a shutdown attempt before the original startup
                        # failure is re-raised to the host.
                        cleanup_failures.append(exc)
            try:
                await self._application.stop()
            except BaseException as exc:
                cleanup_failures.append(exc)
            for failure in cleanup_failures:
                _LOG.error(
                    "Startup cleanup failed after middleware startup error",
                    extra={"error_type": safe_exception_type_name(failure)},
                )
            raise

    async def _shutdown_middleware(self) -> None:
        """Stop middleware in reverse registration order before application cleanup."""
        failures: list[BaseException] = []
        for middleware in reversed(self._middleware):
            hook = getattr(middleware, "shutdown", None)
            if hook is None:
                continue
            try:
                await self._call_middleware_hook(hook)
            except asyncio.CancelledError as exc:
                # A hook may use cancellation as its own failure signal. Preserve it as
                # cleanup evidence, but continue so application-owned resources still close.
                failures.append(exc)
            except Exception as exc:
                failures.append(exc)
        application_failure: BaseException | None = None
        try:
            await self._application.stop()
        except asyncio.CancelledError as exc:
            application_failure = exc
            failures.append(exc)
        except Exception as exc:
            # Application cleanup is independent of middleware cleanup. Preserve both
            # failures so an operator can diagnose the complete shutdown outcome.
            application_failure = exc
            failures.append(exc)
        if failures:
            title = (
                "Application shutdown failed: cleanup failed"
                if application_failure is not None
                else "Middleware shutdown failed"
            )
            raise BaseExceptionGroup(title, failures)

    async def _call_middleware_hook(self, hook: Any) -> None:
        """Run one middleware lifecycle hook within the application deadline."""
        result = hook()
        if not inspect.isawaitable(result):
            return
        task = asyncio.ensure_future(result)
        try:
            done, _ = await asyncio.wait(
                {task}, timeout=self._application.config.application.lifecycle_timeout
            )
            if not done:
                self._detach_middleware_hook(task)
                raise TimeoutError("Middleware lifecycle hook exceeded its deadline.")
            task.result()
        except asyncio.CancelledError:
            if task.done():
                self._retire_middleware_hook(task)
            else:
                self._detach_middleware_hook(task)
            raise

    def _detach_middleware_hook(self, task: asyncio.Task[Any]) -> None:
        """Detach a cancellation-resistant hook while retaining its eventual result."""
        self._detached_middleware_hooks.add(task)
        task.cancel()
        task.add_done_callback(self._retire_middleware_hook)

    def _retire_middleware_hook(self, task: asyncio.Task[Any]) -> None:
        """Release a detached hook and consume late exceptions without warnings."""
        self._detached_middleware_hooks.discard(task)
        _consume_task_result(task)

    async def _shutdown(self) -> None:
        self._draining = True
        pending = tuple(self._requests)
        if pending:
            timeout = self._application.config.application.lifecycle_timeout
            _, unfinished = await asyncio.wait(pending, timeout=timeout)
            for task in unfinished:
                task.cancel()
            if unfinished:
                _, unfinished = await asyncio.wait(unfinished, timeout=timeout)
                if unfinished:
                    # Python cannot forcefully terminate a coroutine that suppresses
                    # cancellation. Keep worker shutdown bounded and consume eventual
                    # failures while the request task finishes independently.
                    for task in unfinished:
                        task.add_done_callback(_consume_task_result)
                    _LOG.error(
                        "HTTP requests did not terminate before shutdown deadline",
                        extra={"count": len(unfinished)},
                    )
        await self._shutdown_middleware()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Handle one ASGI scope and preserve cancellation/disconnect cleanup semantics."""
        from orbit.runtime.context import bind_request_id, reset_request_id

        if not isinstance(scope, dict):
            raise RuntimeError("ASGI scope must be a mapping.")
        kind = scope.get("type")
        if not isinstance(kind, str):
            raise RuntimeError("ASGI scope type is required.")
        if kind == "lifespan":
            await handle_lifespan(
                self._application,
                receive,
                send,
                startup=self._startup,
                shutdown=self.shutdown,
            )
            return
        if kind == "websocket":
            await send({"type": "websocket.close", "code": 1003})
            return
        if kind != "http":
            # Scope types originate at the host boundary. Do not interpolate an unbounded
            # or attacker-controlled value into an exception or host log message.
            raise RuntimeError("Unsupported ASGI scope type.")
        config = self._application.config.application
        rejected = self._draining or len(self._requests) >= config.max_concurrent_requests
        task = asyncio.current_task()
        if task is None:
            raise RuntimeError("ASGI request handling requires an active task.")
        if not rejected:
            self._requests.add(task)
        request_id: RequestId = new_request_id()
        request_id_text = str(request_id)
        begin = monotonic()
        status = 499
        started = False
        outcome: Literal["completed", "failed", "cancelled", "disconnected"] = "completed"
        request_token = bind_request_id(request_id)
        from orbit.runtime.context import (
            bind_correlation_id,
            bind_span_id,
            bind_trace_id,
            reset_correlation_id,
            reset_span_id,
            reset_trace_id,
        )

        correlation_token = bind_correlation_id(request_id_text)
        span_token = bind_span_id(uuid4().hex[:16])
        trace_token = bind_trace_id(self._trace_id(scope))

        async def tracked_send(message: dict[str, Any]) -> None:
            """Forward an ASGI message while recording response framing and byte limits."""
            nonlocal started, status
            if message["type"] == "http.response.start":
                headers = message.get("headers")
                if not isinstance(headers, list) or any(
                    not isinstance(pair, (list, tuple))
                    or len(pair) != 2
                    or not isinstance(pair[0], bytes)
                    or not isinstance(pair[1], bytes)
                    for pair in headers
                ):
                    raise ValueError("Invalid response headers.")
                # These headers are owned by the runtime. Remove handler values
                # before adding canonical correlation and browser hardening
                # values, avoiding ambiguous duplicates downstream.
                headers[:] = [
                    (key, value)
                    for key, value in headers
                    if key.lower() not in {b"x-request-id", b"x-content-type-options"}
                ]
                headers.extend(
                    [
                        (b"x-request-id", request_id_text.encode()),
                        (b"x-content-type-options", b"nosniff"),
                    ]
                )
                if (
                    len(headers) > Response.MAX_HEADER_COUNT
                    or sum(len(key) + len(value) + 2 for key, value in headers)
                    > Response.MAX_HEADER_BYTES
                ):
                    raise ValueError("Response headers exceed the configured safety limit.")
                started = True
                status = message["status"]
            try:
                await send(message)
            except OSError as exc:
                raise _Disconnected from exc

        # Runtime/security context is always restored, including on authentication failures.
        principal_token = bind_principal(None)
        try:
            from orbit.runtime.context import bind_application, reset_application

            application_token = bind_application(self._application)
            try:
                async with asyncio.timeout(config.request_timeout):
                    if rejected:
                        await self._send(
                            Response.json({"code": "runtime.unavailable"}, status=503),
                            scope.get("method", "GET"),
                            tracked_send,
                            max_response_bytes=config.max_response_bytes,
                            cleanup_timeout=config.request_timeout,
                        )
                        return
                    request = await self._read_request(scope, receive, request_id)
                    async with self._application.container.scope() as container:
                        request = replace(request, container=container)
                        if self._authenticator is not None:
                            principal = await self._authenticator.authenticate(request)
                            bind_principal(principal)
                        response = await self._dispatch_traced(request)
                        await self._send(
                            response,
                            request.method,
                            tracked_send,
                            max_response_bytes=config.max_response_bytes,
                            cleanup_timeout=config.request_timeout,
                        )
            finally:
                reset_application(application_token)
        except _Disconnected:
            outcome = "disconnected"
            return
        except asyncio.CancelledError:
            outcome = "cancelled"
            raise
        except Exception as exc:
            outcome = "failed"
            if started:
                _LOG.exception("Response interrupted", extra={"request_id": request_id_text})
                raise
            error_headers: list[tuple[str, str]] = []
            if isinstance(exc, HTTPError):
                status, code, message = exc.status, exc.code, str(exc)
            elif isinstance(exc, ValidationError):
                status, code, message = 422, "request.validation", "Request validation failed."
            elif isinstance(exc, SecurityError):
                status = 401 if current_principal() is None else 403
                code, message = "security.forbidden", "Authentication or authorization required."
                challenge = getattr(self._authenticator, "challenge", None)
                if status == 401 and isinstance(challenge, str):
                    error_headers.append(("www-authenticate", challenge))
            elif isinstance(exc, TimeoutError):
                status, code, message = 504, "request.timeout", "Request deadline exceeded."
            else:
                _LOG.exception("Unhandled request failure", extra={"request_id": request_id_text})
                status, code, message = 500, "runtime.internal", "Internal server error."
            try:
                async with asyncio.timeout(config.request_timeout):
                    await self._send(
                        Response.json(
                            {"code": code, "message": message, "request_id": request_id_text},
                            status=status,
                            headers=error_headers,
                        ),
                        scope.get("method", "GET"),
                        tracked_send,
                        max_response_bytes=config.max_response_bytes,
                        cleanup_timeout=config.request_timeout,
                    )
            except _Disconnected:
                outcome = "disconnected"
                return
        finally:
            reset_principal(principal_token)
            self._requests.discard(task)
            self._application.diagnostics.record_request(
                RequestRecord(
                    request_id=request_id,
                    method=self._diagnostic_method(scope),
                    status=status,
                    duration_seconds=monotonic() - begin,
                    outcome=outcome,
                )
            )
            reset_request_id(request_token)
            reset_correlation_id(correlation_token)
            reset_span_id(span_token)
            reset_trace_id(trace_token)

    @staticmethod
    def _diagnostic_method(scope: Scope) -> str:
        """Return a bounded method token for diagnostics, even after wire validation fails."""
        method = scope.get("method")
        if isinstance(method, str) and re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]{1,32}", method):
            return method.upper()
        return "INVALID"

    @staticmethod
    def _trace_id(scope: Scope) -> str | None:
        """Accept one valid W3C trace ID without scanning an overlong header scope."""
        raw_headers = scope.get("headers", [])
        if not isinstance(raw_headers, (list, tuple)):
            return None
        if len(raw_headers) > _MAX_REQUEST_HEADERS:
            return None
        trace_id: str | None = None
        for pair in raw_headers:
            if (
                not isinstance(pair, (list, tuple))
                or len(pair) != 2
                or not isinstance(pair[0], bytes)
                or not isinstance(pair[1], bytes)
            ):
                return None
            key, value = pair
            if key.lower() != b"traceparent":
                continue
            if trace_id is not None:
                return None
            try:
                version, trace, span, flags = value.decode("ascii").split("-")
            except (UnicodeDecodeError, ValueError):
                return None
            if (
                version == "00"
                and len(trace) == 32
                and len(span) == 16
                and len(flags) == 2
                and all(character in "0123456789abcdef" for character in trace + span + flags)
                and any(character != "0" for character in trace)
                and any(character != "0" for character in span)
            ):
                trace_id = str(trace)
                continue
            return None
        return trace_id

    async def _read_request(self, scope: Scope, receive: Receive, request_id: RequestId) -> Request:
        limit = self._application.config.application.max_body_bytes
        header_limit = self._application.config.application.max_header_bytes
        method = scope.get("method")
        if not isinstance(method, str) or not re.fullmatch(
            r"[!#$%&'*+.^_`|~0-9A-Za-z-]{1,32}", method
        ):
            raise HTTPError(400, "request.method", "Invalid HTTP method.")
        raw_headers = scope.get("headers", [])
        if not isinstance(raw_headers, (list, tuple)):
            raise HTTPError(400, "request.headers", "Invalid HTTP headers.")
        if len(raw_headers) > _MAX_REQUEST_HEADERS:
            raise HTTPError(431, "request.headers-too-many", "Too many request headers.")
        header_size = 0
        decoded_headers: list[tuple[str, str]] = []
        for pair in raw_headers:
            if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                raise HTTPError(400, "request.headers", "Invalid HTTP headers.")
            key, value = pair
            if not isinstance(key, bytes) or not isinstance(value, bytes):
                raise HTTPError(400, "request.headers", "Invalid HTTP headers.")
            header_size += len(key) + len(value) + 2
            if header_size > header_limit:
                raise HTTPError(431, "request.headers-too-large", "Request headers are too large.")
            decoded_key = key.decode("latin-1")
            decoded_value = value.decode("latin-1")
            if not re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", decoded_key) or any(
                (ord(character) < 32 and ord(character) != 9) or ord(character) == 127
                for character in decoded_value
            ):
                raise HTTPError(400, "request.headers", "Invalid HTTP headers.")
            decoded_headers.append((decoded_key, decoded_value))
        headers = Headers(decoded_headers)
        self._validate_host_header(headers)
        if len(headers.getall("content-type")) > 1:
            raise HTTPError(
                400,
                "request.content-type",
                "Duplicate Content-Type headers are not allowed.",
            )
        if len(headers.getall("cookie")) > 1:
            raise HTTPError(400, "request.cookie", "Duplicate Cookie headers are not allowed.")
        lengths = headers.getall("content-length")
        if (
            len(lengths) > 1
            or (lengths and not lengths[0].isascii())
            or (lengths and not lengths[0].isdigit())
        ):
            raise HTTPError(400, "request.content-length", "Invalid Content-Length.")
        if lengths and (len(lengths[0]) > 20 or int(lengths[0]) > limit):
            raise HTTPError(413, "request.too-large", "Request body is too large.")
        chunks = bytearray()
        frame_count = 0
        while True:
            message = await receive()
            if not isinstance(message, dict) or not isinstance(message.get("type"), str):
                raise HTTPError(400, "request.protocol", "Invalid request message.")
            if message["type"] == "http.disconnect":
                raise _Disconnected
            if message["type"] != "http.request":
                raise HTTPError(400, "request.protocol", "Unexpected request message.")
            frame_count += 1
            if frame_count > _MAX_REQUEST_FRAMES:
                raise HTTPError(400, "request.protocol", "Too many request body frames.")
            body = message.get("body", b"")
            if not isinstance(body, bytes) or not isinstance(message.get("more_body", False), bool):
                raise HTTPError(400, "request.protocol", "Invalid request body frame.")
            if len(chunks) + len(body) > limit:
                raise HTTPError(413, "request.too-large", "Request body is too large.")
            chunks.extend(body)
            if not message.get("more_body", False):
                break
        if lengths and len(chunks) != int(lengths[0]):
            raise HTTPError(400, "request.content-length", "Content-Length does not match body.")
        raw_path = scope.get("path")
        if not isinstance(raw_path, str):
            raise HTTPError(400, "request.path", "Invalid HTTP path.")
        try:
            decoded_path_bytes = raw_path.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise HTTPError(400, "request.path", "Invalid HTTP path.") from exc
        if len(decoded_path_bytes) > MAX_PATH_BYTES:
            raise HTTPError(414, "request.path-too-long", "Request path is too long.")
        encoded_path = scope.get("raw_path")
        if encoded_path is not None:
            if not isinstance(encoded_path, bytes):
                raise HTTPError(400, "request.path", "Invalid raw HTTP path.")
            if len(encoded_path) > MAX_PATH_BYTES:
                raise HTTPError(414, "request.path-too-long", "Request path is too long.")
            if self._validate_raw_path(encoded_path) != raw_path:
                raise HTTPError(400, "request.invalid-path", "Request path is not canonical.")
        query_string = scope.get("query_string", b"")
        if not isinstance(query_string, bytes):
            raise HTTPError(400, "request.query", "Invalid query string.")
        if len(query_string) > 64 * 1024:
            raise HTTPError(414, "request.query-too-large", "Query string is too large.")
        path = raw_path
        root = scope.get("root_path", "")
        if not isinstance(root, str):
            raise HTTPError(400, "request.path", "Invalid HTTP root path.")
        if root:
            try:
                root_size = len(root.encode("utf-8"))
            except UnicodeEncodeError as exc:
                raise HTTPError(400, "request.path", "Invalid HTTP root path.") from exc
            if root_size > MAX_PATH_BYTES:
                raise HTTPError(414, "request.path-too-long", "Request root path is too long.")
            self._validate_request_path(root)
            if root != "/" and root.endswith("/"):
                raise HTTPError(400, "request.path", "Invalid HTTP root path.")
            if root != "/" and path != root and not path.startswith(root + "/"):
                raise HTTPError(400, "request.path", "HTTP path is outside the root path.")
        if root and (path == root or path.startswith(root + "/")):
            path = path[len(root) :] or "/"
        self._validate_request_path(path)
        # Resolve proxy-derived identity once so host and port share one fail-closed decision.
        client_host, client_port = self._client(scope, headers)
        return Request(
            method=method.upper(),
            path=path,
            headers=headers,
            body=bytes(chunks),
            query_string=query_string,
            request_id=request_id,
            root_path=root,
            client_host=client_host,
            client_port=client_port,
            scheme=self._scheme(scope, headers),
        )

    @staticmethod
    def _validate_host_header(headers: Headers) -> None:
        """Reject ambiguous or malformed HTTP authority values before dispatch."""
        values = headers.getall("host")
        if len(values) > 1:
            raise HTTPError(400, "request.host", "Duplicate Host headers are not allowed.")
        if not values:
            return
        value = values[0]
        if (
            not value
            or value != value.strip()
            or len(value) > 255
            or any(ord(character) < 32 or ord(character) == 127 for character in value)
        ):
            raise HTTPError(400, "request.host", "Invalid Host header.")
        if value.startswith("["):
            closing = value.find("]")
            if closing <= 1 or value[closing + 1 :].count(":") > 1:
                raise HTTPError(400, "request.host", "Invalid Host header.")
            address = value[1:closing]
            suffix = value[closing + 1 :]
            try:
                parsed = ip_address(address)
            except ValueError as exc:
                raise HTTPError(400, "request.host", "Invalid Host header.") from exc
            if parsed.version != 6 or "%" in address:
                raise HTTPError(400, "request.host", "Invalid Host header.")
            if suffix:
                ASGIApplication._validate_host_port(suffix[1:] if suffix.startswith(":") else "")
            return
        if value.count(":") > 1:
            raise HTTPError(400, "request.host", "IPv6 Host values must be bracketed.")
        host, separator, port = value.partition(":")
        if separator:
            ASGIApplication._validate_host_port(port)
        if not host or len(host) > 253:
            raise HTTPError(400, "request.host", "Invalid Host header.")
        if re.fullmatch(r"(?:%[0-9A-Fa-f]{2}|[A-Za-z0-9._~!$&'()*+,;=-])+", host) is None:
            raise HTTPError(400, "request.host", "Invalid Host header.")

    @staticmethod
    def _validate_host_port(port: str) -> None:
        """Validate an optional numeric authority port without implicit coercion."""
        if not port.isascii() or not 1 <= len(port) <= 5 or not port.isdigit():
            raise HTTPError(400, "request.host", "Invalid Host port.")
        if int(port) > 65535:
            raise HTTPError(400, "request.host", "Invalid Host port.")

    @staticmethod
    def _validate_request_path(path: str) -> None:
        """Reject ambiguous or unsafe decoded paths before they reach application routing."""
        if (
            not path.startswith("/")
            or "//" in path
            or "\\" in path
            or "?" in path
            or "#" in path
            or any(ord(character) < 32 or ord(character) == 127 for character in path)
            or any(segment in {".", ".."} for segment in path.split("/"))
        ):
            raise HTTPError(400, "request.invalid-path", "Request path is not canonical.")

    @staticmethod
    def _validate_raw_path(raw_path: bytes) -> str:
        """Reject ambiguous raw URL paths before any downstream path decoding.

        ASGI exposes both ``path`` (decoded text) and ``raw_path`` (the original URL
        bytes). The two values must not disagree about routing boundaries. In
        particular, an encoded slash or backslash must never become a new path
        segment after a proxy or application performs another decode. Dot segments,
        query/fragment delimiters, controls, and malformed escapes are rejected at
        this boundary as well.

        A segment is decoded only to identify unsafe bytes. Ordinary encoded
        characters, including a dot inside a name such as ``file%2Etxt``, remain
        valid. The decoded UTF-8 result is returned so the host-supplied
        ``scope['path']`` can be checked for exact agreement.
        """
        if not isinstance(raw_path, bytes) or not raw_path.startswith(b"/"):
            raise HTTPError(400, "request.invalid-path", "Request path is not canonical.")
        if (
            b"?" in raw_path
            or b"#" in raw_path
            or b"\\" in raw_path
            or b"//" in raw_path
            or re.search(rb"%(?![0-9A-Fa-f]{2})", raw_path)
        ):
            raise HTTPError(400, "request.invalid-path", "Request path is not canonical.")
        try:
            decoded_path = unquote_to_bytes(raw_path).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise HTTPError(400, "request.invalid-path", "Request path is not canonical.") from exc
        for segment in raw_path.split(b"/"):
            decoded = unquote_to_bytes(segment)
            if (
                decoded in {b".", b".."}
                or b"/" in decoded
                or b"\\" in decoded
                or b"?" in decoded
                or b"#" in decoded
                or any(byte < 32 or byte == 127 for byte in decoded)
            ):
                raise HTTPError(400, "request.invalid-path", "Request path is not canonical.")
        return decoded_path

    def _client(self, scope: Scope, headers: Headers) -> tuple[str | None, int | None]:
        host, port = self._client_address(scope)
        config = self._application.config.application
        if not config.trust_forwarded_headers or not self._trusted(host, config.trusted_proxies):
            return host, port
        if not self._proxy_headers_are_unambiguous(headers):
            return host, port
        forwarded_for, _ = self._forwarded(headers)
        forwarded = forwarded_for or self._single_proxy_header(headers, "x-forwarded-for")
        if forwarded:
            candidate = forwarded.split(",", 1)[0].strip()
            try:
                ip_address(candidate)
            except ValueError:
                # A trusted proxy may still send malformed forwarding metadata. Fail closed by
                # retaining the socket peer instead of allowing unvalidated identity text through.
                pass
            else:
                host, port = candidate, None
        return host, port

    def _scheme(self, scope: Scope, headers: Headers) -> str:
        raw_scheme = scope.get("scheme", "http")
        if not isinstance(raw_scheme, str) or raw_scheme.lower() not in {"http", "https"}:
            raise HTTPError(400, "request.scheme", "Invalid HTTP scheme.")
        scheme = raw_scheme.lower()
        config = self._application.config.application
        if config.trust_forwarded_headers and self._trusted(
            self._client_address(scope)[0], config.trusted_proxies
        ):
            if not self._proxy_headers_are_unambiguous(headers):
                return scheme
            _, forwarded = self._forwarded(headers)
            forwarded = (
                forwarded
                or (self._single_proxy_header(headers, "x-forwarded-proto", default="") or "")
                .split(",", 1)[0]
                .strip()
                .lower()
            )
            if forwarded in {"http", "https"}:
                scheme = forwarded
        return scheme

    @staticmethod
    def _client_address(scope: Scope) -> tuple[str | None, int | None]:
        """Validate the optional ASGI client tuple before using it for identity decisions."""
        value = scope.get("client")
        if value is None:
            return None, None
        if not isinstance(value, (tuple, list)) or len(value) != 2:
            raise HTTPError(400, "request.client", "Invalid client address.")
        host, port = value
        if host is not None:
            if not isinstance(host, str):
                raise HTTPError(400, "request.client", "Invalid client address.")
            if (
                not host
                or len(host) > 255
                or "%" in host
                or any(
                    character.isspace() or ord(character) < 32 or ord(character) == 127
                    for character in host
                )
            ):
                raise HTTPError(400, "request.client", "Invalid client address.")
        if port is not None and (
            isinstance(port, bool) or not isinstance(port, int) or not 0 <= port <= 65535
        ):
            raise HTTPError(400, "request.client", "Invalid client port.")
        return host, port

    @staticmethod
    def _forwarded(headers: Headers) -> tuple[str | None, str | None]:
        """Parse the first RFC 7239 element, ignoring malformed values safely."""
        value = ASGIApplication._single_proxy_header(headers, "forwarded", default="")
        if not value:
            return None, None
        parameters: dict[str, str] = {}
        seen_parameters: set[str] = set()
        for item in value.split(",", 1)[0].split(";"):
            key, separator, candidate = item.strip().partition("=")
            normalized_key = key.lower()
            if not separator or normalized_key not in {"for", "proto"}:
                continue
            if normalized_key in seen_parameters:
                return None, None
            seen_parameters.add(normalized_key)
            candidate = candidate.strip()
            if len(candidate) >= 2 and candidate[0] == candidate[-1] == '"':
                candidate = candidate[1:-1]
            parameters[normalized_key] = candidate
        forwarded_for = parameters.get("for")
        if forwarded_for is None or forwarded_for in {"", "unknown"}:
            forwarded_for = None
        elif forwarded_for.startswith("["):
            closing = forwarded_for.find("]")
            if closing < 0:
                forwarded_for = None
            else:
                host = forwarded_for[1:closing]
                suffix = forwarded_for[closing + 1 :]
                if suffix and (
                    not suffix.startswith(":")
                    or not suffix[1:].isdigit()
                    or len(suffix[1:]) > 5
                    or not 0 <= int(suffix[1:]) <= 65535
                ):
                    forwarded_for = None
                elif "%" in host:
                    # RFC 7239 carries an IP address, not a host-interface scoped
                    # IPv6 literal. Python's ipaddress module accepts the latter.
                    forwarded_for = None
                else:
                    forwarded_for = host
        elif forwarded_for.count(":") == 1:
            host, port, separator = forwarded_for.rpartition(":")
            if not separator or not port.isdigit() or len(port) > 5 or not 0 <= int(port) <= 65535:
                forwarded_for = None
            else:
                forwarded_for = host
        elif "%" in forwarded_for:
            forwarded_for = None
        try:
            if forwarded_for is not None:
                ip_address(forwarded_for)
        except (TypeError, ValueError):
            forwarded_for = None
        proto = parameters.get("proto", "").lower()
        return forwarded_for, proto if proto in {"http", "https"} else None

    @staticmethod
    def _single_proxy_header(
        headers: Headers, name: str, *, default: str | None = None
    ) -> str | None:
        """Return one forwarding field only when the header is present exactly once."""
        values = headers.getall(name)
        return values[0] if len(values) == 1 else default

    @staticmethod
    def _proxy_headers_are_unambiguous(headers: Headers) -> bool:
        """Reject repeated forwarding fields before trusted proxy metadata is interpreted.

        A deployment may receive a valid comma-separated proxy chain in one field. Repeated
        fields are rejected instead of selecting the first value because an intermediary could
        otherwise disagree with another proxy while Core silently trusts only one of them.
        """
        return all(
            len(headers.getall(name)) <= 1
            for name in ("forwarded", "x-forwarded-for", "x-forwarded-proto")
        )

    @staticmethod
    def _trusted(host: object, networks: tuple[str, ...]) -> bool:
        if not isinstance(host, str) or "%" in host:
            return False
        try:
            address = ip_address(host)
        except ValueError:
            return False
        return any(address in ip_network(network, strict=False) for network in networks)

    async def _dispatch_traced(self, request: Request) -> Response:
        """Dispatch with route-template metadata, never a raw user-controlled path."""
        if self._tracer is None:
            return await self._dispatch(request)
        route_template: str | None = None
        is_core_endpoint = request.path in {
            "/openapi.json",
            "/health/live",
            "/health/ready",
        }
        if not is_core_endpoint:
            try:
                route, _ = self._router.match(request.method, request.path)
            except RoutingError:
                # Unmatched requests have no safe route template to export.
                pass
            else:
                route_template = route.metadata.path
        async with self._tracer.start_span(f"http.{request.method.lower()}") as span:
            span.set_attribute("http.method", request.method)
            if route_template is not None:
                span.set_attribute("http.route", route_template)
            response = await self._dispatch(request)
            span.set_attribute("http.status_code", response.status)
            span.set_status("error" if response.status >= 500 else "ok")
            return response

    async def _dispatch(self, request: Request) -> Response:
        async def endpoint(current: Request) -> Response:
            """Invoke the selected endpoint inside its request-owned dependency scope."""
            if current.path == "/openapi.json":
                if current.method not in {"GET", "HEAD"}:
                    return Response(status=405, headers={"allow": "GET, HEAD"})
                config = self._application.config.application
                return Response.json(
                    self._router.openapi(title=config.name, version="0.1.0"), status=200
                )
            if current.path in {"/health/live", "/health/ready"}:
                if current.method not in {"GET", "HEAD"}:
                    return Response(status=405, headers={"allow": "GET, HEAD"})
                if current.path == "/health/live":
                    return Response.json(
                        {"status": "healthy" if self._application.is_live else "unhealthy"},
                        status=200 if self._application.is_live else 503,
                    )
                report = await self._application.health()
                return Response.json(
                    {"status": report.status}, status=200 if self._application.is_ready else 503
                )
            if self._application.lifecycle.phase is not LifecyclePhase.RUNNING:
                return Response.json({"code": "runtime.not-ready"}, status=503)
            allowed = self._router.allowed_methods(current.path)
            if current.method == "OPTIONS" and allowed:
                return Response(status=204, headers={"allow": ", ".join(allowed)})
            try:
                route, parameters = self._router.match(current.method, current.path)
            except RoutingError as exc:
                if exc.problem.code == "routing.method-not-allowed":
                    return (
                        Response.json({"code": exc.problem.code}, status=405)
                        if not allowed
                        else (Response(status=405, headers={"allow": ", ".join(allowed)}))
                    )
                return Response.json({"code": exc.problem.code}, status=404)
            if route.metadata.roles:
                if self._authorizer is None:
                    raise SecurityError(
                        OrbitProblem(
                            code="security.forbidden",
                            message="An authorizer is required for this route.",
                            category=ErrorCategory.SECURITY,
                        )
                    )
                await self._authorizer.authorize_roles(current_principal(), route.metadata.roles)
            routed = replace(current, path_parameters=parameters)
            if route.request_model is not None:
                try:
                    routed = replace(routed, validated_body=routed.validate(route.request_model))
                except ValidationError as exc:
                    raise HTTPError(
                        422, "request.validation", "Request validation failed."
                    ) from exc

            async def route_handler(request: Request) -> Response:
                """Apply route validation and authorization before invoking the endpoint."""
                result = route.handler(request)
                return await result if inspect.isawaitable(result) else result

            handler = route_handler
            for route_middleware in reversed(route.middleware):
                next_handler = handler

                async def wrapped(
                    request: Request,
                    middleware: Middleware = route_middleware,
                    next_handler: NextHandler = next_handler,
                ) -> Response:
                    """Run one middleware layer and preserve the downstream response contract."""
                    return await middleware(request, next_handler)

                handler = wrapped
            response = await handler(routed)
            if not isinstance(response, Response):
                raise TypeError("Route handlers must return Response.")
            if route.response_model is not None:
                if not isinstance(response.headers, Headers):
                    raise TypeError("Responses must expose validated headers.")
                media = response.headers.get("content-type", "").partition(";")[0].lower()
                if media != "application/json" or response.stream is not None:
                    raise TypeError("Validated route responses must be buffered JSON.")
                try:
                    route.response_model.model_validate_json(response.body)
                except ValidationError as exc:
                    raise TypeError("Route response failed response_model validation.") from exc
            return response

        handler: NextHandler = endpoint
        for middleware in reversed(self._middleware):
            handler = partial(middleware, next_handler=handler)
        return await handler(request)

    @staticmethod
    async def _send(
        response: Response,
        method: str,
        send: Send,
        *,
        max_response_bytes: int | None = None,
        cleanup_timeout: float = 30,
    ) -> None:
        limit = Response.MAX_BODY_BYTES if max_response_bytes is None else max_response_bytes
        if response.stream is None and len(response.body) > limit:
            raise ValueError("Response body exceeds the configured safety limit.")
        # Error paths may reach here before request-method validation; malformed values
        # must not create a second exception while applying HEAD semantics.
        normalized_method = method.upper() if isinstance(method, str) else ""
        sent = 0
        try:
            await send(
                {
                    "type": "http.response.start",
                    "status": response.status,
                    "headers": response.wire_headers(),
                }
            )
            if normalized_method == "HEAD" or response.status in {204, 205, 304}:
                await send({"type": "http.response.body", "body": b"", "more_body": False})
            elif response.stream is not None:
                async for chunk in response.stream:
                    if not isinstance(chunk, bytes):
                        raise TypeError("Response streams must yield bytes.")
                    if sent + len(chunk) > limit:
                        raise ValueError("Response stream exceeds the configured safety limit.")
                    sent += len(chunk)
                    await send({"type": "http.response.body", "body": chunk, "more_body": True})
                await send({"type": "http.response.body", "body": b"", "more_body": False})
            else:
                await send(
                    {"type": "http.response.body", "body": response.body, "more_body": False}
                )
        finally:
            if response.stream is not None:
                close = getattr(response.stream, "aclose", None)
                if close is not None:
                    primary_error = sys.exc_info()[1]
                    task = asyncio.create_task(close())
                    try:
                        await asyncio.wait_for(asyncio.shield(task), timeout=cleanup_timeout)
                    except TimeoutError:
                        task.add_done_callback(_consume_task_result)
                        _LOG.error("Response stream cleanup exceeded its deadline")
                    except asyncio.CancelledError:
                        task.add_done_callback(_consume_task_result)
                        raise
                    except Exception:
                        if primary_error is None:
                            raise
                        _LOG.exception(
                            "Response stream cleanup failed after the primary response error"
                        )


def _consume_task_result(task: asyncio.Task[Any]) -> None:
    """Consume an abandoned request task's eventual exception without warnings."""
    try:
        task.exception()
    except (asyncio.CancelledError, Exception):
        return


__all__ = ["ASGIApplication"]
