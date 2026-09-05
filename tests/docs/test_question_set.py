"""Prerequisite **V2** (`docs/09-release.md` §4.3) as a machine check rather than a claim.

V2 wants *"questions with relevance judgements for retrieval and reference answers for
generation; the provenance of each answer recorded (who wrote it, from which passage); and
unanswerable questions included"*, and it fails when *"ground truth is missing for any question
and the harness scores it anyway"*. `eval/check_questions.py` refuses a malformed question as it
is read; this file checks the properties that need the whole set, the manifest, and the corpus on
disk.

**Why the quote check is here and not in a review checklist.** These questions were written in two
rounds by 24 agents, each of which verified its own quotes before handing them over. An
independent mechanical re-check still found 4 of 287 quotes that appear nowhere in the file they
name — one attributing a table from one paper to another. Self-verification is not evidence, so
the only thing that makes a quote believable is this test reading the document and finding the
span. It found five more stale Polish quotes and five wrong page numbers the first time it ran,
against a corpus repaired one commit earlier.

**It must be able to fail, and it is not made tolerant to avoid that.** `weft-pdf` ships two
backends whose output differs visibly on the same page, and a Wikipedia revision re-rendered by
`scripts/wikitext.py` moves every Polish span. When a quote stops matching, that is the ground
truth no longer describing what the pipeline reads — a fact worth a red gate, and one that
normalised whitespace or a similarity ratio would quietly absorb. The backend each format is
verified through is named in `VERIFYING_BACKEND` below and resolved in the registry, so changing
it is a configuration edit (`.phase2-findings.md` finding 9) that produces a visible diff and a
visible re-verification.

**Nothing here can pass because a walk found nothing** (task 1.18). The corpus payload is
untracked — six papers are under publisher copyright — so a checkout with nothing materialised is
normal, and the quote checks would otherwise be a subset test over an empty set reporting V2 as
satisfied. Four things stop that: the `materialised` fixture **skips** rather than passes when no
document is on disk, so the run summary says *not verified here* instead of *verified*; the floor
below it asserts that every document which is on disk actually produced text; every quote check
reports its own **coverage**, because a corpus that is present in part is the ordinary case and a
pass over two thirds of the quotes must say so rather than read as a pass over all of them; and
`test_the_quote_check_can_fail` and `test_the_page_check_can_fail` show each comparison rejecting
what it exists to reject, which is what makes a green result above them evidence rather than a
shape.
"""

import tomllib
import warnings
from collections.abc import Callable, Mapping, Sequence
from importlib import metadata
from pathlib import Path
from typing import Final, cast

import pytest
from check_questions import (
    Difficulty,
    Kind,
    Question,
    Quote,
    QuoteCoverage,
    load_questions,
    misplaced_quotes,
    quote_coverage,
    reproducible_questions,
    unmatched_quotes,
)
from fetch_corpus import Document, Status, Tier, load_manifest, verify_one

from tests.discovery import discover_for_tests
from weft_extract.contract import Extractor, SourceDoc
from weft_kernel.context import Context
from weft_kernel.payload import Node, Produced, SourceId
from weft_kernel.registry import Registry
from weft_pdf.document import PdfPages

#: Backends that turn bytes into text with no third-party library behind them — nothing to pin,
#: and saying so here is what keeps `test_the_extraction_step_the_quotes_were_taken_from_is_pinned`
#: from reading as a gap. `text` is `weft-extract`'s own decoder.
_BACKENDS_WITH_NO_LIBRARY: Final[frozenset[str]] = frozenset({"text"})

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
MANIFEST: Final[Path] = REPO_ROOT / "corpus" / "manifest.toml"

