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
"""Validated operational limits shared by application, ASGI, health and admin."""

from ipaddress import ip_network

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    field_validator,
)

from orbit._limits import _MAX_CORE_CAPACITY
from orbit.types import ApplicationId, new_application_id


class ApplicationConfig(BaseModel):
    """Immutable process configuration with bounded resource and timeout defaults."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        allow_inf_nan=False,
        validate_default=True,
    )
    id: ApplicationId = Field(default_factory=new_application_id)
    name: StrictStr = Field(pattern=r"^[a-z][a-z0-9-]{0,62}$")
    environment: StrictStr = Field(default="development", pattern=r"^[a-z][a-z0-9-]{0,62}$")
    lifecycle_timeout: StrictFloat = Field(default=30.0, gt=0, le=600)
    health_timeout: StrictFloat = Field(default=2.0, gt=0, le=60)
    request_timeout: StrictFloat = Field(default=30.0, gt=0, le=600)
    max_body_bytes: StrictInt = Field(default=1024 * 1024, ge=0, le=1024 * 1024 * 1024)
    max_response_bytes: StrictInt = Field(
        default=16 * 1024 * 1024, ge=1024, le=4 * 1024 * 1024 * 1024
    )
    max_header_bytes: StrictInt = Field(default=64 * 1024, ge=1024, le=16 * 1024 * 1024)
    max_concurrent_requests: StrictInt = Field(default=1000, ge=1, le=_MAX_CORE_CAPACITY)
    trust_forwarded_headers: StrictBool = False
    trusted_proxies: tuple[StrictStr, ...] = ()

    @field_validator(
        "lifecycle_timeout",
        "health_timeout",
        "request_timeout",
        "max_body_bytes",
        "max_response_bytes",
        "max_header_bytes",
        "max_concurrent_requests",
        mode="before",
    )
    @classmethod
    def reject_boolean_limits(cls, value: object) -> object:
        """Reject Python's implicit bool-as-number coercion in resource policies."""
        if isinstance(value, bool):
            raise ValueError("application numeric limits must not be booleans.")
        return value

    @field_validator("trusted_proxies")
    @classmethod
    def validate_trusted_proxies(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        """Validate bounded CIDR entries and remove duplicates while preserving order."""
        if len(values) > _MAX_CORE_CAPACITY:
            raise ValueError("trusted_proxies cannot exceed Core's capacity limit.")
        if any(
            not 1 <= len(value) <= 255
            or any(ord(character) < 32 or ord(character) == 127 for character in value)
            for value in values
        ):
            raise ValueError("trusted_proxies must contain bounded printable CIDR values.")
        unique_values = tuple(dict.fromkeys(values))
        try:
            for value in unique_values:
                ip_network(value, strict=False)
        except (TypeError, ValueError) as exc:
            raise ValueError("trusted_proxies must contain valid IP networks.") from exc
        return unique_values


__all__ = ["ApplicationConfig"]
