"""Unit tests for `weft_prompts.contract`.

Mirrors `packages/weft-prompts/src/weft_prompts/contract.py`. Covers the two properties every
contract test in this tree checks — capability is structural, and the version constant is the
contract's own — plus the mechanical rule that keeps a *service* out of the contract
reference: `Prompts` carries no `version` and is not `@runtime_checkable`.
"""

from typing import ClassVar

from pydantic import BaseModel

from weft_prompts.contract import PROMPT_CONTRACT_VERSION, Prompt, Prompts


class _Ask(BaseModel):
    question: str


def test_capability_is_structural_and_needs_no_import_of_the_contract() -> None:
    # Arrange — a class that declares the three members and never mentions `Prompt`.
    class _Plain:
        input_model: ClassVar[type[BaseModel]] = _Ask
        output_model: ClassVar[type[BaseModel] | None] = None

        async def render(self, values: BaseModel, ctx: object) -> object:
            del values, ctx
            raise NotImplementedError

    class _NoModels:
        async def render(self, values: BaseModel, ctx: object) -> object:
            del values, ctx
            raise NotImplementedError

    # Act / Assert — the input model is part of the capability, not decoration: a prompt whose
    # inputs are untyped is exactly the untyped-dict prompt this contract exists to replace.
    assert isinstance(_Plain(), Prompt)
    assert not isinstance(_NoModels(), Prompt)


def test_the_contract_carries_its_own_version_constant() -> None:
    # Act / Assert — fitness function 6's subject.
    assert Prompt.version == PROMPT_CONTRACT_VERSION


def test_the_prompts_service_is_not_a_registrable_contract() -> None:
    # Act / Assert — `.phase2-design.md` §3: a service "carries no `version` and is never
    # registered under a name", which is what keeps it out of `manual/contract-reference.md`.
    assert not hasattr(Prompts, "version")
    assert getattr(Prompts, "_is_runtime_protocol", False) is False
