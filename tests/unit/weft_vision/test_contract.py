"""The `Describer` contract — ledger task `9.9`.

**One method, and it names the medium rather than the model.** `describe(data, media_type,
instruction)`: bytes, what they are, and what to say about them. `11` §2.2's own proposal, and the
reason it is shaped that way is in `11` §2.1 — *"the same contract covers audio transcription
later"*. A contract called `VisionLLM`, or one taking a `model=` argument, would be the vendor's
category leaking into Weft's; a contract taking `media_type` is Weft's own.

**A service, not a stage.** No pipeline position, no `run`, no `Stage[In, Out]` base. `TokenSink`
is the precedent, and the seam wraps stages and `flush` and nothing else. Two stages consume it at
opposite ends of a pipeline — `describe-figure` at index time (`9.11`) and a query-side enricher
that `10` §4 reserves and nobody has built — which is the argument for one service contract rather
than an index-only `Enhancer`.

**It answers `Outcome[str]`, not `str`.** A describer that cannot see the image, or is refused by
the provider, must be able to say so without raising through a stage that has other figures to
process. `NothingToProduce` and `Failed` are the two ways to say it, and they are not the same
claim — `02` §1's three-outcome rule applied to a service.

**A local or hosted VLM is the same plugin with a different `base_url`.** That sentence in `9.9`'s
ledger line is a constraint on this contract, not a note about deployment: nothing here may name a
provider, a model family, or a hosting arrangement.
"""

from typing import Protocol

from weft_kernel.context import ServiceRole
from weft_kernel.payload import Outcome, Produced
from weft_vision.contract import DESCRIBE_ROLE, DESCRIBER_CONTRACT_VERSION, Describer


class _StrangerDescriber:
    """Satisfies `Describer` structurally, importing nothing from it — a stranger's path."""

    async def describe(self, data: bytes, media_type: str, instruction: str) -> Outcome[str]:
        del data, media_type, instruction
        return Produced(value="a description")


def test_a_class_that_imports_nothing_from_the_contract_satisfies_it() -> None:
    # Act / Assert
    assert isinstance(_StrangerDescriber(), Describer)


def test_a_class_missing_the_method_does_not_satisfy_it() -> None:
    """The contrast that makes the check above mean something."""

    # Arrange
    class _Partial:
        async def transcribe(self, data: bytes) -> str:
            del data
            return ""

    # Act / Assert
    assert not isinstance(_Partial(), Describer)


def test_the_contract_is_one_method_and_is_not_a_stage() -> None:
    """A service has no pipeline position, so `run` must not be a member."""
    # Act / Assert
    assert _members() == {"describe"}


def test_the_one_method_is_async() -> None:
    """`CLAUDE.md`: async only. A blocking vision call would stall every other stage."""
    # Act / Assert
    assert Describer.describe.__code__.co_flags & 0x80


def test_the_contract_names_no_provider_and_no_model() -> None:
    """`9.9`'s own clause — *names the medium and not the model*.

    Asserted over the contract module's whole source rather than over the signature, because the
    way this gets broken is a docstring example, a default, or a type alias mentioning a vendor —
    none of which a signature check would see. `11` §2.3's naming rule one level up: the plugin
    names the role, and the model is `with: model:`.
    """
    # Arrange
    from pathlib import Path

    import weft_vision.contract as module

    source = Path(str(module.__file__)).read_text(encoding="utf-8").lower()

    # Act / Assert — a vendor may be named as a *counter*-example in prose; none of these is.
    for vendor in ("openai", "anthropic", "gemini", "qwen", "gpt-", "claude", "llava"):
        assert vendor not in source, f"the contract module names {vendor!r}"


def test_the_contract_declares_a_version_off_the_protocol_attribute_set() -> None:
    """Fitness function 6's subject, with `version` kept out of `__protocol_attrs__`."""
    # Act / Assert
    assert Describer.version == DESCRIBER_CONTRACT_VERSION
    assert "version" not in _members()


def test_the_pack_declares_which_services_key_selects_a_describer() -> None:
    """Task 9.0's seam: one constant beside the Protocol, never a `ClassVar` on it."""
    # Act / Assert
    assert isinstance(DESCRIBE_ROLE, ServiceRole)
    assert DESCRIBE_ROLE.contract is Describer


def test_the_protocol_is_a_protocol_rather_than_a_base_class() -> None:
    """A stranger must never import this module to be a describer."""
    # Act / Assert
    assert Protocol in _mro()


def _members() -> set[str]:
    """`Describer.__protocol_attrs__`, through a cast — `typing` declares it on no Protocol."""
    import typing

    return typing.cast("set[str]", typing.cast("typing.Any", Describer).__protocol_attrs__)


def _mro() -> tuple[type, ...]:
    import typing

    return typing.cast("tuple[type, ...]", typing.cast("typing.Any", Describer).__mro__)
