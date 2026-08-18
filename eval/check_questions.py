"""Prerequisite **V2** (`docs/09-release.md` §4.3) — the question set, and what may be believed.

V2 wants *"questions with relevance judgements for retrieval and reference answers for
generation; the provenance of each answer recorded (who wrote it, from which passage); and
unanswerable questions included"*, and it states its own failure condition: *"ground truth is
missing for any question and the harness scores it anyway."* This module is the reader of that
set, and every rule below exists because the set can be wrong in a way nobody notices.

**Self-verification is not evidence, and that is measured rather than assumed.** These questions
were written in two rounds by agents that had read the document they cite, each verifying its own
quotes; an independent mechanical re-check still rejected 4 of 287 quotes as appearing nowhere in
the file they named — one of them attributing a table from one paper to another. So the check runs
in the gate, over the corpus that is actually on disk, and it is the *only* reason to believe a
quote. `tests/docs/test_question_set.py` drives it, and this module holds no `main()` — see the
bottom of this docstring for why.

**A judgement is pinned to `(document, quote)`, never to a node id.** A `NodeId` is a content
digest over the chunker's output, so a judgement pinned to one is invalidated by any chunking
change — which is how the reference ended up reaching for a paper-level fallback and inflating
precision toward 1.0 (`09` §4.2). A literal span survives re-chunking and resolves, at scoring
time, to whatever units the pipeline under test actually retrieved.

**The quote check is meant to be able to fail.** `weft-pdf` ships two backends that produce
visibly different text from the same page, so a quote taken from one may stop matching under the
other, and a re-rendered Wikipedia revision moves the Polish spans. That failure is information:
it says this ground truth no longer describes what the pipeline reads, and a tolerant match —
normalised whitespace, fuzzy ratio — would hide exactly the drift the check exists to surface.
Five Polish quotes and five page numbers were already stale when this file was written, against a
corpus repaired one commit earlier, and nothing but an exact match would have said so.

**A tier is a fact about a document, so a question never states one.** Which questions a stranger
can reproduce follows from the tiers of the documents they name — `reproducible_questions` derives
it — and the file a question lives in is the round it was written in, nothing more. An earlier
draft carried `tier` on the question itself and it disagreed with the manifest for 24 of the 136,
which is what a second copy of someone else's fact does.

**There is no `main()` here, and that is forced rather than an omission.** The design record calls
this a hand-run validator; verifying a quote means reading the text an `Extractor` produces, every
contract method is `async def` (G6), and `asyncio.run` may appear exactly once in the whole tree
(fitness function 7(a), asserted by path). A second bridge here to make a CLI convenient is
precisely what that check exists to refuse. So the async half lives in the gate test, which is
also how this is run by hand: `uv run pytest tests/docs/test_question_set.py`.
"""

from __future__ import annotations

import tomllib
from collections.abc import Callable, Iterable, Mapping
from enum import StrEnum
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[1]

#: Where the tracked question files live. Every `.toml` under it is part of the set; the file names
#: are authoring rounds, and nothing reads meaning off them.
QUESTIONS_DIR: Final[Path] = REPO_ROOT / "eval" / "questions"


class Kind(StrEnum):
    """What a question asks for — the axis a baseline slices its results along.

    `UNANSWERABLE` is the member V2 names outright: *"a RAG engine that cannot say 'not in this
    corpus' is untested for its most damaging failure."* It is also the one member with a
    structural consequence, checked below rather than trusted — such a question has no relevant
    document and no quote, because there is nothing in the corpus to point at.
    """

    DEFINITIONAL = "definitional"
    METHODOLOGICAL = "methodological"
    QUANTITATIVE = "quantitative"
    COMPARATIVE = "comparative"
    LIMITATION = "limitation"
    CROSS_DOCUMENT = "cross-document"
    UNANSWERABLE = "unanswerable"


