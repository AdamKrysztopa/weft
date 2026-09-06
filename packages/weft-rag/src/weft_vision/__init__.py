"""First-party vision pack — it publishes a contract, and registers one `Enhancer`.

`Describer` lives in `contract.py`, per the canonical-file convention
`docs/07-extension-cost.md` §1 sets for a brand new contract. The one *service*
implementation this project ships against it is `openai-vision`, in `weft-openai`, because
that is the pack that already holds the provider's client — a second distribution for one
plugin would need `weft-openai` as a dependency to reach it, the inverted-dependency shape
this tree refuses elsewhere.

**`register()` used to register nothing, and the entry point still had to exist.**
`weft_chunk` publishes `Chunker` and also implements one; until ledger task `9.11`, this pack
published and did not. What the entry point buys, independent of that, is the *import*:
`weft_kernel.discovery._read_service_roles` reads `SERVICE_ROLES` off the module a pack's
entry point names, at import time, and a module nothing imports declares nothing. Without
the entry point, `[services] describe` would not be a key an operator could set even though
the contract exists.

**Task 9.11 is the first stage this pack ships**, `describe-figure` — the `Enhancer` that
reads a figure's pixels back through `BlobStore`, calls `Describer`, and augments the node's
caption with what it saw. See `describe_figure.py`'s own module docstring for the whole
design; `weft_enhance` publishes the contract this registers into, the same as any
third-party `Enhancer` pack would.
"""

from pydantic import BaseModel, ConfigDict

from weft_enhance.contract import Enhancer
from weft_kernel.discovery import PackRegistrar
from weft_vision.contract import DESCRIBE_ROLE, DESCRIBER_CONTRACT_VERSION, Describer
from weft_vision.describe_figure import FigureDescriber, FigureDescription


class Settings(BaseModel):
    """`weft-vision` takes no pack settings — an empty model is still the required shape."""

    model_config = ConfigDict(frozen=True, extra="forbid")


def register(registrar: PackRegistrar, settings: Settings) -> None:
    """Register `FigureDescriber` as `"describe-figure"` for `Enhancer`, and `FigureDescription`
    as this pack's own `ExtModel` — the same two-call shape `weft_enhance.__init__` uses for
    `KeyBertKeywordExtractor` and `Keywords`.
    """
    del settings
    registrar.add(Enhancer, "describe-figure", FigureDescriber)
    registrar.add_ext_model(FigureDescription)


#: Ledger task **9.0** — read by `weft_kernel.discovery._read_service_roles` at import time,
#: before settings are validated. Module-level rather than buffered through `register()` because
#: which `[services]` key a pack declares is a static fact about the pack, and an operator
#: configuring their way out of a problem needs the key to exist even on a machine where the pack
#: contributed nothing. `weft_store.__init__.SERVICE_ROLES` carries the case that settles it.
SERVICE_ROLES = (DESCRIBE_ROLE,)


__all__ = [
    "DESCRIBER_CONTRACT_VERSION",
    "DESCRIBE_ROLE",
    "Describer",
    "FigureDescriber",
    "FigureDescription",
    "SERVICE_ROLES",
    "Settings",
    "register",
]