#: Which registered `Extractor` each corpus format is verified through — a plugin **name**,
#: resolved in the registry, never an import. Swapping `pdf-text` for `pdf-layout` here is the
#: configuration edit `.phase2-findings.md` finding 9 requires a parser swap to be, and it is
#: expected to turn this file red until every quote is re-taken from the new backend's output.
#: An unknown name fails through `UnknownPluginError`, which lists what *is* registered.
VERIFYING_BACKEND: Final[dict[str, str]] = {".txt": "text", ".md": "text", ".pdf": "pdf-text"}

#: The tiers a stranger can obtain, and therefore the ones a published baseline may be measured
#: over. Stated the same way `tests/docs/test_corpus_manifest.py` states it, for the same reason:
#: Phase 6's exit is somebody else reproducing the number, and no price obtains an `operator`
#: paper.
REPRODUCIBLE_TIERS: Final[frozenset[str]] = frozenset(
    tier.value for tier in Tier if tier.reproducible
)

_CONTEXT: Final[Context] = Context(
    tenant_id="eval", run_id="question-set", trace_id="question-set", locale="en"
)

#: The module's one reading of the corpus, memoised — see `_extracted`. A plain dict rather than a
#: fixture, because two of the three tests that need it are `async`, and a module-scoped async
#: fixture has to be tied to a module-scoped event loop as well: a second thing to keep true for
#: something that is only "read the papers once".
_CACHE: dict[str, Node] = {}


class PartialCorpus(UserWarning):
    """A quote check passed over less ground truth than the question set carries.

    Its own category so a run can be filtered on it and a reader can tell it from anything a
    dependency emits. Deliberately not an error: the six papers under publisher copyright cannot be
    fetched at any price, so a checkout without them is legitimate — what is not legitimate is that
    run reporting the same green as one that read every quote.
    """


@pytest.fixture(scope="module")
def questions() -> tuple[Question, ...]:
    """Every tracked question, refused at load if it is malformed."""
    return load_questions()


@pytest.fixture(scope="module")
def documents() -> tuple[Document, ...]:
    """Every document the tracked manifest declares."""
    _, entries = load_manifest(MANIFEST)
    return tuple(entries)


@pytest.fixture(scope="module")
def materialised(documents: tuple[Document, ...]) -> tuple[Document, ...]:
    """The corpus documents whose bytes are on this machine and match their digest.

    **Skips rather than passes when there are none.** The corpus payload is untracked — six of the
    papers are under publisher copyright — so a clean checkout legitimately holds nothing, and a
    quote check over nothing would report V2 as satisfied on a machine that has never seen the
    corpus. A skip says *not verified here* in the run summary; a green test says *verified*, and
    only one of those is true.

    **The skip is all-or-nothing, and a partial corpus is the ordinary case**, so it is not what
    makes a partial run readable — `_report` is. `test_corpus_manifest.py`'s
    `test_a_materialised_tier_is_whole_and_verifies` rejects a *half*-fetched tier and deliberately
    permits a wholly absent one, which is exactly the state of anyone who has run
    `fetch_corpus.py fetch` and has not been handed the six operator papers: this fixture returns
    the fetch tier, both quote checks pass, and a third of the set's quotes were never opened. What
    they say about that is the coverage line, not this skip.
    """
    present = tuple(entry for entry in documents if verify_one(entry).status is Status.OK)
    if not present:
        pytest.skip(
            "no corpus document is materialised on this machine, so no quote can be read back "
            "out of the document it names. Run `python scripts/fetch_corpus.py fetch` for the "
            "reproducible tiers; the operator tier is placed by hand."
        )
    return present


# --- The floors, which is what stops an empty walk reporting success ---------------------------


def test_the_question_set_is_non_empty_and_names_each_question_once(
    questions: tuple[Question, ...],
) -> None:
    # Floor A. The walk is over tracked TOML, which an unfetched corpus cannot empty. The id is
    # how a baseline reports a per-question error and how `check_baseline` names a regression, so
    # two questions sharing one make the run unreadable at exactly the moment it matters.
    # Arrange
    identifiers = [question.id for question in questions]

    # Act
    repeated = sorted({one for one in identifiers if identifiers.count(one) > 1})

    # Assert
    assert questions, (
        f"no questions under {REPO_ROOT / 'eval' / 'questions'}; every check below would then be "
        f"vacuous, and V2 would be reported as satisfied by an empty set"
    )
    assert not repeated, f"question ids used more than once: {repeated}"


