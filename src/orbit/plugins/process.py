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
"""Optional gRPC host for trusted, separately packaged process plugins."""

from __future__ import annotations

import asyncio
import hmac
import json
import os
import re
import secrets
from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import suppress
from typing import Any, cast

try:
    import grpc
except ImportError as exc:  # pragma: no cover - exercised in a base-only installation.
    raise ImportError(
        "Process plugins require the optional dependencies; install 'orbit-core[process-plugins]'."
    ) from exc

from google.protobuf.any_pb2 import Any as ProtobufAny
from google.protobuf.message import Message

from orbit.errors import ErrorCategory, OrbitProblem, PluginError
from orbit.health.models import HealthReport, HealthStatus
from orbit.plugins.metadata import PluginMetadata
from orbit.plugins.v1 import process_plugin_pb2 as wire
from orbit.plugins.v1 import process_plugin_pb2_grpc as wire_grpc

PROTOCOL_MAJOR = 1
PROTOCOL_MINOR = 0
_MAX_BOOTSTRAP_BYTES = 64 * 1024
_MAX_CONFIGURATION_BYTES = 1024 * 1024
_MAX_MESSAGE_BYTES = _MAX_CONFIGURATION_BYTES + _MAX_BOOTSTRAP_BYTES
_MAX_COMMAND_PARTS = 128
_MAX_COMMAND_BYTES = 32 * 1024
_MAX_ENVIRONMENT_BYTES = 64 * 1024
_ERROR_CODE = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")
_METHOD = re.compile(r"^/[A-Za-z][A-Za-z0-9_.]*/[A-Za-z][A-Za-z0-9_]*$")
_SENTINEL = object()


def _plugin_error(code: str, message: str) -> PluginError:
    return PluginError(
        OrbitProblem(
            code="plugin.process." + code,
            message=message,
            category=ErrorCategory.PLUGIN,
        )
    )


def _wire_metadata_matches(actual: wire.PluginMetadata, expected: PluginMetadata) -> bool:
    return (
        actual.id == str(expected.id)
        and actual.name == expected.name
        and actual.version == expected.version
        and actual.api_version == expected.api_version
        and tuple(actual.dependencies) == expected.dependencies
        and tuple(actual.optional_dependencies) == expected.optional_dependencies
        and tuple(actual.capabilities) == tuple(sorted(expected.capabilities))
        and tuple(actual.required_capabilities) == tuple(sorted(expected.required_capabilities))
    )


