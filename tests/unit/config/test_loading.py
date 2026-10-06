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
"""Layering, validation and secret handling across extension configuration."""

import asyncio
from collections.abc import Iterator, Mapping
from concurrent.futures import ThreadPoolExecutor

import pytest
from pydantic import BaseModel, ConfigDict, SecretStr, ValidationError

from orbit.config import ApplicationConfig
from orbit.config.config import Config, ConfigChange, ConfigSnapshot
from orbit.config.loader import load_application_config, load_config
from orbit.errors import ConfigurationError


class Database(BaseModel):
    model_config = ConfigDict(extra="forbid")
    host: str
    password: SecretStr


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    database: Database


class _BoundedConfigMapping(Mapping[str, object]):
    """Mapping that fails if a copier requests entries beyond the configured work budget."""

    def __getitem__(self, key: str) -> object:
        if key in {"first", "second"}:
            return True
        raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        yield "first"
        yield "second"
        raise AssertionError("configuration mapping was materialized past its budget")

    def __len__(self) -> int:
        return 0


class _SinglePassConfigMapping(Mapping[str, object]):
    """Mapping that fails if configuration composition reads caller input twice."""

    def __init__(self) -> None:
        self.iterations = 0

    def __getitem__(self, key: str) -> object:
        if key == "name":
            return "test"
        raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        self.iterations += 1
        if self.iterations > 1:
            raise AssertionError("configuration input was read after detachment")
        return iter(("name",))

    def __len__(self) -> int:
        return 1


class _HashableConfigMapping(Mapping[str, object]):
    """Mapping-shaped input that exposes invalid set-member normalization."""

    def __getitem__(self, key: str) -> object:
        if key == "value":
            return True
        raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        return iter(("value",))

    def __len__(self) -> int:
        return 1

    def __hash__(self) -> int:
        return id(self)


def test_nested_configuration_precedence_and_redaction(tmp_path):
    file = tmp_path / "config.toml"
    file.write_text('[database]\nhost="file"\npassword="private"\n')
    settings = load_config(
        Settings,
        file=file,
        values={"database": {"host": "mapping"}},
        environment={"ORBIT_DATABASE__HOST": "environment"},
    )
    assert settings.database.host == "environment"
    config = Config(ApplicationConfig(name="test"))
    config.register("database", settings)
    assert "private" not in str(config.inspect())
    config.freeze()
    with pytest.raises(ValueError):
        config.register("other", settings)


@pytest.mark.parametrize(
    "environment",
    [
        {},
        {"ORBIT_NAME": "INVALID"},
        {"ORBIT_NAME": "test", "ORBIT_UNKNOWN": "secret"},
        {"ORBIT_NAME": "test", "ORBIT_REQUEST_TIMEOUT": "-1"},
        {"ORBIT_NAME": "test", "ORBIT__": "x"},
    ],
)
def test_invalid_config_never_exposes_submitted_values(environment):
    with pytest.raises(ConfigurationError) as caught:
        load_application_config(environment)
    assert "secret" not in str(caught.value)
    assert "secret" not in caught.value.problem.model_dump_json()


def test_environment_coercion():
    config = load_application_config({"ORBIT_NAME": "test", "ORBIT_MAX_CONCURRENT_REQUESTS": "42"})
    assert config.max_concurrent_requests == 42


def test_application_defaults_preserve_declared_numeric_types() -> None:
    """Validated defaults must retain the strict runtime types exposed by the model."""
    config = ApplicationConfig(name="test")
    assert isinstance(config.lifecycle_timeout, float)
    assert isinstance(config.health_timeout, float)
    assert isinstance(config.request_timeout, float)


def test_application_header_limit_is_bounded():
    with pytest.raises(ValidationError):
        ApplicationConfig(name="test", max_header_bytes=512)
    with pytest.raises(ValidationError):
        ApplicationConfig(name="test", max_header_bytes=17 * 1024 * 1024)
    with pytest.raises(ValidationError, match="trusted_proxies"):
        ApplicationConfig(name="test", trusted_proxies=("not-an-network",))
    with pytest.raises(ValidationError, match="trusted_proxies"):
        ApplicationConfig(name="test", trusted_proxies=(None,))  # type: ignore[arg-type]
    with pytest.raises(ValidationError, match="trusted_proxies"):
        ApplicationConfig(name="test", trusted_proxies=("127.0.0.1/32\n",))
    with pytest.raises(ValidationError, match="trusted_proxies"):
        ApplicationConfig(name="test", trusted_proxies=("x" * 256,))


