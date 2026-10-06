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
"""Stable error categories and severity levels."""

from enum import StrEnum


class ErrorCategory(StrEnum):
    """Classifies an operational error by owning Core boundary."""

    CONFIGURATION = "configuration"
    CONTAINER = "container"
    LIFECYCLE = "lifecycle"
    PLUGIN = "plugin"
    ROUTING = "routing"
    RUNTIME = "runtime"
    SECURITY = "security"
    VALIDATION = "validation"


class ErrorSeverity(StrEnum):
    """Expresses operational impact independently of the transport."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


__all__ = ["ErrorCategory", "ErrorSeverity"]
