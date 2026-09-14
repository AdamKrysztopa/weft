"""Prerequisite **V2** (`docs/09-release.md` §4.3) — the quote checks, over the corpus on disk.

The question set's schema and its reader — `Kind`, `Difficulty`, `Quote`, `Question`,
`load_questions`, `reproducible_questions` — moved into `weft_eval.question_set` at repair
**R22.4a**, importable from the installed wheel with no checkout. What stays here is what needs
the corpus's own extracted text: `quote_coverage`, `unmatched_quotes` and `misplaced_quotes`,
which verify that every literal span a question quotes is actually found — and found on the page
it claims — in the document it names. `tests/docs/test_question_set.py` drives them; this module
holds no `main()` because verifying a quote means reading the text an `Extractor` produces, every
contract method is `async def` (G6), and `asyncio.run` may appear exactly once in the whole tree
(fitness function 7(a), asserted by path).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

from weft_eval.question_set import Question

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[1]

#: Where the tracked question files live. Every `.toml` under it is part of the set; the file names
#: are authoring rounds, and nothing reads meaning off them.
QUESTIONS_DIR: Final[Path] = REPO_ROOT / "eval" / "questions"


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

    `page_at(document_id, offset)` is supplied rather than computed here, and that is still the
    point after G17 changed what supplies it. It used to defer to the parser pack's own
    `PdfPages.page_at`, so that `eval/` held no second copy of a rule a citation is resolved by.
    G17 retired that rule with the offset table it read — extraction now hands over one node per
    page and the page is a scalar on it — so what this callable answers from is whatever *joined*
    string its caller searched, which only the caller knows. A document with no pages answers `0`.

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
