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
"""Authentication and authorization extension contracts."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from orbit.asgi.request import Request


@runtime_checkable
class Authenticator(Protocol):
    """Authenticate an ASGI request through an optional provider plugin."""

    async def authenticate(self, request: Request) -> object | None:
        """Return an opaque authenticated value, or ``None`` for anonymous requests."""


@runtime_checkable
class RouteAuthorizer(Protocol):
    """Optional extension hook for evaluating route requirement labels.

    Core stores bounded route metadata but does not interpret roles or policies. Applications
    install an authorizer from a capability package when they use protected routes.
    """

    async def authorize_roles(
        self, principal: object | None, required_roles: frozenset[str]
    ) -> None:
        """Return only when the current principal satisfies every required route label."""


__all__ = ["Authenticator", "RouteAuthorizer"]
