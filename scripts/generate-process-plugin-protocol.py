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
"""Regenerate checked-in gRPC and typed Protocol Buffer bindings."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src"
PROTO = SOURCE / "orbit" / "plugins" / "v1" / "process_plugin.proto"
OUTPUTS = (
    SOURCE / "orbit" / "plugins" / "v1" / "process_plugin_pb2.py",
    SOURCE / "orbit" / "plugins" / "v1" / "process_plugin_pb2_grpc.py",
    SOURCE / "orbit" / "plugins" / "v1" / "process_plugin_pb2.pyi",
    SOURCE / "orbit" / "plugins" / "v1" / "process_plugin_pb2_grpc.pyi",
)
LICENSE = """# Copyright 2026-present Orbit Contributors.
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
"""


def main() -> int:
    """Compile Python bindings and type stubs with the declared development tools."""
    command = [
        sys.executable,
        "-m",
        "grpc_tools.protoc",
        "-I",
        str(SOURCE),
        "--python_out=" + str(SOURCE),
        "--grpc_python_out=" + str(SOURCE),
        "--mypy_out=" + str(SOURCE),
        "--mypy_grpc_out=async_only:" + str(SOURCE),
        str(PROTO),
    ]
    subprocess.run(command, cwd=ROOT, check=True)
    for path in OUTPUTS:
        text = path.read_text(encoding="utf-8")
        if 'Licensed under the Apache License, Version 2.0 (the "License");' not in text[:1024]:
            first, separator, rest = text.partition("\n")
            if first.startswith("# -*- coding:"):
                text = first + "\n" + LICENSE + rest
            else:
                text = LICENSE + text
            path.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