class _Session:
    """One authenticated bidi stream with bounded commands and correlated results."""

    def __init__(self, metadata: PluginMetadata, max_concurrency: int) -> None:
        self.metadata = metadata
        self.outgoing: asyncio.Queue[wire.CoreFrame | object] = asyncio.Queue(
            maxsize=max_concurrency
        )
        self.ready: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        self.closed: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        self.pending: dict[int, asyncio.Future[wire.PluginFrame]] = {}
        self.next_id = 0
        self.slots = asyncio.Semaphore(max_concurrency)

    async def read(self, messages: AsyncIterator[wire.PluginFrame]) -> None:
        """Validate the handshake and consume only bounded, correlated plugin frames."""
        try:
            first = True
            async for frame in messages:
                if first:
                    first = False
                    if frame.WhichOneof("payload") != "hello":
                        raise _plugin_error("handshake", "Plugin did not send a valid handshake.")
                    hello = frame.hello
                    if (
                        hello.protocol_major != PROTOCOL_MAJOR
                        or hello.protocol_minor > PROTOCOL_MINOR
                    ):
                        raise _plugin_error(
                            "protocol-version", "Plugin protocol version is unsupported."
                        )
                    if not _wire_metadata_matches(hello.metadata, self.metadata):
                        raise _plugin_error(
                            "metadata-mismatch", "Plugin metadata did not match its registration."
                        )
                    if not self.ready.done():
                        self.ready.set_result(None)
                    continue
                kind = frame.WhichOneof("payload")
                if kind not in {"command_result", "health", "capability_result"}:
                    raise _plugin_error(
                        "protocol-frame", "Plugin sent an unsupported protocol frame."
                    )
                if kind == "command_result":
                    request_id = frame.command_result.request_id
                elif kind == "health":
                    request_id = frame.health.request_id
                else:
                    request_id = frame.capability_result.request_id
                future = self.pending.get(request_id)
                if future is not None and not future.done():
                    future.set_result(frame)
            if first:
                raise _plugin_error("handshake", "Plugin closed before completing its handshake.")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if not self.ready.done():
                self.ready.set_exception(exc)
            for future in self.pending.values():
                if not future.done():
                    future.set_exception(
                        _plugin_error("disconnected", "Plugin process disconnected.")
                    )
        finally:
            if not self.closed.done():
                self.closed.set_result(None)
            if not self.outgoing.full():
                self.outgoing.put_nowait(_SENTINEL)

    async def call(
        self,
        frame: wire.CoreFrame,
        timeout: float,
        *,
        expected_payload: str,
    ) -> wire.PluginFrame:
        """Send one bounded in-flight request and match its response by request identifier."""
        acquired = False
        request_id = 0
        try:
            async with asyncio.timeout(timeout):
                await self.slots.acquire()
                acquired = True
                if self.closed.done():
                    raise _plugin_error("disconnected", "Plugin process is not connected.")
                self.next_id += 1
                request_id = self.next_id
                if frame.WhichOneof("payload") == "command":
                    frame.command.request_id = request_id
                elif frame.WhichOneof("payload") == "health_probe":
                    frame.health_probe.request_id = request_id
                elif frame.WhichOneof("payload") == "capability_call":
                    frame.capability_call.request_id = request_id
                future: asyncio.Future[wire.PluginFrame] = (
                    asyncio.get_running_loop().create_future()
                )
                self.pending[request_id] = future
                await self.outgoing.put(frame)
                result = await future
        except TimeoutError as exc:
            raise _plugin_error("timeout", "Plugin did not answer before its deadline.") from exc
        finally:
            if request_id:
                self.pending.pop(request_id, None)
            if acquired:
                self.slots.release()
        if result.WhichOneof("payload") != expected_payload:
            raise _plugin_error("protocol-frame", "Plugin replied with the wrong response type.")
        return result


class _ProcessPluginServicer(wire_grpc.ProcessPluginServicer):
    """Authenticate the local child process and bridge its stream to Core lifecycle calls."""

    def __init__(self, token: bytes, session: _Session) -> None:
        self._token = token
        self._session = session
        self._connected = False
        self._connection_lock = asyncio.Lock()

    async def Connect(
        self,
        request_iterator: AsyncIterator[wire.PluginFrame],
        context: grpc.aio.ServicerContext[Any, Any],
    ) -> AsyncIterator[wire.CoreFrame]:
        """Authenticate the one-use token and serve correlated process messages."""
        credentials = [
            value for key, value in (context.invocation_metadata() or ()) if key == "authorization"
        ]
        received = credentials[0] if len(credentials) == 1 else ""
        expected = "Bearer " + self._token.hex()
        if not isinstance(received, str) or not hmac.compare_digest(received, expected):
            await context.abort(grpc.StatusCode.UNAUTHENTICATED, "Plugin authentication failed.")
        async with self._connection_lock:
            if self._connected:
                await context.abort(
                    grpc.StatusCode.ALREADY_EXISTS, "Plugin connection already used."
                )
            self._connected = True
        reader = asyncio.create_task(self._session.read(request_iterator))
        try:
            await self._session.ready
            while True:
                frame = await self._session.outgoing.get()
                if frame is _SENTINEL:
                    return
                assert isinstance(frame, wire.CoreFrame)
                yield frame
        except asyncio.CancelledError:
            raise
        finally:
            if not reader.done():
                reader.cancel()
            await asyncio.gather(reader, return_exceptions=True)


