"""Regenerates `manual/contract-reference.md` from the installed packs' own Protocols.

`docs/08-manuals.md` §3 clause (b): "manual/contract-reference.md is the generator's
output, checked in so it is readable without running anything, and regenerated in CI."
`tests/docs/test_generated_docs.py` is what "regenerated in CI" means in practice — it
calls the same functions this script does and fails the build if the checked-in file has
drifted. Run this script by hand after a contract's Protocol, docstring or version
changes, and commit the result:

    uv run python scripts/generate_contract_reference.py

Not wired into `poe ci-checks` itself — `tests/docs/test_generated_docs.py` already is
(swept up by the existing `test` step, per `08` §3's decision **D1**), and that test
*checks* the committed file rather than *writing* it, so a CI run never mutates the
working tree.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from weft_cli.contract_reference import (
    discover_for_reference,
    published_contracts,
    render_contract_reference,
)

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
REFERENCE: Final[Path] = REPO_ROOT / "manual" / "contract-reference.md"


def main() -> None:
    registry = discover_for_reference()
    contracts = published_contracts(registry)
    REFERENCE.write_text(render_contract_reference(contracts), encoding="utf-8")
    print(
        f"wrote {REFERENCE} ({len(contracts)} contract(s): "  # noqa: T201 - the point of a script
        f"{', '.join(sorted(c.contract.__qualname__ for c in contracts))})"
    )


if __name__ == "__main__":
    main()
