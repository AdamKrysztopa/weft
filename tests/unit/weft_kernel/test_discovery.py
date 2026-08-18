"""Unit tests for `weft_kernel.discovery`.

Mirrors `packages/weft-kernel/src/weft_kernel/discovery.py`. Covers a
permitted pack being imported and registered with attribution and disclosure
filled in, the ambient flag and an uninstalled `allow` entry, a refused pack
never having its entry point loaded at all (fitness function 8(a)), a raising
`register()` folded into a `FAILED` report rather than propagating, a pack
that registers and then raises leaving the registry exactly as it found it
(`contributed=0` is true, not merely reported), a pack whose settings fail
validation before `register()` ever runs, a pack whose `DISCLOSURE` is
present but malformed, an entry point with no distribution metadata folded
into `FAILED` rather than aborting discovery, the `packs:`/`allow` asymmetry
— an unclaimed `pack_settings` key raises, an unclaimed `allow` entry does
not — and the `${env:}` and `[packs] allow` helpers on their own.

Every pack under test is a hand-built double satisfying `EntryPointLike`
structurally, not a real installed distribution — real, installed-pack
discovery is exactly what the architecture test exercises against the
canary, so this file stays fast and does not need `uv pip install` anywhere.
"""

import sys
import types
from collections.abc import Callable, Generator

import pytest
from pydantic import BaseModel

from weft_kernel.discovery import (
    Disclosure,
    EnvInterpolationError,
    PackRegistrar,
    PackStatus,
    UnknownPackSettingsError,
    allow_list_from_config,
    discover,
    interpolate_env,
)
from weft_kernel.registry import Registry, UnknownPluginError


class _Chunker:
    """A stand-in contract. Discovery must not know or care what this is."""


class _Settings(BaseModel):
    endpoint: str = "unset"


class _FakeDistribution:
    def __init__(self, name: str) -> None:
        self.name = name


class _FakeEntryPoint:
    """A double satisfying `EntryPointLike` structurally, with no real distribution behind it."""

    def __init__(self, *, distribution: str, module: str, target: Callable[..., None]) -> None:
        self.name = f"{distribution}-entry-point"
        self.module = module
        self.dist = _FakeDistribution(distribution)
        self._target = target
        self.loaded = False

    def load(self) -> Callable[..., None]:
        self.loaded = True
        return self._target


class _NoDistEntryPoint:
    """A double whose `.dist` is `None` — the shape `_distribution_name` must fold, not crash on."""

    def __init__(self, *, name: str) -> None:
        self.name = name
        self.module = "_weft_test_never_imported"
        self.dist = None

    def load(self) -> Callable[..., None]:
        raise AssertionError(
            "must never be loaded: discover() cannot know which pack this is without "
            "distribution metadata, so nothing should reach load()"
        )


def _install_fake_module(name: str, **attributes: object) -> None:
    module = types.ModuleType(name)
    for key, value in attributes.items():
        setattr(module, key, value)
    sys.modules[name] = module


@pytest.fixture(autouse=True)
def uninstall_fake_modules() -> Generator[None]:
    yield
    for name in [candidate for candidate in sys.modules if candidate.startswith("_weft_test_")]:
        del sys.modules[name]


def test_discover_registers_a_permitted_pack_and_reads_its_disclosure() -> None:
    # Arrange
    registry = Registry()
    seen_endpoints: list[str] = []

    def register(registrar: PackRegistrar, settings: _Settings) -> None:
        seen_endpoints.append(settings.endpoint)
        registrar.add(_Chunker, "fixed-size", lambda: "instance")

    disclosure = Disclosure(network=("https://example.com",), note="reads a remote index")
    _install_fake_module("_weft_test_happy_pack", DISCLOSURE=disclosure)
    entry_point = _FakeEntryPoint(
        distribution="weft-happy", module="_weft_test_happy_pack", target=register
    )

    # Act
    reports = discover(
        registry,
        allow=["weft-happy"],
        pack_settings={"weft-happy": {"endpoint": "https://api"}},
        direct_dependencies=["weft-happy"],
        entry_points=[entry_point],
    )

    # Assert
    [report] = reports
    assert report.distribution == "weft-happy"
    assert report.status == PackStatus.ACTIVE
    assert report.contributed == 1
    assert report.ambient is False
    assert report.disclosure == disclosure
    assert seen_endpoints == ["https://api"]
    assert registry.lookup(_Chunker, "fixed-size")() == "instance"


