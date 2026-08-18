"""The live half of `weft-openai`: a vector that carries semantic meaning, measured.

`docs/build-ledger.md` task 2.29 — "a vector carries semantic meaning when a
model is configured, and the gate still runs with no credentials and no
download because the deterministic embedder stays the offline default." The
second clause is what every other test in this tree checks, by never needing
an account. This file is the first clause, and it cannot be checked without
one: whether an embedding *means* anything is a property of the model, not of
this pack's plumbing, and a stubbed client can only ever prove the plumbing.

**Against the real API, skipped with a clear reason when the credential is
absent — never silently passed.** The same discipline
`tests/integration/test_ingest_pipeline.py` states for the container, applied
to the other external dependency Weft has. `docs/09-release.md` §4's offline
subset is exactly this line: with no `OPENAI_API_KEY`, `poe ci-checks` runs
end to end and reports one skip; with one, it also re-measures the claim the
pack's own docstring makes.

**What is asserted is a separation, not a number.** `09` §4.4 forbids
inventing a quality threshold, and "cosine ≥ 0.5" would be exactly that. The
property is ordinal and is the whole reason to run a model at all: two ways
of saying one thing are closer to each other than either is to a sentence
about something else. `HashEmbedder` fails that by construction — it is
measured here beside the model, at the same width, so the claim "not a
quality component" is a comparison this file makes rather than a sentence
somewhere asserting it.
"""

import math
import os
from collections.abc import Sequence

import pytest
from pydantic import SecretStr

from weft_embed import HashEmbedder, HashEmbedderConfig
from weft_kernel.context import Context
from weft_kernel.payload import MediaType, Node, Produced, Vector
from weft_openai import OpenAIEmbedder, OpenAIEmbedderConfig, Settings

_API_KEY_VAR = "OPENAI_API_KEY"

#: Two ways of saying one thing, and one sentence about something else. Ordinary prose
#: rather than a term-overlap trap: "kitten"/"napping" share no word with "cat"/"sleeping",
#: so nothing but a model can put the first two closer together than the third.
_RELATED_A = "a cat sleeping on a warm windowsill"
_RELATED_B = "a kitten napping in the sun"
_UNRELATED = "quarterly amortisation of intangible assets"

#: The native width of `text-embedding-3-small`, measured against the live API rather than
#: read off a page — see `weft_openai.embedder`'s module docstring.
_NATIVE_DIMENSION = 1536


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


def _node(content: str) -> Node:
    return Node.synthetic(content=content, media_type=MediaType.TEXT, reason="live probe")


def _credential() -> SecretStr:
    key = os.environ.get(_API_KEY_VAR)
    if not key:
        pytest.skip(f"{_API_KEY_VAR} is unset: the live OpenAI embedding checks cannot run")
    return SecretStr(key)


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    return dot / (math.sqrt(sum(a * a for a in left)) * math.sqrt(sum(b * b for b in right)))


async def _vectors(embedder: OpenAIEmbedder | HashEmbedder) -> tuple[Vector, Vector, Vector]:
    nodes = [_node(_RELATED_A), _node(_RELATED_B), _node(_UNRELATED)]
    outcome = await embedder.run(nodes, _ctx())
    assert isinstance(outcome, Produced)
    first, second, third = (node.embedding for node in outcome.value)
    assert first is not None and second is not None and third is not None
    return first, second, third


async def test_the_model_puts_two_ways_of_saying_one_thing_closer_together() -> None:
    # Arrange
    embedder = OpenAIEmbedder(Settings(api_key=_credential()))

    # Act
    related_a, related_b, unrelated = await _vectors(embedder)

    # Assert — ordinal, never a threshold. Measured on 2026-08-17: 0.62 against 0.07.
    close = _cosine(related_a.values, related_b.values)
    far = _cosine(related_a.values, unrelated.values)
    assert close > far
    await embedder.aclose()


async def test_the_deterministic_embedder_does_not_and_says_so() -> None:
    # Arrange — the same three strings, the same width, no network. This is the control:
    # without it, the test above only says the API answered something.
    embedder = HashEmbedder(HashEmbedderConfig(dimension=_NATIVE_DIMENSION))

    # Act
    related_a, related_b, unrelated = await _vectors(embedder)

    # Assert — both scores are noise around zero, and the "related" pair is not reliably
    # the closer one. Measured on 2026-08-17: 0.005 against -0.005.
    close = _cosine(related_a.values, related_b.values)
    far = _cosine(related_a.values, unrelated.values)
    assert abs(close) < 0.1
    assert abs(far) < 0.1


async def test_the_default_model_returns_its_native_width_and_a_shortened_one_on_request() -> None:
    # Arrange
    settings = Settings(api_key=_credential())
    native = OpenAIEmbedder(settings)
    shortened = OpenAIEmbedder(settings, OpenAIEmbedderConfig(dimensions=256))

    # Act
    outcome = await native.run([_node(_RELATED_A)], _ctx())
    trimmed = await shortened.run([_node(_RELATED_A)], _ctx())

    # Assert — `dimensions` is a knob that reaches the API, not one this pack records and
    # ignores; the vector really is shorter.
    assert isinstance(outcome, Produced)
    assert isinstance(trimmed, Produced)
    full_vector = outcome.value[0].embedding
    short_vector = trimmed.value[0].embedding
    assert full_vector is not None and short_vector is not None
    assert full_vector.dimension == _NATIVE_DIMENSION
    assert short_vector.dimension == 256
    await native.aclose()
    await shortened.aclose()
