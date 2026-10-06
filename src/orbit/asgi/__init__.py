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
"""Orbit's framework-owned ASGI boundary and HTTP composition primitives.

The package implements the protocol boundary required by the orchestrator without selecting a
third-party web framework. Provider integrations and business features remain plugin-owned.
"""

from typing import Any

from orbit.asgi.middleware import Middleware, NextHandler
from orbit.asgi.request import (
    MAX_BODY_BYTES,
    MAX_HEADER_BYTES,
    MAX_HEADER_COUNT,
    MAX_PATH_BYTES,
    MAX_QUERY_BYTES,
    Headers,
    Request,
)
from orbit.asgi.response import Response
from orbit.asgi.types import Message, Receive, Scope, Send

__all__ = [
    "ASGIApplication",
    "MAX_BODY_BYTES",
    "MAX_HEADER_BYTES",
    "MAX_HEADER_COUNT",
    "MAX_PATH_BYTES",
    "MAX_QUERY_BYTES",
    "Headers",
    "Message",
    "Middleware",
    "NextHandler",
    "Receive",
    "Request",
    "Response",
    "Scope",
    "Send",
]


def __getattr__(name: str) -> Any:
    """Load the ASGI application lazily to keep routing contracts import-cycle free."""
    if name == "ASGIApplication":
        from orbit.asgi.application import ASGIApplication

        return ASGIApplication
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
