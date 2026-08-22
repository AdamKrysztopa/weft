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
from weft_example_ingest.enhancer import ExampleWordCountEnhancer, WordCount
from weft_example_ingest.expander import NAME as EXPANDER_NAME
from weft_example_ingest.expander import ExampleFirstSentenceExpander
from weft_example_ingest.extractor import ExampleExtractor
from weft_example_ingest.renderer import ExamplePlainRenderer
from weft_example_ingest.store import InMemoryNodeStore
from weft_extract.contract import Extractor, Renderer
from weft_index.contract import Expander
from weft_kernel.discovery import PackRegistrar
from weft_kernel.pipeline import StageDeclaration
from weft_store.contract import NodeStore

#: This pack's own local id for the stage it contributes into a slot — task 5.3a (S8).
#: Unqualified: `Contribution.stage.id` is a pack's local name, qualified by distribution
#: only once actually placed (`weft_kernel.resolution.Contribution`'s own docstring).
_ENRICH_STAGE_ID = "wordcount"

#: The slot name this pack offers into — `02` §3 → *Slots*' own worked example
#: (`weft-graph:entities`) targets a slot named `enrich`; this pack reuses that name
#: rather than inventing a second convention for the identical kind of position.
ENRICH_SLOT = "enrich"


class Settings(BaseModel):
    """This pack takes no settings — an empty model is still the required shape."""

    model_config = ConfigDict(frozen=True, extra="forbid")


def register(registrar: PackRegistrar, settings: Settings) -> None:
    """Register this pack's seven plugins — one per contract it implements — its own
    `WordCount` `ExtModel` (task 5.2g), and a slot contribution (task 5.3a, `S8`): the real
    proof that a stranger's own contributed stage reaches a resolved pipeline with no core
    edit, since this distribution is installed rather than linked (fitness function 9(a)).

    The contribution reuses the same `example-enhancer` plugin already registered under
    `Enhancer` — offering a plugin as both an ordinary stage *and* a slot contribution costs
    nothing extra to declare, and it is the identical class either way: what changes is only
    whether a pipeline document names it directly (`use: example-enhancer`) or opts a slot
    into receiving it (`slots: [{id: enrich, ...}]`).
    """
    del settings
    registrar.add(Extractor, "example-extractor", ExampleExtractor)
    registrar.add(Renderer, "example-renderer", ExamplePlainRenderer)
    registrar.add(Cleaner, "example-cleaner", ExampleBlankLineCollapser)
    registrar.add(Enhancer, "example-enhancer", ExampleWordCountEnhancer)
    registrar.add(Embedder, "example-embedder", ExampleChecksumEmbedder)
    registrar.add(Expander, EXPANDER_NAME, ExampleFirstSentenceExpander)
    registrar.add(NodeStore, "example-store", InMemoryNodeStore)
    registrar.add_ext_model(WordCount)
    registrar.add_contribution(
        ENRICH_SLOT, StageDeclaration(id=_ENRICH_STAGE_ID, use="example-enhancer")
    )


__all__ = ["ENRICH_SLOT", "Settings", "WordCount", "register"]