class Difficulty(StrEnum):
    """How much of the document a question makes a retriever reach for.

    The author's own estimate, and recorded as one: nothing here checks it, and it is carried
    because a baseline that scores 0.9 on `EASY` and 0.3 on `HARD` has said something a single
    mean cannot.
    """

    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class Quote(BaseModel):
    """One literal span of a document's extracted text, and where in that document it is.

    `page` is `0` for a document that has no pages — a Wikipedia article is one stream of text and
    inventing a page for it would be a number nothing could check. For a PDF it is 1-based and
    verified against the extractor's own page boundaries, so it is a checked fact rather than an
    annotation, in the shape `corpus/manifest.toml` already uses for `math_blocks_dropped`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    document: str = Field(min_length=1)
    page: int = Field(ge=0)
    text: str = Field(min_length=1)

    @field_validator("text", mode="after")
    @classmethod
    def _without_toml_s_own_newlines(cls, text: str) -> str:
        """Drop the newlines TOML's multi-line form adds, and nothing else.

        A `\"\"\"…\"\"\"` value written over several lines carries a trailing newline that belongs
        to the closing delimiter and not to the passage. Leading and trailing *spaces* are left
        exactly as authored: a rendering that lost one is the drift this whole module exists to
        catch, and a `.strip()` here would swallow it.
        """
        return text.strip("\n")


class Question(BaseModel):
    """One question, its reference answer, and the spans that support it.

    Every per-question invariant V2 implies is refused here rather than asserted somewhere else,
    so a malformed question fails at the moment it is read and names itself while doing it. The
    set-level properties — ids unique across files, documents known to the manifest, the corpus
    covered — need more than one question to state and live in `tests/docs/test_question_set.py`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    #: BCP-47, matching `corpus/manifest.toml`'s `language`. A fact about the ask.
    language: str = Field(min_length=1)
    kind: Kind
    difficulty: Difficulty
    #: The documents an answer must be drawn from — the retrieval judgement. Empty exactly when
    #: the question is unanswerable.
    relevant_documents: tuple[str, ...] = ()
    reference_answer: str = Field(min_length=1)
    #: V2's *"the provenance of each answer recorded (who wrote it, from which passage)"*. Prose
    #: rather than a sub-table because it carries the reasoning as well as the attribution — what
    #: was searched for and not found is most of what makes an unanswerable question believable.
    notes: str = Field(min_length=1)
    quote: tuple[Quote, ...] = ()

    @property
    def answerable(self) -> bool:
        """Whether the corpus contains an answer. Derived, so no field can disagree with it."""
        return self.kind is not Kind.UNANSWERABLE

    @model_validator(mode="after")
    def _ground_truth_agrees_with_the_stance(self) -> Question:
        """The failure V2 names: ground truth missing while the harness scores the question anyway.

        Both directions, because each is a different lie. An answerable question with no quote
        would be scored against nothing and count as a miss for every pipeline. An unanswerable
        one carrying a relevant document says the corpus answers it after all, and the stance
        metric — the one generation-side number that needs no judge — would then be measured
        against a question that is not what it claims to be.
        """
        if self.answerable:
            if not self.relevant_documents:
                raise ValueError(f"{self.id}: {self.kind.value} but names no relevant document")
            if not self.quote:
                raise ValueError(f"{self.id}: {self.kind.value} but carries no supporting quote")
            quoted = {quote.document for quote in self.quote}
            stray = sorted(quoted - set(self.relevant_documents))
            if stray:
                raise ValueError(f"{self.id}: quotes a document it does not call relevant: {stray}")
            silent = sorted(set(self.relevant_documents) - quoted)
            if silent:
                raise ValueError(
                    f"{self.id}: calls a document relevant but quotes nothing from it: {silent}"
                )
        else:
            if self.relevant_documents:
                raise ValueError(
                    f"{self.id}: unanswerable, yet names {list(self.relevant_documents)} as "
                    f"relevant — an unanswerable question is one the corpus does not answer"
                )
            if self.quote:
                raise ValueError(
                    f"{self.id}: unanswerable, yet carries {len(self.quote)} supporting quote(s)"
                )
        multi = len(set(self.relevant_documents)) > 1
        if multi != (self.kind is Kind.CROSS_DOCUMENT):
            raise ValueError(
                f"{self.id}: kind is {self.kind.value} over "
                f"{len(set(self.relevant_documents))} document(s); "
                f"'{Kind.CROSS_DOCUMENT.value}' means more than one and nothing else means it"
            )
        return self


def load_questions(directory: Path = QUESTIONS_DIR) -> tuple[Question, ...]:
    """Every question under `directory`, in file then declaration order.

    A parse or validation failure names the file it came from. `tomllib` reports a syntax error by
    byte offset and pydantic reports a field error by index, and neither says which of four files
    is meant — in a set of 136 questions that is most of the work still to do.
    """
    questions: list[Question] = []
    for path in sorted(directory.glob("*.toml")):
        with path.open("rb") as handle:
            raw = tomllib.load(handle)
        for index, entry in enumerate(raw.get("question", ())):
            try:
                questions.append(Question.model_validate(entry))
            except ValueError as exc:
                message = f"{path.name}, question {index}: {exc}"
                raise ValueError(message) from exc
    return tuple(questions)


def reproducible_questions(
    questions: Iterable[Question], *, tiers: Mapping[str, str], reproducible: frozenset[str]
) -> tuple[Question, ...]:
    """The questions a stranger can score, given which corpus tiers they can obtain.

    **This is the subset a published baseline is measured on**, and the reason is Phase 6's exit:
    the release is reproduced by someone who is not us, and a question resting on a paper under
    publisher copyright is one they cannot obtain at any price. Measuring the published number
    over the whole set would make it a number only this machine can produce.

    Derived from the manifest's own tier labels rather than from anything written on a question,
    so adding a document to the operator tier moves the subset without anyone editing this file.
    Unanswerable questions name no document and are therefore always in — which is right, and
    worth saying: they are the subset's hardest members and the only ones that need no corpus at
    all to be judged.

    As of the commit that introduced this, 95 of 136 questions are reproducible. That number is
    stated as a measurement, not pinned as a constant: `tests/docs/test_question_set.py` asserts
    the properties that must hold whatever it becomes.
    """
    tier_of = dict(tiers)
    return tuple(
        question
        for question in questions
        if all(tier_of[document] in reproducible for document in question.relevant_documents)
    )