def test_discover_flags_an_active_pack_ambient_and_an_allowed_but_uninstalled_name() -> None:
    # Arrange
    registry = Registry()

    def register(registrar: PackRegistrar, settings: _Settings) -> None:
        registrar.add(_Chunker, "semantic", lambda: "instance")

    _install_fake_module("_weft_test_ambient_pack")
    entry_point = _FakeEntryPoint(
        distribution="weft-ambient", module="_weft_test_ambient_pack", target=register
    )

    # Act
    reports = discover(
        registry,
        allow=["weft-ambient", "weft-missing"],
        direct_dependencies=["weft-declared-only"],
        entry_points=[entry_point],
    )

    # Assert
    by_distribution = {report.distribution: report for report in reports}
    assert by_distribution["weft-ambient"].status == PackStatus.ACTIVE
    assert by_distribution["weft-ambient"].ambient is True
    assert by_distribution["weft-missing"].status == PackStatus.ALLOWED_NOT_INSTALLED


def test_discover_refuses_an_unlisted_pack_without_ever_loading_its_entry_point() -> None:
    # Arrange
    registry = Registry()
    entry_point = _FakeEntryPoint(
        distribution="weft-refused", module="_weft_test_refused_pack", target=lambda *a: None
    )

    # Act
    reports = discover(registry, allow=["weft-other"], entry_points=[entry_point])

    # Assert
    by_distribution = {report.distribution: report for report in reports}
    report = by_distribution["weft-refused"]
    assert report.status == PackStatus.REFUSED
    assert "weft-refused" in (report.reason or "")
    assert entry_point.loaded is False


def test_discover_folds_a_raising_register_into_failed_and_continues_with_the_rest() -> None:
    # Arrange
    registry = Registry()

    def broken_register(registrar: PackRegistrar, settings: _Settings) -> None:
        raise RuntimeError("boom")

    def good_register(registrar: PackRegistrar, settings: _Settings) -> None:
        registrar.add(_Chunker, "good", lambda: "ok")

    _install_fake_module("_weft_test_broken_pack")
    _install_fake_module("_weft_test_good_pack")
    broken = _FakeEntryPoint(
        distribution="weft-broken", module="_weft_test_broken_pack", target=broken_register
    )
    good = _FakeEntryPoint(
        distribution="weft-good", module="_weft_test_good_pack", target=good_register
    )

    # Act
    reports = discover(registry, entry_points=[broken, good])

    # Assert
    by_distribution = {report.distribution: report for report in reports}
    assert by_distribution["weft-broken"].status == PackStatus.FAILED
    assert "boom" in (by_distribution["weft-broken"].reason or "")
    assert by_distribution["weft-good"].status == PackStatus.ACTIVE


def test_discover_fails_a_pack_whose_settings_do_not_validate_before_register_runs() -> None:
    # Arrange
    class _Strict(BaseModel):
        required_field: str

    called = False

    def register(registrar: PackRegistrar, settings: _Strict) -> None:
        nonlocal called
        called = True

    registry = Registry()
    _install_fake_module("_weft_test_misconfigured_pack")
    entry_point = _FakeEntryPoint(
        distribution="weft-misconfigured",
        module="_weft_test_misconfigured_pack",
        target=register,
    )

    # Act
    reports = discover(
        registry, pack_settings={"weft-misconfigured": {}}, entry_points=[entry_point]
    )

    # Assert
    [report] = reports
    assert report.status == PackStatus.FAILED
    assert "weft-misconfigured" in (report.reason or "")
    assert called is False


def test_discover_rolls_back_a_pack_that_registers_and_then_raises() -> None:
    # Arrange
    registry = Registry()

    def half_register(registrar: PackRegistrar, settings: _Settings) -> None:
        registrar.add(_Chunker, "a", lambda: "a")
        registrar.add(_Chunker, "b", lambda: "b")
        raise RuntimeError("boom after registering two")

    _install_fake_module("_weft_test_half_pack")
    entry_point = _FakeEntryPoint(
        distribution="weft-half", module="_weft_test_half_pack", target=half_register
    )

    # Act
    reports = discover(registry, entry_points=[entry_point])

    # Assert
    [report] = reports
    assert report.status == PackStatus.FAILED
    assert report.contributed == 0
    with pytest.raises(UnknownPluginError):
        registry.lookup(_Chunker, "a")
    with pytest.raises(UnknownPluginError):
        registry.lookup(_Chunker, "b")


