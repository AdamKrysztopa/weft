"""Fitness function 26 — a catalogue row claims no configuration its plugin has not got, and
no proof its cited file does not make. `01` -> *Fitness functions* item 26; ledger task **10.1**.

`docs/10-technique-catalogue.md` is where this project states, for every technique it ships,
*what the code actually does* against *what the literature calls it*. Two kinds of claim in it
are checkable and were both found untrue on the same plugin within one day of each other:

**The configuration annotation.** The `raptor` row carried *(mode: `collapsed` \\| `traversal`)*
in its name column from task 2.32 until 2026-09-06 — a `mode:` field `RaptorConfig` has never
had (`raptor.py`, seven fields, none of them it), advertising two values nothing could be
configured with. A correction block four lines above the row had withdrawn the claim, and the
row went on making it, because a correction that does not edit what it corrects leaves both
readings standing (`docs/internal/lessons.md` `L9.30`). An annotation naming a field is a promise an
operator can act on: they will write it into a `with:` block.

**The proof citation.** The same row's block said cascade delete was *"proven against a real
corpus, real embeddings and a real store in `tests/integration/test_raptor_pipeline.py`, not
merely asserted of the type"*. That file never deleted anything — `grep -c delete` over it
returned `0` — so the strongest sentence in the section rested on a file that could not support
it (`L9.38`). Task 10.1 wrote the proof and this clause is what keeps the citation honest.

**A proof claim must say what to grep for, and that is the design decision here.** Fitness
function 17 already proves a cited path *resolves*; its own docstring is explicit that it can
never prove the cited file says what the citing sentence claims, because that is a judgement no
walk can make. This clause does not try to make it either. It requires the *claim* to name a
literal string the cited file contains — `` proven in `<path>` (`<needle>`) `` — which turns a
sentence into something mechanically falsifiable at the cost of one parenthesis. That is prose
becoming a spec deliberately rather than by accident (`L6.3`): the author chooses the needle,
and choosing one they cannot find is the moment the claim gets checked. The needle for the
withdrawn claim above would have been `delete_source`, and it was not there.

**Both waivers are pinned empty**, and both populations carry a non-vacuity floor: a clause
whose subject is empty passes by having nothing to look at, which is indistinguishable from
passing by being satisfied. `test_the_check_can_actually_fail` plants one of each against the
real machinery.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

import pytest
from pydantic import BaseModel, ValidationError

from tests.discovery import discover_for_tests
from weft_kernel.registry import Registry, unwrap_factory

from .conftest import REPO_ROOT, tracked_files

CATALOGUE: Final[Path] = REPO_ROOT / "docs" / "10-technique-catalogue.md"

#: A table row's first cell — everything between the leading `|` and the next unescaped `|`.
#: Rows are the only place a *plugin* is named in this document; the prose around them names
#: sections and papers, and reading those as plugin names is how a sweep starts reporting
#: rows that do not exist.
_ROW: Final[re.Pattern[str]] = re.compile(r"^\|(?P<first>(?:[^|\\]|\\.)*)\|", re.MULTILINE)

#: The plugin names a first cell holds — one or more, since two rows name a pair.
_NAME: Final[re.Pattern[str]] = re.compile(r"`(?P<name>[a-z][a-z0-9-]*)`")

#: `*(method: `sides` \| `forward` \| `reverse`)*` — a configuration annotation. The field is
#: the word before the colon; the values are every backticked token after it.
_ANNOTATION: Final[re.Pattern[str]] = re.compile(
    r"\*\((?P<field>[a-z_][a-z0-9_]*):(?P<values>(?:\s*`[^`]+`\s*(?:\\\|)?)+)\)\*"
)

#: `proven in `<path>` (`<needle>`)` — the checkable form this clause requires. `proven`/`proves`
#: appearing without it is itself a failure: see `test_every_proof_claim_says_what_to_grep_for`.
_PROOF: Final[re.Pattern[str]] = re.compile(
    r"prove[nsd]\s+in\s+`(?P<path>[^`]+)`\s*\(`(?P<needle>[^`]+)`\)"
)

#: Any use of the word at all, so a claim written in prose instead of the checkable form is
#: refused rather than skipped. Deliberately generous: `proven`, `proves`, `proved`.
_PROOF_WORD: Final[re.Pattern[str]] = re.compile(r"\bprove[nsd]\b")

#: A double-quoted span, across lines. **Quotations are excluded from the prose clause, and that
#: is a rule rather than a convenience.** This document's corrections work by quoting the sentence
#: they withdraw — `10` §1.2 carries *"proven against a real corpus, real embeddings and a real
#: store in ..."* inside quotation marks precisely in order to say it was untrue — and a check
#: that refused that would be refusing the withdrawal rather than the claim. What is checked is
#: this document's **own** prose; a sentence in quotation marks is somebody else's, including
#: this document's own earlier self. Measured before it was adopted: `10` holds 106 double
#: quotes, exactly 53 balanced spans, the longest 146 characters, and **every** occurrence of the
#: proof word today lies inside one — so the clause below is genuinely quiet on the live document
#: rather than quiet because the exclusion swallowed it.
_QUOTED: Final[re.Pattern[str]] = re.compile(r'"[^"]*"', re.DOTALL)

#: Proof claims permitted to name no needle. **Pinned empty.** A claim nobody can grep is the
#: one this whole check exists for, and the honest options are to write the needle or to stop
#: claiming the proof.
PROOF_CLAIMS_WITHOUT_A_NEEDLE: Final[frozenset[str]] = frozenset()

#: Configuration annotations permitted to name a field no plugin carries. **Pinned empty.**
#: An annotation an operator cannot write into a `with:` block is a lie about a config surface,
#: and the honest options are to add the field or to delete the annotation.
ANNOTATIONS_WITHOUT_A_FIELD: Final[frozenset[str]] = frozenset()


def _flattened() -> str:
    """The catalogue with its line wrapping and blockquote markers folded away.

    A claim is a sentence, and a sentence in this document wraps at 100 columns and carries a
    `> ` marker on every continuation line inside a correction block. Matching the checkable
    form against raw lines would make whether a claim is seen depend on where the wrap landed —
    which is a property of the editor, not of the claim, and is precisely the shape `L10.7` was
    paid for one file over: a pattern that silently matches nothing because the document is not
    written the way the pattern assumed.
    """
    return re.sub(r"\n\s*>?[ \t]*", " ", CATALOGUE.read_text("utf-8"))


def _first_cells() -> list[str]:
    """Every table row's first cell, header rows included — harmless, since a header names no
    plugin in backticks and carries no annotation.
    """
    return [match.group("first").strip() for match in _ROW.finditer(CATALOGUE.read_text("utf-8"))]


def _config_model(registry: Registry, name: str) -> type[BaseModel] | None:
    """The `config_model` of whatever `name` is registered as, across every contract.

    `None` when nothing registers the name — which is not this check's business: fitness
    function 5 owns *"a declared capability resolves"*, and a catalogue row may legitimately
    name a plugin an optional distribution provides and this environment has not installed.
    What this clause checks is only the rows whose plugin is actually here to be asked.
    """
    for contract in registry.contracts():
        if name in registry.names_for(contract):
            plugin = unwrap_factory(registry.entry(contract, name).factory)
            model = getattr(plugin, "config_model", None)
            return model if isinstance(model, type) and issubclass(model, BaseModel) else None
    return None


def _rejects(model: type[BaseModel], field: str, value: str) -> bool:
    """Does `model` refuse `value` for `field`?

    Asked by constructing the model and reading the error's own `loc`, rather than by comparing
    against a field's annotation: an annotation may be an `Enum`, a constrained `str`, a union
    or a pattern, and re-deriving what each of those accepts here would be a second, divergent
    copy of pydantic's own answer. Errors reported against *other* fields are not this field's
    business — every plugin config in this tree is constructible with nothing supplied, so one
    would mean the model changed, not that the annotation is wrong.
    """
    try:
        model(**{field: value})
    except ValidationError as exc:
        return any(error["loc"] == (field,) for error in exc.errors())
    return False


def test_every_configuration_annotation_names_a_field_its_plugin_carries() -> None:
    """Clause (a) — `L9.30`'s defect, made mechanical."""
    # Arrange
    registry = discover_for_tests()
    found: list[tuple[str, str]] = []
    wrong: list[str] = []

    # Act
    for cell in _first_cells():
        annotation = _ANNOTATION.search(cell)
        if annotation is None:
            continue
        field = annotation.group("field")
        values = _NAME.findall(annotation.group("values")) or [
            token for token in re.findall(r"`([^`]+)`", annotation.group("values"))
        ]
        for name in _NAME.findall(cell[: annotation.start()]):
            if f"{name}:{field}" in ANNOTATIONS_WITHOUT_A_FIELD:
                continue
            model = _config_model(registry, name)
            if model is None:
                continue
            found.append((name, field))
            if field not in model.model_fields:
                wrong.append(
                    f"'{name}' is annotated `{field}:` and {model.__name__} has no such field "
                    f"— it carries {sorted(model.model_fields)}"
                )
                continue
            wrong.extend(
                f"'{name}' advertises `{field}: {value}` and {model.__name__} refuses that value"
                for value in values
                if _rejects(model, field, value)
            )

    # Assert
    assert found, (
        "no configuration annotation in the catalogue named a plugin this environment has "
        "installed, so this clause looked at nothing. That is not a pass — see the module "
        "docstring on vacuity."
    )
    assert not wrong, (
        "a catalogue row advertises configuration its plugin has not got. An operator reads "
        "that column and writes it into a `with:` block:\n  " + "\n  ".join(wrong)
    )


