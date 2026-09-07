"""`weft-docling` — the learned-layout PDF pack. Ledger `9.13`.

One `Extractor` backend, `pdf-layout-model` (`pdf_layout_model.py`), registered here under the
same `Extractor` contract `weft-pdf` publishes against, so a pipeline document selects it by
name exactly the way it selects `pdf-text` or `pdf-layout`.

**Registered even when its weights are absent, and reported `PARTIAL` when they are — the
`bertscore` shape** (`weft_eval.__init__.register`, ledger `6.29`, fitness function 5's second
half). The alternative — registering nothing until the weights are found — would make a
pipeline naming `pdf-layout-model` fail with "unknown plugin", which sends an operator looking
in the wrong place: nothing is wrong with the *name*, something is missing from *disk*.
Registering the plugin and calling `registrar.unavailable` instead makes `weft plugins doctor`
say so before a run does, and a pipeline that names it anyway is refused by name with a reason.
`weights.missing_weights` is a pure filesystem check — no network, ever, on this path, because
discovery imports and registers every allowed pack on every command.
"""

from functools import partial

from pydantic import BaseModel, ConfigDict

from weft_docling.pdf_layout_model import NAME, PdfLayoutModelExtractor
from weft_docling.weights import artifacts_dir, missing_weights
from weft_extract.contract import Extractor
from weft_kernel.discovery import Disclosure, PackRegistrar

#: What this pack touches — `02` §2 → *The trust model*, and `weft_blob.DISCLOSURE`'s shape:
#: concrete facts rather than booleans. Two entries rather than one, because they are answers to
#: different operator questions. The weights directory is read at *registration*, on every
#: command, before any pipeline runs — an operator watching `weft plugins doctor` reach a
#: directory deserves to be told which. And docling's conversion loads several hundred megabytes
#: of model into memory from that directory, which is the fact that decides whether this pack
#: belongs on a given machine at all.
#:
#: **This note claimed "no network call on any path this pack owns" for about an hour and it was
#: false.** It was written from the design; running the binary then downloaded 593 MB into the
#: Hugging Face cache mid-conversion, because docling reads `artifacts_path=None` as "resolve
#: these yourself" rather than as a default directory. `pdf_layout_model.run` now resolves the
#: path before handing it over, which is what makes the sentence true — the disclosure and the
#: repair landed together, and neither would have been written without the run.
DISCLOSURE = Disclosure(
    network=(),
    filesystem=(
        "[packs.docling] artifacts_path — the model weights are read from here, at registration "
        "and again at every conversion; unset means docling's own cache directory",
    ),
    subprocess=(),
    note=(
        "Runs a learned page-layout model locally over each PDF page's rendered image, from "
        "weights already on disk. Nothing here fetches them: docling is always handed a "
        "concrete local directory, so a missing model is a loud failure rather than a "
        "download. Fetching them in the first place is docling's own downloader, which an "
        "operator runs deliberately."
    ),
)


class Settings(BaseModel):
    """`weft-docling`'s one pack setting: where its weights live on disk.

    A *pack* setting rather than a *stage* one, unlike the four decisions
    `PdfLayoutModelConfig` exposes: `register` is what has to read this to decide whether the
    rung it is about to register can actually run, and registration sees only pack settings —
    it runs once per process, before any pipeline document naming a stage config exists.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    artifacts_path: str | None = None


def register(registrar: PackRegistrar, settings: Settings) -> None:
    """Register `pdf-layout-model`, and declare it unavailable if its weights are not on disk.

    Always registers the extractor first — see the module docstring for why the plugin stays
    registered regardless. The weights check that follows is pure filesystem (`weights.py`): no
    network call reaches this path, so a corpus that has never called docling's own downloader
    still gets a fast, offline registration.
    """
    # `partial` so the pack setting reaches the extractor: `weft_kernel.runner` calls the
    # registered factory with the *stage's* config and nothing else, so a pack setting has no
    # other route in. The shape `weft_blob` and `weft_qdrant` already register, and
    # `weft_kernel.registry.unwrap_factory` is what keeps the class-level declarations
    # (`provides`, `extensions`) readable through it.
    registrar.add(Extractor, NAME, partial(PdfLayoutModelExtractor, settings.artifacts_path))

    # The document that places this rung — see its own header. Without this line the file
    # exists on disk and satisfies fitness function 11's glob, while FF16 reads only what a
    # pack actually contributed, so the rung would be unreachable from any document a user
    # can name. `L9.83`.
    registrar.add_pipeline_resource("weft_docling", "pipelines/index-pdf-learned.yaml")

    root = artifacts_dir(settings.artifacts_path)
    missing = missing_weights(root)
    if missing:
        registrar.unavailable(
            NAME,
            reason=(
                f"weights not found under {root}: missing {', '.join(missing)}. "
                "Either point the 'artifacts_path' pack setting at a directory that already "
                "holds them, or fetch them there with docling's own downloader "
                "('docling-tools models download')."
            ),
        )


__all__ = ["DISCLOSURE", "Settings", "register"]
