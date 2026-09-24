"""Ledger task **39.1**: the bar a model anchor finder must clear to replace the shape rule.

The gate of ledger task **39.1**, second form: does the model decomposition find every anchor of
eighty questions it never saw, without flooding the text arm? Opt-in, because it reaches a model.

G24's Q-A was reopened by measurement on 2026-09-18: the deterministic rule gated at precision
0.800 and recall 0.923 on a blind forty, because a shape cannot tell `32MB` from `AX6000` or
`ETIMEDOUT` from `SMTP`. The owner made the model decomposition the candidate mechanism, and after
its first gate reversed the trade: **recall 1.0, precision at least 0.95**, scored by which
identifier was found rather than how its span was spelled — `RFC7231` and `7231`, `TLS 1.3` and
`1.3`, `getSocketOpt()` and `getSocketOpt` name one thing each. The prompt names no token that
occurs in either fixture set.
"""

import os
import re
import tomllib
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path
from typing import Final

import pytest
from pydantic import SecretStr

from weft_kernel.context import Context, ServiceRegistry
from weft_kernel.payload import Produced
from weft_kernel.registry import Registry
from weft_llm.client import NullSink, llm_service
from weft_llm.contract import LLM, LLMProvider, TokenSink
from weft_llm.roles import LLMRoles, RoleMapping
from weft_openai import OpenAILLMProvider
from weft_openai import Settings as OpenAISettings
from weft_openai.llm import DEFAULT_MODEL
from weft_prompts.contract import Prompt
from weft_retrieve.contract import StageLookup
from weft_retrieve.intent_and_anchors import (
    NAME,
    AnchorMethod,
    IntentAndAnchors,
    IntentAndAnchorsConfig,
)
from weft_retrieve.payload import Query, QuerySet
from weft_retrieve.prompts import QUESTION_ANCHORS_NAME, QuestionAnchorsPrompt

_API_KEY_VAR = "OPENAI_API_KEY"

#: The explicit opt-in, separate from the credential — ledger task **6.28**; see
#: `tests/integration/test_openai_llm.py`'s own copy for why each module repeats it.
_LIVE_OPT_IN_VAR = "WEFT_LIVE_API_TESTS"

_FIXTURES: Final[Path] = Path(__file__).parents[1] / "unit" / "weft_retrieve" / "fixtures"
_SETS: Final[tuple[str, ...]] = ("anchor_questions_first.toml", "anchor_questions_gate.toml")
_PRECISION_FLOOR: Final[float] = 0.95


def _canonical(anchor: str) -> str:
    text = anchor.strip().removesuffix("()").removesuffix("'s")
    return re.sub(r"^RFC ?(?=\d)", "", text, flags=re.IGNORECASE)


def _same_identifier(expected: str, found: str) -> bool:
    """One identifier however its span was drawn: equal, or one is a word of the other."""
    left, right = _canonical(expected), _canonical(found)
    return left == right or left in right.split() or right in left.split()


class _PromptLookup:
    """A `StageLookup` narrowed to `build_capability` over a real `Registry`.

    `test_hypothetical_questions_pipeline.py`'s own.
    """

    def __init__(self, registry: Registry) -> None:
        self._registry = registry

    def names(self, contract: type[object]) -> frozenset[str]:
        return frozenset(self._registry.names_for(contract))

    async def build(self, contract: type[object], name: str, config: object = None) -> object:
        raise AssertionError("this test resolves a capability by name, never a stage")

    async def build_capability(
        self, contract: type[object], name: str, config: object = None
    ) -> object:
        return self._registry.entry(contract, name).factory(config)


@pytest.fixture
def api_key() -> SecretStr:
    key = os.environ.get(_API_KEY_VAR)
    if not os.environ.get(_LIVE_OPT_IN_VAR):
        pytest.skip(
            f"{_LIVE_OPT_IN_VAR} is unset: this reaches a live service, so it is opt-in "
            f"separately from {_API_KEY_VAR} — having a credential is not asking for a "
            f"network run, and `poe ci-checks` stays deterministic without it."
        )
    if not key:
        pytest.skip(f"{_API_KEY_VAR} is unset: this test needs a real OpenAI account")
    return SecretStr(key)


