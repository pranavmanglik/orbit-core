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
"""Nested mutability regressions for Core's public structured models."""

from collections.abc import Iterator, Mapping
from copy import copy, deepcopy
from datetime import UTC, datetime, timedelta, tzinfo
from types import MappingProxyType

import pytest

from orbit._immutability import FrozenDict, freeze_mapping, freeze_value, validate_mapping
from orbit.application.models import ApplicationSummary
from orbit.container import Scope
from orbit.diagnostics import DiagnosticSnapshot, LatencyBucket, RequestRecord
from orbit.diagnostics.inspection import CompositionSnapshot, ProviderDescription
from orbit.errors import ErrorCategory, ErrorResponse, OrbitProblem
from orbit.events import Event
from orbit.health import HealthReport
from orbit.services import ServiceDescriptor
from orbit.state import ApplicationState
from orbit.state.models import ComponentState
from orbit.types import new_application_id, new_configuration_id, new_provider_id, new_request_id


class _MisreportingMapping(Mapping[str, object]):
    """Mapping that reports no entries but yields more than a configured safety bound."""

    def __init__(self, count: int) -> None:
        self._count = count

    def __getitem__(self, key: str) -> object:
        index = int(key)
        if 0 <= index < self._count:
            return True
        raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        return iter(str(index) for index in range(self._count))

    def __len__(self) -> int:
        return 0


class _MisreportingStatusCounts(Mapping[int, int]):
    """Status-count mapping that reports no entries but yields 501 valid HTTP statuses."""

    def __iter__(self) -> Iterator[int]:
        return iter((*range(100, 600), 599))

    def __getitem__(self, key: int) -> int:
        if 99 <= key <= 599:
            return 1
        raise KeyError(key)

    def __len__(self) -> int:
        return 0


@pytest.mark.parametrize(
    "factory, field",
    [
        (
            lambda mapping: Event(name="orders.created", payload={}, metadata=mapping),
            "metadata",
        ),
        (lambda mapping: ServiceDescriptor(name="orders", metadata=mapping), "metadata"),
        (lambda mapping: HealthReport(details=mapping), "details"),
        (
            lambda mapping: OrbitProblem(
                code="runtime.failed",
                message="failed",
                category=ErrorCategory.RUNTIME,
                context=mapping,
            ),
            "context",
        ),
    ],
)
def test_structured_model_mappings_are_detached_and_immutable(factory, field: str) -> None:
    """Frozen models reject nested mutation and do not retain caller-owned mappings."""
    source = {"nested": {"value": 1}}
    model = factory(source)
    source["nested"]["value"] = 2
    value = getattr(model, field)
    assert value["nested"]["value"] == 1
    with pytest.raises(TypeError, match="immutable"):
        value["nested"]["value"] = 3


@pytest.mark.parametrize(
    "factory",
    [
        lambda mapping: Event(name="orders.created", payload={}, metadata=mapping),
        lambda mapping: ServiceDescriptor(name="orders", metadata=mapping),
        lambda mapping: OrbitProblem(
            code="runtime.failed",
            message="failed",
            category=ErrorCategory.RUNTIME,
            context=mapping,
        ),
        lambda mapping: OrbitProblem(
            code="runtime.failed",
            message="failed",
            category=ErrorCategory.RUNTIME,
            metadata=mapping,
        ),
    ],
)
@pytest.mark.parametrize(
    "mapping", [{"unsafe\nkey": True}, {str(index): True for index in range(2_049)}]
)
def test_structured_model_mappings_reject_unsafe_or_unbounded_keys(factory, mapping) -> None:
    """Retained Core mappings have bounded, printable key contracts."""
    with pytest.raises(ValueError):
        factory(mapping)
    with pytest.raises(ValueError):
        factory({b"unsafe": True})  # type: ignore[dict-item]


def test_structured_error_metadata_is_immutable() -> None:
    problem = OrbitProblem(
        code="runtime.failed",
        message="failed",
        category=ErrorCategory.RUNTIME,
        metadata={"trace": {"id": "abc"}},
    )
    with pytest.raises(TypeError, match="immutable"):
        problem.metadata["trace"]["id"] = "changed"


def test_structured_models_reject_cyclic_or_excessively_nested_values() -> None:
    cyclic: dict[str, object] = {}
    cyclic["self"] = cyclic
    with pytest.raises(ValueError, match="cyclic"):
        Event(name="orders.created", payload={}, metadata=cyclic)

    nested: object = "leaf"
    for _ in range(64):
        nested = [nested]
    with pytest.raises(ValueError, match="nested"):
        HealthReport(details={"nested": nested})


