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
"""Public errors, categories, and exception types for Orbit Core."""

from orbit.errors.categories import ErrorCategory, ErrorSeverity
from orbit.errors.error import ErrorResponse, OrbitProblem
from orbit.errors.exceptions import (
    ConfigurationError,
    ContainerError,
    LifecycleError,
    OrbitError,
    PluginError,
    RoutingError,
    SecurityError,
    ValidationError,
)

__all__ = [
    "ErrorResponse",
    "ConfigurationError",
    "ContainerError",
    "ErrorCategory",
    "ErrorSeverity",
    "LifecycleError",
    "OrbitError",
    "OrbitProblem",
    "PluginError",
    "RoutingError",
    "SecurityError",
    "ValidationError",
]
