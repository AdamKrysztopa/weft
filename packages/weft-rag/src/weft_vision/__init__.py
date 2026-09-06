"""First-party vision pack — it publishes a contract and registers nothing.

`Describer` lives in `contract.py`, per the canonical-file convention
`docs/07-extension-cost.md` §1 sets for a brand new contract. The one implementation this project
ships is `openai-vision`, in `weft-openai`, because that is the pack that already holds the
provider's client — a second distribution for one plugin would need `weft-openai` as a dependency
to reach it, the inverted-dependency shape this tree refuses elsewhere.

**`register()` registers nothing, and the entry point still has to exist.** `weft_chunk` publishes
`Chunker` and also implements one; this pack publishes and does not. What the entry point buys is
the *import*: `weft_kernel.discovery._read_service_roles` reads `SERVICE_ROLES` off the module a
pack's entry point names, at import time, and a module nothing imports declares nothing. Without
the entry point, `[services] describe` would not be a key an operator could set even though the
contract exists.
"""

from pydantic import BaseModel, ConfigDict

from weft_kernel.discovery import PackRegistrar
from weft_vision.contract import DESCRIBE_ROLE, DESCRIBER_CONTRACT_VERSION, Describer


class Settings(BaseModel):
    """`weft-vision` takes no pack settings — an empty model is still the required shape."""

    model_config = ConfigDict(frozen=True, extra="forbid")


def register(registrar: PackRegistrar, settings: Settings) -> None:
    """Register nothing. See the module docstring for why this function exists at all."""
    del registrar, settings


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
    "SERVICE_ROLES",
    "Settings",
    "register",
]