class QuoteCoverage(BaseModel):
    """How much of the ground truth a comparison actually opened, and what it could not.

    `unmatched_quotes` and `misplaced_quotes` pass over a quote whose document is not in `texts`,
    which is right — the corpus payload is untracked and an unfetched document is not a bad quote.
    It also makes their silence ambiguous: *no failures* can mean every span was read back out of
    the paper it names, or that a third of them were never opened. Six of the papers are under
    publisher copyright and are placed by hand, so on every machine but the author's the second
    reading is the true one, and the caller reports this next to the result rather than letting a
    partial run read as an unqualified pass.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: Quotes whose document was in `texts`, and which were therefore actually compared.
    compared: int = Field(ge=0)
    #: Every quote the questions carry, compared or not.
    total: int = Field(ge=0)
    #: The documents those quotes name that the comparison had no text for, sorted.
    absent_documents: tuple[str, ...] = ()

    @property
    def whole(self) -> bool:
        """Whether every quote was read back out of the document it names."""
        return not self.absent_documents

    def describe(self) -> str:
        """One line for a run's own output: how much was checked, and what was missing."""
        if self.whole:
            return f"all {self.total} quotes checked"
        return (
            f"{self.compared} of {self.total} quotes checked; no text for "
            f"{len(self.absent_documents)} document(s): {', '.join(self.absent_documents)}"
        )


def quote_coverage(questions: Iterable[Question], texts: Mapping[str, str]) -> QuoteCoverage:
    """What a comparison over `texts` would actually read, and which documents it would skip.

    Here rather than in the caller, and by the same rule the two checks below skip on, because a
    coverage number computed somewhere else is free to drift into describing a comparison nobody
    ran.
    """
    compared = 0
    total = 0
    absent: set[str] = set()
    for question in questions:
        for quote in question.quote:
            total += 1
            if quote.document in texts:
                compared += 1
            else:
                absent.add(quote.document)
    return QuoteCoverage(compared=compared, total=total, absent_documents=tuple(sorted(absent)))


def unmatched_quotes(questions: Iterable[Question], texts: Mapping[str, str]) -> tuple[str, ...]:
    """Every quote that is not an exact substring of the text it names, one line each.

    Documents absent from `texts` are skipped rather than reported: the corpus payload is
    untracked, so a checkout with nothing materialised is normal, and calling an unfetched
    document a bad quote would report the wrong fact. The caller is what makes that safe — the
    gate test asserts the set of documents it managed to extract is non-empty before believing an
    empty result here.
    """
    failures: list[str] = []
    for question in questions:
        for quote in question.quote:
            body = texts.get(quote.document)
            if body is None or quote.text in body:
                continue
            failures.append(
                f"{question.id}: quote not found in {quote.document!r} — {_head(quote.text)!r}"
            )
    return tuple(failures)


def misplaced_quotes(
    questions: Iterable[Question],
    texts: Mapping[str, str],
    page_at: Callable[[str, int], int],
) -> tuple[str, ...]:
    """Every quote whose `page` disagrees with where the extractor says that span is.

    `page_at(document_id, offset)` is supplied rather than computed here, and that is the point:
    the parser pack already owns the rule that turns an offset into a page number
    (`weft_pdf.PdfPages.page_at`), and a second implementation of it in `eval/` would be a copy
    free to disagree with the citation a reader is eventually shown. A document with no pages
    answers `0`.

    **Every occurrence is considered, not the first.** A table header repeated on the following
    page is one span in two places, and taking `str.index` alone would report the author's correct
    page as wrong — a false failure, which in a check whose whole value is that its failures are
    believed is worse than a missed one. The claim under test is *"this span is on that page"*, so
    finding it there satisfies it.

    A quote that is not in the text at all is `unmatched_quotes`' business and is passed over
    here, so one stale span produces one failure rather than two.
    """
    failures: list[str] = []
    for question in questions:
        for quote in question.quote:
            body = texts.get(quote.document)
            if body is None or quote.text not in body:
                continue
            found = sorted({page_at(quote.document, at) for at in _occurrences(body, quote.text)})
            if quote.page not in found:
                failures.append(
                    f"{question.id}: quote in {quote.document!r} says page {quote.page}, "
                    f"extraction puts it on {found} — {_head(quote.text)!r}"
                )
    return tuple(failures)


def _occurrences(body: str, span: str) -> Iterable[int]:
    """Every offset at which `span` starts in `body`."""
    at = body.find(span)
    while at != -1:
        yield at
        at = body.find(span, at + 1)


def _head(text: str, limit: int = 60) -> str:
    """The opening of a quote, enough to find it in the file without printing a paragraph."""
    return text[:limit] + ("…" if len(text) > limit else "")
