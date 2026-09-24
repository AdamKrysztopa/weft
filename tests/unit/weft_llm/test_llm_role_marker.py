"""Repair **R43.35**: `LLMRole` is published by `weft_llm`, moving its contract by a minor.

Repair **R43.35**: `LLMRole` is published by `weft_llm`, and publishing it moves the contract
version by a minor — an addition a stranger's pack can now depend on.
"""

import weft_llm
from weft_llm import LLM_CONTRACT_VERSION
from weft_llm import contract as llm_contract


def test_the_marker_is_published_from_the_pack_and_its_contract_module() -> None:
    # Assert
    assert "LLMRole" in weft_llm.__all__
    assert weft_llm.LLMRole is llm_contract.LLMRole


def test_publishing_the_marker_is_a_minor_contract_version() -> None:
    # Assert
    assert LLM_CONTRACT_VERSION == "1.1.0"
