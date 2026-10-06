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
"""Regression checks for documented focused-package imports and composition limits."""

from importlib import import_module
from pathlib import Path

import pytest

_PUBLIC_PACKAGES = (
    "orbit",
    "orbit.admin",
    "orbit.asgi",
    "orbit.application",
    "orbit.cli",
    "orbit.config",
    "orbit.container",
    "orbit.diagnostics",
    "orbit.errors",
    "orbit.events",
    "orbit.health",
    "orbit.lifecycle",
    "orbit.plugins",
    "orbit.routing",
    "orbit.runtime",
    "orbit.security",
    "orbit.services",
    "orbit.state",
    "orbit.types",
)
_EXPECTED_PUBLIC_EXPORTS = {
    "orbit": {
        "Application",
        "ApplicationBuilder",
        "ApplicationConfig",
        "Service",
        "ServiceDescriptor",
        "__version__",
    },
    "orbit.admin": {
        "AdminContribution",
    },
    "orbit.asgi": {
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
    },
    "orbit.application": {"Application", "ApplicationBuilder", "ApplicationSummary"},
    "orbit.cli": {"app"},
    "orbit.config": {
        "ApplicationConfig",
        "Config",
        "ConfigChange",
        "ConfigObserver",
        "ConfigSnapshot",
        "ConfigurationWatcher",
        "MAX_CONFIG_FILE_BYTES",
        "MAX_CONFIG_PREFIX_LENGTH",
        "SecretManager",
        "SecretReference",
        "SecretValue",
        "load_application_config",
        "load_config",
    },
    "orbit.container": {
        "Container",
        "ContainerContract",
        "DependencyKey",
        "Provider",
        "ProviderObserver",
        "ProviderResolution",
        "Scope",
    },
    "orbit.diagnostics": {
        "Counter",
        "DiagnosticSnapshot",
        "Diagnostics",
        "Gauge",
        "Histogram",
        "InMemoryTracer",
        "LatencyBucket",
        "MetricSnapshot",
        "MetricsRegistry",
        "RequestRecord",
        "Span",
        "SpanRecord",
        "TelemetrySink",
        "inspect_composition",
        "Tracer",
    },
    "orbit.errors": {
        "ConfigurationError",
        "ContainerError",
        "ErrorCategory",
        "ErrorResponse",
        "ErrorSeverity",
        "LifecycleError",
        "OrbitError",
        "OrbitProblem",
        "PluginError",
        "RoutingError",
        "SecurityError",
        "ValidationError",
    },
    "orbit.events": {
        "Delivery",
        "Event",
        "EventBus",
        "EventFilter",
        "EventHandler",
        "EventStore",
        "EventTransport",
        "FailurePolicy",
        "InMemoryEventStore",
        "StoredEvent",
        "Subscription",
    },
    "orbit.health": {"HealthCheck", "HealthReport", "HealthService", "HealthStatus"},
    "orbit.lifecycle": {"Lifecycle", "LifecycleObserver", "LifecyclePhase", "LifecycleTransition"},
    "orbit.plugins": {
        "CORE_API_VERSION",
        "Plugin",
        "PluginContract",
        "PluginMetadata",
        "PluginRegistry",
        "discover_plugins",
    },
    "orbit.routing": {"Route", "RouteGroup", "RouteMetadata", "Router"},
    "orbit.runtime": {
        "HostServer",
        "HostingConfig",
        "RestartPolicy",
        "Runtime",
        "RuntimeInfo",
        "TaskFailure",
        "TaskInfo",
        "TaskState",
        "TaskSupervisor",
    },
    "orbit.security": {
        "Authenticator",
        "RouteAuthorizer",
    },
    "orbit.services": {"Service", "ServiceContract", "ServiceDescriptor", "ServiceRegistry"},
    "orbit.state": {
        "ApplicationState",
        "InMemoryStateCoordinator",
        "InMemoryStateProvider",
        "Lease",
        "NamespaceTransaction",
        "State",
        "StateCoordinator",
        "StateEntry",
        "StateNamespace",
        "StateProvider",
        "StateStore",
        "StateTransaction",
    },
    "orbit.types": {
        "ApplicationId",
        "ConfigurationId",
        "EventId",
        "PluginId",
        "ProviderId",
        "RequestId",
        "RouteId",
        "ServiceId",
        "SubscriptionId",
        "new_application_id",
        "new_configuration_id",
        "new_event_id",
        "new_plugin_id",
        "new_provider_id",
        "new_request_id",
        "new_route_id",
        "new_service_id",
        "new_subscription_id",
    },
}


def test_documented_packages_have_resolvable_public_exports() -> None:
    """Every documented import boundary exposes a unique, non-private ``__all__``."""
    reference = Path(__file__).parents[2] / "docs" / "reference.md"
    documented_packages = {
        line.split("|")[1].strip().strip("`")
        for line in reference.read_text(encoding="utf-8").splitlines()
        if line.startswith("| `")
    }
    assert documented_packages == set(_EXPECTED_PUBLIC_EXPORTS), (
        "API reference package rows and the explicit public-export manifest must match"
    )
    assert set(_PUBLIC_PACKAGES) == set(_EXPECTED_PUBLIC_EXPORTS)

    for package_name in _PUBLIC_PACKAGES:
        package = import_module(package_name)
        exports = getattr(package, "__all__", None)
        assert isinstance(exports, (list, tuple)), f"{package_name} must define a sequence __all__"
        assert set(exports) == _EXPECTED_PUBLIC_EXPORTS[package_name], (
            f"{package_name} public exports changed; update the API contract and documentation"
        )
        assert len(exports) == len(set(exports)), f"{package_name} has duplicate exports"
        assert all(
            isinstance(name, str) and (not name.startswith("_") or name == "__version__")
            for name in exports
        )
        for name in exports:
            assert hasattr(package, name), f"{package_name}.{name} is not importable"


def test_security_authenticator_is_exported_from_focused_package() -> None:
    """The documented provider-neutral authentication contract has a stable import path."""
    from orbit.security import Authenticator

    assert Authenticator.__name__ == "Authenticator"


def test_generic_configuration_loader_is_exported_from_focused_package() -> None:
    """The documented generic configuration entry point has a stable import path."""
    from orbit.config import load_config

    assert callable(load_config)


def test_core_contracts_are_exported_from_focused_packages() -> None:
    """Extension authors can import the documented Core contracts without private modules."""
    from orbit.admin import AdminContribution
    from orbit.asgi import Middleware, NextHandler
    from orbit.container import ContainerContract, DependencyKey
    from orbit.health import HealthCheck
    from orbit.lifecycle import LifecycleObserver
    from orbit.plugins import PluginContract
    from orbit.services import ServiceContract

    for contract in (
        AdminContribution,
        Middleware,
        NextHandler,
        ContainerContract,
        DependencyKey,
        HealthCheck,
        LifecycleObserver,
        PluginContract,
        ServiceContract,
    ):
        assert contract is not None


def test_application_builder_service_capacity_is_bounded(monkeypatch) -> None:
    """The fluent composition helper cannot retain an unbounded service list."""
    from orbit.application import ApplicationBuilder
    from orbit.config import ApplicationConfig

    monkeypatch.setattr("orbit.application.builder._MAX_CORE_CAPACITY", 1)
    builder = ApplicationBuilder(ApplicationConfig(name="builder-capacity"))
    builder.service(object())  # type: ignore[arg-type]
    with pytest.raises(RuntimeError, match="capacity"):
        builder.service(object())  # type: ignore[arg-type]
