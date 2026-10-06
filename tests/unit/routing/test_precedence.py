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
"""Route registration invariants, path semantics and service boundaries."""

import pytest

from orbit.asgi import Response
from orbit.errors import RoutingError
from orbit.routing import Route, RouteMetadata, Router


async def handler(request):
    return Response.text("ok")


@pytest.mark.parametrize(
    "path",
    ["relative", "/a/{bad-name}", "/a/{x}/{x}", "/a//b", "/a/../b", "/a?query", "/a/{x}tail"],
)
def test_invalid_route_templates(path):
    with pytest.raises(ValueError):
        RouteMetadata(name="route", path=path, method="GET")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"path": "/" + "a" * 2048},
        {"path": "/route", "summary": "x" * 1025},
        {"path": "/route", "summary": "unsafe\nsummary"},
        {"path": "/route", "api_version": "v" + "1" * 32},
    ],
)
def test_route_metadata_is_bounded_for_openapi_and_inspection(kwargs):
    with pytest.raises(ValueError):
        RouteMetadata(name="route", method="GET", **kwargs)


def test_route_metadata_matches_the_request_path_parameter_limits() -> None:
    """Route composition rejects templates that Request cannot safely materialize."""
    too_many = "/" + "/".join(f"{{value{index}}}" for index in range(129))
    with pytest.raises(ValueError, match="parameters"):
        RouteMetadata(name="too-many-parameters", path=too_many, method="GET")

    too_long = "/{" + "a" * 128 + "}"
    with pytest.raises(ValueError, match="Parameters"):
        RouteMetadata(name="long-parameter", path=too_long, method="GET")


def test_equivalent_templates_are_rejected():
    router = Router()
    router.register(Route(RouteMetadata(name="one", path="/a/{id}", method="GET"), handler))
    with pytest.raises(RoutingError):
        router.register(Route(RouteMetadata(name="two", path="/a/{name}", method="GET"), handler))


def test_route_construction_validates_handler_models_and_middleware():
    router = Router()
    metadata = RouteMetadata(name="route", path="/route", method="GET")
    with pytest.raises(TypeError, match="Route handlers"):
        Route(metadata, object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="Pydantic"):
        Route(metadata, handler, request_model=object)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="middleware"):
        Route(metadata, handler, middleware=(object(),))  # type: ignore[arg-type]
    with pytest.raises(RoutingError, match="Routes"):
        router.register(object())  # type: ignore[arg-type]


def test_route_registry_capacity_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    """Route composition cannot grow an unbounded dispatch table."""
    monkeypatch.setattr("orbit.routing.router._MAX_CORE_CAPACITY", 1)
    router = Router()
    router.register(Route(RouteMetadata(name="first", path="/first", method="GET"), handler))
    with pytest.raises(RoutingError, match="capacity"):
        router.register(Route(RouteMetadata(name="second", path="/second", method="GET"), handler))


def test_static_paths_take_precedence_independent_of_registration():
    router = Router()
    router.register(Route(RouteMetadata(name="dynamic", path="/a/{id}", method="GET"), handler))
    router.register(Route(RouteMetadata(name="static", path="/a/current", method="GET"), handler))
    assert router.match("GET", "/a/current")[0].metadata.name == "static"
    with pytest.raises(RoutingError):
        router.match("GET", "/a/current/")
    assert router.allowed_methods("/absent") == ()
    router.freeze()
    with pytest.raises(RoutingError):
        router.register(Route(RouteMetadata(name="late", path="/late", method="GET"), handler))


def test_static_path_precedence_only_applies_when_the_full_static_route_matches():
    """A dead static prefix must not hide a matching parameter route."""
    router = Router()
    router.register(
        Route(RouteMetadata(name="static-other", path="/a/fixed/other", method="GET"), handler)
    )
    router.register(
        Route(RouteMetadata(name="parameter", path="/a/{key}/current", method="GET"), handler)
    )

    route, parameters = router.match("GET", "/a/fixed/current")

    assert route.metadata.name == "parameter"
    assert parameters == {"key": "fixed"}


def test_static_path_method_mismatch_does_not_fall_back_to_parameter_route():
    """A more specific path keeps its own Allow methods even when another path could match."""
    router = Router()
    router.register(Route(RouteMetadata(name="parameter", path="/a/{key}", method="GET"), handler))
    router.register(Route(RouteMetadata(name="static", path="/a/current", method="POST"), handler))

    with pytest.raises(RoutingError, match="Method is not allowed") as error:
        router.match("GET", "/a/current")

    assert error.value.problem.context["allow"] == "OPTIONS, POST"


