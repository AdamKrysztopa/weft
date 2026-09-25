"""Carried repair **R43.29** — a superseded generation is withdrawn now and reclaimed later.

A handle fixes its manifest when it opens (`43.14`), and `retract_generation` deleted the nodes only
the old generation held and stripped its id from the ones both shared, so a query that opened
before a corpus layer's publish was left holding neither tree. `withdraw_generation` takes the
generation out of every later manifest and changes no node; `reclaim_withdrawn(layer)` does what
the retract did, at the layer's next build or at `weft reconcile`. `GenerationWithdrawing` is its
own optional Protocol, `43.22`'s precedent, so the store contract moves a minor.

The stranger is `examples/weft-example-ingest`'s store, the only in-process `GenerationHolding`.
"""

import importlib
import sys
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest

from weft_kernel.errors import UnresolvedNameError, WeftError
from weft_store.conformance import (
    GenerationWithdrawingStore,
    check_a_handle_opened_after_a_withdraw_sees_only_the_generation_that_replaced_it,
    check_a_handle_opened_before_a_withdraw_keeps_reading_the_tree_it_opened_on,
    check_a_layer_rebuilt_twice_reads_as_one_tree_at_every_step,
    check_reclaiming_a_layer_removes_the_nodes_only_its_withdrawn_generations_held,
    check_withdrawing_an_unknown_or_unpublished_generation_is_refused_by_name,
    checks_for,
    unsupported_checks,
)
from weft_store.contract import (
    STORE_CONTRACT_VERSION,
    GenerationHolding,
    GenerationId,
    GenerationStatus,
    GenerationWithdrawing,
    NotAPublishedGenerationError,
)
from weft_store.memory import MemoryStore

_OPERATIONS = ("withdraw_generation", "reclaim_withdrawn")
_PROTOCOL = "GenerationWithdrawing"
_STORE_TYPE = "GenerationWithdrawingStore"
_KIT_CHECKS = (
    check_a_handle_opened_before_a_withdraw_keeps_reading_the_tree_it_opened_on,
    check_a_handle_opened_after_a_withdraw_sees_only_the_generation_that_replaced_it,
    check_a_layer_rebuilt_twice_reads_as_one_tree_at_every_step,
    check_reclaiming_a_layer_removes_the_nodes_only_its_withdrawn_generations_held,
    check_withdrawing_an_unknown_or_unpublished_generation_is_refused_by_name,
)

_EXAMPLE_SRC = Path(__file__).resolve().parents[3] / "examples/weft-example-ingest/src"


@pytest.fixture
def stranger(monkeypatch: pytest.MonkeyPatch) -> Callable[[], GenerationWithdrawingStore]:
    monkeypatch.setattr(sys, "path", [str(_EXAMPLE_SRC), *sys.path])
    module = importlib.import_module("weft_example_ingest.store")
    return lambda: cast("GenerationWithdrawingStore", module.InMemoryNodeStore())


def test_withdrawing_is_its_own_optional_protocol_so_the_contract_moves_a_minor() -> None:
    # Assert
    assert STORE_CONTRACT_VERSION == "3.0.0"
    assert GenerationWithdrawing.version == STORE_CONTRACT_VERSION
    assert GenerationStatus("withdrawn") is GenerationStatus.WITHDRAWN
    for operation in _OPERATIONS:
        assert callable(getattr(GenerationWithdrawing, operation, None)), operation
        assert not hasattr(GenerationHolding, operation), operation


def test_a_refused_withdraw_names_the_generation_its_status_and_the_published_ones() -> None:
    # Act
    refused = NotAPublishedGenerationError(
        GenerationId("g-2"), status=GenerationStatus.BUILDING, valid_options=("g-1", "g-3")
    )

    # Assert
    assert isinstance(refused, WeftError)
    assert isinstance(refused, UnresolvedNameError)
    assert (refused.generation, refused.status) == ("g-2", GenerationStatus.BUILDING)
    assert refused.valid_options == ("g-1", "g-3")
    for fact in ("'g-2'", "building", "g-1", "g-3"):
        assert fact in str(refused), fact


def test_the_kit_offers_the_withdrawing_checks_only_to_a_store_that_withdraws() -> None:
    # Act
    offered = checks_for(MemoryStore())
    withheld = dict(unsupported_checks(MemoryStore()))

    # Assert
    for check in _KIT_CHECKS:
        assert check.__annotations__.get("store") == _STORE_TYPE
        assert check not in offered
        assert withheld[check] == _PROTOCOL


async def test_a_strangers_store_withdraws_generations_and_passes_the_published_checks(
    stranger: Callable[[], GenerationWithdrawingStore],
) -> None:
    """Fitness function 9(c)'s stranger for the new capability, on `43.22`'s footing."""
    # Arrange
    withdrawing_checks = [
        check
        for check in checks_for(stranger())
        if check.__annotations__.get("store") == _STORE_TYPE
    ]

    # Act — a fresh store per check: the kit owns no lifecycle.
    for check in withdrawing_checks:
        await check(stranger())

    # Assert
    assert isinstance(stranger(), GenerationWithdrawing)
    assert sorted(check.__name__ for check in withdrawing_checks) == sorted(
        check.__name__ for check in _KIT_CHECKS
    )
