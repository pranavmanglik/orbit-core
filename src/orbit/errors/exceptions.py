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
"""Python exception hierarchy backed by structured Orbit problems."""

from orbit.errors.error import OrbitProblem


class OrbitError(Exception):
    """Base exception for expected Orbit framework failures."""

    def __init__(self, problem: OrbitProblem) -> None:
        """Create an exception carrying a reusable operational problem."""
        self.problem = problem
        super().__init__(problem.message)


class ConfigurationError(OrbitError):
    """Raised when typed configuration cannot be composed or validated."""


class ContainerError(OrbitError):
    """Raised when dependency registration or resolution violates a contract."""


class LifecycleError(OrbitError):
    """Raised when a managed component makes an invalid state transition."""


class PluginError(OrbitError):
    """Raised when plugin metadata, discovery, or activation fails."""


class RoutingError(OrbitError):
    """Raised when routing metadata is ambiguous or cannot match a request."""


class SecurityError(OrbitError):
    """Raised when an identity or authorization contract rejects an action."""


class ValidationError(OrbitError):
    """Raised when an Orbit invariant fails outside Pydantic validation."""


__all__ = [
    "ConfigurationError",
    "ContainerError",
    "LifecycleError",
    "OrbitError",
    "PluginError",
    "RoutingError",
    "SecurityError",
    "ValidationError",
]
