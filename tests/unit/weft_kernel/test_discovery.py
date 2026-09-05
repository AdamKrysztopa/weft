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

**Task 5.2e** adds `PackRegistrar.deprecate`/`deprecations`: buffered exactly like a
pipeline resource, landing on the `PackReport` only once `register()` returns without
raising, and the `DeprecationWarning` itself coming from `weft_kernel.seam.warn_deprecated`
— the registration wrapper — rather than from the pack's own `register()` body.

**Task 5.3a (`S8`)** adds `PackRegistrar.add_contribution`/`contributions`: buffered
exactly like `add_ext_model`, with `distribution` filled in by the registrar rather than
stated by the pack, and landing on the `PackReport` only once `register()` returns without
raising.
"""

import sys
import types
import warnings
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
from weft_kernel.pipeline import StageDeclaration
from weft_kernel.registry import Registry, UnknownPluginError
from weft_kernel.seam import RemovalClock


class _Chunker:
    """A stand-in contract. Discovery must not know or care what this is."""


class _Settings(BaseModel):
    endpoint: str = "unset"


class _FakeDistribution:
    def __init__(self, name: str) -> None:
        self.name = name


class _FakeEntryPoint:
    """A double satisfying `EntryPointLike` structurally, with no real distribution behind it."""

    def __init__(
        self,
        *,
        distribution: str,
        module: str,
        target: Callable[..., None],
        pack: str | None = None,
    ) -> None:
        # The entry-point name is the *pack* identity and is deliberately not the
        # distribution name: `[packs.<pack>]` settings and every `plugins list|doctor` row
        # key on this, while `[packs] allow` keys on the distribution. A double whose two
        # identities were the same string could not tell the two apart.
        self.name = pack if pack is not None else f"{distribution}-entry-point"
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
        distribution="weft-happy", pack="happy", module="_weft_test_happy_pack", target=register
    )

    # Act — settings key on the pack, `allow` on the distribution, and the two names differ
    # here so that neither could be passing by accident.
    reports = discover(
        registry,
        allow=["weft-happy"],
        pack_settings={"happy": {"endpoint": "https://api"}},
        direct_dependencies=["weft-happy"],
        entry_points=[entry_point],
    )

    # Assert
    [report] = reports
    assert report.pack == "happy"
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
        pack="misconfigured",
        module="_weft_test_misconfigured_pack",
        target=register,
    )

    # Act
    reports = discover(registry, pack_settings={"misconfigured": {}}, entry_points=[entry_point])

    # Assert
    [report] = reports
    assert report.status == PackStatus.FAILED
    # The pack, not the distribution: a settings failure is one pack's, and a distribution
    # shipping fourteen of them would name thirteen innocents.
    assert "'misconfigured'" in (report.reason or "")
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


def test_two_packs_in_one_distribution_are_configured_and_reported_separately() -> None:
    """The property the whole `pack`/`distribution` split exists for.

    One wheel, two `weft.packs` entry points. Each pack must get its own `[packs.<pack>]`
    slice and its own row; before the split, `settings_source.get(distribution)` handed
    both packs the same table and `plugins list` printed the distribution name twice.
    """
    # Arrange
    registry = Registry()
    seen: dict[str, str] = {}

    def register_first(registrar: PackRegistrar, settings: _Settings) -> None:
        seen["first"] = settings.endpoint
        registrar.add(_Chunker, "first", lambda: "instance")

    def register_second(registrar: PackRegistrar, settings: _Settings) -> None:
        seen["second"] = settings.endpoint
        registrar.add(_Chunker, "second", lambda: "instance")

    _install_fake_module("_weft_test_bundled_first")
    _install_fake_module("_weft_test_bundled_second")
    entry_points = [
        _FakeEntryPoint(
            distribution="weft-bundle",
            pack="first",
            module="_weft_test_bundled_first",
            target=register_first,
        ),
        _FakeEntryPoint(
            distribution="weft-bundle",
            pack="second",
            module="_weft_test_bundled_second",
            target=register_second,
        ),
    ]

    # Act
    reports = discover(
        registry,
        allow=["weft-bundle"],
        pack_settings={"first": {"endpoint": "one"}, "second": {"endpoint": "two"}},
        entry_points=entry_points,
    )

    # Assert
    assert seen == {"first": "one", "second": "two"}
    assert {report.pack for report in reports} == {"first", "second"}
    assert {report.distribution for report in reports} == {"weft-bundle"}
    assert all(report.status == PackStatus.ACTIVE for report in reports)


def test_allow_naming_the_distribution_permits_every_pack_it_ships() -> None:
    """`[packs] allow` is a trust boundary, so it keys on what you installed.

    Listing `weft-bundle` permits both of its packs; the operator never has to enumerate
    names chosen inside a wheel they had already accepted.
    """
    # Arrange
    registry = Registry()

    def register(registrar: PackRegistrar, settings: _Settings) -> None:
        registrar.add(_Chunker, registrar_name, lambda: "instance")

    registrar_name = "only"
    _install_fake_module("_weft_test_allow_bundled")
    entry_point = _FakeEntryPoint(
        distribution="weft-bundle",
        pack="inner",
        module="_weft_test_allow_bundled",
        target=register,
    )

    # Act
    reports = discover(registry, allow=["weft-bundle"], entry_points=[entry_point])

    # Assert — allowed by its distribution, reported under its own pack name.
    [report] = reports
    assert report.status == PackStatus.ACTIVE
    assert report.pack == "inner"

    # Act / Assert — and naming the pack instead does not permit it: `allow` is not
    # keyed on the pack, and saying so is the point of this half.
    refused = discover(Registry(), allow=["inner"], entry_points=[entry_point])
    assert [item.status for item in refused if item.pack == "inner"] == [PackStatus.REFUSED]


def test_discover_raises_when_pack_settings_names_an_uninstalled_pack() -> None:
    # Arrange
    registry = Registry()

    # Act / Assert
    with pytest.raises(UnknownPackSettingsError) as excinfo:
        discover(registry, pack_settings={"not-installed": {"x": 1}}, entry_points=[])

    assert "not-installed" in str(excinfo.value)


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


# --- pipeline resources (task 2.8) -----------------------------------------------------


def test_a_committed_pack_reports_the_pipeline_resource_it_buffered() -> None:
    """`add_pipeline_resource` is buffered exactly like `add`, and lands on the report
    once `register()` returns without raising — `weft_retrieve.contract.RouteCatalogue`'s
    own docstring: "populated by the same eager discovery pass that builds the registry."
    """
    # Arrange
    registry = Registry()

    def register(registrar: PackRegistrar, settings: _Settings) -> None:
        registrar.add(_Chunker, "fixed-size", lambda: "instance")
        registrar.add_pipeline_resource("weft_happy", "pipelines/route.yaml")

    _install_fake_module("_weft_test_pipeline_pack")
    entry_point = _FakeEntryPoint(
        distribution="weft-happy", module="_weft_test_pipeline_pack", target=register
    )

    # Act
    reports = discover(registry, allow=["weft-happy"], entry_points=[entry_point])

    # Assert
    [report] = reports
    [resource] = report.pipeline_resources
    assert resource.distribution == "weft-happy"
    assert resource.package == "weft_happy"
    assert resource.resource == "pipelines/route.yaml"


def test_a_raising_register_discards_its_buffered_pipeline_resource_too() -> None:
    """The same atomicity `add` gets: nothing a raising `register()` buffered — plugin
    registration or pipeline resource alike — reaches the `PackReport`, because reporting
    a resource nobody actually contributed would make a catalogue advertise a pipeline the
    pack that named it never actually shipped.
    """
    # Arrange
    registry = Registry()

    def register(registrar: PackRegistrar, settings: _Settings) -> None:
        registrar.add_pipeline_resource("weft_broken", "pipelines/route.yaml")
        raise RuntimeError("boom")

    _install_fake_module("_weft_test_broken_pipeline_pack")
    entry_point = _FakeEntryPoint(
        distribution="weft-broken-pipeline",
        module="_weft_test_broken_pipeline_pack",
        target=register,
    )

    # Act
    reports = discover(registry, entry_points=[entry_point])

    # Assert
    [report] = reports
    assert report.status == PackStatus.FAILED
    assert report.pipeline_resources == ()


# --- deprecation (task 5.2e) ------------------------------------------------------------


def test_a_committed_pack_reports_the_deprecation_it_buffered_and_warns_once() -> None:
    """`deprecate` is buffered exactly like `add_pipeline_resource`, lands on the report
    once `register()` returns without raising, and the warning comes from the registration
    wrapper (`weft_kernel.seam.warn_deprecated`) rather than from the pack itself —
    `docs/09-release.md` §3: "the warning is emitted by the registration wrapper."
    """
    # Arrange
    registry = Registry()

    def register(registrar: PackRegistrar, settings: _Settings) -> None:
        registrar.add(_Chunker, "legacy", lambda: "instance")
        registrar.deprecate("_Chunker:legacy", reason="superseded by 'fixed-size'")

    _install_fake_module("_weft_test_deprecated_pack")
    entry_point = _FakeEntryPoint(
        distribution="weft-old", module="_weft_test_deprecated_pack", target=register
    )

    # Act
    with pytest.warns(DeprecationWarning, match="weft-old.*_Chunker:legacy.*superseded"):
        reports = discover(registry, entry_points=[entry_point])

    # Assert
    [report] = reports
    assert report.status == PackStatus.ACTIVE
    [notice] = report.deprecations
    assert notice.distribution == "weft-old"
    assert notice.surface == "_Chunker:legacy"
    assert notice.reason == "superseded by 'fixed-size'"
    # Task 6.5 — the mark carries G9's clock, derived at registration and never declared by the
    # pack. `weft-old` is a fake distribution with no installed metadata, which is a state the
    # record reports rather than hides (`docs/lessons.md` L5.9).
    assert notice.removal.clock is RemovalClock.VERSION_UNREADABLE
    assert notice.removal.distribution == "weft-old"


def test_a_deprecation_from_a_real_distribution_carries_its_own_removal_release() -> None:
    """Task 6.5. The clock is a fact about the *publishing* distribution, so the derivation is
    exercised against one that really is installed rather than against a fake name — otherwise
    the only state ever seen would be `VERSION_UNREADABLE`, and the check would pass while
    proving nothing about the rule it exists for.
    """
    # Arrange
    registry = Registry()

    def register(registrar: PackRegistrar, settings: _Settings) -> None:
        registrar.deprecate("legacy", reason="superseded")

    _install_fake_module("_weft_test_real_distribution_pack")
    entry_point = _FakeEntryPoint(
        distribution="weft-store", module="_weft_test_real_distribution_pack", target=register
    )

    # Act
    with pytest.warns(DeprecationWarning):
        reports = discover(registry, entry_points=[entry_point])

    # Assert — `weft-store` is 2.x, so G9's clock reads its next major.
    [report] = reports
    [notice] = report.deprecations
    assert notice.removal.clock is RemovalClock.NEXT_MAJOR
    assert notice.removal.release == "weft-store 3.0.0"


def test_a_raising_register_discards_its_buffered_deprecation_and_warns_of_nothing() -> None:
    """The same atomicity as pipeline resources: a pack that raises after marking a
    surface deprecated must not leave a warning standing about a mark that never
    actually committed.
    """
    # Arrange
    registry = Registry()

    def register(registrar: PackRegistrar, settings: _Settings) -> None:
        registrar.deprecate("legacy", reason="boom")
        raise RuntimeError("boom")

    _install_fake_module("_weft_test_broken_deprecated_pack")
    entry_point = _FakeEntryPoint(
        distribution="weft-broken-deprecation",
        module="_weft_test_broken_deprecated_pack",
        target=register,
    )

    # Act
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        reports = discover(registry, entry_points=[entry_point])

    # Assert
    [report] = reports
    assert report.status == PackStatus.FAILED
    assert report.deprecations == ()


# --- renderer offers (task 6.20, G13) ---------------------------------------------------


def test_a_committed_pack_reports_the_renderer_it_buffered_with_its_own_attribution() -> None:
    """`add_renderer` is buffered exactly like `add_contribution`, with `distribution` filled
    in by the registrar rather than stated by the pack.

    Task **6.20**, G13's third repair (`docs/03-cli.md` → *Plugin-contributed commands*): a
    result type nobody outside the CLI can format is only half a contract, so a renderer is
    registered at the same seam a command is. **The kernel names neither `CommandResult` nor
    `Rendered`** — it remembers that this pack offered *some* type and *some* callable and
    goes no further, exactly as `add_ext_model` stops at "this pack declared this class".
    """
    # Arrange
    registry = Registry()

    class _Result:
        pass

    def _render(result: object) -> object:
        return f"rendered {type(result).__name__}"

    def register(registrar: PackRegistrar, settings: _Settings) -> None:
        registrar.add_renderer(_Result, _render)

    _install_fake_module("_weft_test_rendering_pack")
    entry_point = _FakeEntryPoint(
        distribution="weft-graph", module="_weft_test_rendering_pack", target=register
    )

    # Act
    reports = discover(registry, entry_points=[entry_point])

    # Assert
    [report] = reports
    assert report.status == PackStatus.ACTIVE
    [offer] = report.renderers
    assert offer.distribution == "weft-graph"
    assert offer.result_type is _Result
    assert offer.render is _render


def test_a_raising_register_discards_its_buffered_renderer_too() -> None:
    """The same atomicity as pipeline resources, ext models and contributions: nothing a
    raising `register()` buffered may reach a report, or the CLI would advertise a way to
    format a result the pack never actually finished offering.
    """
    # Arrange
    registry = Registry()

    class _Result:
        pass

    def register(registrar: PackRegistrar, settings: _Settings) -> None:
        registrar.add_renderer(_Result, lambda result: result)
        raise RuntimeError("half way through")

    _install_fake_module("_weft_test_raising_renderer_pack")
    entry_point = _FakeEntryPoint(
        distribution="weft-broken", module="_weft_test_raising_renderer_pack", target=register
    )

    # Act
    reports = discover(registry, entry_points=[entry_point])

    # Assert
    [report] = reports
    assert report.status == PackStatus.FAILED
    assert report.renderers == ()


# --- slot contributions (task 5.3a, S8) -------------------------------------------------


def test_a_committed_pack_reports_the_contribution_it_buffered_with_its_own_attribution() -> None:
    """`add_contribution` is buffered exactly like `add_ext_model`, and `distribution` is
    filled in by the registrar — never something the pack states — on `add`'s own
    footing (module docstring: "attribution is never something the author states").
    """
    # Arrange
    registry = Registry()

    def register(registrar: PackRegistrar, settings: _Settings) -> None:
        registrar.add(_Chunker, "entity-extractor", lambda: "instance")
        registrar.add_contribution(
            "enrich", StageDeclaration(id="entities", use="entity-extractor")
        )

    _install_fake_module("_weft_test_contributing_pack")
    entry_point = _FakeEntryPoint(
        distribution="weft-graph", module="_weft_test_contributing_pack", target=register
    )

    # Act
    reports = discover(registry, entry_points=[entry_point])

    # Assert
    [report] = reports
    assert report.status == PackStatus.ACTIVE
    [contribution] = report.contributions
    assert contribution.slot == "enrich"
    assert contribution.distribution == "weft-graph"
    assert contribution.stage.id == "entities"  # local, unqualified — see Contribution's docstring
    assert contribution.stage.use == "entity-extractor"


def test_a_raising_register_discards_its_buffered_contribution_too() -> None:
    """The same atomicity as pipeline resources and ext models: nothing a raising
    `register()` buffered reaches the `PackReport` — a slot must never look filled by a
    pack that never actually committed.
    """
    # Arrange
    registry = Registry()

    def register(registrar: PackRegistrar, settings: _Settings) -> None:
        registrar.add_contribution(
            "enrich", StageDeclaration(id="entities", use="entity-extractor")
        )
        raise RuntimeError("boom")

    _install_fake_module("_weft_test_broken_contributing_pack")
    entry_point = _FakeEntryPoint(
        distribution="weft-broken-contribution",
        module="_weft_test_broken_contributing_pack",
        target=register,
    )

    # Act
    reports = discover(registry, entry_points=[entry_point])

    # Assert
    [report] = reports
    assert report.status == PackStatus.FAILED
    assert report.contributions == ()


# --- unavailability, declared at registration (task 6.29) --------------------------------


def test_a_pack_that_declares_something_unavailable_reports_partial_and_says_why() -> None:
    """Fitness function 5's second half — `01`: "or the plugin must declare it unavailable and
    say why", **at discovery time**.

    `PackStatus.PARTIAL` has been in the vocabulary since Phase 0 and no pack could produce it:
    this module's own docstring deferred the mechanism to "a later step's job" and no later step
    took it, so a plugin that could not run said so when a run failed instead of when `weft
    plugins doctor` asked. `weft-eval`'s `bertscore` is the real instance.
    """
    # Arrange
    registry = Registry()

    def register(registrar: PackRegistrar, settings: _Settings) -> None:
        registrar.add(_Chunker, "fast", lambda: "instance")
        registrar.unavailable("slow", reason="needs the optional 'acme' package, not installed")

    _install_fake_module("_weft_test_partial_pack")
    entry_point = _FakeEntryPoint(
        distribution="weft-partial", module="_weft_test_partial_pack", target=register
    )

    # Act
    reports = discover(registry, entry_points=[entry_point])

    # Assert
    [report] = reports
    assert report.status is PackStatus.PARTIAL, (
        "a pack that registered part of what it offers is PARTIAL, not ACTIVE — `02` section 2's "
        "vocabulary answers 'why is this not contributing?' for every reason at once"
    )
    [notice] = report.unavailable
    assert notice.surface == "slow"
    assert "acme" in notice.reason
    assert report.contributed == 1, "what did register still registered, and still counts"


def test_a_pack_that_declares_nothing_unavailable_is_still_active() -> None:
    """The other side: PARTIAL means *part*, so a pack with nothing missing must not become one."""
    # Arrange
    registry = Registry()

    def register(registrar: PackRegistrar, settings: _Settings) -> None:
        registrar.add(_Chunker, "fast", lambda: "instance")

    _install_fake_module("_weft_test_whole_pack")
    entry_point = _FakeEntryPoint(
        distribution="weft-whole", module="_weft_test_whole_pack", target=register
    )

    # Act
    [report] = discover(registry, entry_points=[entry_point])

    # Assert
    assert report.status is PackStatus.ACTIVE
    assert report.unavailable == ()


def test_a_raising_register_discards_its_unavailability_notices() -> None:
    """The same atomicity every other buffer here has: a pack whose `register()` raises must not
    leave a report standing about a mark that never committed.
    """
    # Arrange
    registry = Registry()

    def register(registrar: PackRegistrar, settings: _Settings) -> None:
        registrar.unavailable("slow", reason="boom")
        raise RuntimeError("register failed after marking")

    _install_fake_module("_weft_test_partial_raiser")
    entry_point = _FakeEntryPoint(
        distribution="weft-raiser", module="_weft_test_partial_raiser", target=register
    )

    # Act
    [report] = discover(registry, entry_points=[entry_point])

    # Assert
    assert report.status is PackStatus.FAILED, "a raising register is FAILED, never PARTIAL"
    assert report.unavailable == ()
