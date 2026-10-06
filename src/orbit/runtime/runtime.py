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
"""The common hosting facade for application orchestration and authenticated ASGI."""

from orbit.application import Application
from orbit.asgi import ASGIApplication
from orbit.asgi.types import Receive, Scope, Send
from orbit.diagnostics.tracing import Tracer
from orbit.runtime.models import HostingConfig, RuntimeInfo
from orbit.security.contracts import Authenticator, RouteAuthorizer


class Runtime:
    """Expose an application's shared router and optional authentication provider."""

    def __init__(
        self,
        application: Application,
        *,
        authenticator: Authenticator | None = None,
        authorizer: RouteAuthorizer | None = None,
        tracer: Tracer | None = None,
        hosting: HostingConfig | None = None,
    ) -> None:
        if not isinstance(application, Application):
            raise TypeError("Runtime requires an Application instance.")
        if hosting is not None and not isinstance(hosting, HostingConfig):
            raise TypeError("Runtime hosting must be a HostingConfig instance.")
        self.application = application
        self.hosting = HostingConfig() if hosting is None else hosting
        self.asgi = ASGIApplication(
            application, authenticator=authenticator, authorizer=authorizer, tracer=tracer
        )

    @property
    def info(self) -> RuntimeInfo:
        """Read current lifecycle state, without a second runtime state machine."""
        return RuntimeInfo(
            application_name=self.application.config.application.name,
            phase=self.application.lifecycle.phase,
            service_count=len(self.application.services.services),
            task_count=len(self.application.tasks.infos),
            failed_task_count=sum(
                task.state.value == "failed" for task in self.application.tasks.infos
            ),
            child_count=len(self.application.children),
            hosting=self.hosting,
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Delegate ASGI calls so ``module:runtime`` works with every host process."""
        await self.asgi(scope, receive, send)


__all__ = ["Runtime"]
