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
"""Diagnostics snapshots built from Core-owned state."""

from typing import TYPE_CHECKING, Any

from orbit.diagnostics.diagnostics import Diagnostics
from orbit.diagnostics.metrics import Counter, Gauge, Histogram, MetricSnapshot, MetricsRegistry
from orbit.diagnostics.models import DiagnosticSnapshot, LatencyBucket, RequestRecord, TelemetrySink
from orbit.diagnostics.tracing import InMemoryTracer, Span, SpanRecord, Tracer

if TYPE_CHECKING:
    from orbit.diagnostics.inspection import inspect_composition

__all__ = [
    "DiagnosticSnapshot",
    "Diagnostics",
    "Counter",
    "Gauge",
    "Histogram",
    "InMemoryTracer",
    "LatencyBucket",
    "MetricSnapshot",
    "MetricsRegistry",
    "RequestRecord",
    "Span",
    "SpanRecord",
    "Tracer",
    "TelemetrySink",
    "inspect_composition",
]


def __getattr__(name: str) -> Any:
    """Load application inspection lazily to avoid import cycles with routing contracts."""
    if name == "inspect_composition":
        from orbit.diagnostics.inspection import inspect_composition

        return inspect_composition
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
