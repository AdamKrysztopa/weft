"""First-party cross-encoder reranking pack — one plugin, `httpx` behind its own extra.

Ledger **41.2**. `weft-rag[cross-encoder]` is what installs `httpx`; a bare install still
carries this pack's code and reports `failed` at discovery, G19's accepted degradation for
every extra-backed pack (`weft_qdrant`'s own module docstring, `scripts/check_isolated_
installs.py`'s `EXTRA_BACKED_MODULES`).

**Registered through the same public `weft.packs` entry point a third party uses**, with
nothing extra for being first-party — fitness function 2.
"""

from functools import partial

from weft_cross_encoder.rerank import NAME, CrossEncoderRerank
from weft_cross_encoder.settings import CrossEncoderSettings
from weft_kernel.discovery import Disclosure, PackRegistrar
from weft_retrieve.contract import Reranker

#: What this pack touches — `02` §2 → *The trust model*, `weft_qdrant.__init__`'s own shape.
#:
#: The address is `[packs.cross-encoder] url`, defaulting to a local TEI server, so the
#: disclosure names the setting and its default rather than pretending to know where an
#: operator points it.
DISCLOSURE = Disclosure(
    network=("whatever [packs.cross-encoder] url names — http://localhost:8080 by default",),
    filesystem=(),
    subprocess=(),
    note=(
        "Sends the question and each passage's text to that server's /rerank endpoint to be "
        "scored, and reads its /info before doing so."
    ),
)


def register(registrar: PackRegistrar, settings: CrossEncoderSettings) -> None:
    """Register `CrossEncoderRerank` as `"cross-encoder-rerank"` for `Reranker`, and both rungs.

    `settings` is bound in through `functools.partial`, exactly as `weft_qdrant.register`
    binds its own deployment settings — `Runner.resolve`'s `entry.factory(spec.config)` call
    becomes `CrossEncoderRerank(settings, spec.config)`.
    """
    registrar.add(Reranker, NAME, partial(CrossEncoderRerank, settings))
    registrar.add_pipeline_resource("weft_cross_encoder", "pipelines/cross-encoder-retrieve.yaml")
    registrar.add_pipeline_resource(
        "weft_cross_encoder", "pipelines/cross-encoder-rerank-then-generate.yaml"
    )


__all__ = ["DISCLOSURE", "NAME", "CrossEncoderRerank", "CrossEncoderSettings", "register"]
