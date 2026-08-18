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

**Task 1.12** adds two packs colliding over one `(contract, name)` that a
`[plugins]` pin (already present on the `Registry` passed in) resolves
without failing either pack, and the loud `InertPluginPinError` `discover()`
raises once enumeration finishes if a pin never got to arbitrate anything —
see `weft_kernel.registry`'s own module docstring for the full reasoning.
"""

import sys
import types
from collections.abc import Callable, Generator

import pytest
from pydantic import BaseModel

from weft_kernel.discovery import (
    Disclosure,
    EnvInterpolationError,
    InertPluginPinError,
    PackRegistrar,
    PackStatus,
    UnknownPackSettingsError,
    allow_list_from_config,
    discover,
    interpolate_env,
    plugin_pins_from_config,
)
from weft_kernel.errors import WeftError
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


def test_allow_list_from_config_refuses_a_packs_value_that_is_not_a_table() -> None:
    # Arrange — the plausible typo for `[packs]\nallow = [...]`: `packs = ["weft-store"]`
    # parses to a *list*, which used to fail the `isinstance(packs, Mapping)` check and be
    # read as absent — the open-by-default posture, silently, with an operator's allow-list
    # ignored. `docs/02-extension-model.md` §2 → *The trust model* names this refused, not
    # absent, because absent is a choice a `weft.toml` with no `[packs]` table makes and this
    # is not that document.
    document = {"packs": ["weft-store"]}

    # Act / Assert
    with pytest.raises(WeftError, match=r"\[packs\].*table"):
        allow_list_from_config(document)


def test_plugin_pins_from_config_reads_the_plugins_table_and_treats_absence_as_empty() -> None:
    # Arrange
    present = {"plugins": {"Chunker:keybert": "weft-kw"}}
    absent: dict[str, object] = {}

    # Act / Assert
    assert plugin_pins_from_config(present) == {"Chunker:keybert": "weft-kw"}
    assert plugin_pins_from_config(absent) == {}


def test_discover_resolves_a_pinned_collision_and_leaves_both_packs_active() -> None:
    # Arrange — the registry already carries the pin, the way `weft_cli.registry_bootstrap`
    # constructs it from `weft.toml` before calling `discover()`.
    registry = Registry(plugin_pins={"_Chunker:shared": "weft-winner"})

    def loser_register(registrar: PackRegistrar, settings: _Settings) -> None:
        registrar.add(_Chunker, "shared", lambda: "loser")

    def winner_register(registrar: PackRegistrar, settings: _Settings) -> None:
        registrar.add(_Chunker, "shared", lambda: "winner")
        registrar.add(_Chunker, "extra", lambda: "extra")

    _install_fake_module("_weft_test_loser_pack")
    _install_fake_module("_weft_test_winner_pack")
    loser = _FakeEntryPoint(
        distribution="weft-loser", module="_weft_test_loser_pack", target=loser_register
    )
    winner = _FakeEntryPoint(
        distribution="weft-winner", module="_weft_test_winner_pack", target=winner_register
    )

    # Act
    reports = discover(registry, entry_points=[loser, winner])

    # Assert — neither pack failed; the loser is `active` and merely lost one name.
    by_distribution = {report.distribution: report for report in reports}
    assert by_distribution["weft-loser"].status == PackStatus.ACTIVE
    assert by_distribution["weft-winner"].status == PackStatus.ACTIVE
    assert registry.lookup(_Chunker, "shared")() == "winner"
    assert registry.lookup(_Chunker, "extra")() == "extra"
    [displaced] = registry.displaced()
    assert displaced.distribution == "weft-loser"
    assert displaced.winner == "weft-winner"


def test_discover_raises_when_a_pin_never_sees_a_collision() -> None:
    # Arrange — error case: only one distribution ever registers this name, so the pin
    # never had anything to arbitrate — `docs/02-extension-model.md` §3 calls this a lie
    # about what is running rather than a harmless no-op.
    registry = Registry(plugin_pins={"_Chunker:shared": "weft-only"})

    def register(registrar: PackRegistrar, settings: _Settings) -> None:
        registrar.add(_Chunker, "shared", lambda: "only")

    _install_fake_module("_weft_test_only_pack")
    entry_point = _FakeEntryPoint(
        distribution="weft-only", module="_weft_test_only_pack", target=register
    )

    # Act / Assert
    with pytest.raises(InertPluginPinError) as excinfo:
        discover(registry, entry_points=[entry_point])

    assert "_Chunker:shared" in str(excinfo.value)


def test_strict_pins_false_returns_every_report_instead_of_raising() -> None:
    # Arrange — repair for a reviewer finding: `weft plugins list`/`weft plugins doctor`
    # must be able to explain an inert pin, not die before a single `PackReport` exists.
    # Same fixture as the error case above; `strict_pins=False` is the only difference.
    registry = Registry(plugin_pins={"_Chunker:shared": "weft-only"})

    def register(registrar: PackRegistrar, settings: _Settings) -> None:
        registrar.add(_Chunker, "shared", lambda: "only")

    _install_fake_module("_weft_test_strict_pins_pack")
    entry_point = _FakeEntryPoint(
        distribution="weft-only", module="_weft_test_strict_pins_pack", target=register
    )

    # Act
    reports = discover(registry, entry_points=[entry_point], strict_pins=False)

    # Assert — the report is real and the pin's own state is still readable off the
    # registry, just no longer fatal to getting either.
    assert len(reports) == 1
    assert reports[0].distribution == "weft-only"
    assert reports[0].status == PackStatus.ACTIVE
    assert registry.unconsulted_pins() == frozenset({"_Chunker:shared"})
