"""The machine-checked constraint tasks 1.7 and 2.35 exist to prove.

Mirrors nothing in `packages/weft-rag/src/`; it exercises the whole pack
against `weft_kernel.resolution.resolve` the way a real pipeline document
would. `docs/02-extension-model.md` §3 → *Ordering constraints* observes
that a code comment warning readers not to change a stage order cannot
enforce it — nothing stops a later edit from reordering the stages anyway.
Task 1.2 built the mechanism generically (`test_resolution.py`'s own
`_WordBoundaries` worked example already uses "hyphenation repair" and
"chunking" as its stand-in names); this file is where the *real* pack's
stages stand in for themselves instead — an ordering constraint that would
otherwise live only in a comment now fails a real pipeline's resolution at
load, naming the two real stage ids and the real property, rather than
silently producing a `ResolvedPipeline` whose stage list happens to be
wrong.

Every stage a real cleaning `weft.yaml` would name is exercised in the
load-bearing tests: `HyphenationRepair` needing `Newlines` intact,
`TableLinearizer` needing `WhitespaceGaps` intact, both destroyed in one
stroke by `WhitespaceNormalizer` — see `weft_clean.property`'s module
docstring for why one stage destroys both facts. Task 2.35 adds the mirror
case: `UnicodeNormalizer` needing `Verbatim` intact, destroyed by every one
of the other five stages, which is what forces it to position 1 — the same
mechanism pointed the other way, proven here against
`UnicodeNormalizer`/`HyphenationRepair` the same way the whitespace-first
case is proven against `WhitespaceNormalizer`/`HyphenationRepair`. A final
test resolves all six plugins in a legal order together, so the constraint
is proven against the whole chain this pack ships, not only a slice of it.
"""

from weft_clean.artifact_remover import ArtifactRemover
from weft_clean.contract import Cleaner
from weft_clean.dictionary_spacing import PolishFusedWordFixer
from weft_clean.hyphenation import HyphenationRepair
from weft_clean.table_linearizer import TableLinearizer
from weft_clean.unicode_normalizer import UnicodeNormalizer
from weft_clean.whitespace import WhitespaceNormalizer
from weft_kernel import resolution
from weft_kernel.pipeline import Pipeline, StageDeclaration
from weft_kernel.registry import Registry


def _registry() -> Registry:
    registry = Registry()
    registry.add(Cleaner, "unicode-normalize", UnicodeNormalizer, distribution="weft-clean")
    registry.add(Cleaner, "artifact-remove", ArtifactRemover, distribution="weft-clean")
    registry.add(Cleaner, "hyphenation", HyphenationRepair, distribution="weft-clean")
    registry.add(Cleaner, "table-linearize", TableLinearizer, distribution="weft-clean")
    registry.add(
        Cleaner, "polish-dictionary-spacing", PolishFusedWordFixer, distribution="weft-clean"
    )
    registry.add(Cleaner, "whitespace", WhitespaceNormalizer, distribution="weft-clean")
    return registry


def test_whitespace_before_hyphenation_fails_resolution_naming_both_stages() -> None:
    # Arrange — the exact mistake an order-warning comment cannot prevent: a stage inserted
    # between hyphenation repair and the destructive step it depends on running after it.
    pipeline = Pipeline(
        name="cleaning",
        stages=(
            StageDeclaration(id="whitespace", use="whitespace"),
            StageDeclaration(id="hyphenation", use="hyphenation"),
        ),
    )
    contracts = {"whitespace": Cleaner, "hyphenation": Cleaner}

    # Act / Assert
    try:
        resolution.resolve(pipeline, registry=_registry(), contracts=contracts)
    except resolution.IntactViolationError as excinfo:
        message = str(excinfo)
        assert "hyphenation" in message
        assert "whitespace" in message
        assert "Newlines" in message
    else:
        raise AssertionError(
            "resolving a pipeline that runs WhitespaceNormalizer before HyphenationRepair "
            "must raise IntactViolationError — changing this order breaks functionality"
        )


def test_whitespace_before_table_linearize_fails_resolution_naming_both_stages() -> None:
    # Arrange — the same shape as the test above, the other property.
    pipeline = Pipeline(
        name="cleaning",
        stages=(
            StageDeclaration(id="whitespace", use="whitespace"),
            StageDeclaration(id="table", use="table-linearize"),
        ),
    )
    contracts = {"whitespace": Cleaner, "table": Cleaner}

    # Act / Assert
    try:
        resolution.resolve(pipeline, registry=_registry(), contracts=contracts)
    except resolution.IntactViolationError as excinfo:
        message = str(excinfo)
        assert "table" in message
        assert "whitespace" in message
        assert "WhitespaceGaps" in message
    else:
        raise AssertionError(
            "resolving a pipeline that runs WhitespaceNormalizer before TableLinearizer "
            "must raise IntactViolationError"
        )


def test_hyphenation_before_unicode_normalize_fails_resolution_naming_both_stages() -> None:
    # Arrange — task 2.35's own worked example: a stage placing `UnicodeNormalizer` after
    # another cleaner fails to resolve, naming both stages and the property that forces
    # position 1 — the mirror of the two tests above, pointed the other direction.
    pipeline = Pipeline(
        name="cleaning",
        stages=(
            StageDeclaration(id="hyphenation", use="hyphenation"),
            StageDeclaration(id="unicode", use="unicode-normalize"),
        ),
    )
    contracts = {"hyphenation": Cleaner, "unicode": Cleaner}

    # Act / Assert
    try:
        resolution.resolve(pipeline, registry=_registry(), contracts=contracts)
    except resolution.IntactViolationError as excinfo:
        message = str(excinfo)
        assert "unicode" in message
        assert "hyphenation" in message
        assert "Verbatim" in message
    else:
        raise AssertionError(
            "resolving a pipeline that runs HyphenationRepair before UnicodeNormalizer "
            "must raise IntactViolationError — mojibake repair needs the character "
            "sequence extraction produced still contiguous, which an earlier repair "
            "stage can no longer guarantee"
        )


def test_the_whole_six_stage_chain_resolves_in_a_legal_order() -> None:
    # Arrange — a legal order: unicode normalisation and artifact removal before the two
    # structure-reading repairs, both
    # before the destructive whitespace pass; the Polish fixer, needing nothing intact,
    # is legal anywhere after `UnicodeNormalizer`, including last.
    pipeline = Pipeline(
        name="cleaning",
        stages=(
            StageDeclaration(id="unicode", use="unicode-normalize"),
            StageDeclaration(id="artifacts", use="artifact-remove"),
            StageDeclaration(id="hyphenation", use="hyphenation"),
            StageDeclaration(id="table", use="table-linearize"),
            StageDeclaration(id="whitespace", use="whitespace"),
            StageDeclaration(id="polish", use="polish-dictionary-spacing"),
        ),
    )
    contracts = {
        "unicode": Cleaner,
        "artifacts": Cleaner,
        "hyphenation": Cleaner,
        "table": Cleaner,
        "whitespace": Cleaner,
        "polish": Cleaner,
    }

    # Act
    resolved = resolution.resolve(pipeline, registry=_registry(), contracts=contracts)

    # Assert
    assert [stage.id for stage in resolved.stages] == [
        "unicode",
        "artifacts",
        "hyphenation",
        "table",
        "whitespace",
        "polish",
    ]