def _questions() -> list[tuple[str, str, tuple[str, ...]]]:
    rows: list[tuple[str, str, tuple[str, ...]]] = []
    for name in _SETS:
        raw = tomllib.loads((_FIXTURES / name).read_text(encoding="utf-8"))
        rows.extend(
            (entry["id"], entry["text"], tuple(entry["anchors"])) for entry in raw["question"]
        )
    return rows


@dataclass
class _Tally:
    """The gate's running counts, and every anchor missed, span invented or run failed."""

    missed: list[str] = field(default_factory=list[str])
    invented: list[str] = field(default_factory=list[str])
    failed: list[str] = field(default_factory=list[str])
    expected_total: int = 0
    returned_total: int = 0
    found_expected: int = 0
    matched_returned: int = 0

    def score(self, identifier: str, expected: tuple[str, ...], found: tuple[str, ...]) -> None:
        self.expected_total += len(expected)
        self.returned_total += len(found)
        for anchor in expected:
            if any(_same_identifier(anchor, span) for span in found):
                self.found_expected += 1
            else:
                self.missed.append(f"{identifier}: {anchor!r}")
        for span in found:
            if any(_same_identifier(anchor, span) for anchor in expected):
                self.matched_returned += 1
            else:
                self.invented.append(f"{identifier}: {span!r}")


#: Eighty sequential completions; the suite's 60 s default killed the first run.
@pytest.mark.timeout(600)
async def test_the_model_finds_every_anchor_and_nothing_else_on_both_sets(
    api_key: SecretStr,
) -> None:
    # Arrange
    registry = Registry()
    registry.add(
        LLMProvider,
        "openai",
        partial(OpenAILLMProvider, OpenAISettings(api_key=api_key)),
        distribution="weft-openai",
    )
    registry.add(Prompt, QUESTION_ANCHORS_NAME, QuestionAnchorsPrompt, distribution="weft-rag")
    llm = llm_service(
        registry=registry,
        roles=LLMRoles(roles={"anchors": RoleMapping(provider="openai", model=DEFAULT_MODEL)}),
    )
    services = ServiceRegistry()
    services.add(LLM, llm)
    services.add(TokenSink, NullSink())
    services.add(StageLookup, _PromptLookup(registry))
    ctx = Context(
        tenant_id="tenant-a", run_id="gate", trace_id="gate", locale="en", services=services
    )
    transform = IntentAndAnchors(IntentAndAnchorsConfig(method=AnchorMethod.MODEL))
    questions = _questions()

    # Act
    tally = _Tally()
    for identifier, text, expected in questions:
        query = Query(text=text, locale="en")
        outcome = await transform.run(QuerySet(origin=query, queries=(query,)), ctx)
        found: tuple[str, ...] = ()
        if isinstance(outcome, Produced):
            found = tuple(q.text for q in outcome.value.queries if q.produced_by == NAME)
        else:
            tally.failed.append(f"{identifier}: {outcome}")
        tally.score(identifier, expected, found)
    await llm.close()
    recall = tally.found_expected / tally.expected_total
    precision = tally.matched_returned / tally.returned_total if tally.returned_total else 1.0
    # One message carries every number: the gate is run once, so a first failing assertion
    # must not hide the rest of the measurement.
    verdict = (
        f"recall={recall:.4f} ({tally.found_expected}/{tally.expected_total}) "
        f"precision={precision:.4f} ({tally.matched_returned}/{tally.returned_total}) "
        f"failed={tally.failed} invented={tally.invented} missed={tally.missed}"
    )
    print(verdict)

    # Assert
    assert len(questions) == 80
    assert recall == 1.0 and precision >= _PRECISION_FLOOR, verdict
