"""A stranger's ingest-side pack — the independence proof for the pipeline's first half.

`docs/07-extension-cost.md` §2 clause (c), the task 2.11 backfill: every contract Phase 0
through Phase 2 publishes on the ingest side needs an implementation that lives *outside*
this repository's workspace, installed the same way any third-party pack would be,
registering through the same `weft.packs` entry point every first-party pack uses — no
shortcut, no private import path. `examples/weft-example-chunker` is the precedent this
pack's file shape copies exactly; the difference is scope, not mechanism — one distribution
covering `Extractor`, `Renderer`, `Cleaner`, `Enhancer`, `Embedder`, `Expander` and the whole
`NodeStore` capability family (`NodeStore`, `VectorSearch`, `TextSearch`, `MetadataFilter`),
per `.phase2-design.md` §9's "one multi-contract pack per publishing half" — clause (c) is
set equality over *contracts*, which a multi-point pack satisfies, and a single install
registering across many extension points is exactly requirement 2, the thing Weft exists to
make cheap.

`tests/architecture/test_ff9c_every_contract_has_a_stranger.py` installs this distribution
(built as a real wheel) into a throwaway environment, with the `weft` repository nowhere on
`sys.path`, and asks the resulting registry which contracts it registered under and which
capability Protocols its registered classes satisfy.
"""

from pydantic import BaseModel, ConfigDict

from weft_clean.contract import Cleaner
from weft_embed.contract import Embedder
from weft_enhance.contract import Enhancer
from weft_example_ingest.cleaner import ExampleBlankLineCollapser
from weft_example_ingest.embedder import ExampleChecksumEmbedder
from weft_example_ingest.enhancer import ExampleWordCountEnhancer
from weft_example_ingest.expander import NAME as EXPANDER_NAME
from weft_example_ingest.expander import ExampleFirstSentenceExpander
from weft_example_ingest.extractor import ExampleExtractor
from weft_example_ingest.renderer import ExamplePlainRenderer
from weft_example_ingest.store import InMemoryNodeStore
from weft_extract.contract import Extractor, Renderer
from weft_index.contract import Expander
from weft_kernel.discovery import PackRegistrar
from weft_store.contract import NodeStore


class Settings(BaseModel):
    """This pack takes no settings — an empty model is still the required shape."""

    model_config = ConfigDict(frozen=True, extra="forbid")


def register(registrar: PackRegistrar, settings: Settings) -> None:
    """Register this pack's seven plugins — one per contract it implements."""
    del settings
    registrar.add(Extractor, "example-extractor", ExampleExtractor)
    registrar.add(Renderer, "example-renderer", ExamplePlainRenderer)
    registrar.add(Cleaner, "example-cleaner", ExampleBlankLineCollapser)
    registrar.add(Enhancer, "example-enhancer", ExampleWordCountEnhancer)
    registrar.add(Embedder, "example-embedder", ExampleChecksumEmbedder)
    registrar.add(Expander, EXPANDER_NAME, ExampleFirstSentenceExpander)
    registrar.add(NodeStore, "example-store", InMemoryNodeStore)


__all__ = ["Settings", "register"]
