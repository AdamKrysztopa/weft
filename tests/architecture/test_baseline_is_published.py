"""What reproduces the published number ships with the release — ledger task **6.35**.

`docs/09-release.md` §5.2: *"the baseline run is published with the release"*, and V6 requires it
to be a persisted run rather than terminal output. It is one — `eval/baselines/` holds it, with
`eval/questions/` beside it and `corpus/manifest.toml` pinning the documents.

**And task 6.13 found that none of the three was reachable.** The whole product was installed from
an index into a clean environment and everything needed to *reproduce* the number was still only in
this repository. The shipped CLI can do the work — `weft eval run` and `weft eval compare` are both
on the installed binary — so the gap was never capability. It was that "published with the release"
described a directory in a git checkout (`docs/lessons.md` **L6.34**).

**Three answers were available and this is the one `09` §5.2's own words pick.** *Inside a
distribution* would put one corpus's judgements into `weft-eval`, which publishes the metric
contracts and is installed by people with no interest in Weft's own corpus. *Fetched by a pinned
script* is already the answer for the corpus **bytes** (`scripts/fetch_corpus.py`), and cannot be
the answer for the pins themselves without circularity — the manifest is what the fetch reads.
*Attached to the release* is the literal reading of "published **with** the release", costs no
architectural change, and puts the three artefacts exactly where somebody holding a release looks.

**What this checks is that the release job carries them, not that they are correct.** Whether the
baseline reproduces is `eval/check_baseline.py`'s question and task 6.30's; whether every quote is
a literal span is `tests/docs/test_question_set.py`'s. This is the reachability half, and it is the
half that was silently false.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from .conftest import REPO_ROOT

RELEASE_WORKFLOW: Final[Path] = REPO_ROOT / ".github" / "workflows" / "release.yml"

#: The three artefacts a stranger needs to reproduce the published number, and why each is here.
#: Named rather than globbed, because the question *"what does a reproduction need"* is answered by
#: `eval/run_baseline.py`'s own reads and not by whatever happens to sit in a directory.
REPRODUCTION_ARTEFACTS: Final[tuple[tuple[str, str], ...]] = (
    ("eval/baselines", "the persisted baseline runs themselves — V6's own artefact"),
    ("eval/questions", "the question set with its relevance judgements and quotes — V2"),
    ("corpus/manifest.toml", "the pinned, checksummed document identities the run measured — V1"),
)


def _workflow_text() -> str:
    return RELEASE_WORKFLOW.read_text(encoding="utf-8")


def test_the_artefacts_a_reproduction_needs_exist() -> None:
    """The floor. A workflow that attached three paths which are not there would still pass a
    check that only read the workflow.
    """
    # Act
    missing = [path for path, _ in REPRODUCTION_ARTEFACTS if not (REPO_ROOT / path).exists()]

    # Assert
    assert not missing, f"{missing} do not exist, and the release job claims to attach them"
    assert list((REPO_ROOT / "eval" / "baselines").glob("*.json")), (
        "no persisted baseline run is present. V6 requires the baseline to exist as a run rather "
        "than as terminal output, and there is nothing to publish with the release."
    )


def test_the_release_job_attaches_them() -> None:
    """`09` §5.2's clause, made a fact about the job rather than a sentence about the plan."""
    # Arrange
    workflow = _workflow_text()

    # Act
    unattached = [f"{path} ({why})" for path, why in REPRODUCTION_ARTEFACTS if path not in workflow]

    # Assert
    assert RELEASE_WORKFLOW.is_file(), f"{RELEASE_WORKFLOW} does not exist"
    assert not unattached, (
        "the release job does not attach:\n  " + "\n  ".join(unattached) + "\n\n"
        "`09` §5.2 says the baseline run is published with the release. Task 6.13 installed the "
        "product from an index and found everything needed to reproduce the number still only in "
        "this repository — the shipped CLI can do the work, so the gap is reachability."
    )


def test_the_check_can_actually_fail() -> None:
    """Planted, because the real workflow names all three once this task lands.

    Through the real comparison rather than against a literal, so what is proved is that a
    workflow missing an artefact is reported — and that a workflow mentioning it in a comment
    still counts, which is a deliberate limit: this asks whether the path is *named*, not whether
    the upload is correct, and pretending otherwise would be a check claiming more than it does.
    """
    # Arrange
    partial = "jobs:\n  publish:\n    steps:\n      - run: gh release upload eval/baselines\n"

    # Act
    unattached = [path for path, _ in REPRODUCTION_ARTEFACTS if path not in partial]

    # Assert
    assert unattached == ["eval/questions", "corpus/manifest.toml"]
