"""What a retrieval score means, read off whatever produced it — ledger task **21.1**.

`docs/03-cli.md` → *Output*, *Score display* settled in Phase 0 that a human sees rank order and
never the raw number, because `Scored.score` is a similarity — unbounded, and routinely negative
with the hash embedder — and a bare `-0.31` reads as broken to somebody with no context for it.
That decision was right and it left a gap: the ladder's own output cannot be inspected by the
person climbing it. `12-roadmap.md` §4 measured `--explain` and `score_semantics` as appearing
**zero** times in this tree, and §5c is the argument for closing it.

**The rule this module exists to hold: a number is shown only with its meaning, and the meaning
comes from whatever produced the number.** Not from a table here. A producer writes an English
sentence beside the code that computes its score, which is G11's own answer for error text —
*"a plugin writes its message where it raises, in English, and does not look it up"* — applied to
a score.

**Declared, never required.** `score_semantics` is read with `getattr(..., default)`, the same
defensive idiom `weft_kernel.runner` uses for `lifetime`, `requires` and `provides`, and for the
reason `02` → *What a plugin receives* records at its Phase 0 step 7 narrowing: a `ClassVar` in a
`@runtime_checkable` Protocol's body becomes a **required** `isinstance` member, so a third-party
retriever that never restated it would fail a capability check that has nothing to do with
capability. A producer that declares nothing renders as an absence and never as a guess — inventing
a plausible sentence for a plugin that never wrote one is the silent fallback `CLAUDE.md` refuses,
because a reader cannot tell it from a real claim.

**No central list, and that was the phase's one open question.** `12` §5c says that a task finding
itself inventing an enum of score meanings has found a gate rather than a bug — a closed key space
the kernel would have to name, which `01` → *The kernel boundary* and requirement 5 both bear on.
It did not arise: the sentence is the producer's own string, this module holds none of its own, and
adding a retriever adds a meaning without editing anything here.

**Two producers, because there are two.** A `Retriever` has one `run` and declares one
`score_semantics`. `weft_store.PgVectorStore` satisfies two published capabilities that return
incommensurable numbers — `VectorSearch` gives `1 - cosine distance`, `TextSearch` gives whatever
`ts_rank_cd` says under the normalization ledger task `21.0` made selectable — so it declares one
per *capability*. A single attribute on that class would have to describe two different numbers,
which is the field being wrong rather than the class being awkward.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast

#: What a producer that declared nothing renders as. **An absence, stated.** `01` requirement 5's
#: posture for an unknown name applied to an undeclared fact: say what was wanted and why it is
#: unavailable, rather than filling the hole with something that reads like an answer.
_UNDECLARED = "{produced_by} did not say what its score means"


@dataclass(frozen=True, slots=True)
class ScoreExplanation:
    """One producer, and what it says its numbers mean."""

    produced_by: str
    semantics: str | None

    @classmethod
    def of(
        cls, producer: object, *, produced_by: str, attribute: str = "score_semantics"
    ) -> ScoreExplanation:
        """Read `producer`'s own declaration, defensively.

        `attribute` exists because a producer can satisfy more than one capability and they need
        not agree: `weft_store.PgVectorStore` declares `vector_score_semantics` and
        `text_score_semantics`, and the caller is the one that knows which arm it just invoked. A
        `Retriever` has one `run` and uses the default.

        A `score_semantics` that is not a string is treated exactly as no declaration at all —
        an author's typo, and the failure it would otherwise produce is a `dict` spliced into the
        middle of a sentence a person reads, which is the defect `weft_cli.confirm.gate`'s own
        comment records happening one seam over and Phase 3's fourth repair fixed.
        """
        declared = getattr(producer, attribute, None)
        return cls(
            produced_by=produced_by,
            semantics=declared if isinstance(declared, str) and declared else None,
        )

    def rendered(self) -> str:
        """One line for a person: what produced the column, and what its numbers mean."""
        if self.semantics is None:
            return _UNDECLARED.format(produced_by=self.produced_by)
        return f"{self.produced_by}: {self.semantics}"


def explanations_for(
    produced_by: Sequence[str], *, producers: Mapping[str, object]
) -> tuple[ScoreExplanation, ...]:
    """One explanation per **distinct** producer, in first-seen order.

    Per hit would be unreadable at `top_k: 20` and would repeat one fact twenty times; what a
    reader wants is *what this column means*, which is a property of the producer and not of the
    row. First-seen rather than sorted so the order matches the ranking a reader is looking at.

    A name with no producer in `producers` still gets a line: it is a real producer that this
    caller could not resolve, and dropping it would silently shorten the list of scales in play —
    which is the one thing `incomparable_note` below is counting.
    """
    seen: dict[str, ScoreExplanation] = {}
    for name in produced_by:
        if name not in seen:
            seen[name] = ScoreExplanation.of(_producer_for(name, producers), produced_by=name)
    return tuple(seen.values())


def _producer_for(label: str, producers: Mapping[str, object]) -> object:
    """The plugin behind a `retrieved_by` label, which is not always the whole label.

    **Found by running the binary at task 21.1, not by a test.** A fan-out labels each arm
    `<plugin>:<arm>` — `weft_retrieve.hybrid`'s own docstring writes `weights: {"hybrid:vector":
    1.0, "hybrid:text": 0.7}` — so `weft ask --pipeline hybrid-then-generate --explain` looked up
    `hybrid:vector`, found nothing, and reported *"hybrid:vector did not say what its score
    means"*. Honest, and useless: the plugin right there had the sentence.

    The label stays whole in what a reader sees, because which *arm* produced a number is the
    thing they are asking about; only the lookup falls back to the part before the first colon.
    """
    if label in producers:
        return producers[label]
    plugin, _, _arm = label.partition(":")
    return producers.get(plugin)


def arm_explanations(
    produced_by: Sequence[str], *, producers: Mapping[str, object], store: object
) -> tuple[ScoreExplanation, ...]:
    """One line per fan-out arm whose retriever names the store capability it called.

    **Carried repair `R21.2`.** `explanations_for` reports the fused column's own meaning;
    it does not say what each arm's underlying search returned, because that number is the
    *store's*, not the retriever's — `Hybrid.arm_score_attributes` is the retriever saying
    which store attribute each arm read. An arm whose retriever declares no such mapping, or
    whose name the mapping does not recognise, gets no line: the fused line already covers the
    column, and a guessed one would be worse than silence.
    """
    explanations: list[ScoreExplanation] = []
    seen: set[str] = set()
    for label in produced_by:
        if label in seen:
            continue
        seen.add(label)
        plugin, sep, arm = label.partition(":")
        if not sep:
            continue
        producer = producers.get(plugin)
        declared = getattr(producer, "arm_score_attributes", None)
        if not isinstance(declared, Mapping):
            continue
        mapping = cast(Mapping[str, object], declared)
        attribute = mapping.get(arm)
        if not isinstance(attribute, str):
            continue
        explanations.append(
            ScoreExplanation.of(store, produced_by=f"{label}'s own ranking", attribute=attribute)
        )
    return tuple(explanations)


def incomparable_note(produced_by: Sequence[str]) -> str | None:
    """`None` when every score came from one producer; otherwise the sentence saying they did not.

    **The half of `21.1` with a live instance.** A fan-out — `multi-retriever`, `hybrid` — puts
    passages from different retrievers in one list and `Passage.retrieved_by` records which. Their
    numbers are on different scales, and printing them in one column with no note invites exactly
    the comparison `weft_retrieve.fusion` exists because you cannot make: reciprocal-rank fusion
    combines *rankings* precisely because the scores underneath them do not commensurate.

    It names the producers rather than saying "some of these differ", because a reader's next
    question is which ones, and an answer that does not contain it sends them to the source.
    """
    distinct = sorted(set(produced_by))
    if len(distinct) < 2:
        return None
    named = ", ".join(distinct)
    return (
        f"these scores come from more than one retriever ({named}) and are on different scales — "
        f"compare the ranking, not the numbers"
    )


__all__ = ["ScoreExplanation", "arm_explanations", "explanations_for", "incomparable_note"]
