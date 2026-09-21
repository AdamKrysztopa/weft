"""Where the learned-layout rung's weights live, and whether they are there — ledger `9.13`.

Two questions, both answered without touching the network: **which** folders this rung needs
(`REQUIRED_MODEL_FOLDERS`), and whether `artifacts_dir` already holds them (`missing_weights`).
`weft_docling.__init__.register` is the only caller — declaring a plugin unavailable is a
registration-time fact, and registration must never open a socket, because discovery imports
and registers every allowed pack on every command, `weft plugins doctor` included.

**The two folder names are literals, not read off docling.** Reading them off docling imports
torch and transformers at every registration (R29.5). Two tests in
`tests/unit/weft_docling/test_init.py` fail the moment docling renames either model.
"""

from pathlib import Path
from typing import Final

#: The on-disk folder names this rung needs under its artifacts directory — layout first,
#: tableformer second, because `weft_docling.pdf_layout_model.convert_pdf` loads them in that
#: order. Literals, per the module docstring.
REQUIRED_MODEL_FOLDERS: Final[tuple[str, ...]] = (
    "docling-project--docling-layout-heron",
    "docling-project--docling-models",
)


def artifacts_dir(artifacts_path: str | None) -> Path:
    """Where this rung's weights should live: `artifacts_path` verbatim, or docling's own cache.

    `None` means "wherever docling keeps them" — the only answer that stays true once an
    operator has already run docling's own downloader, rather than a second, competing default
    this pack would have to keep in sync with docling's.
    """
    if artifacts_path is not None:
        return Path(artifacts_path)
    from docling.datamodel.settings import settings

    return settings.cache_dir / "models"


def missing_weights(root: Path) -> tuple[str, ...]:
    """The entries of `REQUIRED_MODEL_FOLDERS` not present under `root`, in that order.

    Present means the folder exists *and is not empty* — an empty directory is what a
    half-completed download leaves behind, and reading it as success would tell an operator
    their weights are there when a conversion would still fail. Not-empty rather than
    holds-a-file deliberately: what a docling release puts inside is its business, and a check
    that named a filename would go stale the way a pasted repository id would. Pure filesystem:
    no network call, no docling downloader, so this is safe to run on every registration.
    """
    missing: list[str] = []
    for folder in REQUIRED_MODEL_FOLDERS:
        candidate = root / folder
        if not candidate.is_dir() or not any(candidate.iterdir()):
            missing.append(folder)
    return tuple(missing)