def test_discover_fails_a_pack_whose_disclosure_is_not_a_disclosure_instance() -> None:
    # Arrange
    registry = Registry()
    called = False

    def register(registrar: PackRegistrar, settings: _Settings) -> None:
        nonlocal called
        called = True
        registrar.add(_Chunker, "should-not-register", lambda: "instance")

    _install_fake_module(
        "_weft_test_malformed_disclosure_pack", DISCLOSURE={"network": ["bolt://x"]}
    )
    entry_point = _FakeEntryPoint(
        distribution="weft-malformed-disclosure",
        module="_weft_test_malformed_disclosure_pack",
        target=register,
    )

    # Act
    reports = discover(registry, entry_points=[entry_point])

    # Assert
    [report] = reports
    assert report.status == PackStatus.FAILED
    assert "weft-malformed-disclosure" in (report.reason or "")
    assert "DISCLOSURE" in (report.reason or "")
    assert called is False


def test_discover_folds_a_missing_distribution_entry_point_into_failed_and_continues() -> None:
    # Arrange
    registry = Registry()

    def good_register(registrar: PackRegistrar, settings: _Settings) -> None:
        registrar.add(_Chunker, "good", lambda: "ok")

    _install_fake_module("_weft_test_good_pack_no_dist_sibling")
    mystery = _NoDistEntryPoint(name="mystery-entry-point")
    good = _FakeEntryPoint(
        distribution="weft-good-no-dist-sibling",
        module="_weft_test_good_pack_no_dist_sibling",
        target=good_register,
    )

    # Act
    reports = discover(registry, entry_points=[mystery, good])

    # Assert
    by_distribution = {report.distribution: report for report in reports}
    assert by_distribution["mystery-entry-point"].status == PackStatus.FAILED
    assert by_distribution["weft-good-no-dist-sibling"].status == PackStatus.ACTIVE


def test_discover_raises_when_pack_settings_names_an_uninstalled_distribution() -> None:
    # Arrange
    registry = Registry()

    # Act / Assert
    with pytest.raises(UnknownPackSettingsError) as excinfo:
        discover(registry, pack_settings={"weft-not-installed": {"x": 1}}, entry_points=[])

    assert "weft-not-installed" in str(excinfo.value)


def test_discover_allow_naming_an_uninstalled_distribution_is_reported_not_raised() -> None:
    # Arrange — pins the `packs:`/`allow` asymmetry: the sibling test above raises for the
    # same shape of absence under `pack_settings`; `allow` never does.
    registry = Registry()

    # Act
    reports = discover(registry, allow=["weft-missing"], entry_points=[])

    # Assert
    [report] = reports
    assert report.status == PackStatus.ALLOWED_NOT_INSTALLED
    assert report.distribution == "weft-missing"


def test_interpolate_env_replaces_a_whole_string_token_and_leaves_the_rest_alone() -> None:
    # Arrange
    raw = {"api_key": "${env:WEFT_TEST_SECRET}", "endpoint": "bolt://localhost:7687"}

    # Act
    resolved = interpolate_env(raw, environ={"WEFT_TEST_SECRET": "s3cr3t"})

    # Assert
    assert resolved == {"api_key": "s3cr3t", "endpoint": "bolt://localhost:7687"}


def test_interpolate_env_raises_naming_the_unset_variable() -> None:
    # Arrange / Act / Assert
    with pytest.raises(EnvInterpolationError) as excinfo:
        interpolate_env("${env:WEFT_TEST_DOES_NOT_EXIST}", environ={})

    assert "WEFT_TEST_DOES_NOT_EXIST" in str(excinfo.value)


def test_allow_list_from_config_reads_packs_allow_and_treats_absence_as_open() -> None:
    # Arrange
    present = {"packs": {"allow": ["weft-extract", "weft-chunk"]}}
    absent: dict[str, object] = {}

    # Act / Assert
    assert allow_list_from_config(present) == ("weft-extract", "weft-chunk")
    assert allow_list_from_config(absent) is None
