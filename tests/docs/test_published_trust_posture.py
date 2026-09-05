"""The published trust posture is the one `02` §2 actually claims — ledger task **6.10**.

`docs/09-release.md` §3, closing: "**One thing the release must not soften.** `02` §2 → *The trust
model* states the posture plainly: a pack runs with your full privileges, and installing is
trusting; signature verification, sandboxing and per-pack privilege separation are out of reach
without a process boundary. **That paragraph must appear in the published README of the release,
not only in the plan.** A design that refused to simulate a control it cannot enforce would be
undone by a package page that lets a reader assume one exists."

**The gap this closes is exactly the one that sentence predicts.** The repository's own
`README.md` has carried the posture since Phase 0. `packages/weft/README.md` — the `readme` the
release set declares, and therefore the page a reader sees on an index — carried none of it: no
privileges, no trusting, no list of what is out of reach. Everything a stranger would read before
installing said nothing about the one thing `02` §2 spent a section refusing to simulate.

**Two clauses.**

- **(a) The published page states the posture**, in the two claims that carry it — a pack runs
  with your full privileges, and installing is trusting — plus the named absences, because "we
  have no sandbox" is the half a reader acts on and the half a marketing edit removes first.
- **(b) No published page implies isolation.** Swept for the words that would assert a control the
  design refused, with each hit required to sit in a **negated** sentence. `02` §2's own text says
  "sandboxing... out of reach", so a sweep that flagged the word alone would flag every honest
  disclaimer and be turned off within a week; a sweep that ignored the word entirely would miss
  the one sentence that matters.

**What "published" means here**, and why it is not every `.md` in the tree: the pages an index
renders. That is `packages/weft/README.md` (the release set's declared `readme`), the repository
`README.md` that GitHub renders beside it, and every distribution's own one-line `description`,
which is what a search result shows. `docs/` is the plan and argues about the posture at length;
sweeping it would flag the argument for containing the words it is about.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import Any, Final, cast

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
RELEASE_SET_PAGE: Final[Path] = REPO_ROOT / "packages" / "weft-rag" / "README.md"
REPOSITORY_PAGE: Final[Path] = REPO_ROOT / "README.md"

#: The two claims `02` §2 makes, as facts rather than as a quotation — a page that reworded them
#: still has to say them. Each entry is a set of alternatives; the page must contain one of each.
POSTURE_CLAIMS: Final[tuple[tuple[str, ...], ...]] = (
    ("full privileges", "your own privileges", "the same privileges"),
    ("installing is trusting", "installing one is trusting", "installing it is trusting"),
)

#: What `02` §2 says is out of reach, named on the page rather than left to inference: "signature
#: verification, sandboxing, per-pack privilege separation, and any defence against a pack that is
#: hostile once running."
NAMED_ABSENCES: Final[tuple[str, ...]] = ("signature", "sandbox", "privilege separation")

#: Words that would assert a control `02` §2 refused to simulate.
_ISOLATION_WORDS: Final[re.Pattern[str]] = re.compile(
    r"\b(?:sandbox\w*|isolat\w*|privilege separation|untrusted)\b", re.IGNORECASE
)

#: What makes a sentence containing one of those words a *disclaimer* rather than a claim.
_NEGATION: Final[re.Pattern[str]] = re.compile(
    r"\b(?:no|not|never|without|cannot|can't|refus\w*|out of reach|does not|do not|lacks?)\b",
    re.IGNORECASE,
)

#: Sentences that name an isolation word affirmatively and are **not** about pack execution —
#: pinned, and each is checked against what the sweep actually produces so a reworded page stops
#: being excused rather than silently continuing to excuse something else
#: (`docs/lessons.md` L6.29).
ISOLATION_SENTENCES_WAIVED: Final[frozenset[str]] = frozenset()


#: Fenced blocks are commands and file listings, not claims. Stripping them is not tidiness: a
#: fence collapses into one enormous "sentence", so a negation word anywhere inside it excuses
#: every isolation word in the whole block. `README.md`'s distribution listing contains
#: `kernel-isolated` and was being excused by the word "refused" from a different line entirely —
#: a false negative arrived at by accident, which is the direction this sweep must not fail in.
_FENCE: Final[re.Pattern[str]] = re.compile(r"^```.*?^```", re.MULTILINE | re.DOTALL)


def _sentences(text: str) -> list[str]:
    collapsed = re.sub(r"\s+", " ", _FENCE.sub(" ", text))
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", collapsed) if part.strip()]


def _distribution_descriptions() -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for manifest in sorted((REPO_ROOT / "packages").glob("*/pyproject.toml")):
        with manifest.open("rb") as handle:
            document: dict[str, Any] = tomllib.load(handle)
        project: object = document.get("project", {})
        if not isinstance(project, dict):
            continue
        table = cast("dict[str, object]", project)
        name, description = table.get("name"), table.get("description")
        if isinstance(name, str) and isinstance(description, str):
            found.append((name, description))
    return found


def published_pages() -> list[tuple[str, str]]:
    """`(label, text)` for every surface an index or a search result renders."""
    pages = [
        (
            str(RELEASE_SET_PAGE.relative_to(REPO_ROOT)),
            RELEASE_SET_PAGE.read_text(encoding="utf-8"),
        ),
        (str(REPOSITORY_PAGE.relative_to(REPO_ROOT)), REPOSITORY_PAGE.read_text(encoding="utf-8")),
    ]
    pages.extend(
        (f"{name} description", description) for name, description in _distribution_descriptions()
    )
    return pages


def isolation_claims(pages: list[tuple[str, str]]) -> list[str]:
    """Every sentence on a published page that names an isolation word without negating it."""
    return [
        f"{label}: {sentence}"
        for label, text in pages
        for sentence in _sentences(text)
        if _ISOLATION_WORDS.search(sentence) and not _NEGATION.search(sentence)
    ]


def test_the_published_pages_are_found() -> None:
    """The floor: a sweep over nothing reports no claims, which is a different answer."""
    # Act
    pages = published_pages()

    # Assert
    assert RELEASE_SET_PAGE.is_file(), (
        f"{RELEASE_SET_PAGE} does not exist, and `packages/weft/pyproject.toml` declares it as "
        f"the release set's `readme` — the page an index renders."
    )
    # Derived rather than a magic number: two pages plus one description per published
    # distribution. It read `> 10` while twenty distributions shipped, and six do now — a
    # constant calibrated against a distribution count is a check that has to be re-tuned
    # whenever packaging changes, which is exactly when it should be doing its job instead.
    descriptions = _distribution_descriptions()
    manifests = sorted((REPO_ROOT / "packages").glob("*/pyproject.toml"))
    assert len(descriptions) == len(manifests), (
        f"{len(descriptions)} of {len(manifests)} distributions under packages/ carry a "
        f"description; every published one owes an index a sentence"
    )
    assert len(pages) == len(descriptions) + 2, (
        f"only {len(pages)} published surfaces were found; the reader is wrong"
    )


def test_the_release_sets_published_page_states_the_posture() -> None:
    """Clause (a). `09` §3: "that paragraph must appear in the published README of the release,
    not only in the plan."
    """
    # Arrange
    page = RELEASE_SET_PAGE.read_text(encoding="utf-8").lower()

    # Act
    unsaid = [claims[0] for claims in POSTURE_CLAIMS if not any(c in page for c in claims)]
    unnamed = [absence for absence in NAMED_ABSENCES if absence not in page]

    # Assert
    assert not unsaid, (
        f"{RELEASE_SET_PAGE.name} does not state {unsaid}. `02` §2 states the posture instead of "
        f"simulating a control, and `09` §3 requires it on the published page: a design that "
        f"refused to simulate a control it cannot enforce is undone by a package page that lets "
        f"a reader assume one exists."
    )
    assert not unnamed, (
        f"{RELEASE_SET_PAGE.name} does not name {unnamed} among what is out of reach. `02` §2 "
        f"names all of them so nobody assumes otherwise, and the absence is the half a reader "
        f"acts on."
    )


def test_no_published_page_implies_isolation() -> None:
    """Clause (b): the words appear only where they are being denied."""
    # Act
    claims = [
        claim
        for claim in isolation_claims(published_pages())
        if not any(waived in claim for waived in ISOLATION_SENTENCES_WAIVED)
    ]

    # Assert
    assert not claims, (
        "a published page names an isolation control without denying it:\n  "
        + "\n  ".join(claims)
        + "\n\n`02` §2: signature verification, sandboxing and per-pack privilege separation are "
        "out of reach without a process boundary, and a control that looks like enforcement but "
        "is not is worse than an acknowledged gap, because people build policy on it."
    )


def test_the_check_can_actually_fail() -> None:
    """Both clauses, planted through the real readers — the real pages agree, so this is the only
    place either comparison is seen disagreeing (`docs/lessons.md` L5.19), and the sweep is shown
    telling a claim from a denial rather than merely finding the word.
    """
    # Arrange
    planted = [
        ("brochure", "Weft runs every pack in a secure sandbox, isolated from your data."),
        ("honest", "Packs are not sandboxed: a pack runs with your full privileges."),
    ]
    thin_page = "# weft\n\nA release set. It installs the product.\n".lower()

    # Act
    claims = isolation_claims(planted)
    unsaid = [c[0] for c in POSTURE_CLAIMS if not any(alt in thin_page for alt in c)]

    # Assert
    assert len(claims) == 1, f"the sweep did not separate the claim from the denial: {claims}"
    assert "secure sandbox" in claims[0]
    assert unsaid == ["full privileges", "installing is trusting"]