async def test_every_materialised_document_extracts_to_text(
    materialised: tuple[Document, ...],
) -> None:
    # Floor B. The quote checks are "no failures in this set", which is true of the empty set —
    # and a backend answering `NothingToProduce` for every paper would empty it while raising
    # nothing. `materialised` has already refused to let this run over an absent corpus, so this
    # is the half that says the documents which *are* here were actually read.
    # Arrange
    registry = discover_for_tests()

    # Act
    texts, _ = await _extracted(materialised, registry)

    # Assert
    assert set(texts) == {entry.id for entry in materialised}, (
        f"documents that are on disk and verify, yet produced no text: "
        f"{sorted({entry.id for entry in materialised} - set(texts))}. Every quote taken from one "
        f"of them would then be silently unchecked."
    )


# --- Ground truth against the corpus it names --------------------------------------------------


def test_every_relevant_document_is_declared_in_the_manifest(
    questions: tuple[Question, ...], documents: tuple[Document, ...]
) -> None:
    # A judgement pointing at a document the corpus does not contain is scored against nothing —
    # V2's own failure condition, and the reference's `open_rag_loader.py:191` defect by name.
    # Arrange
    known = {entry.id for entry in documents}

    # Act
    dangling = sorted(
        f"{question.id} -> {document}"
        for question in questions
        for document in question.relevant_documents
        if document not in known
    )

    # Assert
    assert not dangling, (
        f"questions naming a document that is not in {MANIFEST}: {dangling}. Either the id is "
        f"misspelled or the corpus lost an entry the ground truth still rests on."
    )


def test_every_corpus_document_is_asked_about(
    questions: tuple[Question, ...], documents: tuple[Document, ...]
) -> None:
    # The other direction. A document nothing asks about contributes only distractors to every
    # retrieval, so it makes the baseline look worse without any question being able to say why —
    # and it is the shape a corpus grows into when documents are added and questions are not.
    # Act
    named = {document for question in questions for document in question.relevant_documents}
    unasked = sorted({entry.id for entry in documents} - named)

    # Assert
    assert not unasked, (
        f"corpus documents no question names as relevant: {unasked}. Every document in the "
        f"manifest is retrieved against; one nothing asks about can only add noise to the "
        f"measurement."
    )


def test_the_set_includes_the_two_subsets_v2_asks_for_by_name(
    questions: tuple[Question, ...],
) -> None:
    # V2 asks for unanswerable questions outright — "a RAG engine that cannot say 'not in this
    # corpus' is untested for its most damaging failure" — and V1 asks for a non-English body,
    # which is only exercised if something is asked in that language.
    # Act
    unanswerable = [question for question in questions if not question.answerable]
    other_languages = sorted({q.language for q in questions if q.language != "en"})

    # Assert
    assert unanswerable, "no unanswerable question; V2 requires them by name"
    assert other_languages, (
        "every question is in English. Polish retrieval is shipped product under requirement 6, "
        "and a corpus with a Polish body nobody asks about tests none of it."
    )