class ProcessPlugin:
    """Supervise one trusted local gRPC plugin and adapt its lifecycle to PluginContract.

    The host starts the exact executable and argument vector supplied by the application; it does
    not invoke a shell. The child receives a one-use local endpoint and token on stdin, then proves
    its metadata over a long-lived gRPC stream. This provides process lifecycle isolation, not a
    sandbox: install and enable only plugin code trusted to run with the application's privileges.
    Configuration is sent only after authentication. The local transport is plaintext loopback and
    is intended for same-user trusted processes, not remote or mutually untrusted plugins.
    """

    def __init__(
        self,
        metadata: PluginMetadata,
        command: Sequence[str],
        *,
        configuration_json: bytes = b"{}",
        env: Mapping[str, str] | None = None,
        cwd: str | os.PathLike[str] | None = None,
        startup_timeout: float = 10.0,
        command_timeout: float = 10.0,
        shutdown_timeout: float = 3.0,
        max_concurrency: int = 16,
    ) -> None:
        self._metadata = PluginMetadata.model_validate(metadata)
        self._command = self._validate_command(command)
        self._configuration_json = self._validate_configuration(configuration_json)
        self._env = self._validate_env(env or {})
        self._cwd = None if cwd is None else os.fspath(cwd)
        self._startup_timeout = self._validate_timeout(startup_timeout, "startup")
        self._command_timeout = self._validate_timeout(command_timeout, "command")
        self._shutdown_timeout = self._validate_timeout(shutdown_timeout, "shutdown")
        if (
            isinstance(max_concurrency, bool)
            or not isinstance(max_concurrency, int)
            or not 1 <= max_concurrency <= 1024
        ):
            raise ValueError("Process plugin concurrency must be between 1 and 1024.")
        self._max_concurrency = max_concurrency
        self._server: grpc.aio.Server | None = None
        self._session: _Session | None = None
        self._process: asyncio.subprocess.Process | None = None
        self._lock = asyncio.Lock()

    @property
    def metadata(self) -> PluginMetadata:
        """Return the validated metadata snapshot used during Core registration."""
        return self._metadata

    def __repr__(self) -> str:
        return f"ProcessPlugin(name={self._metadata.name!r}, version={self._metadata.version!r})"

    async def activate(self) -> None:
        """Start the child, authenticate its stream, and send bounded configuration."""
        async with self._lock:
            if self._process is not None:
                raise _plugin_error("already-active", "Plugin process is already active.")
            token = secrets.token_bytes(32)
            session = _Session(self._metadata, self._max_concurrency)
            server = grpc.aio.server(
                options=(
                    ("grpc.max_receive_message_length", _MAX_MESSAGE_BYTES),
                    ("grpc.max_send_message_length", _MAX_MESSAGE_BYTES),
                ),
                maximum_concurrent_rpcs=1,
            )
            wire_grpc.add_ProcessPluginServicer_to_server(
                _ProcessPluginServicer(token, session), server
            )
            port = server.add_insecure_port("127.0.0.1:0")
            if port == 0:
                raise _plugin_error("bind", "Could not bind the local plugin endpoint.")
            try:
                self._server = server
                self._session = session
                await server.start()
                bootstrap = (
                    json.dumps(
                        {
                            "endpoint": f"127.0.0.1:{port}",
                            "token": token.hex(),
                            "metadata": {
                                "id": str(self._metadata.id),
                                "name": self._metadata.name,
                                "version": self._metadata.version,
                                "api_version": self._metadata.api_version,
                                "dependencies": self._metadata.dependencies,
                                "optional_dependencies": self._metadata.optional_dependencies,
                                "capabilities": sorted(self._metadata.capabilities),
                                "required_capabilities": sorted(
                                    self._metadata.required_capabilities
                                ),
                            },
                        },
                        separators=(",", ":"),
                        allow_nan=False,
                    ).encode("utf-8")
                    + b"\n"
                )
                if len(bootstrap) > _MAX_BOOTSTRAP_BYTES:
                    raise _plugin_error(
                        "metadata-size", "Plugin bootstrap metadata exceeds its size limit."
                    )
                try:
                    self._process = await asyncio.create_subprocess_exec(
                        *self._command,
                        stdin=asyncio.subprocess.PIPE,
                        stdout=asyncio.subprocess.DEVNULL,
                        stderr=asyncio.subprocess.DEVNULL,
                        cwd=self._cwd,
                        env=self._child_environment(),
                    )
                except OSError:
                    raise _plugin_error("spawn", "Plugin process could not be started.") from None
                assert self._process.stdin is not None
                self._process.stdin.write(bootstrap)
                await self._process.stdin.drain()
                self._process.stdin.close()
                await self._wait_for_handshake(session, self._process, self._startup_timeout)
                command = wire.CoreFrame(
                    command=wire.PluginCommand(
                        kind=wire.PluginCommand.KIND_ACTIVATE,
                        configuration_json=self._configuration_json,
                    )
                )
                result = await session.call(
                    command,
                    self._command_timeout,
                    expected_payload="command_result",
                )
                self._validate_command_result(result.command_result)
            except BaseException:
                await self._stop_locked(notify_child=False)
                raise

    async def deactivate(self) -> None:
        """Ask the child to stop, then always reap it and close the local gRPC server."""
        async with self._lock:
            if self._process is None:
                await self._stop_locked(notify_child=False)
                return
            failure: BaseException | None = None
            try:
                session = self._session
                if session is not None and not session.closed.done():
                    result = await session.call(
                        wire.CoreFrame(
                            command=wire.PluginCommand(kind=wire.PluginCommand.KIND_DEACTIVATE)
                        ),
                        self._command_timeout,
                        expected_payload="command_result",
                    )
                    self._validate_command_result(result.command_result)
            except BaseException as exc:
                failure = exc
            try:
                await self._stop_locked(notify_child=True)
            except BaseException as exc:
                if failure is None:
                    failure = exc
            if failure is not None:
                raise failure

    async def health(self) -> HealthReport:
        """Return a bounded health result from the running child process."""
        session = self._session
        process = self._process
        if session is None or process is None or process.returncode is not None:
            return HealthReport(
                status=HealthStatus.UNHEALTHY, message="Plugin process is not running."
            )
        try:
            response = await session.call(
                wire.CoreFrame(health_probe=wire.HealthProbe()),
                min(self._command_timeout, 2.0),
                expected_payload="health",
            )
        except Exception:
            return HealthReport(
                status=HealthStatus.UNHEALTHY, message="Plugin health check failed."
            )
        status = {
            wire.PluginHealth.STATUS_HEALTHY: HealthStatus.HEALTHY,
            wire.PluginHealth.STATUS_DEGRADED: HealthStatus.DEGRADED,
            wire.PluginHealth.STATUS_UNHEALTHY: HealthStatus.UNHEALTHY,
        }.get(response.health.status, HealthStatus.UNKNOWN)
        message = {
            HealthStatus.HEALTHY: "Plugin process is healthy.",
            HealthStatus.DEGRADED: "Plugin process is degraded.",
            HealthStatus.UNHEALTHY: "Plugin process is unhealthy.",
            HealthStatus.UNKNOWN: "Plugin process health is unknown.",
        }[status]
        return HealthReport(status=status, message=message)

    async def invoke(
        self,
        method: str,
        request: Message,
        response: Message,
        *,
        timeout: float | None = None,
    ) -> Message:
        """Call a capability's typed Protocol Buffer method over the supervised stream.

        Capability packages own the request/response message definitions and should expose their
        own typed adapters around this method. Core only validates a bounded canonical method name
        and transports protobuf ``Any`` values; it does not define capability behavior.
        """
        if not isinstance(method, str) or _METHOD.fullmatch(method) is None:
            raise ValueError("Capability method must be a canonical gRPC method path.")
        if not isinstance(request, Message) or not isinstance(response, Message):
            raise TypeError("Capability requests and responses must be Protocol Buffer messages.")
        deadline = (
            self._command_timeout
            if timeout is None
            else self._validate_timeout(timeout, "capability")
        )
        if request.ByteSize() > _MAX_CONFIGURATION_BYTES:
            raise ValueError("Capability request exceeds the 1 MiB message limit.")
        packed = ProtobufAny()
        packed.Pack(request)
        session = self._session
        if session is None:
            raise _plugin_error("not-active", "Plugin process is not active.")
        result = await session.call(
            wire.CoreFrame(capability_call=wire.CapabilityCall(method=method, request=packed)),
            deadline,
            expected_payload="capability_result",
        )
        capability_result = result.capability_result
        if capability_result.error_code:
            code = (
                capability_result.error_code
                if _ERROR_CODE.fullmatch(capability_result.error_code)
                else "failed"
            )
            raise _plugin_error(code, "Plugin capability call failed.")
        response.Clear()
        if not capability_result.response.Unpack(response):
            raise _plugin_error("response-type", "Plugin returned an unexpected response type.")
        return response

    @staticmethod
    async def _wait_for_handshake(
        session: _Session,
        process: asyncio.subprocess.Process,
        timeout: float,
    ) -> None:
        """Wait for authenticated plugin metadata or early child exit."""
        process_wait = asyncio.create_task(process.wait())
        try:
            done, _ = await asyncio.wait(
                {
                    cast(asyncio.Future[Any], session.ready),
                    cast(asyncio.Future[Any], process_wait),
                },
                timeout=timeout,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if session.ready in done:
                session.ready.result()
                if process_wait.done():
                    raise _plugin_error("early-exit", "Plugin process exited during startup.")
                return
            if process_wait in done:
                raise _plugin_error("early-exit", "Plugin process exited before connecting.")
            raise _plugin_error(
                "startup-timeout", "Plugin did not connect before its startup deadline."
            )
        finally:
            if not process_wait.done():
                process_wait.cancel()
                await asyncio.gather(process_wait, return_exceptions=True)
            if session.ready.done():
                if not session.ready.cancelled():
                    session.ready.exception()
            else:
                session.ready.add_done_callback(
                    lambda future: future.exception() if not future.cancelled() else None
                )

    async def _stop_locked(self, *, notify_child: bool) -> None:
        """Close stream and server, terminate within a bound, and clear owned references."""
        session, process, server = self._session, self._process, self._server
        self._session = None
        self._process = None
        self._server = None
        if session is not None:
            if notify_child and not session.closed.done() and not session.outgoing.full():
                session.outgoing.put_nowait(wire.CoreFrame(shutdown=wire.Shutdown()))
            elif not session.closed.done() and not session.outgoing.full():
                session.outgoing.put_nowait(_SENTINEL)
        if process is not None and process.returncode is None:
            try:
                await asyncio.wait_for(process.wait(), timeout=self._shutdown_timeout)
            except TimeoutError:
                with suppress(ProcessLookupError):
                    process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=1.0)
                except TimeoutError:
                    with suppress(ProcessLookupError):
                        process.kill()
                    await process.wait()
        if server is not None:
            await server.stop(grace=0.2)

    def _child_environment(self) -> dict[str, str]:
        """Pass a small safe base environment plus explicit plugin overrides."""
        allowed = (
            "PATH",
            "SystemRoot",
            "WINDIR",
            "TEMP",
            "TMP",
            "HOME",
            "USERPROFILE",
            "LANG",
            "LC_ALL",
            "LC_CTYPE",
        )
        base = {key: os.environ[key] for key in allowed if key in os.environ}
        base.update(self._env)
        return base

    @staticmethod
    def _validate_command(command: Sequence[str]) -> tuple[str, ...]:
        """Copy and bound a shell-free executable vector; reject secret bootstrap flags."""
        if isinstance(command, (str, bytes)) or not isinstance(command, Sequence):
            raise TypeError("Process plugin command must be a sequence of strings.")
        parts = tuple(command)
        if not 1 <= len(parts) <= _MAX_COMMAND_PARTS:
            raise ValueError("Process plugin command must contain between 1 and 128 arguments.")
        if any(not isinstance(part, str) or not part or "\x00" in part for part in parts):
            raise ValueError(
                "Process plugin command arguments must be non-empty strings without NUL."
            )
        if len(parts[0].encode("utf-8")) > 4096 or not os.path.isabs(parts[0]):
            raise ValueError(
                "Process plugin executable must be an absolute path no longer than 4096 bytes."
            )
        if sum(len(part.encode("utf-8")) + 1 for part in parts) > _MAX_COMMAND_BYTES:
            raise ValueError("Process plugin command exceeds its argument size limit.")
        return parts

    @staticmethod
    def _validate_configuration(configuration_json: bytes) -> bytes:
        """Require bounded UTF-8 JSON-object configuration before launching child code."""
        if (
            not isinstance(configuration_json, bytes)
            or len(configuration_json) > _MAX_CONFIGURATION_BYTES
        ):
            raise ValueError("Process plugin configuration must be bytes within the 1 MiB limit.")

        def reject_constant(_value: str) -> None:
            raise ValueError("Non-finite JSON numbers are not supported.")

        try:
            text = configuration_json.decode("utf-8", errors="strict")
            value = json.loads(text, parse_constant=reject_constant)
        except (UnicodeDecodeError, ValueError, json.JSONDecodeError, RecursionError) as exc:
            raise ValueError("Process plugin configuration must be valid UTF-8 JSON.") from exc
        if not isinstance(value, dict):
            raise ValueError("Process plugin configuration must be a JSON object.")
        return bytes(configuration_json)

    @staticmethod
    def _validate_env(env: Mapping[str, str]) -> dict[str, str]:
        """Detach and bound child environment overrides without allowing protocol spoofing."""
        if not isinstance(env, Mapping):
            raise TypeError("Process plugin environment must be a mapping.")
        result: dict[str, str] = {}
        total = 0
        for index, (key, value) in enumerate(env.items(), start=1):
            if index > 256:
                raise ValueError("Process plugin environment cannot exceed 256 entries.")
            if (
                not isinstance(key, str)
                or not key
                or "=" in key
                or "\x00" in key
                or key.startswith("ORBIT_PLUGIN_")
                or not isinstance(value, str)
                or "\x00" in value
            ):
                raise ValueError("Process plugin environment entries are invalid or reserved.")
            total += len(key.encode()) + len(value.encode()) + 2
            if total > _MAX_ENVIRONMENT_BYTES:
                raise ValueError("Process plugin environment exceeds its size limit.")
            result[key] = value
        return result

    @staticmethod
    def _validate_timeout(timeout: float, label: str) -> float:
        """Validate a finite, bounded timeout before acquiring process resources."""
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
            raise TypeError(f"Process plugin {label} timeout must be a number.")
        if not 0 < timeout <= 300:
            raise ValueError(
                f"Process plugin {label} timeout must be greater than zero and at most 300 seconds."
            )
        return float(timeout)

    @staticmethod
    def _validate_command_result(result: wire.CommandResult) -> None:
        """Convert child failures to generic safe plugin errors without trusting raw text."""
        if result.succeeded:
            if result.error_code or result.error_message:
                raise _plugin_error("protocol-result", "Plugin returned an invalid success result.")
            return
        code = result.error_code if _ERROR_CODE.fullmatch(result.error_code) else "failed"
        message = result.error_message
        if len(message) > 1024 or any(ord(char) < 32 and char not in "\t" for char in message):
            message = "Plugin command failed."
        # The child is a separate trust boundary; never forward arbitrary error text that may
        # contain credentials or provider payloads. Stable bounded codes remain actionable.
        del message
        raise _plugin_error(code, "Plugin command failed.")


__all__ = ["PROTOCOL_MAJOR", "PROTOCOL_MINOR", "ProcessPlugin"]
