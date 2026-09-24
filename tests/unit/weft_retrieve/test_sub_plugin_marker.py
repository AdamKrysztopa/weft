"""Repair **R43.42**: `SubPlugin` is published by `weft_retrieve` beside `StageLookup`.

Repair **R43.42**: `SubPlugin` is published by `weft_retrieve` beside `StageLookup`, and
publishing it moves the retrieve contract family by a minor — an addition a stranger can depend on.
"""

import weft_retrieve
from weft_retrieve import RETRIEVE_CONTRACT_VERSION
from weft_retrieve import contract as retrieve_contract


def test_the_marker_is_published_from_the_pack_and_its_contract_module() -> None:
    # Assert
    assert "SubPlugin" in weft_retrieve.__all__
    assert weft_retrieve.SubPlugin is retrieve_contract.SubPlugin


def test_the_marker_names_the_field_holding_the_sub_plugin_config() -> None:
    # Act
    marker = weft_retrieve.SubPlugin(config="leaf_config")

    # Assert
    assert marker.config == "leaf_config"
    assert weft_retrieve.SubPlugin().config is None


def test_publishing_the_marker_is_a_minor_contract_version() -> None:
    # Assert
    assert RETRIEVE_CONTRACT_VERSION == "1.1.0"