def test_the_reproducible_subset_is_derived_and_is_neither_empty_nor_everything(
    questions: tuple[Question, ...], documents: tuple[Document, ...]
) -> None:
    # **The subset the published baseline is measured over.** Phase 6's exit is a stranger
    # reproducing the number, and a question resting on a paper under publisher copyright is one
    # they cannot obtain — so it is derived here from the manifest's tiers rather than declared on
    # a question, where it was wrong for 24 of 136 before this file existed.
    # Arrange
    tiers = {entry.id: entry.tier.value for entry in documents}

    # Act
    subset = reproducible_questions(questions, tiers=tiers, reproducible=REPRODUCIBLE_TIERS)
    excluded = tuple(q for q in questions if q.id not in {s.id for s in subset})

    # Assert
    assert subset, (
        "no question can be scored from the reproducible tiers alone, so the published baseline "
        "would have nothing to be measured over"
    )
    assert len(subset) < len(questions), (
        "every question is reproducible, which given an operator tier in the manifest means the "
        "derivation stopped reading tiers — the number this guards is the one a stranger repeats"
    )
    # The defining property, and the one the three shape assertions around it do not reach: a
    # derivation reading the *wrong* tier set returns something non-empty, strictly smaller, and
    # containing every unanswerable question, so all of those pass while the published baseline
    # rests on the six papers under publisher copyright. Both directions are derived from the
    # manifest, so neither pins a number.
    unobtainable = sorted(
        f"{q.id} -> {d} ({tiers[d]})"
        for q in subset
        for d in q.relevant_documents
        if tiers[d] not in REPRODUCIBLE_TIERS
    )
    assert not unobtainable, (
        f"questions called reproducible that rest on a document outside "
        f"{sorted(REPRODUCIBLE_TIERS)}: {unobtainable}. A stranger cannot obtain those bytes at "
        f"any price, so the number they repeat would not be the number we published."
    )
    obtainable = sorted(
        q.id for q in excluded if all(tiers[d] in REPRODUCIBLE_TIERS for d in q.relevant_documents)
    )
    assert not obtainable, (
        f"questions excluded from the reproducible subset that name only obtainable documents: "
        f"{obtainable}. The subset is smaller than the tiers justify, so the published baseline is "
        f"measured over less than a stranger could actually reproduce."
    )
    assert {q.id for q in questions if not q.answerable} <= {q.id for q in subset}, (
        "an unanswerable question was excluded from the reproducible subset. It names no "
        "document, so no tier can put it out of a stranger's reach, and it is the subset's whole "
        "generation-side signal."
    )


# --- The quotes, against the text an extractor actually produces --------------------------------


async def test_every_quote_is_a_literal_span_of_the_document_it_names(
    questions: tuple[Question, ...], materialised: tuple[Document, ...]
) -> None:
    # Arrange
    registry = discover_for_tests()

    # Act
    texts, _ = await _extracted(materialised, registry)
    failures = unmatched_quotes(questions, texts)
    coverage = quote_coverage(questions, texts)

    # Assert
    assert coverage.compared, (
        f"documents are materialised, yet not one quote could be compared against them: "
        f"{coverage.describe()}. 'No failures' over an empty comparison is the vacuous pass this "
        f"file exists to refuse."
    )
    assert not failures, (
        f"quotes that are not in the document they name, read through "
        f"{sorted(set(VERIFYING_BACKEND.values()))}:\n" + "\n".join(failures) + "\n\n"
        "A quote is the whole of a retrieval judgement, so one that no longer resolves makes its "
        "question unscoreable. Either the extraction backend moved and the quotes must be "
        "re-taken from its output, or the quote was never in that document — which is the "
        "mistake this check exists to catch and self-verification did not."
    )
    _report(coverage, "the substring check")


async def test_every_quote_is_on_the_page_it_claims(
    questions: tuple[Question, ...], materialised: tuple[Document, ...]
) -> None:
    # `page` is what a reader goes and looks at, so an unchecked one is a citation that sends them
    # to the wrong place — the manifest's `math_blocks_dropped` argument applied to ground truth.
    # Arrange
    registry = discover_for_tests()

    # Act
    texts, pages = await _extracted(materialised, registry)
    failures = misplaced_quotes(questions, texts, _page_at(pages))
    coverage = quote_coverage(questions, texts)

    # Assert
    assert coverage.compared, (
        f"documents are materialised, yet not one quote's page could be checked against them: "
        f"{coverage.describe()}"
    )
    assert not failures, (
        "quotes whose page number disagrees with the extractor's own page boundaries:\n"
        + "\n".join(failures)
        + "\n\nA printed page number and a PDF page index are not the same thing, and five of "
        "these were off by one to nine when this check was first run."
    )
    _report(coverage, "the page check")


