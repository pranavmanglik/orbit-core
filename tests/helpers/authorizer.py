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
"""Minimal test-only route authorizer for Core integration tests."""

from orbit.errors import ErrorCategory, OrbitProblem, SecurityError


class TestAuthorizer:
    """Authorize a route only when the test principal has every required label."""

    async def authorize_roles(self, principal, required_roles) -> None:
        if principal is None or not required_roles.issubset(principal.roles):
            raise SecurityError(
                OrbitProblem(
                    code="security.forbidden",
                    message="Authentication or authorization required.",
                    category=ErrorCategory.SECURITY,
                )
            )
