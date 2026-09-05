"""`Language` — the source-language fact a language-specific cleaner narrows itself to.

Written to close a real gap a review of tasks 1.7/1.8 found: `PolishFusedWordFixer`
shipped with no `applies_to` at all, so `weft_kernel.runner`'s documented default —
"a stage that declares no `applies_to` applies to everything" — applied to it
literally, and its Polish exception-list logic ran on every node in a mixed-language
batch, corrupting English text with no error and no signal. `docs/02-extension-
model.md` §3 → *Language, and what a var is for* already specifies the fix: "A Polish
fixer applies to Polish nodes; English nodes flow past... A mixed corpus becomes
correct in one pass instead of uniformly wrong" — a property task 1.8's own ledger
line claims, but which `tests/unit/weft_kernel/test_language_and_vars.py` proved only
on a test-local stand-in (`_Language`), whose own docstring records that "`02` §3
assigns no pack this namespace yet." This module is what gives the one real
language-specific stage in the tree something real to narrow on.

`weft-clean` is the interim owner. `02` §3 names the extractor or an ordinary
`detect` stage as the eventual producer of this fact, and neither exists yet;
namespace ownership is not restricted to a producer pack — any pack may declare an
`ExtModel` that owns a namespace, per `02` → *The payload model*. Until a real
`detect` stage exists to populate it, no node carries this fact at all, which is
the safe-side default `02` §3 itself prescribes: absence routes every node past
`PolishFusedWordFixer` untouched, exactly as "unknown language flows past" already
promises. A future `detect` stage — first-party or not — needs only to `provide`
and populate this same model to make the fixer apply for real.
"""

from weft_kernel.payload import ExtModel


class Language(ExtModel):
    """The source language of a node's text — an ISO 639-1 code such as `"pl"` or `"en"`."""

    __namespace__ = "weft-clean"
    __schema_version__ = "1.0.0"

    code: str
