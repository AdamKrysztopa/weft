"""First-party text-cleaning pack.

Publishes the `Cleaner` contract, in `contract.py`, and four plugins for it —
`hyphenation.py`, `table_linearizer.py`, `dictionary_spacing.py`,
`whitespace.py` — task **1.7**: *the cleaning chain's learned order survives
the lift as a machine-checked constraint, not as prose*
(`docs/04-reference-inventory.md` category B; `docs/01-high-level-plan.md` →
Phase 1 **Lift**). Registered through the public entry point, with no
shortcut a third party lacks — fitness function 2.

Registration order here is irrelevant — `Registry.add_many` writes all four
in one batch, and it is `weft_kernel.resolution.resolve` that checks a
pipeline's *stage* order against `intact`/`destroys` once a document names
these plugins, never this function.
"""

from pydantic import BaseModel, ConfigDict

from weft_clean.contract import CLEANER_CONTRACT_VERSION, Cleaner
from weft_clean.dictionary_spacing import PolishFusedWordFixer, PolishFusedWordFixerConfig
from weft_clean.hyphenation import HyphenationRepair, HyphenationRepairConfig
from weft_clean.language import Language
from weft_clean.property import Newlines, WhitespaceGaps
from weft_clean.table_linearizer import TableLinearizer, TableLinearizerConfig
from weft_clean.whitespace import WhitespaceNormalizer, WhitespaceNormalizerConfig
from weft_kernel.discovery import PackRegistrar


class Settings(BaseModel):
    """`weft-clean` takes no pack settings — an empty model is still the required shape."""

    model_config = ConfigDict(frozen=True, extra="forbid")


def register(registrar: PackRegistrar, settings: Settings) -> None:
    """Register all four `Cleaner` plugins this pack ships."""
    del settings
    registrar.add(Cleaner, "hyphenation", HyphenationRepair)
    registrar.add(Cleaner, "table-linearize", TableLinearizer)
    registrar.add(Cleaner, "polish-dictionary-spacing", PolishFusedWordFixer)
    registrar.add(Cleaner, "whitespace", WhitespaceNormalizer)


__all__ = [
    "CLEANER_CONTRACT_VERSION",
    "Cleaner",
    "HyphenationRepair",
    "HyphenationRepairConfig",
    "Language",
    "Newlines",
    "PolishFusedWordFixer",
    "PolishFusedWordFixerConfig",
    "Settings",
    "TableLinearizer",
    "TableLinearizerConfig",
    "WhitespaceGaps",
    "WhitespaceNormalizer",
    "WhitespaceNormalizerConfig",
    "register",
]
