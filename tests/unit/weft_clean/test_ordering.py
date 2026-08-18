"""The machine-checked constraint task 1.7 exists to prove.

Mirrors nothing in `packages/weft-clean/src/`; it exercises the whole pack
against `weft_kernel.resolution.resolve` the way a real pipeline document
would. `docs/02-extension-model.md` §3 → *Ordering constraints* quotes the
reference's own docstring — "IMPORTANT: Changing this order will break
functionality" — and observes that prose cannot enforce it. Task 1.2 built
the mechanism generically (`test_resolution.py`'s own `_WordBoundaries`
worked example already uses "hyphenation repair" and "chunking" as its
stand-in names); this file is where the *real* pack's stages stand in for
themselves instead — the ordering that used to live only in a comment in
`indexing/cleaning/pipeline.py:30-51` now fails a real pipeline's resolution
at load, naming the two real stage ids and the real property, rather than
silently producing a `ResolvedPipeline` whose stage list happens to be
wrong.

Every stage a real cleaning `weft.yaml` would name is exercised in the two
load-bearing tests: `HyphenationRepair` needing `Newlines` intact,
`TableLinearizer` needing `WhitespaceGaps` intact, both destroyed in one
stroke by `WhitespaceNormalizer` — see `weft_clean.property`'s module
docstring for why one stage destroys both facts. A third test resolves all
four plugins in a legal order together, so the constraint is proven against
the whole chain this pack ships, not only a two-stage slice of it.
"""

from weft_clean.contract import Cleaner
from weft_clean.dictionary_spacing import PolishFusedWordFixer
from weft_clean.hyphenation import HyphenationRepair
from weft_clean.table_linearizer import TableLinearizer
from weft_clean.whitespace import WhitespaceNormalizer
from weft_kernel import resolution
from weft_kernel.pipeline import Pipeline, StageDeclaration
from weft_kernel.registry import Registry


def _registry() -> Registry:
    registry = Registry()
    registry.add(Cleaner, "hyphenation", HyphenationRepair, distribution="weft-clean")
    registry.add(Cleaner, "table-linearize", TableLinearizer, distribution="weft-clean")
    registry.add(
        Cleaner, "polish-dictionary-spacing", PolishFusedWordFixer, distribution="weft-clean"
    )
    registry.add(Cleaner, "whitespace", WhitespaceNormalizer, distribution="weft-clean")
    return registry


def test_whitespace_before_hyphenation_fails_resolution_naming_both_stages() -> None:
    # Arrange — the exact mistake the reference's docstring warns against: a stage inserted
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
            "must raise IntactViolationError — the reference's own docstring: 'Changing this "
            "order will break functionality'"
        )


def test_whitespace_before_table_linearize_fails_resolution_naming_both_stages() -> None:
    # Arrange — the reference's second worked example, same shape, the other property.
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


def test_the_whole_chain_resolves_in_a_legal_order() -> None:
    # Arrange — hyphenation and table work before whitespace destroys what they need;
    # the Polish fixer, needing nothing intact, is legal anywhere, including last.
    pipeline = Pipeline(
        name="cleaning",
        stages=(
            StageDeclaration(id="hyphenation", use="hyphenation"),
            StageDeclaration(id="table", use="table-linearize"),
            StageDeclaration(id="whitespace", use="whitespace"),
            StageDeclaration(id="polish", use="polish-dictionary-spacing"),
        ),
    )
    contracts = {
        "hyphenation": Cleaner,
        "table": Cleaner,
        "whitespace": Cleaner,
        "polish": Cleaner,
    }

    # Act
    resolved = resolution.resolve(pipeline, registry=_registry(), contracts=contracts)

    # Assert
    assert [stage.id for stage in resolved.stages] == [
        "hyphenation",
        "table",
        "whitespace",
        "polish",
    ]