def test_every_proof_claim_says_what_to_grep_for() -> None:
    """Clause (b), first half — a proof claim is written in the checkable form or not at all."""
    # Arrange / Act
    own_prose = _QUOTED.sub(" ", _flattened())
    checkable = [span for claim in _PROOF.finditer(own_prose) for span in [claim.span()]]
    unchecked = [
        own_prose[max(0, word.start() - 60) : word.start() + 120].strip()
        for word in _PROOF_WORD.finditer(own_prose)
        if not any(start <= word.start() < end for start, end in checkable)
        and own_prose[max(0, word.start() - 60) : word.start() + 120].strip()
        not in PROOF_CLAIMS_WITHOUT_A_NEEDLE
    ]

    # Assert
    assert not unchecked, (
        "the catalogue claims something is proven without saying what to grep for. Write it as "
        "`proven in `<path>` (`<needle>`)`, where the needle is a literal string the cited file "
        "contains — the strongest sentence in this document rested on a file that never deleted "
        "anything, and nothing could see it (`docs/internal/lessons.md` L9.38):\n  "
        + "\n  ".join(unchecked)
    )


def test_every_proof_claim_names_a_file_that_carries_its_needle() -> None:
    """Clause (b), second half — the needle is actually there."""
    # Arrange
    claims = list(_PROOF.finditer(_flattened()))
    broken: list[str] = []

    # Act
    for claim in claims:
        path, needle = claim.group("path"), claim.group("needle")
        if path not in tracked_files():
            broken.append(f"'{path}' is not tracked in this repository")
            continue
        if needle not in (REPO_ROOT / path).read_text("utf-8"):
            broken.append(f"'{path}' does not contain '{needle}'")

    # Assert
    assert claims, (
        "the catalogue makes no checkable proof claim at all, so this clause read nothing. "
        "See the module docstring on vacuity — task 10.1 wrote the first one."
    )
    assert not broken, "a proof claim names a file that cannot support it:\n  " + "\n  ".join(
        broken
    )


