"""Unit tests for `weft_kernel.registry`.

Mirrors `packages/weft-kernel/src/weft_kernel/registry.py`. Covers a
successful registration and lookup, the fixed-and-not-arbitrated duplicate
refusal `docs/06-phase-0-build.md` takes for G2's open question, the loud
unknown-name error `docs/02-extension-model.md` specifies, `add_many`'s
all-or-nothing commit — a collision against an existing entry and a
collision within the batch itself both leave the registry exactly as they
found it — and task 1.2's mandatory-`destroys` check: a contract that
publishes a property vocabulary (`02` §3 → *Ordering constraints*) refuses a
factory that never mentions `destroys` at all, detected generically off
`_GovernedContract.publishes_property_vocabulary`, never off a hardcoded
contract name.

**Task 1.12 — G2's relaxation.** `docs/02-extension-model.md` §3 → *When
resolution fails*: a `(contract, name)` collision is still refused with no
`[plugins]` pin present, but the refusal now prints the exact pin that would
resolve it. With a pin present, the named distribution's registration wins,
the other is recorded as `displaced` rather than dropped, and a pin naming
neither contender — or one that never sees a collision at all — fails loudly
instead of being read as a no-op.

**Task 3.1 — the mandatory-declaration check generalised.** `docs/03-cli.md`
→ *Permissions* needs the identical shape `destroys` already has —
registration refuses a factory silent about a required class attribute,
naming the plugin, the contract and the remedy — but for `permission_class`
on `weft_command.contract.Command`, a contract the kernel must not know the
name of. `_GovernedContract.publishes_property_vocabulary` above is now one
*source* of a required-declaration name (`"destroys"`) rather than the whole
mechanism; `_DeclaringContract` below is a second, contract-agnostic source —
`required_declarations`, a plain tuple of attribute names — and the tests
after the `destroys` block prove both sources feed the same check and the
same `MissingRequiredDeclarationError` family, never two parallel checks.
"""

import functools
from typing import TYPE_CHECKING, ClassVar

import pytest

from weft_kernel.registry import (
    DuplicateRegistrationError,
    MissingDestroysDeclarationError,
    MissingRequiredDeclarationError,
    Registry,
    UnknownPluginError,
    UnresolvedPluginPinError,
    unwrap_factory,
)


class _Chunker:
    """A stand-in contract. `Registry` must not know or care what this is."""


class _Extractor:
    """A second, unrelated contract, used to show the key includes the contract."""


class _GovernedContract:
    """A stand-in contract that publishes a property vocabulary — `02` §3's mandatory case.

    `publishes_property_vocabulary` is assigned after the class body, the
    same way a real contract's `version` is (`weft_extract.contract`,
    `weft_chunk.contract`) — not that this matters for `isinstance`, since
    this stand-in is not a `Protocol`, but it keeps the shape identical to
    what `Registry.add` actually reads off a real contract.
    """

    if TYPE_CHECKING:
        publishes_property_vocabulary: ClassVar[bool]


_GovernedContract.publishes_property_vocabulary = True


def test_add_then_lookup_returns_the_registered_factory() -> None:
    # Arrange
    registry = Registry()
    factory = lambda: "a chunker instance"  # noqa: E731 - stand-in, not production code

    # Act
    registry.add(_Chunker, "fixed-size", factory, distribution="weft-chunk")
    resolved = registry.lookup(_Chunker, "fixed-size")

    # Assert
    assert resolved is factory


def test_duplicate_registration_is_refused_naming_both_distributions() -> None:
    # Arrange
    registry = Registry()
    first_factory = lambda: "the first registration"  # noqa: E731 - stand-in, not production code
    registry.add(_Chunker, "semantic", first_factory, distribution="weft-chunk")

    # Act / Assert
    with pytest.raises(DuplicateRegistrationError) as excinfo:
        registry.add(
            _Chunker, "semantic", lambda: "the refused second one", distribution="weft-graph"
        )

    message = str(excinfo.value)
    assert "weft-chunk" in message
    assert "weft-graph" in message
    assert "semantic" in message
    assert registry.lookup(_Chunker, "semantic") is first_factory


def test_entry_returns_the_factory_and_the_distribution_that_registered_it() -> None:
    # Arrange
    registry = Registry()
    factory = lambda: "an entry's factory"  # noqa: E731 - stand-in, not production code
    registry.add(_Chunker, "semantic", factory, distribution="weft-chunk")

    # Act
    found = registry.entry(_Chunker, "semantic")

    # Assert
    assert found.factory is factory
    assert found.distribution == "weft-chunk"