def test_the_quote_check_can_fail() -> None:
    # The self-test `test_every_quote_is_a_literal_span_of_the_document_it_names` needs to be worth
    # running. The corpus is untracked, so on a fresh checkout it walks whatever is present — and
    # "every quote matched" is only evidence if a quote that moved would be reported.
    # Arrange
    question = _question_quoting("a  span the rendering once had", page=0)

    # Act
    intact = unmatched_quotes(
        [question], {"self-test-doc": "before a  span the rendering once had"}
    )
    moved = unmatched_quotes([question], {"self-test-doc": "before a span the rendering once had"})

    # Assert
    assert not intact
    assert len(moved) == 1, (
        "a single collapsed space left the quote matching, so the comparison is normalising "
        "whitespace somewhere — which is exactly the drift these checks exist to surface"
    )
    assert "self-test" in moved[0] and "self-test-doc" in moved[0]


def test_the_page_check_can_fail() -> None:
    # The same self-test for the other half, and the half with more to go wrong: the page check
    # rests on `PdfPages` surviving onto the root node, on `_page_at`'s fallback for a document
    # with no pages, and on `_occurrences` looking past the first hit. Any of those regressing
    # turns `test_every_quote_is_on_the_page_it_claims` into a check that found nothing to compare
    # and reported that as agreement — replacing `misplaced_quotes`' body with `return ()` left the
    # whole gate green until this existed.
    # Arrange
    question = _question_quoting("the table this claim reads off", page=4)
    texts = {"self-test-doc": "front matter " + question.quote[0].text}

    # Act
    agreeing = misplaced_quotes([question], texts, _page_always(4))
    disagreeing = misplaced_quotes([question], texts, _page_always(9))

    # Assert
    assert not agreeing
    assert len(disagreeing) == 1, (
        "a quote whose only occurrence is on a page it does not claim was not reported, so the "
        "page check is answering from something other than the extractor's boundaries"
    )
    assert "self-test" in disagreeing[0] and "self-test-doc" in disagreeing[0]


def test_a_span_repeated_on_a_second_page_is_not_a_wrong_page() -> None:
    # The complement, and the reason the check considers every occurrence rather than the first: a
    # table header repeated on the following page is one span in two places, and the claim under
    # test is "this span is on that page". Taking `str.index` alone would report the author's
    # correct page as wrong, and a false failure in a check whose whole value is that its failures
    # are believed costs more than a missed one.
    # Arrange
    span = "Table 3: relevance against redundancy"
    question = _question_quoting(span, page=9)
    prefix = "first appearance: "
    texts = {"self-test-doc": prefix + span + " … continued overleaf: " + span}

    # Act
    failures = misplaced_quotes([question], texts, _page_after(len(prefix) + len(span), 4, 9))

    # Assert
    assert not failures, (
        f"the second occurrence of a repeated span was not considered, so a correct page was "
        f"reported as wrong: {failures}"
    )


def test_the_coverage_count_names_the_ground_truth_that_was_never_opened() -> None:
    # What makes a partial run readable. Both checks above pass over a quote whose document is not
    # in `texts` — an unfetched corpus is normal here — so "no failures" on a machine missing a
    # tier is a much smaller claim than it looks, and `materialised` does not catch it because it
    # skips only when *nothing* is on disk. This count is what the two tests report alongside their
    # result, so a partial pass reads as one.
    # Arrange
    here = _question_quoting("a span of the paper this machine has", page=0)
    absent = _question_quoting("a span of the paper nobody fetched", page=0, document="operator-1")

    # Act
    partial = quote_coverage([here, absent], {"self-test-doc": here.quote[0].text})
    whole = quote_coverage(
        [here, absent], {"self-test-doc": here.quote[0].text, "operator-1": absent.quote[0].text}
    )

    # Assert
    assert (partial.compared, partial.total) == (1, 2)
    assert partial.absent_documents == ("operator-1",)
    assert not partial.whole
    assert "operator-1" in partial.describe(), (
        "the coverage line does not name the document it could not read, so a reader of the run "
        "cannot tell which tier is missing"
    )
    assert whole.whole and whole.compared == whole.total == 2