def test_the_check_can_actually_fail(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Both clauses, against a planted catalogue — `tests/architecture/test_ff0b_checks_are_real.py`
    accepts this spelling, and the two populations above are small enough that "green" and "looked
    at nothing" would otherwise be the same reading.
    """
    # Arrange
    planted = tmp_path / "10-technique-catalogue.md"
    planted.write_text(
        "| Weft name | What it does |\n"
        "|---|---|\n"
        "| **`repack`** *(mode: `collapsed` \\| `traversal`)* | a field it has not got |\n"
        "| **`repack`** *(method: `sideways`)* | a value it refuses |\n"
        "\n"
        "> Cascade delete is proven in `tests/integration/test_raptor_cascade_delete.py` "
        "(`no_such_symbol_exists_here`).\n"
        "> And this one is proven the old way, in prose, naming no needle at all.\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "tests.architecture.test_ff26_catalogue_claims_are_carried.CATALOGUE", planted
    )

    # Act / Assert
    with pytest.raises(AssertionError, match="has no such field"):
        test_every_configuration_annotation_names_a_field_its_plugin_carries()
    with pytest.raises(AssertionError, match="does not contain"):
        test_every_proof_claim_names_a_file_that_carries_its_needle()
    with pytest.raises(AssertionError, match="without saying what to grep for"):
        test_every_proof_claim_says_what_to_grep_for()