@pytest.mark.parametrize("key", [b"bytes-key", "control\nkey", "x" * 256])
def test_structured_models_reject_unsafe_nested_mapping_keys(key: object) -> None:
    """Nested mapping keys cannot bypass JSON-safe Core metadata contracts."""
    with pytest.raises(ValueError, match="Structured mapping keys"):
        Event(name="orders.created", payload={}, metadata={"nested": {key: "value"}})


def test_structured_models_freeze_nested_mapping_implementations() -> None:
    model = Event(
        name="orders.created",
        payload={},
        metadata={"nested": MappingProxyType({"value": 1})},
    )
    with pytest.raises(TypeError, match="immutable"):
        model.metadata["nested"]["value"] = 2


@pytest.mark.parametrize(
    "operation",
    [
        lambda value: value.__setitem__("new", 2),
        lambda value: value.__delitem__("value"),
        lambda value: value.__ior__({"new": 2}),
        lambda value: value.clear(),
        lambda value: value.pop("value"),
        lambda value: value.popitem(),
        lambda value: value.setdefault("new", 2),
        lambda value: value.update({"new": 2}),
    ],
)
def test_frozen_dict_rejects_every_in_place_mapping_mutator(operation) -> None:
    """All dict mutation spellings preserve Core snapshots as immutable values."""
    value = freeze_mapping({"value": 1})

    with pytest.raises(TypeError, match="immutable"):
        operation(value)
    assert value == {"value": 1}


def test_frozen_dict_copies_remain_immutable_and_detached() -> None:
    """Snapshot copies retain the immutability invariant Pydantic relies on."""
    value = freeze_mapping({"nested": {"value": 1}})

    shallow = copy(value)
    recursive = deepcopy(value)

    assert isinstance(shallow, FrozenDict)
    assert isinstance(recursive, FrozenDict)
    assert shallow == recursive == value
    with pytest.raises(TypeError, match="immutable"):
        recursive["nested"]["value"] = 2


def test_freezing_allows_shared_children_without_retaining_caller_ownership() -> None:
    """Repeated references are copied safely; only references on the active path are cycles."""
    child = {"value": 1}
    frozen = freeze_value({"first": child, "second": child})

    child["value"] = 2
    assert frozen == {"first": {"value": 1}, "second": {"value": 1}}
    with pytest.raises(TypeError, match="immutable"):
        frozen["first"]["value"] = 3


def test_structured_models_enforce_recursive_work_budget(monkeypatch) -> None:
    import orbit._immutability as immutability

    monkeypatch.setattr(immutability, "_MAX_FREEZE_ITEMS", 3)
    with pytest.raises(ValueError, match="items"):
        Event(name="orders.created", payload={}, metadata={"items": [1, 2]})


def test_mapping_boundaries_enforce_limits_during_materialization() -> None:
    """Misreported mapping lengths cannot bypass incremental structured-value limits."""
    with pytest.raises(ValueError, match="2 entries"):
        validate_mapping(_MisreportingMapping(3), name="test mapping", max_entries=2)


@pytest.mark.parametrize(
    "factory",
    [
        lambda: OrbitProblem(
            code="runtime.failed",
            message="bad\nmessage",
            category=ErrorCategory.RUNTIME,
        ),
        lambda: OrbitProblem(
            code="runtime.failed",
            message="x" * 1025,
            category=ErrorCategory.RUNTIME,
        ),
        lambda: ErrorResponse(code="Bad Code"),
        lambda: ErrorResponse(code="runtime.failed", message="bad\x7fmessage"),
    ],
)
def test_structured_error_text_is_bounded_and_printable(factory) -> None:
    """Shared error models cannot carry unsafe text into HTTP or diagnostics surfaces."""
    with pytest.raises(ValueError):
        factory()


def test_health_report_keeps_aware_timestamp() -> None:
    report = HealthReport(checked_at=datetime(2026, 1, 1, tzinfo=UTC))
    assert report.checked_at.tzinfo is UTC
    with pytest.raises(ValueError):
        HealthReport(details={b"unsafe": True})  # type: ignore[dict-item]


class _BrokenTimezone(tzinfo):
    """Timezone used to prove malformed offsets fail as Core validation errors."""

    def utcoffset(self, dt: datetime | None) -> timedelta:
        del dt
        raise RuntimeError("synthetic timezone failure")


def test_health_report_rejects_broken_timezone_without_leaking_datetime_error() -> None:
    """Health reports convert broken custom timezone offsets into bounded validation errors."""
    with pytest.raises(ValueError, match="timestamps"):
        HealthReport(checked_at=datetime(2026, 1, 1, tzinfo=_BrokenTimezone()))