def test_trusted_proxy_capacity_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    """Proxy trust policy cannot retain an unbounded network allowlist."""
    import orbit.config.models as config_models

    monkeypatch.setattr(config_models, "_MAX_CORE_CAPACITY", 1)
    with pytest.raises(ValidationError, match="trusted_proxies"):
        ApplicationConfig(
            name="test",
            trusted_proxies=("127.0.0.1/32", "10.0.0.0/8"),
        )


def test_application_concurrency_limit_is_bounded() -> None:
    """Request admission cannot be configured beyond Core's shared capacity ceiling."""
    with pytest.raises(ValidationError):
        ApplicationConfig(name="test", max_concurrent_requests=1_000_001)


@pytest.mark.parametrize(
    "field",
    [
        "lifecycle_timeout",
        "health_timeout",
        "request_timeout",
        "max_body_bytes",
        "max_response_bytes",
        "max_header_bytes",
        "max_concurrent_requests",
    ],
)
def test_application_numeric_limits_reject_booleans(field: str) -> None:
    with pytest.raises(ValidationError, match="must not be booleans"):
        ApplicationConfig(name="test", **{field: True})


@pytest.mark.parametrize(
    "field",
    [
        "lifecycle_timeout",
        "health_timeout",
        "request_timeout",
        "max_body_bytes",
        "max_response_bytes",
        "max_header_bytes",
        "max_concurrent_requests",
    ],
)
def test_application_numeric_limits_reject_string_coercion(field: str) -> None:
    """Operational limits cannot change type through direct model construction."""
    with pytest.raises(ValidationError):
        ApplicationConfig(name="test", **{field: "1"})


@pytest.mark.parametrize("field", ["trust_forwarded_headers"])
def test_application_flags_reject_coercion(field: str) -> None:
    """Security and administration flags require actual booleans."""
    with pytest.raises(ValidationError):
        ApplicationConfig(name="test", **{field: "true"})


def test_application_identity_and_proxy_entries_reject_string_coercion() -> None:
    """Application identity and proxy trust policy require actual text values."""
    with pytest.raises(ValidationError):
        ApplicationConfig(name=1)  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        ApplicationConfig(name="test", environment=1)  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        ApplicationConfig(name="test", trusted_proxies=(1,))  # type: ignore[arg-type]


def test_strict_application_environment_values_are_decoded_before_validation() -> None:
    config = load_application_config(
        {
            "ORBIT_NAME": "test",
            "ORBIT_REQUEST_TIMEOUT": "15.5",
            "ORBIT_MAX_CONCURRENT_REQUESTS": "250",
        }
    )
    assert config.request_timeout == 15.5
    assert config.max_concurrent_requests == 250

    custom = load_config(
        ApplicationConfig,
        prefix="APP_",
        environment={"APP_NAME": "custom", "APP_REQUEST_TIMEOUT": "12.5"},
    )
    assert custom.name == "custom"
    assert custom.request_timeout == 12.5


def test_configuration_snapshots_history_and_structural_diff():
    config = Config(ApplicationConfig(name="test"))
    initial = config.snapshot()
    settings = Settings(database=Database(host="db-a", password="secret"))
    config.register("database", settings)
    current = config.snapshot()

    assert current.version > initial.version
    assert initial.configuration_id == current.configuration_id == config.configuration_id
    assert len(config.history) >= 2
    diff = config.diff(initial)
    assert diff["database.database.host"]["after"] == "db-a"
    assert "secret" not in str(diff)
    with pytest.raises(TypeError):
        current.values["database"] = {}  # type: ignore[index]
    assert current.as_dict()["database"]["database"]["host"] == "db-a"

    with pytest.raises(TypeError, match="ConfigSnapshot"):
        config.diff(object())  # type: ignore[arg-type]
    other = Config(ApplicationConfig(name="other"))
    with pytest.raises(ValueError, match="different configuration"):
        config.diff(other.snapshot())


def test_configuration_history_is_bounded() -> None:
    config = Config(ApplicationConfig(name="test"), history_size=3)
    settings = Settings(database=Database(host="db-a", password="secret"))
    config.register("database", settings)
    config.freeze()
    for host in ("db-b", "db-c", "db-d"):
        config.reload_section("database", Settings(database=Database(host=host, password="x")))
    assert len(config.history) == 3
    assert config.history[-1].values["database"]["database"]["host"] == "db-d"  # type: ignore[index]
    with pytest.raises(ValueError):
        Config(ApplicationConfig(name="test"), history_size=0)
    with pytest.raises(ValueError, match="1,000,000"):
        Config(ApplicationConfig(name="test"), history_size=1_000_001)
    with pytest.raises(ValueError):
        Config(ApplicationConfig(name="test"), history_size=True)
    with pytest.raises(ValueError):
        Config(ApplicationConfig(name="test"), history_size="3")  # type: ignore[arg-type]