# --- What the reader refuses ---------------------------------------------------------------------


def test_an_unanswerable_question_naming_a_relevant_document_is_refused() -> None:
    # The stance metric is measured on this subset, so a question that is unanswerable in name and
    # answerable in its ground truth would make that number describe something else entirely.
    # Arrange
    entry = _self_test_question(kind="unanswerable", relevant_documents=["self-test-doc"])

    # Act / Assert
    with pytest.raises(ValueError, match="unanswerable"):
        Question.model_validate(entry)


def test_an_answerable_question_with_no_supporting_quote_is_refused() -> None:
    # V2's failure condition, stated as a refusal: ground truth missing for a question the harness
    # would score anyway. It cannot be scored — it would count as a miss against every pipeline.
    # Arrange
    entry = _self_test_question(quote=[])

    # Act / Assert
    with pytest.raises(ValueError, match="no supporting quote"):
        Question.model_validate(entry)


def test_a_field_the_reader_does_not_declare_is_refused() -> None:
    # `tier` used to be written on a question and disagreed with the manifest for 24 of the 136 —
    # a second copy of a fact the corpus owns. `extra="forbid"` is what stops it, or anything like
    # it, coming back unnoticed rather than being read by nothing.
    # Arrange
    entry = _self_test_question(tier="fetch")

    # Act / Assert
    with pytest.raises(ValueError, match="tier"):
        Question.model_validate(entry)


# --- Helpers ------------------------------------------------------------------------------------


async def _extracted(
    documents: Sequence[Document], registry: Registry
) -> tuple[dict[str, str], dict[str, PdfPages]]:
    """Every document handed in, as the text a pipeline would see it as.

    Cached for the module, because reading 25 papers takes about five seconds and three tests need
    the same answer. The cache is keyed by nothing — one corpus, one manifest, one backend per
    format — and a test that wanted a different reading would build it rather than share this.
    """
    if not _CACHE:
        for document in documents:
            _CACHE[document.id] = await _extract_one(document, registry)
    return (
        {identifier: node.content for identifier, node in _CACHE.items()},
        {
            identifier: pages
            for identifier, node in _CACHE.items()
            if (pages := node.ext_as(PdfPages)) is not None
        },
    )


async def _extract_one(document: Document, registry: Registry) -> Node:
    """The root node one corpus document extracts to, through the backend named for its format.

    The `isinstance` is against the runtime-checkable `Extractor` Protocol, and it is doing work
    rather than satisfying a type checker: the registry hands back a factory for *some* plugin,
    and a name in `VERIFYING_BACKEND` that turned out to be registered under a different contract
    would otherwise fail somewhere inside `run` with a message about arity.
    """
    name = VERIFYING_BACKEND[document.path.suffix]
    extractor = registry.lookup(Extractor, name)()
    if not isinstance(extractor, Extractor):
        message = f"{name!r} is registered but does not satisfy the Extractor contract"
        raise AssertionError(message)
    source = SourceDoc(
        source_id=SourceId(document.id),
        uri=document.path.resolve().as_uri(),
        content=document.path.read_bytes(),
    )

    outcome = await extractor.run([source], _CONTEXT)

    if not isinstance(outcome, Produced):
        message = f"{document.id}: {name} produced no text — {outcome}"
        raise AssertionError(message)
    nodes = list(outcome.value)
    if len(nodes) != 1:
        message = f"{document.id}: {name} produced {len(nodes)} nodes for one document"
        raise AssertionError(message)
    return nodes[0]


