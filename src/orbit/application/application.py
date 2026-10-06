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
"""Application orchestration with transactional startup and bounded reverse cleanup.

An application is a single-use, single-event-loop owner. Public lifecycle methods serialize
on one lock. Hooks must not recursively call application lifecycle methods. Providers,
plugins and services participate in the same resource ownership hierarchy.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import re
from collections import deque
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from contextlib import asynccontextmanager
from contextvars import ContextVar
from types import MappingProxyType
from typing import cast

from pydantic import BaseModel

from orbit._limits import _MAX_CORE_CAPACITY
from orbit.admin.contracts import AdminContribution
from orbit.config import ApplicationConfig, Config
from orbit.config.contracts import ConfigurationWatcher
from orbit.container import Container, ProviderResolution
from orbit.diagnostics.diagnostics import Diagnostics
from orbit.errors import ErrorCategory, LifecycleError, OrbitProblem
from orbit.events import Event, EventBus, EventStore
from orbit.health import HealthReport, HealthService, HealthStatus
from orbit.health.check import HealthCheck
from orbit.lifecycle import Lifecycle
from orbit.lifecycle import LifecyclePhase as Phase
from orbit.lifecycle.transition import LifecycleTransition
from orbit.plugins import PluginRegistry
from orbit.plugins.contracts import PluginContract
from orbit.routing import Router
from orbit.runtime.tasks import TaskFailure, TaskSupervisor
from orbit.services import ServiceRegistry
from orbit.services.contracts import ServiceContract
from orbit.services.models import ServiceDescriptor
from orbit.state import ApplicationState, State, StateNamespace, StateStore
from orbit.state.models import ComponentState

_LOG = logging.getLogger(__name__)
_operations: ContextVar[tuple[Application, ...]] = ContextVar("orbit_operations", default=())


class Application:
    """Own the complete Core graph and perform resource-safe lifecycle operations."""

    def __init__(self, config: ApplicationConfig, *, event_store: EventStore | None = None) -> None:
        if not isinstance(config, ApplicationConfig):
            raise TypeError("Application requires an ApplicationConfig instance.")
        self.config = Config(config)
        self.container = Container(cleanup_timeout=config.lifecycle_timeout)
        self.events = EventBus(timeout=config.lifecycle_timeout, store=event_store)
        self.lifecycle = Lifecycle(observer_timeout=min(config.lifecycle_timeout, 1.0))
        self.services = ServiceRegistry()
        self.plugins = PluginRegistry()
        self.router = Router()
        self.diagnostics = Diagnostics()
        self._health_service = HealthService()
        self.container.observe(self._record_provider_resolution)
        self.tasks = TaskSupervisor(
            shutdown_timeout=config.lifecycle_timeout,
            observer=self._record_task_failure,
        )
        self._admin_contributions: dict[str, AdminContribution] = {}
        self._running_admin_inspections: dict[str, asyncio.Task[BaseModel]] = {}
        self._detached_admin_inspections: dict[str, asyncio.Task[BaseModel]] = {}
        self._children: dict[str, Application] = {}
        self._parent: Application | None = None
        self._config_watchers: list[ConfigurationWatcher] = []
        self._store = StateStore(ApplicationState(application_id=config.id))
        self.state = State(self._store)
        self._namespaces: dict[str, StateNamespace] = {}
        self._entered: list[ServiceContract] = []
        self._service_phases: dict[str, Phase] = {}
        self._service_health: dict[str, HealthStatus] = {}
        self._health_history: deque[HealthReport] = deque(maxlen=100)
        self._health_task: asyncio.Task[HealthReport] | None = None
        self._lock = asyncio.Lock()
        self._cleaned = False
        self.container.register_instance(Application, self)
        self.container.register_instance(ApplicationConfig, config)
        self.container.register_instance(Container, self.container)
        self.container.register_instance(EventBus, self.events)
        self.lifecycle.observe(self._reflect_lifecycle)

    @property
    def is_ready(self) -> bool:
        """Return cached readiness; health() refreshes it from current checks."""
        state = self.state.application
        return (
            state.phase is Phase.RUNNING
            and state.health is HealthStatus.HEALTHY
            and not any(task.state.value == "failed" for task in self.tasks.infos)
        )

    @property
    def is_live(self) -> bool:
        """Return whether the application process is able to serve lifecycle work."""
        return self.lifecycle.phase not in {Phase.STOPPED, Phase.FAILED}

    @property
    def health_history(self) -> tuple[HealthReport, ...]:
        """Return bounded health reports in chronological order."""
        return tuple(report.model_copy(deep=True) for report in self._health_history)

    def register(self, service: ServiceContract) -> None:
        """Register a service during composition."""
        self.lifecycle.require(Phase.CREATED)
        descriptor = self.services.register(service)
        self._service_phases[descriptor.name] = Phase.CREATED
        self._snapshot()

    @property
    def children(self) -> Mapping[str, Application]:
        """Return the explicitly registered nested applications."""
        return MappingProxyType(self._children)

    def register_child(self, name: str, child: Application) -> None:
        """Register a nested application owned by this application's lifecycle."""
        self.lifecycle.require(Phase.CREATED)
        if not isinstance(name, str):
            raise TypeError("Child application names must be strings.")
        if not isinstance(child, Application):
            raise TypeError("Child applications must be Application instances.")
        if child._parent is not None:  # noqa: SLF001 - ownership is an application invariant.
            raise ValueError("Child application is already owned by another parent.")
        if not re.fullmatch(r"[a-z][a-z0-9-]{0,62}", name):
            raise ValueError("Invalid child application name.")
        if name in self._children or child is self:
            raise ValueError("Child application names must be unique and cannot self-reference.")

        def contains(root: Application, target: Application) -> bool:
            """Detect graph reachability without consuming Python call-stack depth."""
            pending = [root]
            visited: set[int] = set()
            while pending:
                current = pending.pop()
                if current is target:
                    return True
                identity = id(current)
                if identity in visited:
                    continue
                visited.add(identity)
                pending.extend(current._children.values())
            return False

        if contains(child, self):
            raise ValueError("Nested application cycle detected.")
        if len(self._children) >= _MAX_CORE_CAPACITY:
            raise RuntimeError("Child application capacity reached.")
        self._children[name] = child
        # Record ownership only after every registration check succeeds, so a rejected
        # composition attempt cannot strand the child under a partially mutated parent.
        child._parent = self  # noqa: SLF001 - both sides are the same Core owner model.

    def register_config_watcher(self, watcher: ConfigurationWatcher) -> None:
        """Register an optional configuration observer under application lifecycle ownership."""
        self.lifecycle.require(Phase.CREATED)
        if not callable(getattr(watcher, "start", None)) or not callable(
            getattr(watcher, "stop", None)
        ):
            raise TypeError("Configuration watchers must provide callable start and stop methods.")
        if watcher in self._config_watchers:
            raise ValueError("Configuration watcher is already registered.")
        if len(self._config_watchers) >= _MAX_CORE_CAPACITY:
            raise RuntimeError("Configuration watcher capacity reached.")
        self._config_watchers.append(watcher)

    def namespace(self, name: str) -> StateNamespace:
        """Return an application-owned isolated state namespace."""
        namespace = self._namespaces.get(name)
        if namespace is None:
            self.lifecycle.require(Phase.CREATED)
            namespace = StateNamespace(name)
            if len(self._namespaces) >= _MAX_CORE_CAPACITY:
                raise RuntimeError("Application namespace capacity reached.")
            self._namespaces[name] = namespace
        return namespace

    def register_plugin(self, plugin: PluginContract) -> None:
        """Register an explicitly trusted plugin before configuration."""
        self.lifecycle.require(Phase.CREATED)
        self.plugins.register(plugin)

    def validate(self) -> None:
        """Validate component/provider graphs without acquiring resources."""
        self.services.ordered()
        self.plugins.ordered()
        self.container.validate()
        for child in self._children.values():
            child.validate()
        ids = {d.id for d in self.services.descriptors}
        for route in self.router.routes:
            if route.metadata.path in {
                "/health/live",
                "/health/ready",
                "/openapi.json",
            }:
                raise ValueError("This path is reserved for a Core-owned endpoint.")
            if route.metadata.service_id is not None and route.metadata.service_id not in ids:
                raise ValueError(f"Route {route.metadata.name} belongs to an unknown service.")

    def register_admin(self, contribution: AdminContribution) -> None:
        """Register a trusted read-only admin extension during composition."""
        self.lifecycle.require(Phase.CREATED)
        if not isinstance(contribution, AdminContribution):
            raise TypeError("Admin contributions must implement AdminContribution.")
        name = contribution.name
        if not isinstance(name, str):
            raise TypeError("Admin contribution names must be strings.")
        if not callable(getattr(contribution, "inspect", None)):
            raise TypeError("Admin contributions must provide a callable inspect method.")
        if not re.fullmatch(r"[a-z][a-z0-9-]{0,62}", name):
            raise ValueError("Invalid admin contribution name.")
        if name in self._admin_contributions:
            raise ValueError("Duplicate admin contribution name.")
        if len(self._admin_contributions) >= _MAX_CORE_CAPACITY:
            raise RuntimeError("Admin contribution capacity reached.")
        self._admin_contributions[name] = contribution

    @property
    def admin_contributions(self) -> Mapping[str, AdminContribution]:
        """Read the immutable administrative contribution registry."""
        return MappingProxyType(self._admin_contributions)

    async def inspect_admin_contribution(self, name: str) -> BaseModel | None:
        """Inspect one registered admin extension within Core's configured health deadline.

        The bounded, cancellation-aware inspection behavior is a stable extension contract used
        by optional Admin packages. The HTTP routes and presentation remain outside Core.
        """
        if not isinstance(name, str) or name not in self._admin_contributions:
            raise KeyError(name)
        return await self._inspect_admin_contribution(
            name,
            self._admin_contributions[name],
            self.config.application.health_timeout,
        )

    async def _inspect_admin_contribution(
        self,
        name: str,
        contribution: AdminContribution,
        timeout: float,
    ) -> BaseModel | None:
        """Inspect one contribution without allowing cancellation-resistant work to pile up."""
        existing = self._detached_admin_inspections.get(name)
        if existing is not None:
            if existing.done():
                self._retire_admin_inspection(name, existing)
            else:
                return None
        running = self._running_admin_inspections.get(name)
        if running is not None:
            if running.done():
                # The inspection may complete between concurrent callers. Reuse its completed
                # result instead of starting duplicate provider work before the original waiter
                # retires the task.
                return self._completed_admin_inspection(name, running)
            else:
                return None
        result = contribution.inspect()
        if not inspect.isawaitable(result):
            raise TypeError("Admin contribution inspect methods must return an awaitable.")
        task = asyncio.ensure_future(result)
        self._running_admin_inspections[name] = task
        try:
            done, _ = await asyncio.wait({task}, timeout=timeout)
            if not done:
                self._detach_admin_inspection(name, task)
                return None
            return self._completed_admin_inspection(name, task)
        except asyncio.CancelledError:
            if task.done():
                self._retire_admin_inspection(name, task)
            else:
                self._detach_admin_inspection(name, task)
            raise
        except BaseException:
            self._detached_admin_inspections.pop(name, None)
            raise

    def _completed_admin_inspection(self, name: str, task: asyncio.Task[BaseModel]) -> BaseModel:
        """Return one completed inspection and retire its ownership without duplication."""
        try:
            view = task.result()
        except BaseException:
            self._retire_admin_inspection(name, task)
            raise
        self._retire_admin_inspection(name, task)
        if not isinstance(view, BaseModel):
            raise TypeError("Admin contributions must return Pydantic models.")
        return view

    def _detach_admin_inspection(self, name: str, task: asyncio.Task[BaseModel]) -> None:
        """Retain one late admin result so repeated requests cannot create orphan inspections."""
        if self._detached_admin_inspections.get(name) is task:
            task.cancel()
            return
        self._detached_admin_inspections[name] = task
        task.cancel()
        task.add_done_callback(lambda finished: self._retire_admin_inspection(name, finished))

    def _retire_admin_inspection(self, name: str, task: asyncio.Task[BaseModel]) -> None:
        """Forget a detached inspection and consume its late result or exception."""
        if self._running_admin_inspections.get(name) is task:
            del self._running_admin_inspections[name]
        if self._detached_admin_inspections.get(name) is task:
            del self._detached_admin_inspections[name]
        try:
            task.exception()
        except (asyncio.CancelledError, Exception):
            return

    def _cancel_pending_admin_inspections(self) -> None:
        """Request cancellation of extension inspections that outlived an admin deadline."""
        for name, task in tuple(self._running_admin_inspections.items()):
            if not task.done():
                # Shutdown takes ownership from any active waiter so completed work can retire
                # even when the waiter itself is cancelled with the application.
                self._detach_admin_inspection(name, task)
            else:
                self._retire_admin_inspection(name, task)
        for task in tuple(self._detached_admin_inspections.values()):
            if not task.done():
                task.cancel()

    async def configure(self) -> None:
        """Compose plugins, freeze registrations and configure services transactionally."""
        await self._execute(self._configure)

    async def _configure(self) -> None:
        self.lifecycle.require(Phase.CREATED)
        try:
            self.plugins.setup(self)
            self.validate()
            self.services.freeze()
            self.container.freeze()
            self.config.freeze()
            self.router.freeze()
            for child in self._children.values():
                await child.configure()
            for service in self.services.ordered():
                self._entered.append(service)
                await self._call(service.configure())
                self._service_phases[self.services.descriptor_for(service).name] = Phase.CONFIGURED
            await self.lifecycle.transition(Phase.CONFIGURED)
        except BaseException:
            await self._abort()
            raise

    async def initialize(self) -> None:
        """Activate plugins and initialize service resources; rollback on any failure."""
        await self._execute(self._initialize)

    async def _initialize(self) -> None:
        self.lifecycle.require(Phase.CONFIGURED)
        try:
            await self.plugins.activate(self.config.application.lifecycle_timeout)
            for child in self._children.values():
                await child.initialize()
            for service in self.services.ordered():
                await self._call(service.initialize())
                self._service_phases[self.services.descriptor_for(service).name] = Phase.INITIALIZED
            await self.lifecycle.transition(Phase.INITIALIZED)
        except BaseException:
            await self._abort()
            raise

    async def start(self) -> None:
        """Start services dependency-first; readiness follows a current health check."""
        await self._execute(self._start)

    async def _start(self) -> None:
        self.lifecycle.require(Phase.INITIALIZED)
        try:
            await self.lifecycle.transition(Phase.STARTING)
            for service in self.services.ordered():
                descriptor = self.services.descriptor_for(service)
                self._service_phases[descriptor.name] = Phase.STARTING
                await self._call(service.start())
                self._service_phases[descriptor.name] = Phase.RUNNING
            for child in self._children.values():
                await child.start()
            await self.tasks.start()
            for watcher in self._config_watchers:
                await watcher.start()
            await self.lifecycle.transition(Phase.RUNNING)
            await self.health()
        except BaseException:
            await self._abort()
            raise

    async def startup(self) -> None:
        """Run the complete startup sequence; intended for the runtime/ASGI host."""
        await self._execute(self._startup)

    async def _startup(self) -> None:
        await self._configure()
        await self._initialize()
        await self._start()

    async def stop(self) -> None:
        """Stop all entered components, even after partial startup; idempotent after cleanup."""
        await self._execute(self._stop)

    async def restart_service(self, name: str) -> None:
        """Restart one running service when no running service depends on it."""
        await self._execute(lambda: self._restart_service(name))

    async def stop_service(self, name: str) -> None:
        """Stop one running service when no running service depends on it."""
        await self._execute(lambda: self._stop_service(name))

    async def start_service(self, name: str) -> None:
        """Start one initialized service after verifying its dependencies are running."""
        await self._execute(lambda: self._start_service(name))

    async def reload_service(self, name: str) -> None:
        """Reload one running service using its hook, or restart it when unsupported."""
        await self._execute(lambda: self._reload_service(name))

    async def restart_task(self, name: str) -> None:
        """Restart one supervised background task without restarting the application."""
        await self._execute(lambda: self._restart_task(name))

    async def _restart_task(self, name: str) -> None:
        self.lifecycle.require(Phase.RUNNING)
        await self.tasks.restart(name)

    def _running_dependents(self, descriptor: ServiceDescriptor) -> set[str]:
        service_id = descriptor.id
        dependents: set[str] = set()
        for candidate in self.services.services:
            candidate_descriptor = self.services.descriptor_for(candidate)
            if (
                service_id in candidate_descriptor.dependencies
                and self._service_phases.get(candidate_descriptor.name) is Phase.RUNNING
            ):
                dependents.add(candidate_descriptor.name)
        return dependents

    async def _restart_service(self, name: str) -> None:
        self.lifecycle.require(Phase.RUNNING)
        service = self.services.get_by_name(name)
        descriptor = self.services.descriptor_for(service)
        dependents = self._running_dependents(descriptor)
        if dependents:
            raise LifecycleError(
                OrbitProblem(
                    code="lifecycle.service-has-dependents",
                    message="Cannot restart a service while dependent services are running.",
                    category=ErrorCategory.LIFECYCLE,
                    context={"service": name, "dependents": sorted(dependents)},
                )
            )
        self._service_phases[name] = Phase.STOPPING
        try:
            await self._call(service.stop())
        except BaseException:
            # A failed stop is a terminal lifecycle outcome for this service.  Leaving
            # it in STOPPING makes operational inspection claim a transition is still
            # in progress and allows callers to retry a potentially unsafe restart.
            self._service_phases[name] = Phase.FAILED
            self._service_health[name] = HealthStatus.UNHEALTHY
            self._store.update(health=HealthStatus.UNHEALTHY)
            self._snapshot()
            raise
        self._service_phases[name] = Phase.STARTING
        try:
            await self._call(service.start())
            self._service_phases[name] = Phase.RUNNING
            await self.health()
        except BaseException:
            self._service_phases[name] = Phase.FAILED
            self._store.update(health=HealthStatus.UNHEALTHY)
            self._snapshot()
            raise

    async def _reload_service(self, name: str) -> None:
        self.lifecycle.require(Phase.RUNNING)
        service = self.services.get_by_name(name)
        dependents = self._running_dependents(self.services.descriptor_for(service))
        if dependents:
            raise LifecycleError(
                OrbitProblem(
                    code="lifecycle.service-has-dependents",
                    message="Cannot reload a service while dependent services are running.",
                    category=ErrorCategory.LIFECYCLE,
                    context={"service": name, "dependents": sorted(dependents)},
                )
            )
        hook = getattr(service, "reload", None)
        if hook is None:
            await self._restart_service(name)
            return
        try:
            self._service_phases[name] = Phase.STARTING
            await self._call(hook())
            self._service_phases[name] = Phase.RUNNING
            await self.health()
        except BaseException:
            self._service_phases[name] = Phase.FAILED
            self._store.update(health=HealthStatus.UNHEALTHY)
            self._snapshot()
            raise

    async def _stop_service(self, name: str) -> None:
        self.lifecycle.require(Phase.RUNNING)
        service = self.services.get_by_name(name)
        descriptor = self.services.descriptor_for(service)
        if self._service_phases.get(name) is not Phase.RUNNING:
            raise LifecycleError(
                OrbitProblem(
                    code="lifecycle.service-not-running",
                    message="Service is not running.",
                    category=ErrorCategory.LIFECYCLE,
                    context={"service": name},
                )
            )
        dependents = self._running_dependents(descriptor)
        if dependents:
            raise LifecycleError(
                OrbitProblem(
                    code="lifecycle.service-has-dependents",
                    message="Cannot stop a service while dependent services are running.",
                    category=ErrorCategory.LIFECYCLE,
                    context={"service": name, "dependents": sorted(dependents)},
                )
            )
        self._service_phases[name] = Phase.STOPPING
        try:
            await self._call(service.stop())
        except BaseException:
            self._service_phases[name] = Phase.FAILED
            raise
        self._service_phases[name] = Phase.STOPPED
        self._entered = [entered for entered in self._entered if entered is not service]
        self._service_health[name] = HealthStatus.UNKNOWN
        self._snapshot()

    async def _start_service(self, name: str) -> None:
        self.lifecycle.require(Phase.RUNNING)
        service = self.services.get_by_name(name)
        descriptor = self.services.descriptor_for(service)
        if self._service_phases.get(name) is not Phase.STOPPED:
            raise LifecycleError(
                OrbitProblem(
                    code="lifecycle.service-not-stopped",
                    message="Service must be stopped before it can be started.",
                    category=ErrorCategory.LIFECYCLE,
                    context={"service": name},
                )
            )
        missing = [
            dependency.name
            for dependency in self.services.descriptors
            if dependency.id in descriptor.dependencies
            and self._service_phases.get(dependency.name) is not Phase.RUNNING
        ]
        if missing:
            raise LifecycleError(
                OrbitProblem(
                    code="lifecycle.dependencies-not-running",
                    message="Service dependencies must be running before startup.",
                    category=ErrorCategory.LIFECYCLE,
                    context={"service": name, "dependencies": sorted(missing)},
                )
            )
        self._service_phases[name] = Phase.STARTING
        try:
            await self._call(service.start())
        except BaseException:
            self._service_phases[name] = Phase.FAILED
            raise
        self._service_phases[name] = Phase.RUNNING
        self._entered.append(service)
        await self.health()

    async def _stop(self) -> None:
        if self._cleaned:
            return
        failures = await self._finish_cleanup()
        if failures:
            raise ExceptionGroup("Application cleanup failed", failures)

    async def health(self) -> HealthReport:
        """Refresh health from current component checks; non-running applications are unready."""
        if self.lifecycle.phase is not Phase.RUNNING:
            return HealthReport(
                status=HealthStatus.UNHEALTHY, message="Application is not running."
            )
        if self._health_task is None or self._health_task.done():
            self._health_task = asyncio.create_task(self._collect_health())
        report = await asyncio.shield(self._health_task)
        return report.model_copy(deep=True)

    async def _collect_health(self) -> HealthReport:
        checks: dict[str, HealthCheck] = {
            self.services.descriptor_for(service).name: service
            for service in self.services.services
        }
        for plugin in self.plugins.plugins:
            health = getattr(plugin, "health", None)
            if callable(health):
                # Plugin metadata is a registration contract, not a live identity source. Use the
                # frozen snapshot so a provider cannot move its health result under another name.
                name = self.plugins.snapshot_for(plugin).name
                checks[f"plugin:{name}"] = cast(HealthCheck, plugin)
        for name, child in self._children.items():
            checks[f"child:{name}"] = cast(HealthCheck, child)
        report = await self._health_service.check(
            checks,
            timeout=self.config.application.health_timeout,
        )
        failed_tasks = {
            f"task:{task.name}": {
                "status": HealthStatus.UNHEALTHY.value,
                "message": "Supervised task terminated after exhausting its restart policy.",
            }
            for task in self.tasks.infos
            if task.state.value == "failed"
        }
        if failed_tasks:
            report = HealthReport(
                status=HealthStatus.UNHEALTHY,
                message="One or more supervised tasks failed.",
                details={**report.details, **failed_tasks},
            )
        # Shutdown may begin while checks are running.
        if self.lifecycle.phase is Phase.RUNNING:
            self._service_health = {
                name: HealthStatus(details["status"]) for name, details in report.details.items()
            }
            self._store.update(health=report.status)
            self._health_history.append(report.model_copy(deep=True))
            self._snapshot()
            return report
        return HealthReport(status=HealthStatus.UNHEALTHY, message="Application is stopping.")

    @asynccontextmanager
    async def running(self) -> AsyncIterator[Application]:
        """Own a startup/shutdown session for workers, tests and command-line operations."""
        await self.startup()
        try:
            yield self
        finally:
            await self.stop()

    async def _execute(self, operation: Callable[[], Awaitable[None]]) -> None:
        if self in _operations.get():
            raise LifecycleError(
                OrbitProblem(
                    code="lifecycle.reentrant-operation",
                    message="Lifecycle hooks and observers cannot initiate lifecycle operations.",
                    category=ErrorCategory.LIFECYCLE,
                )
            )
        async with self._lock:
            token = _operations.set((*_operations.get(), self))
            from orbit.runtime.context import bind_application, reset_application

            application_token = bind_application(self)
            try:
                await operation()
            finally:
                reset_application(application_token)
                _operations.reset(token)

    async def _call(self, hook: Awaitable[None]) -> None:
        async with asyncio.timeout(self.config.application.lifecycle_timeout):
            await hook

    async def _abort(self) -> None:
        failures = await self._finish_cleanup(failed=True)
        for failure in failures:
            _LOG.error("Rollback cleanup failed", exc_info=failure)

    async def _finish_cleanup(self, *, failed: bool = False) -> list[Exception]:
        # A separate task keeps cancellation of the caller from abandoning resources.
        task = asyncio.create_task(self._cleanup(failed=failed))
        cancelled = False
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                cancelled = True
        failures = task.result()
        if cancelled:
            raise asyncio.CancelledError
        return failures

    async def _cleanup(self, *, failed: bool) -> list[Exception]:
        if self._cleaned:
            return []
        self.lifecycle.cancel_pending()
        await self.lifecycle.transition(Phase.STOPPING)
        self._store.update(health=HealthStatus.UNHEALTHY)
        failures: list[Exception] = []
        if self._health_task is not None and not self._health_task.done():
            self._health_task.cancel()
            await asyncio.gather(self._health_task, return_exceptions=True)
        await self._health_service.close(timeout=self.config.application.lifecycle_timeout)
        self._cancel_pending_admin_inspections()
        for watcher in reversed(self._config_watchers):
            try:
                await watcher.stop()
            except (Exception, asyncio.CancelledError) as exc:
                failures.append(
                    exc
                    if isinstance(exc, Exception)
                    else RuntimeError("Config watcher cleanup cancelled.")
                )
        try:
            await self.tasks.stop()
        except (Exception, asyncio.CancelledError) as exc:
            failures.append(
                exc if isinstance(exc, Exception) else RuntimeError("Task cleanup cancelled.")
            )
        for child in reversed(tuple(self._children.values())):
            try:
                await child.stop()
            except (Exception, asyncio.CancelledError) as exc:
                failures.append(
                    exc if isinstance(exc, Exception) else RuntimeError("Child cleanup cancelled.")
                )
        while self._entered:
            service = self._entered.pop()
            name = self.services.snapshot_for(service).name
            self._service_phases[name] = Phase.STOPPING
            try:
                await self._call(service.stop())
                self._service_phases[name] = Phase.STOPPED
            except (Exception, asyncio.CancelledError) as exc:
                error = (
                    exc if isinstance(exc, Exception) else RuntimeError("Cleanup hook cancelled.")
                )
                failures.append(error)
                self._service_phases[name] = Phase.FAILED
        try:
            await self.plugins.deactivate(self.config.application.lifecycle_timeout)
        except (Exception, asyncio.CancelledError) as exc:
            failures.append(
                exc if isinstance(exc, Exception) else RuntimeError("Plugin cleanup cancelled.")
            )
        finally:
            self.plugins.cancel_pending()
        try:
            await self._call(self.container.aclose())
        except (Exception, asyncio.CancelledError) as exc:
            failures.append(
                exc if isinstance(exc, Exception) else RuntimeError("Resource cleanup cancelled.")
            )
        try:
            await self.events.aclose()
        except (Exception, asyncio.CancelledError) as exc:
            failures.append(
                exc if isinstance(exc, Exception) else RuntimeError("Event cleanup cancelled.")
            )
        self._cleaned = True
        await self.lifecycle.transition(Phase.FAILED if failed or failures else Phase.STOPPED)
        self.lifecycle.cancel_pending()
        return failures

    async def _reflect_lifecycle(self, transition: LifecycleTransition) -> None:
        self._snapshot()
        if self.events.closed:
            return
        await self.events.publish(Event(name="orbit.lifecycle", payload=transition))

    async def _record_task_failure(self, failure: TaskFailure) -> None:
        """Expose supervised task failures through the normal event stream."""
        if self.events.closed:
            return
        await self.events.publish(Event(name="orbit.task.failed", payload=failure))

    def _record_provider_resolution(self, resolution: ProviderResolution) -> None:
        """Forward payload-free DI outcomes to application diagnostics."""
        self.diagnostics.record_provider_resolution(resolution.success)

    def _snapshot(self) -> None:
        self._store.update(
            phase=self.lifecycle.phase,
            service_count=len(self.services.services),
            services=tuple(
                ComponentState(
                    name=name,
                    phase=phase,
                    health=self._service_health.get(name, HealthStatus.UNKNOWN)
                    if phase is Phase.RUNNING
                    else HealthStatus.UNKNOWN,
                )
                for name, phase in self._service_phases.items()
            ),
            plugins=tuple(
                ComponentState(
                    # State inspection must remain stable even when a failing plugin hook has
                    # replaced its live metadata before rollback completes.
                    name=self.plugins.snapshot_for(p).name,
                    phase=Phase.RUNNING
                    if self.plugins.snapshot_for(p).name in self.plugins.active_names
                    else Phase.STOPPED,
                )
                for p in self.plugins.plugins
            ),
        )


__all__ = ["Application"]