def test_configuration_observer_capacity_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    """Configuration reload observers cannot create unbounded callback fan-out."""
    monkeypatch.setattr("orbit.config.config._MAX_CORE_CAPACITY", 1)
    config = Config(ApplicationConfig(name="test"))
    config.subscribe(lambda change: None)
    with pytest.raises(RuntimeError, match="capacity"):
        config.subscribe(lambda change: None)


def test_configuration_section_capacity_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    """Typed configuration sections cannot retain an unbounded composition graph."""
    monkeypatch.setattr("orbit.config.config._MAX_CORE_CAPACITY", 1)
    config = Config(ApplicationConfig(name="test"))
    config.register("first", Settings(database=Database(host="db-a", password="secret")))
    with pytest.raises(RuntimeError, match="capacity"):
        config.register("second", Settings(database=Database(host="db-b", password="secret")))


@pytest.mark.parametrize("source", ["values", "environment", "file"])
def test_configuration_loader_bounds_each_input_source(
    monkeypatch: pytest.MonkeyPatch, tmp_path, source: str
) -> None:
    """Configuration composition bounds explicit, environment, and TOML input work."""
    monkeypatch.setattr("orbit.config.loader._MAX_INPUT_VALUES", 2)
    kwargs: dict[str, object]
    if source == "values":
        kwargs = {"values": {"name": "test"}}
    elif source == "environment":
        kwargs = {"environment": {"ORBIT_NAME": "test"}}
    else:
        file = tmp_path / "config.toml"
        file.write_text('name = "test"\n')
        kwargs = {"file": file}
    with pytest.raises(ConfigurationError):
        load_config(ApplicationConfig, **kwargs)


def test_configuration_loader_detaches_custom_mapping_before_composition() -> None:
    """A caller mapping is validated and consumed exactly once at the loader boundary."""
    values = _SinglePassConfigMapping()

    config = load_config(ApplicationConfig, values=values)

    assert config.name == "test"
    assert values.iterations == 1


def test_configuration_loader_normalizes_invalid_set_members() -> None:
    """Invalid detached set members become the loader's redacted configuration error."""

    class SetSettings(BaseModel):
        model_config = ConfigDict(extra="forbid")
        values: frozenset[object]

    with pytest.raises(ConfigurationError) as caught:
        load_config(SetSettings, values={"values": {_HashableConfigMapping()}})

    assert caught.value.problem.code == "configuration.invalid"
    assert "value" not in caught.value.problem.model_dump_json()


def test_configuration_loader_rejects_cyclic_input() -> None:
    """Configuration composition fails safely on cyclic caller-owned mappings."""
    values: dict[str, object] = {}
    values["self"] = values
    with pytest.raises(ConfigurationError):
        load_config(ApplicationConfig, values=values)

    nested: object = "leaf"
    for _ in range(64):
        nested = {"value": nested}
    with pytest.raises(ConfigurationError):
        load_config(ApplicationConfig, values={"name": "test", "nested": nested})


def test_configuration_registration_rejects_untyped_sections():
    with pytest.raises(TypeError, match="ApplicationConfig"):
        Config(object())  # type: ignore[arg-type]
    config = Config(ApplicationConfig(name="test"))
    with pytest.raises(TypeError, match="nonempty name"):
        config.register("", Settings(database=Database(host="db-a", password="secret")))
    with pytest.raises(TypeError, match="Pydantic model"):
        config.register("database", {"host": "db-a"})  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="identifier-shaped"):
        config.register("Bad Section", Settings(database=Database(host="db-a", password="secret")))
    with pytest.raises(ValueError, match="identifier-shaped"):
        config.register("x" * 64, Settings(database=Database(host="db-a", password="secret")))
    config.register("database", Settings(database=Database(host="db-a", password="secret")))
    with pytest.raises(ValueError, match="frozen"):
        config.reload_section("database", Settings(database=Database(host="db-b", password="x")))


def test_configuration_history_records_validate_identity_and_mapping_keys() -> None:
    snapshot = ConfigSnapshot(0, {"application": {"name": "demo"}})
    change = ConfigChange("database", 1, {"host": "before"}, {"host": "after"})
    assert snapshot.as_dict()["application"]["name"] == "demo"  # type: ignore[index]
    assert change.version == 1

    with pytest.raises(ValueError, match="nonnegative"):
        ConfigSnapshot(-1, {})
    with pytest.raises(ValueError, match="positive"):
        ConfigChange("database", 0, {}, {})
    with pytest.raises(ValueError, match="keys"):
        ConfigSnapshot(1, {1: "not a JSON key"})  # type: ignore[dict-item]
    with pytest.raises(ValueError, match="bounded printable"):
        ConfigSnapshot(1, {"unsafe\nkey": "not a safe JSON key"})
    with pytest.raises(ValueError, match="bounded printable"):
        ConfigSnapshot(1, {"x" * 256: "not a bounded JSON key"})
    with pytest.raises(TypeError, match="JSON-safe"):
        ConfigSnapshot(1, {"value": object()})
    with pytest.raises(TypeError, match="JSON-safe"):
        ConfigChange("database", 1, {"value": float("nan")}, {})