def _report(coverage: QuoteCoverage, check: str) -> None:
    """Say, in the run's own output, how much ground truth a passing check actually read.

    Called after the assertions and only for a partial corpus: a failure already speaks for itself,
    and a run holding the whole manifest has nothing to qualify. The case this exists for is the
    ordinary one — the operator tier is placed by hand, so anyone who is not the author verifies
    the fetch tier's quotes and skips the rest, and two green tests said nothing about which.

    A warning rather than a failure, because those six papers cannot be fetched at any price and a
    checkout without them is legitimate. What is not legitimate is that run reading as though the
    whole set had been checked.
    """
    if coverage.whole:
        return
    warnings.warn(f"{check}: {coverage.describe()}", PartialCorpus, stacklevel=2)


def _page_at(pages: Mapping[str, PdfPages]) -> Callable[[str, int], int]:
    """`page_at` over the whole corpus, answering `0` for a document that has no pages.

    The rule itself is `weft_pdf.PdfPages.page_at` and is not restated — this only decides which
    document's boundaries to ask, and what to answer for a Wikipedia article, which is one stream
    of text with no page to name.
    """

    def page_at(document: str, offset: int) -> int:
        found = pages.get(document)
        return found.page_at(offset) if found is not None else 0

    return page_at


def _question_quoting(span: str, *, page: int, document: str = "self-test-doc") -> Question:
    """A question whose whole ground truth is one span said to be on one page of one document.

    Built for the self-tests below the corpus checks, and deliberately not drawn from the tracked
    set: what they assert is what the comparison does with a span that moved, which must not depend
    on which papers happen to be on this machine.
    """
    return Question(
        id="self-test",
        text="Does the comparison notice what moved?",
        language="en",
        kind=Kind.DEFINITIONAL,
        difficulty=Difficulty.EASY,
        relevant_documents=(document,),
        reference_answer="It does.",
        notes="Written for this test; the text handed to the check is its whole corpus.",
        quote=(Quote(document=document, page=page, text=span),),
    )


def _page_always(page: int) -> Callable[[str, int], int]:
    """A `page_at` that puts every offset on one page — a document of a single page."""

    def page_at(_document: str, _offset: int) -> int:
        return page

    return page_at


def _page_after(boundary: int, before: int, after: int) -> Callable[[str, int], int]:
    """A `page_at` with one page break in it, at `boundary`.

    The smallest thing that can tell "considers every occurrence" apart from "takes the first
    one": a span before the break and the same span after it answer different pages.
    """

    def page_at(_document: str, offset: int) -> int:
        return before if offset < boundary else after

    return page_at


def _self_test_question(**overrides: object) -> dict[str, object]:
    """A valid question as TOML would hand it over, with `overrides` applied.

    Built as a `dict` rather than a `Question` on purpose: every refusal under test is a rule
    about what may be *read*, and constructing the model would mean the reader had already been
    asked and answered.
    """
    entry: dict[str, object] = {
        "id": "self-test",
        "text": "What does the reader refuse?",
        "language": "en",
        "kind": "definitional",
        "difficulty": "easy",
        "relevant_documents": ["self-test-doc"],
        "reference_answer": "Whatever this test overrides.",
        "notes": "Written for this test.",
        "quote": [{"document": "self-test-doc", "page": 0, "text": "a span"}],
    }
    return entry | overrides


# --- The extraction step is pinned too — ledger task 6.27 ---------------------------------------