def test_entry_raises_the_same_unknown_plugin_error_as_lookup() -> None:
    # Arrange
    registry = Registry()

    # Act / Assert
    with pytest.raises(UnknownPluginError) as excinfo:
        registry.entry(_Chunker, "missing")

    assert "missing" in str(excinfo.value)
    assert "Chunker" in str(excinfo.value)


def test_unknown_name_lists_the_wanted_name_and_only_its_own_contracts_options() -> None:
    # Arrange
    registry = Registry()
    registry.add(_Chunker, "fixed-size", lambda: None, distribution="weft-chunk")
    registry.add(_Extractor, "pdf", lambda: None, distribution="weft-extract")

    # Act / Assert
    with pytest.raises(UnknownPluginError) as excinfo:
        registry.lookup(_Chunker, "semantic")

    message = str(excinfo.value)
    assert "semantic" in message
    assert "Chunker" in message
    assert "fixed-size" in message
    assert "pdf" not in message


def test_add_many_commits_every_entry_from_one_distribution() -> None:
    # Arrange
    registry = Registry()

    # Act
    registry.add_many(
        [
            (_Chunker, "a", lambda: "a"),
            (_Chunker, "b", lambda: "b"),
        ],
        distribution="weft-chunk",
    )

    # Assert
    assert registry.lookup(_Chunker, "a")() == "a"
    assert registry.lookup(_Chunker, "b")() == "b"


def test_add_many_rejects_a_collision_against_an_existing_entry_and_writes_nothing() -> None:
    # Arrange
    registry = Registry()
    registry.add(_Chunker, "taken", lambda: "first", distribution="weft-chunk")

    # Act / Assert
    with pytest.raises(DuplicateRegistrationError) as excinfo:
        registry.add_many(
            [
                (_Chunker, "new", lambda: "new"),
                (_Chunker, "taken", lambda: "second"),
            ],
            distribution="weft-graph",
        )

    assert "weft-chunk" in str(excinfo.value)
    with pytest.raises(UnknownPluginError):
        registry.lookup(_Chunker, "new")


def test_contracts_is_empty_on_a_fresh_registry() -> None:
    # Arrange
    registry = Registry()

    # Act / Assert
    assert registry.contracts() == frozenset()


def test_contracts_returns_every_distinct_contract_with_at_least_one_registration() -> None:
    # Arrange
    registry = Registry()
    registry.add(_Chunker, "fixed-size", lambda: None, distribution="weft-chunk")
    registry.add(_Chunker, "semantic", lambda: None, distribution="weft-graph")
    registry.add(_Extractor, "pdf", lambda: None, distribution="weft-extract")

    # Act
    contracts = registry.contracts()

    # Assert — two names under `_Chunker` still count once; the key is the contract itself.
    assert contracts == frozenset({_Chunker, _Extractor})


def test_distributions_for_returns_every_distribution_that_registered_the_contract() -> None:
    # Arrange
    registry = Registry()
    registry.add(_Chunker, "fixed-size", lambda: None, distribution="weft-chunk")
    registry.add(_Chunker, "semantic", lambda: None, distribution="weft-graph")

    # Act
    distributions = registry.distributions_for(_Chunker)

    # Assert
    assert distributions == frozenset({"weft-chunk", "weft-graph"})


def test_distributions_for_an_unregistered_contract_is_empty() -> None:
    # Arrange
    registry = Registry()

    # Act / Assert
    assert registry.distributions_for(_Extractor) == frozenset()


def test_add_many_rejects_a_duplicate_name_within_its_own_batch_and_writes_nothing() -> None:
    # Arrange
    registry = Registry()

    # Act / Assert
    with pytest.raises(DuplicateRegistrationError) as excinfo:
        registry.add_many(
            [
                (_Chunker, "twice", lambda: "first"),
                (_Chunker, "twice", lambda: "second"),
            ],
            distribution="weft-chunk",
        )

    assert "twice" in str(excinfo.value)
    with pytest.raises(UnknownPluginError):
        registry.lookup(_Chunker, "twice")