def test_runtime_models_reject_coerced_operational_values() -> None:
    with pytest.raises(ValueError):
        ApplicationState(application_id=new_application_id(), service_count=True)
    with pytest.raises(ValueError):
        OrbitProblem(
            code=b"runtime.failed",  # type: ignore[arg-type]
            message="failed",
            category=ErrorCategory.RUNTIME,
        )


def test_operator_snapshots_reject_unsafe_component_names() -> None:
    """State and administrative summaries cannot carry malformed operator identifiers."""
    with pytest.raises(ValueError):
        ComponentState(name="service\nname")
    with pytest.raises(ValueError):
        ApplicationSummary(
            state=ApplicationState(application_id=new_application_id()),
            service_names=("service\nname",),
        )


def test_operator_snapshot_collections_reuse_core_capacity(monkeypatch) -> None:
    """Detached application and state summaries cannot bypass registry capacity policy."""
    import orbit.application.models as application_models
    import orbit.state.models as state_models

    monkeypatch.setattr(application_models, "_MAX_CORE_CAPACITY", 1)
    with pytest.raises(ValueError, match="service summaries"):
        ApplicationSummary(
            state=ApplicationState(application_id=new_application_id()),
            service_names=("orders", "users"),
        )

    monkeypatch.setattr(state_models, "_MAX_CORE_CAPACITY", 1)
    with pytest.raises(ValueError, match="component snapshots"):
        ApplicationState(
            application_id=new_application_id(),
            services=(ComponentState(name="orders"), ComponentState(name="users")),
        )


def test_composition_snapshots_detach_configuration_and_validate_provider_text() -> None:
    configuration = {"application": {"name": "demo"}}
    snapshot = CompositionSnapshot(
        services=(),
        plugins=(),
        routes=(),
        dependencies=(
            ProviderDescription(
                id=new_provider_id(),
                key="service",
                scope=Scope.SINGLETON,
                dependencies=(),
                resource=False,
            ),
        ),
        configuration_id=new_configuration_id(),
        configuration=configuration,
    )
    configuration["application"]["name"] = "changed"
    assert snapshot.configuration["application"]["name"] == "demo"
    with pytest.raises(TypeError, match="immutable"):
        snapshot.configuration["application"]["name"] = "changed"  # type: ignore[index]
    with pytest.raises(ValueError, match="printable"):
        ProviderDescription(
            id=new_provider_id(),
            key="bad\nprovider",
            scope=Scope.SINGLETON,
            dependencies=(),
            resource=False,
        )


def test_inspection_collections_reuse_core_capacity(monkeypatch) -> None:
    """Composition and provider inspection models enforce their collection limits directly."""
    import orbit.diagnostics.inspection as inspection

    monkeypatch.setattr(inspection, "_MAX_RELATION_ENTRIES", 1)
    with pytest.raises(ValueError, match="inspection dependencies"):
        ProviderDescription(
            id=new_provider_id(),
            key="service",
            scope=Scope.SINGLETON,
            dependencies=("a", "b"),
            resource=False,
        )

    monkeypatch.setattr(inspection, "_MAX_CORE_CAPACITY", 1)
    with pytest.raises(ValueError, match="Composition snapshot collections"):
        CompositionSnapshot(
            services=(ServiceDescriptor(name="orders"), ServiceDescriptor(name="users")),
            plugins=(),
            routes=(),
            dependencies=(),
            configuration_id=new_configuration_id(),
            configuration={},
        )


def test_diagnostic_snapshot_collections_are_bounded(monkeypatch) -> None:
    """Direct diagnostics snapshots cannot retain unbounded history or bucket metadata."""
    import orbit.diagnostics.models as diagnostic_models

    application = ApplicationSummary(
        state=ApplicationState(application_id=new_application_id()),
        service_names=(),
    )
    monkeypatch.setattr(diagnostic_models, "_MAX_RELATION_ENTRIES", 1)
    with pytest.raises(ValueError, match="latency buckets"):
        DiagnosticSnapshot(
            application=application,
            latency_buckets=(
                LatencyBucket(upper_bound=1.0, count=0),
                LatencyBucket(upper_bound=2.0, count=0),
            ),
        )

    monkeypatch.setattr(diagnostic_models, "_MAX_CORE_CAPACITY", 1)
    records = (
        RequestRecord(request_id=new_request_id(), method="GET", status=200, duration_seconds=0.1),
        RequestRecord(request_id=new_request_id(), method="GET", status=200, duration_seconds=0.2),
    )
    with pytest.raises(ValueError, match="request history"):
        DiagnosticSnapshot(
            application=application,
            request_count=2,
            recent_requests=records,
            status_counts={200: 2},
        )

    with pytest.raises(ValueError, match="500"):
        DiagnosticSnapshot(
            application=application,
            request_count=501,
            status_counts=_MisreportingStatusCounts(),  # type: ignore[arg-type]
        )