def _recorded_extraction_pins() -> dict[str, dict[str, str]]:
    """`{backend: {"library": ..., "version": ...}}` off the corpus manifest."""
    with MANIFEST.open("rb") as handle:
        document: dict[str, object] = tomllib.load(handle)
    table = document.get("extraction", {})
    if not isinstance(table, dict):
        return {}
    pins: dict[str, dict[str, str]] = {}
    for backend, fields in cast("dict[str, object]", table).items():
        if isinstance(fields, dict):
            pins[str(backend)] = {
                str(key): str(value) for key, value in cast("dict[str, object]", fields).items()
            }
    return pins


def test_the_extraction_step_the_quotes_were_taken_from_is_pinned() -> None:
    """The manifest's own argument, one step further — ledger task **6.27**.

    `corpus/manifest.toml` pins what is fetched *and* what renders it, and says why: "Pinning only
    the second is how these nine entries were once pinned to bytes made by hand: every digest
    verified locally and not one of them could be reproduced by anybody else." A quote is a span of
    **extracted text**, which is one step past the document bytes — so pinning only the bytes
    leaves the text the judgements are written against unpinned, and the same sentence applies
    unchanged.

    It is not hypothetical. `weft-pdf` declares `pypdf>=6.16` with no ceiling; `uv.lock` resolves
    `6.16.1`; a fresh resolve takes `6.16.2`; and under `6.16.2` five quotes stop being literal
    spans of the documents they name. Measured at task 6.7, when the suite was first run from
    freshly-built sdists outside the lock.
    """
    # Arrange
    recorded = _recorded_extraction_pins()
    verifying = sorted(set(VERIFYING_BACKEND.values()))

    # Act
    unpinned = [
        backend
        for backend in verifying
        if backend not in recorded and backend not in _BACKENDS_WITH_NO_LIBRARY
    ]

    # Assert
    assert recorded, (
        f"{MANIFEST} records no [extraction] pins at all. Every quote in the question set is a "
        f"span of text some extractor produced, and an unpinned extractor makes those spans "
        f"unreproducible for anyone who does not share this repository's lockfile."
    )
    assert not unpinned, (
        f"{unpinned} verify quotes and are not pinned in {MANIFEST}'s [extraction] table."
    )


def test_the_installed_extraction_library_is_the_one_the_quotes_were_taken_from() -> None:
    """A mismatch is said out loud, first, rather than arriving as unexplained quote failures.

    Five quote mismatches with no named cause is what a `pypdf` patch bump actually looks like
    from inside the gate. The point of this check is not that it forbids the upgrade — it is that
    it names it, so the answer ("re-take the quotes from the new backend's output", which this
    module's own docstring already prescribes for a backend swap) is reachable rather than
    guessed at.
    """
    # Arrange
    recorded = _recorded_extraction_pins()

    # Act
    drifted: list[str] = []
    for backend, pin in sorted(recorded.items()):
        installed = metadata.version(pin["library"])
        if installed != pin["version"]:
            drifted.append(
                f"{backend}: quotes were taken with {pin['library']} {pin['version']}, "
                f"{installed} is installed"
            )

    # Assert
    assert not drifted, (
        "the extraction backend that produced this question set's quotes is not the one "
        "installed:\n  " + "\n  ".join(drifted) + "\n\n"
        "A quote is a span of extracted text, so a different extractor is a different text. "
        "Either install the pinned version, or re-take every affected quote from the new "
        "backend's output and update the pin in the same commit — this module's own docstring "
        "already requires exactly that for a backend swap, and a library bump is the same event "
        "arriving through a dependency instead of through a configuration edit."
    )


def test_the_extraction_pin_check_can_fail() -> None:
    """Planted, because the real comparison agrees whenever the lockfile is respected — which is
    every run inside `ci-checks`, and therefore every run that has ever been seen.
    """
    # Arrange
    pinned = {"pdf-text": {"library": "pypdf", "version": "0.0.0-never-released"}}

    # Act
    drifted = [
        backend
        for backend, pin in pinned.items()
        if metadata.version(pin["library"]) != pin["version"]
    ]

    # Assert
    assert drifted == ["pdf-text"]