def test_add_refuses_a_governed_contract_s_factory_with_no_destroys_declared() -> None:
    # Arrange
    registry = Registry()

    class _NoDestroys:
        """Never mentions `destroys` at all — not even an inherited default."""

    # Act / Assert
    with pytest.raises(MissingDestroysDeclarationError) as excinfo:
        registry.add(_GovernedContract, "widget", _NoDestroys, distribution="acme-widgets")

    message = str(excinfo.value)
    assert "widget" in message
    assert "_GovernedContract" in message
    assert registry.contracts() == frozenset()


def test_add_accepts_a_governed_contract_s_factory_that_destroys_something_real() -> None:
    # Arrange — the edge case: `destroys` need not be empty, only present.
    registry = Registry()

    class _Marker:
        pass

    class _DestroysSomething:
        destroys: tuple[type, ...] = (_Marker,)

    # Act
    registry.add(_GovernedContract, "widget", _DestroysSomething, distribution="acme-widgets")

    # Assert
    assert registry.lookup(_GovernedContract, "widget") is _DestroysSomething


def test_add_many_refuses_a_governed_contract_s_factory_with_no_destroys_and_writes_nothing() -> (
    None
):
    # Arrange
    registry = Registry()

    class _NoDestroys:
        pass

    # Act / Assert
    with pytest.raises(MissingDestroysDeclarationError):
        registry.add_many([(_GovernedContract, "widget", _NoDestroys)], distribution="acme-widgets")

    with pytest.raises(UnknownPluginError):
        registry.lookup(_GovernedContract, "widget")


def test_add_accepts_a_partial_wrapped_factory_that_declares_destroys_on_its_class() -> None:
    # Arrange — the shape a plugin needing pack settings must take
    # (`functools.partial(PluginClass, settings)`, exactly what `weft_store`
    # registers `PgVectorStore` as). `hasattr` on a bare `partial` never reaches
    # `.func`, so `Registry.add` must unwrap it before reading `destroys` off the
    # class the partial actually constructs.
    registry = Registry()

    class _Marker:
        pass

    class _DestroysSomething:
        destroys: tuple[type, ...] = (_Marker,)

        def __init__(self, settings: object) -> None:
            self.settings = settings

    factory = functools.partial(_DestroysSomething, "pack-settings")

    # Act
    registry.add(_GovernedContract, "widget", factory, distribution="acme-widgets")

    # Assert
    assert registry.lookup(_GovernedContract, "widget") is factory


def test_add_refuses_a_partial_wrapped_factory_whose_class_never_declares_destroys() -> None:
    # Arrange — edge case: the unwrap must not paper over a genuine omission.
    registry = Registry()

    class _NoDestroys:
        def __init__(self, settings: object) -> None:
            self.settings = settings

    factory = functools.partial(_NoDestroys, "pack-settings")

    # Act / Assert
    with pytest.raises(MissingDestroysDeclarationError):
        registry.add(_GovernedContract, "widget", factory, distribution="acme-widgets")

    assert registry.contracts() == frozenset()


# --- task 3.1: the generalised required-declarations mechanism --------------------------


class _DeclaringContract:
    """A stand-in contract that names a required declaration directly, never via `destroys`.

    `required_declarations` is the general mechanism task 3.1 adds —
    `weft_command.contract.Command` uses this exact shape for
    `permission_class`, but the kernel must not know that name, so this
    stand-in uses an unrelated one (`widget_colour`) to prove the check is
    genuinely contract-agnostic rather than secretly special-casing a string
    the real contract happens to use. Assigned after the class body, the
    same reason `publishes_property_vocabulary` is on `_GovernedContract`
    above.
    """

    if TYPE_CHECKING:
        required_declarations: ClassVar[tuple[str, ...]]


_DeclaringContract.required_declarations = ("widget_colour",)


def test_add_refuses_a_factory_missing_a_declared_required_declaration() -> None:
    # Arrange
    registry = Registry()

    class _NoColour:
        """Never mentions `widget_colour` at all."""

    # Act / Assert
    with pytest.raises(MissingRequiredDeclarationError) as excinfo:
        registry.add(_DeclaringContract, "widget", _NoColour, distribution="acme-widgets")

    message = str(excinfo.value)
    assert "widget" in message
    assert "_DeclaringContract" in message
    assert "widget_colour" in message
    assert registry.contracts() == frozenset()


def test_add_accepts_a_factory_that_declares_the_required_declaration() -> None:
    # Arrange
    registry = Registry()

    class _HasColour:
        widget_colour = "red"

    # Act
    registry.add(_DeclaringContract, "widget", _HasColour, distribution="acme-widgets")

    # Assert
    assert registry.lookup(_DeclaringContract, "widget") is _HasColour


