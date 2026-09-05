"""Unit tests for `weft_cli.services`.

Mirrors `packages/weft-rag/src/weft_cli/services.py`. Covers the happy path
(a `[services] embed` naming a plugin is what `weft index` and `weft ask`
resolve), the default (no block at all, or no `weft.toml` at all, selects the
deterministic offline embedder), and the error cases: a key nothing reads, a
`[services]` that is not a table, and a value that is not a plugin name.

The default is the one under test that matters most: `poe ci-checks` runs
with no `weft.toml`, no credential and no network, and that has to keep being
true by construction rather than by nobody having written the file yet.
"""

import pytest

from weft_cli.services import (
    DEFAULT_EMBEDDER,
    DEFAULT_ROUTER,
    DEFAULT_STORE,
    ServiceSelection,
    UnknownServiceKeyError,
    service_selection_from_config,
)
from weft_kernel.errors import WeftError


def test_no_document_at_all_selects_the_deterministic_embedder() -> None:
    # Act
    selection = service_selection_from_config(None)

    # Assert
    assert selection == ServiceSelection()
    assert selection.embed == DEFAULT_EMBEDDER == "hash"


def test_a_document_with_no_services_block_selects_the_deterministic_embedder() -> None:
    # Arrange
    document: dict[str, object] = {"packs": {"allow": ["weft-store"]}}

    # Act
    selection = service_selection_from_config(document)

    # Assert
    assert selection.embed == "hash"


def test_services_embed_names_the_embedder_a_run_resolves() -> None:
    # Arrange — the whole operation for swapping which embedder runs: one line, in the
    # project's own configuration file, with no package edited and nothing reinstalled.
    document: dict[str, object] = {"services": {"embed": "openai"}}

    # Act
    selection = service_selection_from_config(document)

    # Assert
    assert selection.embed == "openai"


def test_an_unknown_services_key_is_refused_naming_the_keys_that_exist() -> None:
    # Arrange
    document: dict[str, object] = {"services": {"embedd": "openai"}}

    # Act / Assert — silently ignoring it would index a corpus with the deterministic
    # embedder while its operator believes a model ran, which does not crash: it answers
    # plausibly, against vectors that mean nothing.
    with pytest.raises(WeftError) as raised:
        service_selection_from_config(document)
    assert "embedd" in str(raised.value)
    assert "embed" in str(raised.value)


def test_an_unknown_services_key_carries_the_known_keys_as_a_typed_field() -> None:
    # Arrange — repair, 2026-08-20: the message already named the keys, but only inside the
    # string, never as a typed field fitness function 12's family walk can see. `weft_cli.
    # config_surface.UnknownConfigKeyError` is the same-phase precedent this now matches.
    document: dict[str, object] = {"services": {"embedd": "openai"}}

    # Act / Assert
    with pytest.raises(UnknownServiceKeyError) as raised:
        service_selection_from_config(document)
    assert raised.value.valid_options == ("embed", "route", "store")


def test_a_services_value_that_is_not_a_plugin_name_is_refused() -> None:
    # Arrange
    document: dict[str, object] = {"services": {"embed": ["openai"]}}

    # Act / Assert
    with pytest.raises(WeftError) as raised:
        service_selection_from_config(document)
    assert "embed" in str(raised.value)


def test_a_services_key_that_is_not_a_table_is_refused_the_way_packs_is() -> None:
    # Arrange — the same shape `weft_cli.registry_bootstrap.pack_settings_from_config`
    # refuses for `[packs]`: two readers of one file must not disagree about what a
    # malformed block means.
    document: dict[str, object] = {"services": ["embed"]}

    # Act / Assert
    with pytest.raises(WeftError) as raised:
        service_selection_from_config(document)
    assert "[services]" in str(raised.value)


def test_services_store_names_the_backend_a_run_indexes_into_and_searches() -> None:
    # Arrange — repair for a reviewer finding against task 2.6: `weft-qdrant` shipped a
    # second registered `NodeStore` that no command could select, so swapping the backend
    # meant editing `weft_cli.ingest`. One line in the operator's own file is the whole
    # operation, exactly as it already is for the embedder.
    document: dict[str, object] = {"services": {"store": "qdrant"}}

    # Act
    selection = service_selection_from_config(document)

    # Assert
    assert selection.store == "qdrant"
    assert ServiceSelection().store == DEFAULT_STORE == "pgvector"


def test_services_route_names_the_pipeline_document_weft_ask_routes_through() -> None:
    # Arrange — ledger task 8.3. `weft_cli.route_ask` held "route" as a module constant, which
    # made the router the one pipeline nothing could substitute: a pack cannot contribute a
    # second document under a name another pack already holds, and a project that ships its own
    # `route.yaml` is refused by `full_catalogue` outright. So `threshold-ladder` and `always`
    # were registered, listed and documented while being placeable by nobody. One line in the
    # operator's own file is the whole operation, exactly as it already is for the embedder and
    # the store.
    document: dict[str, object] = {"services": {"route": "route-by-score"}}

    # Act
    selection = service_selection_from_config(document)

    # Assert
    assert selection.route == "route-by-score"
    assert ServiceSelection().route == DEFAULT_ROUTER == "route"
