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
"""Task-local security context for runtime and administrative operations."""

from contextvars import ContextVar, Token

_principal: ContextVar[object | None] = ContextVar("orbit_principal", default=None)


def current_principal() -> object | None:
    """Return the opaque authentication value bound to this asynchronous request."""
    return _principal.get()


def bind_principal(principal: object | None) -> Token[object | None]:
    """Bind an opaque authentication value for the current context and return a reset token."""
    return _principal.set(principal)


def reset_principal(token: Token[object | None]) -> None:
    """Restore the authentication value captured by ``bind_principal``."""
    _principal.reset(token)


__all__ = ["bind_principal", "current_principal", "reset_principal"]
