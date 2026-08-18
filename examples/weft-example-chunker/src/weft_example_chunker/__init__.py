"""A stranger's chunking pack — the independence proof, as an artifact.

`docs/06-phase-0-build.md` step 10, in the `weft` repository this example is
built to prove a claim about: a pack that lives *outside* that repository's
workspace, in its own directory with its own `pyproject.toml`, installed the
same way any third-party pack would be, registering one plugin through the
same `weft.packs` entry point every first-party pack uses — no shortcut, no
private import path.

`weft`'s `tests/architecture/test_ff9_extension_from_outside.py` installs
this distribution into a throwaway environment built from wheels, with the
`weft` repository itself nowhere on `sys.path`, and runs a pipeline that
names `"example-chunker"` for `weft_chunk.contract.Chunker` — proving the
plugin resolves and runs. Uninstalling this distribution and running the
same pipeline again is the other half: resolution fails, naming the plugin
weft's `weft_kernel.registry.Registry` never saw.
"""

from pydantic import BaseModel, ConfigDict

from weft_chunk.contract import Chunker
from weft_example_chunker.word_chunker import WordChunker
from weft_kernel.discovery import PackRegistrar


class Settings(BaseModel):
    """This pack takes no settings — an empty model is still the required shape."""

    model_config = ConfigDict(frozen=True, extra="forbid")


def register(registrar: PackRegistrar, settings: Settings) -> None:
    """Register `WordChunker` as `"example-chunker"` for `Chunker` — the only plugin here."""
    del settings
    registrar.add(Chunker, "example-chunker", WordChunker)


__all__ = ["Settings", "WordChunker", "register"]