def test_a_missing_destroys_declaration_is_still_the_specific_destroys_error() -> None:
    # Assert — the fold: `destroys` is a required declaration like any other, but the
    # specific error type task 1.2's own tests catch by name is preserved rather than
    # collapsed into the generic family.
    assert issubclass(MissingDestroysDeclarationError, MissingRequiredDeclarationError)


def test_add_refuses_when_both_the_legacy_flag_and_the_general_mechanism_name_declarations() -> (
    None
):
    # Arrange — a contract using both sources at once: `publishes_property_vocabulary` (the
    # legacy spelling `Chunker`/`Cleaner` already ship) contributing `destroys`, and
    # `required_declarations` contributing a second, unrelated name. Both must be enforced
    # by the one check.
    registry = Registry()

    class _BothSources:
        if TYPE_CHECKING:
            publishes_property_vocabulary: ClassVar[bool]
            required_declarations: ClassVar[tuple[str, ...]]

    _BothSources.publishes_property_vocabulary = True
    _BothSources.required_declarations = ("widget_colour",)

    class _DestroysOnly:
        destroys: tuple[type, ...] = ()

    class _ColourOnly:
        widget_colour = "red"

    class _Neither:
        pass

    class _Both:
        destroys: tuple[type, ...] = ()
        widget_colour = "red"

    # Act / Assert — missing the general-mechanism name still refuses, even with `destroys`
    # present.
    with pytest.raises(MissingRequiredDeclarationError):
        registry.add(_BothSources, "a", _DestroysOnly, distribution="acme-widgets")

    # Act / Assert — missing `destroys` still refuses, as the specific subclass, even with
    # the general-mechanism name present.
    with pytest.raises(MissingDestroysDeclarationError):
        registry.add(_BothSources, "b", _ColourOnly, distribution="acme-widgets")

    with pytest.raises(MissingRequiredDeclarationError):
        registry.add(_BothSources, "c", _Neither, distribution="acme-widgets")

    # Act — both present: registers cleanly.
    registry.add(_BothSources, "d", _Both, distribution="acme-widgets")

    # Assert
    assert registry.lookup(_BothSources, "d") is _Both


def test_names_for_lists_every_name_under_one_contract_and_nothing_under_another() -> None:
    # Arrange
    registry = Registry()
    registry.add(_Chunker, "fast", lambda: "fast", distribution="acme-a")
    registry.add(_Chunker, "thorough", lambda: "thorough", distribution="acme-b")
    registry.add(_Extractor, "fast", lambda: "unrelated", distribution="acme-c")

    # Act / Assert — the contract is part of the key, so one name under two contracts is
    # two registrations, exactly as `Registry`'s own docstring states.
    assert registry.names_for(_Chunker) == frozenset({"fast", "thorough"})
    assert registry.names_for(_Extractor) == frozenset({"fast"})


def test_names_for_a_contract_nothing_registered_is_empty_rather_than_an_error() -> None:
    # Arrange
    class _Unregistered: ...

    # Act / Assert — symmetric with `distributions_for`: a caller enumerating what is
    # installed asks a question, and "nothing" is an answer, not a failure.
    assert Registry().names_for(_Unregistered) == frozenset()


def test_unwrap_factory_returns_a_bare_factory_unchanged() -> None:
    # Arrange
    def factory() -> str:
        return "a chunker instance"

    # Act / Assert
    assert unwrap_factory(factory) is factory


def test_unwrap_factory_peels_a_partial_down_to_the_class_it_constructs() -> None:
    # Arrange
    class _Plugin:
        destroys: tuple[type, ...] = ()

        def __init__(self, settings: object) -> None:
            self.settings = settings

    factory = functools.partial(_Plugin, "settings")

    # Act / Assert
    assert unwrap_factory(factory) is _Plugin


# --- task 1.12: pinned collisions --------------------------------------------------------


def test_duplicate_registration_with_no_pin_prints_the_toml_shape_that_would_resolve_it() -> None:
    # Arrange
    registry = Registry()
    registry.add(_Chunker, "semantic", lambda: "first", distribution="weft-chunk")

    # Act / Assert
    with pytest.raises(DuplicateRegistrationError) as excinfo:
        registry.add(_Chunker, "semantic", lambda: "second", distribution="weft-graph")

    message = str(excinfo.value)
    assert "[plugins]" in message
    assert '"_Chunker:semantic"' in message