def test_configuration_snapshots_reject_cycles_and_excessive_nesting() -> None:
    cyclic: dict[str, object] = {}
    cyclic["self"] = cyclic
    with pytest.raises(ValueError, match="cyclic"):
        ConfigSnapshot(1, cyclic)

    nested: object = "leaf"
    for _ in range(64):
        nested = [nested]
    with pytest.raises(ValueError, match="nested"):
        ConfigSnapshot(1, {"nested": nested})


def test_configuration_snapshot_enforces_work_budget_during_mapping_copy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A custom mapping cannot force full materialization before configuration bounds apply."""
    import orbit.config.config as config_module

    monkeypatch.setattr(config_module, "_MAX_CONFIG_VALUES", 2)
    with pytest.raises(ValueError, match="values"):
        ConfigSnapshot(1, _BoundedConfigMapping())


def test_frozen_configuration_sections_reload_atomically_and_notify():
    config = Config(ApplicationConfig(name="test"))
    settings = Settings(database=Database(host="db-a", password="secret"))
    config.register("database", settings)
    config.freeze()
    changes = []
    config.subscribe(changes.append)

    replacement = Settings(database=Database(host="db-b", password="new-secret"))
    change = config.reload_section("database", replacement)
    assert config.get("database").database.host == "db-b"
    assert change.section == "database"
    assert change.version == config.version
    assert changes == [change]
    assert "new-secret" not in str(change)
    with pytest.raises(TypeError):
        change.after["database"] = {}  # type: ignore[index]


def test_configuration_reloads_are_serialized_across_threads():
    config = Config(ApplicationConfig(name="test"), history_size=32)
    config.register("database", Settings(database=Database(host="db-a", password="secret")))
    config.freeze()

    def reload(index: int) -> int:
        return config.reload_section(
            "database", Settings(database=Database(host=f"db-{index}", password="secret"))
        ).version

    with ThreadPoolExecutor(max_workers=8) as executor:
        versions = list(executor.map(reload, range(20)))
    assert sorted(versions) == list(range(min(versions), max(versions) + 1))
    assert config.version == max(versions)
    assert len(config.history) == config.version


def test_reload_observer_failure_rolls_back_without_new_history():
    config = Config(ApplicationConfig(name="test"))
    settings = Settings(database=Database(host="db-a", password="secret"))
    config.register("database", settings)
    config.freeze()
    version = config.version

    def reject(change):
        raise RuntimeError("service rejected change")

    config.subscribe(reject)
    with pytest.raises(RuntimeError):
        config.reload_section("database", Settings(database=Database(host="db-b", password="x")))
    assert config.version == version
    assert config.get("database").database.host == "db-a"


def test_reload_observer_cancellation_rolls_back_without_new_history():
    config = Config(ApplicationConfig(name="test"))
    config.register("database", Settings(database=Database(host="db-a", password="secret")))
    config.freeze()
    version = config.version

    def cancel(change):
        raise asyncio.CancelledError

    config.subscribe(cancel)
    with pytest.raises(asyncio.CancelledError):
        config.reload_section("database", Settings(database=Database(host="db-b", password="x")))
    assert config.version == version
    assert config.get("database").database.host == "db-a"


def test_reload_observer_cannot_start_a_nested_reload():
    config = Config(ApplicationConfig(name="test"))
    config.register("database", Settings(database=Database(host="db-a", password="secret")))
    config.freeze()
    version = config.version

    def recursive(change):
        config.reload_section("database", Settings(database=Database(host="db-c", password="x")))

    config.subscribe(recursive)
    with pytest.raises(RuntimeError, match="already in progress"):
        config.reload_section("database", Settings(database=Database(host="db-b", password="x")))
    assert config.version == version
    assert config.get("database").database.host == "db-a"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"prefix": 1},
        {"prefix": "x" * 256},
        {"prefix": "APP\n"},
        {"values": []},
        {"environment": {1: "value"}},
        {"environment": {"ORBIT_NAME": 1}},
        {"environment": {"ORBIT_NAME": None}},
        {"file": "settings.toml"},
        {"model": object},
    ],
)
def test_configuration_loader_rejects_malformed_boundary_inputs_without_leaking_values(kwargs):
    with pytest.raises(ConfigurationError) as error:
        if "model" in kwargs:
            load_config(**kwargs)
        else:
            load_config(Settings, **kwargs)
    assert "value" not in str(error.value)
