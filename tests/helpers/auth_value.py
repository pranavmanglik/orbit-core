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
"""Opaque authenticated test values for Core extension-contract checks."""

from dataclasses import dataclass


@dataclass(frozen=True)
class AuthTestIdentity:
    """Minimal test-only identity shape consumed by Admin audit fixtures."""

    subject: str
    provider: str


@dataclass(frozen=True)
class AuthTestPrincipal:
    """Minimal test-only role subject; Core treats this value as opaque."""

    identity: AuthTestIdentity
    roles: frozenset[str]


__all__ = ["AuthTestIdentity", "AuthTestPrincipal"]
