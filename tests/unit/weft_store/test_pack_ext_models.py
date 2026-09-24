"""A hand-built registry learns a pack's `ExtModel`s from the pack itself — repair **R32.5**.

`32.1` made `fixed-size` attach `ChunkPosition`, and two integration fixtures that wire stages by
hand failed with `no 'weft-chunk' is registered for ExtModel`: each listed the classes it expected
to read back, and the list was a copy of what `register()` declared on the day it was written.
That was the third time (`L5.21`, `L6.28`, `L26.3`). `tests.discovery.register_ext_models_of` runs
the named pack's own `register()` and hands what it declared to `register_from_reports`, so a pack
that gains a model reaches every fixture naming that pack with no edit to the fixture.

The ratchet below pins where a `PackReport` is still built with a literal tuple of models: only
files whose models are the test's own, where registration is the subject rather than the setup.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

import weft_chunk
import weft_index
from tests.discovery import register_ext_models_of
from weft_chunk.payload import ChunkPosition
from weft_index.payload import RaptorFacts, Representation
from weft_kernel.payload import ExtModel
from weft_store.rehydrate import ext_models

_TESTS: Final[Path] = Path(__file__).resolve().parents[2]

#: Files that build a `PackReport` around a model the test itself defines, with how many literal
#: model tuples each hands a report; any other file, or a higher count, is a fixture copying a
#: pack's declaration by hand.
_OWN_MODELS: Final[dict[str, int]] = {
    "unit/weft_store/test_rehydrate.py": 2,
    "unit/weft_cli/test_render.py": 1,
    "integration/test_operability.py": 1,
}

#: Spelled in two halves so this file is not one of its own matches.
_LITERAL: Final[re.Pattern[str]] = re.compile("ext_models" + r"=\(")


def _registered(model: type[ExtModel]) -> object:
    return ext_models.entry(ExtModel, model.__namespace__).factory


def test_every_model_a_pack_declares_reads_back_after_the_helper() -> None:
    # Act
    register_ext_models_of(weft_index, weft_chunk)

    # Assert
    assert _registered(Representation) is Representation
    assert _registered(RaptorFacts) is RaptorFacts
    assert _registered(ChunkPosition) is ChunkPosition


def test_the_helper_can_run_twice_in_one_process() -> None:
    """Every fixture calls it, and a real `discover()` may already have registered the classes.

    Every fixture calls it; a suite runs many fixtures, and a real `discover()` may already
    have registered the same classes — `register_ext_model` refuses that, `L6.28`.
    """
    # Act / Assert — no `DuplicateRegistrationError`
    register_ext_models_of(weft_chunk)
    register_ext_models_of(weft_chunk)


def literal_ext_model_sites(root: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    for path in sorted(root.rglob("*.py")):
        found = len(_LITERAL.findall(path.read_text(encoding="utf-8")))
        if found:
            counts[path.relative_to(root).as_posix()] = found
    return counts


def test_no_fixture_copies_a_packs_ext_models_by_hand() -> None:
    # Act
    sites = literal_ext_model_sites(_TESTS)

    # Assert
    assert sites == _OWN_MODELS


def test_the_check_can_actually_fail(tmp_path: Path) -> None:
    # Arrange
    planted = "PackReport(pack='weft-chunk', " + "ext_models" + "=(ChunkPosition,))\n"
    (tmp_path / "test_copy.py").write_text(planted, encoding="utf-8")

    # Act
    sites = literal_ext_model_sites(tmp_path)

    # Assert
    assert sites == {"test_copy.py": 1}
