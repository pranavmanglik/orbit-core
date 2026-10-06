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
"""Minimal independent process-plugin client used by Core integration tests."""

from __future__ import annotations

import asyncio
import json
import sys

import grpc
from google.protobuf.any_pb2 import Any
from google.protobuf.wrappers_pb2 import StringValue

from orbit.plugins.v1 import process_plugin_pb2 as wire
from orbit.plugins.v1 import process_plugin_pb2_grpc as wire_grpc


async def main() -> None:
    bootstrap_line = await asyncio.to_thread(sys.stdin.buffer.readline, 65_537)
    if not bootstrap_line or len(bootstrap_line) > 65_536:
        raise RuntimeError("invalid bootstrap")
    bootstrap = json.loads(bootstrap_line)
    metadata = bootstrap["metadata"]
    token = bootstrap["token"]
    outgoing: asyncio.Queue[wire.PluginFrame | None] = asyncio.Queue()
    await outgoing.put(
        wire.PluginFrame(
            hello=wire.PluginHello(
                protocol_major=1,
                protocol_minor=0,
                metadata=wire.PluginMetadata(
                    id=metadata["id"],
                    name=metadata["name"],
                    version=metadata["version"],
                    api_version=metadata["api_version"],
                    dependencies=metadata["dependencies"],
                    optional_dependencies=metadata["optional_dependencies"],
                    capabilities=metadata["capabilities"],
                    required_capabilities=metadata["required_capabilities"],
                ),
            )
        )
    )

    async def requests():
        while True:
            frame = await outgoing.get()
            if frame is None:
                return
            yield frame

    async with grpc.aio.insecure_channel(bootstrap["endpoint"]) as channel:
        stub = wire_grpc.ProcessPluginStub(channel)
        stream = stub.Connect(requests(), metadata=(("authorization", "Bearer " + token),))
        async for frame in stream:
            kind = frame.WhichOneof("payload")
            if kind == "shutdown":
                await outgoing.put(None)
                return
            if kind == "command":
                command = frame.command
                if command.kind == wire.PluginCommand.KIND_ACTIVATE:
                    config = json.loads(command.configuration_json)
                    failed = config.get("fail_activate", False)
                    await outgoing.put(
                        wire.PluginFrame(
                            command_result=wire.CommandResult(
                                request_id=command.request_id,
                                succeeded=not failed,
                                error_code="provider.failed" if failed else "",
                                error_message=config.get("secret", "") if failed else "",
                            )
                        )
                    )
                elif command.kind == wire.PluginCommand.KIND_DEACTIVATE:
                    await outgoing.put(
                        wire.PluginFrame(
                            command_result=wire.CommandResult(
                                request_id=command.request_id,
                                succeeded=True,
                            )
                        )
                    )
            elif kind == "health_probe":
                await outgoing.put(
                    wire.PluginFrame(
                        health=wire.PluginHealth(
                            request_id=frame.health_probe.request_id,
                            status=wire.PluginHealth.STATUS_HEALTHY,
                            message="health secret must not escape",
                        )
                    )
                )
            elif kind == "capability_call":
                call = frame.capability_call
                if call.method != "/orbit.test.v1.Echo/Call":
                    await outgoing.put(
                        wire.PluginFrame(
                            capability_result=wire.CapabilityResult(
                                request_id=call.request_id,
                                error_code="method.not_found",
                            )
                        )
                    )
                    continue
                request = StringValue()
                if not call.request.Unpack(request):
                    raise RuntimeError("unexpected request type")
                response = StringValue(value="echo:" + request.value)
                packed = Any()
                packed.Pack(response)
                await outgoing.put(
                    wire.PluginFrame(
                        capability_result=wire.CapabilityResult(
                            request_id=call.request_id,
                            response=packed,
                        )
                    )
                )


if __name__ == "__main__":
    asyncio.run(main())