def test_add_resolves_a_pinned_collision_by_letting_the_pinned_distribution_replace_it() -> None:
    # Arrange
    registry = Registry(plugin_pins={"_Chunker:shared": "weft-winner"})
    first_factory = lambda: "first"  # noqa: E731 - stand-in, not production code
    second_factory = lambda: "second"  # noqa: E731 - stand-in, not production code
    registry.add(_Chunker, "shared", first_factory, distribution="weft-loser")

    # Act
    registry.add(_Chunker, "shared", second_factory, distribution="weft-winner")

    # Assert — the pinned winner is what a lookup returns; the loser is recorded, not dropped.
    assert registry.lookup(_Chunker, "shared") is second_factory
    [displaced] = registry.displaced()
    assert displaced.contract is _Chunker
    assert displaced.name == "shared"
    assert displaced.distribution == "weft-loser"
    assert displaced.winner == "weft-winner"
    assert displaced.pin == "_Chunker:shared"


def test_add_resolves_a_pinned_collision_by_keeping_the_already_registered_entry() -> None:
    # Arrange — edge case: the pin names the distribution that registered *first*, so the
    # entry never changes and it is the *second* attempt that is displaced.
    registry = Registry(plugin_pins={"_Chunker:shared": "weft-first"})
    first_factory = lambda: "first"  # noqa: E731 - stand-in, not production code
    registry.add(_Chunker, "shared", first_factory, distribution="weft-first")

    # Act
    registry.add(_Chunker, "shared", lambda: "second", distribution="weft-second")

    # Assert
    assert registry.lookup(_Chunker, "shared") is first_factory
    [displaced] = registry.displaced()
    assert displaced.distribution == "weft-second"
    assert displaced.winner == "weft-first"


def test_add_raises_when_the_pin_names_neither_contending_distribution() -> None:
    # Arrange — error case: a pin naming a distribution that never claimed the name is a lie
    # about what is running, not a tie-breaker to apply anyway.
    registry = Registry(plugin_pins={"_Chunker:shared": "weft-nobody"})
    registry.add(_Chunker, "shared", lambda: "first", distribution="weft-a")

    # Act / Assert
    with pytest.raises(UnresolvedPluginPinError) as excinfo:
        registry.add(_Chunker, "shared", lambda: "second", distribution="weft-b")

    message = str(excinfo.value)
    assert "weft-nobody" in message
    assert "weft-a" in message
    assert "weft-b" in message
    # And the registry is untouched — a rejected pin resolves nothing.
    assert registry.lookup(_Chunker, "shared")() == "first"


def test_unconsulted_pins_reports_a_pin_that_never_saw_a_collision() -> None:
    # Arrange — no second distribution ever contends for this name, so the pin is inert.
    registry = Registry(plugin_pins={"_Chunker:never-fought-over": "weft-a"})

    # Act
    registry.add(_Chunker, "some-other-name", lambda: None, distribution="weft-a")

    # Assert
    assert registry.unconsulted_pins() == frozenset({"_Chunker:never-fought-over"})


def test_unconsulted_pins_is_empty_once_a_pin_actually_resolves_a_collision() -> None:
    # Arrange
    registry = Registry(plugin_pins={"_Chunker:shared": "weft-winner"})
    registry.add(_Chunker, "shared", lambda: "first", distribution="weft-loser")

    # Act
    registry.add(_Chunker, "shared", lambda: "second", distribution="weft-winner")

    # Assert
    assert registry.unconsulted_pins() == frozenset()


def test_add_many_commits_the_rest_of_a_batch_around_a_pinned_collision() -> None:
    # Arrange — a pinned collision must not fail the whole batch the way an unpinned one
    # does: `docs/03-cli.md` describes the losing pack as "installed, active", not failed.
    registry = Registry(plugin_pins={"_Chunker:shared": "weft-graph"})
    registry.add(_Chunker, "shared", lambda: "first", distribution="weft-chunk")

    # Act
    registry.add_many(
        [
            (_Chunker, "shared", lambda: "second"),
            (_Chunker, "extra", lambda: "extra"),
        ],
        distribution="weft-graph",
    )

    # Assert
    assert registry.lookup(_Chunker, "shared")() == "second"
    assert registry.lookup(_Chunker, "extra")() == "extra"
    [displaced] = registry.displaced()
    assert displaced.distribution == "weft-chunk"