def test_route_index_does_not_iterate_the_full_registry_for_match_or_registration():
    """Hot-path lookup and duplicate checks use indexes after composition."""

    class NoScanList(list):
        def __iter__(self):
            raise AssertionError("The route registry was scanned.")

    router = Router()
    router.register(Route(RouteMetadata(name="first", path="/first/{key}", method="GET"), handler))
    router._routes = NoScanList(router._routes)  # noqa: SLF001 - assert the public path uses indexes.

    route, parameters = router.match("GET", "/first/42")
    assert route.metadata.name == "first"
    assert parameters == {"key": "42"}

    router.register(Route(RouteMetadata(name="second", path="/second", method="GET"), handler))


def test_route_index_handles_deep_paths_without_recursive_dispatch():
    """Deep canonical paths do not consume Python's recursion stack."""
    path = "/" + "/".join(["x"] * 1_000)
    router = Router()
    route = Route(RouteMetadata(name="deep", path=path, method="GET"), handler)
    router.register(route)

    matched, parameters = router.match("GET", path)

    assert matched is route
    assert parameters == {}


@pytest.mark.parametrize("method", [None, 1, "CONNECT"])
def test_direct_matching_rejects_unsupported_methods(method):
    router = Router()
    with pytest.raises(RoutingError, match="method"):
        router.match(method, "/a")  # type: ignore[arg-type]


def test_direct_matching_normalizes_method_case():
    router = Router()
    router.register(Route(RouteMetadata(name="lower", path="/a", method="GET"), handler))
    assert router.match("get", "/a")[0].metadata.name == "lower"


@pytest.mark.parametrize(
    "path",
    [
        "relative",
        "/a/../secret",
        "/a//secret",
        "/a\\secret",
        "/a\x7f",
        "/" + "a" * 16384,
        "/\ud800",
    ],
)
def test_direct_router_dispatch_rejects_noncanonical_paths(path):
    router = Router()
    with pytest.raises(RoutingError):
        router.allowed_methods(path)  # type: ignore[arg-type]


def test_route_groups_apply_prefix_names_and_roles_including_nested_groups():
    router = Router()
    api = router.group("/api", name_prefix="api", roles=frozenset({"reader"}))
    nested = api.group("/v1", name_prefix="v1", roles=frozenset({"member"}))

    @nested.route("/users/{user_id}", name="detail")
    async def detail(request):
        return Response.text(request.path_parameters["user_id"])

    route, parameters = router.match("GET", "/api/v1/users/42")
    assert route.metadata.name == "api-v1-detail"
    assert route.metadata.roles == frozenset({"reader", "member"})
    assert parameters == {"user_id": "42"}


def test_route_groups_normalize_role_collections_at_composition_boundary() -> None:
    """Nested groups accept collections but retain immutable validated role metadata."""
    router = Router()
    group = router.group("/api", roles=["reader"])  # type: ignore[arg-type]
    nested = group.group("/v1", roles=("member",))  # type: ignore[arg-type]

    @nested.route("/users", name="list")
    async def list_users(request):
        return Response.text("ok")

    assert router.routes[0].metadata.roles == frozenset({"reader", "member"})
    with pytest.raises(TypeError, match="collections of strings"):
        router.group("/bad", roles="reader")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="Role and scope identifiers must be strings"):
        router.group("/bad", roles={1})  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "prefix",
    [None, "relative", "/a//b", "/a/../b", "/a?query", "/a\\b", "/" + "a" * 16_384],
)
def test_route_groups_reject_noncanonical_prefixes(prefix) -> None:
    """Group composition applies the same canonical path boundary as route metadata."""
    router = Router()
    with pytest.raises((TypeError, ValueError)):
        router.group(prefix)  # type: ignore[arg-type]


def test_route_group_rejects_unsafe_name_prefix() -> None:
    router = Router()
    with pytest.raises(ValueError):
        router.group("/api", name_prefix="bad\nname")


def test_route_group_rejects_non_string_path_at_composition_time() -> None:
    group = Router().group("/api")
    with pytest.raises(TypeError, match="paths must be strings"):
        group.route(None, name="invalid")  # type: ignore[arg-type]


def test_route_metadata_rejects_invalid_unicode_path() -> None:
    with pytest.raises(ValueError):
        RouteMetadata(name="invalid", path="/\ud800", method="GET")
