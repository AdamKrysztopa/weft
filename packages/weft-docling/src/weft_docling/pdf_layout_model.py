"""`pdf-layout-model` — the learned layout rung docling ships. Ledger `9.13`.

**Why this rung exists beside `pdf-layout` and `pdf-text`.** Both of `weft-pdf`'s backends read
glyph geometry `pypdf` or `pdfplumber` already extracted from the PDF's own text layer, so
neither has anything to read on a scanned page — a photograph of a page, with no text layer at
all — and a justified multi-column layout is exactly the shape a rule-based column-guess is
weakest on. docling's rung instead runs a learned object-detection model over each page's
rendered image to find reading order, tables and figures directly, at the cost this pack's own
`pyproject.toml` measures: 897 MB of `torch`, `torchvision` and `transformers`, which is why it
ships as its own distribution rather than folding into `weft-pdf`.

**The conversion runs off the event loop, and the same one thing is weakened by that as in
`weft_pdf.pdf_layout`.** The learned model is seconds of pure computation per document, so
fitness function 7(b) cannot see it holding the loop, and `01` → *Colour* settles the rule
regardless: a CPU-bound stage is still `async def` and offloads its own blocking work. `run`
awaits `asyncio.to_thread` once per document. The weakening, stated here rather than left to be
discovered: a thread cannot be interrupted, so a `CancelledError` delivered while a batch is
converting takes effect only once the **current document** finishes, not immediately — the same
per-document granularity `pdf_layout.py` accepts for the identical reason. It is never
swallowed: `to_thread` re-raises it at the `await`.
"""

import asyncio
from collections.abc import Sequence
from enum import StrEnum
from io import BytesIO
from typing import ClassVar

from docling.datamodel.accelerator_options import AcceleratorDevice
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import (
    PdfPipelineOptions,
    TableFormerMode,
    TableStructureOptions,
)
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.types.io import DocumentStream
from pydantic import BaseModel, ConfigDict

from weft_docling.weights import artifacts_dir
from weft_extract.contract import SourceDoc
from weft_kernel.context import Context
from weft_kernel.payload import (
    ExtModel,
    Failed,
    MediaType,
    Node,
    NothingToProduce,
    Outcome,
    Produced,
)

#: The name this rung is registered and selected under — `docs/10-technique-catalogue.md` §4
#: reserved it, and `pdf-layout` is already the shipped `pdfplumber` rung's name.
NAME = "pdf-layout-model"

#: What this extractor reads — a `SourceDoc.uri` of any other suffix never reaches it.
EXTENSIONS: tuple[str, ...] = (".pdf",)


class TableMode(StrEnum):
    """The two modes `docling.datamodel.pipeline_options.TableFormerMode` accepts.

    `Enum` over `Literal`, and for the same reason `weft_pdf.pdf_layout.TextDirection` gives:
    docling itself validates exactly these two values, so a typo in a pipeline document fails at
    config validation, naming the valid options, rather than inside a worker thread halfway
    through a corpus.
    """

    FAST = "fast"
    ACCURATE = "accurate"


class Device(StrEnum):
    """The five values `docling.datamodel.accelerator_options.AcceleratorDevice` accepts."""

    AUTO = "auto"
    CPU = "cpu"
    CUDA = "cuda"
    MPS = "mps"
    XPU = "xpu"


class PdfLayoutModelConfig(BaseModel):
    """This rung's `with:` configuration — exactly the four decisions it owns, and no fifth.

    **No vendor dict.** docling's own `PdfPipelineOptions` exposes dozens of knobs; handing one
    through wholesale would put an untyped mapping in a configuration model, the shape
    `pdf_layout.PdfLayoutExtractorConfig` refuses `laparams` for, for the identical reason. The
    four named here are the ones a pipeline author actually reaches for — whether to run OCR at
    all, which table-structure mode to trade speed for accuracy with, which accelerator to run
    on, and how converted pages join into one document's text.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: On by default — a scanned PDF, the reason this rung exists, has no text layer for
    #: docling to skip OCR over. `pdf-text` and `pdf-layout` already cover the born-digital case
    #: this default would otherwise duplicate.
    ocr: bool = True
    table_mode: TableMode = TableMode.ACCURATE
    #: docling's own default, and **it fails on Apple Silicon** — `AUTO` selects MPS there and
    #: docling's layout model raises *"Cannot convert a MPS Tensor to float64 dtype as the MPS
    #: framework doesn't support float64"*, measured 2026-09-06 on this project's development
    #: machine. `device: cpu` converts the same document cleanly. The default stays `AUTO`
    #: anyway, on `pdf_layout.PdfLayoutExtractorConfig`'s settled precedent: *"a wrapper that
    #: quietly disagrees with the library it wraps makes the library's own documentation wrong
    #: for its users, and the number worth reaching for is stated here instead."* This is a
    #: defect in a dependency on one platform, not a decision Weft should encode as its own —
    #: pinning `CPU` here would silently cost every CUDA operator their accelerator to work
    #: around a bug that will be fixed upstream. The remedy is one line in a pipeline document
    #: and it is written here so it is findable from the failure.
    device: Device = Device.AUTO
    page_separator: str = "\n\n"


def convert_pdf(content: bytes, *, config: PdfLayoutModelConfig, artifacts_path: str | None) -> str:
    """Run docling's learned pipeline over `content` and return the document's markdown text.

    The only place in this pack that actually calls docling — every test in
    `test_pdf_layout_model.py` replaces this module attribute instead of exercising the model,
    because the 897 MB of weights it needs are not on disk in a test environment (`weights.py`
    is what reports that). `PdfLayoutModelExtractor.run` reaches this through the module
    attribute at call time, so a test's `monkeypatch.setattr` on it is honoured.
    """
    pipeline_options = PdfPipelineOptions(
        artifacts_path=artifacts_path,
        do_ocr=config.ocr,
        table_structure_options=TableStructureOptions(
            mode=TableFormerMode(config.table_mode.value)
        ),
    )
    pipeline_options.accelerator_options.device = AcceleratorDevice(config.device.value)
    converter = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)}
    )
    stream = DocumentStream(name="document.pdf", stream=BytesIO(content))
    result = converter.convert(stream)
    return result.document.export_to_markdown(delim=config.page_separator)


class PdfLayoutModelExtractor:
    """One root `Node` per document, its text read by docling's learned layout model.

    Satisfies `weft_extract.contract.Extractor` structurally — never by subclassing it, the same
    path a third-party pack takes.
    """

    extensions: tuple[str, ...] = EXTENSIONS
    config_model: type[PdfLayoutModelConfig] = PdfLayoutModelConfig
    #: This rung produces one root text node and attaches no fact for a later stage to bind
    #: to — declaring the empty tuple is the honest statement rather than an oversight, per
    #: `pdf_layout.PdfLayoutExtractor.provides`'s own comment on why declaring is not optional.
    provides: ClassVar[tuple[type[ExtModel], ...]] = ()

    def __init__(
        self, artifacts_path: str | None = None, config: PdfLayoutModelConfig | None = None
    ) -> None:
        """`artifacts_path` first, because `register()` binds it and the runner supplies `config`.

        `weft_docling.register` registers `partial(PdfLayoutModelExtractor,
        settings.artifacts_path)` and `weft_kernel.runner` then calls that with the stage's
        own `config` — the shape `weft_blob` and `weft_qdrant` already use, and the only one
        available to a plugin that needs a *pack* setting as well as a *stage* one.

        **Where the weights live cannot be a stage decision.** `register()` is what reports the
        pack `PARTIAL`, and registration sees only pack settings; a per-stage
        `artifacts_path` would let a pipeline point at a directory registration never checked.
        """
        self._artifacts_path = artifacts_path
        self._config = config if config is not None else PdfLayoutModelConfig()

    async def run(self, payload: Sequence[SourceDoc], ctx: Context) -> Outcome[Sequence[Node]]:
        del ctx
        if not payload:
            return NothingToProduce(reason="no documents in this batch")

        nodes: list[Node] = []
        for doc in payload:
            try:
                # `to_thread`, one call per document — see the module docstring, both for the
                # rule (`01` → *Colour*) and for what it weakens about cancellation.
                text = await asyncio.to_thread(
                    convert_pdf,
                    doc.content,
                    config=self._config,
                    # Resolved, never passed through as `None`. To docling `None` does not
                    # mean "your own cache" — it means *"resolve the models yourself"*, and it
                    # resolves them with `snapshot_download`, over the network, into the
                    # Hugging Face cache. That is a directory `weights.py` does not check, so
                    # an unset setting produced a pack reporting `PARTIAL` and then downloading
                    # 593 MB anyway (measured 2026-09-06, by running the binary). Handing
                    # docling a concrete local path is what makes the check and the conversion
                    # read the same place, and what keeps a missing model a loud failure
                    # instead of a silent fetch.
                    artifacts_path=str(artifacts_dir(self._artifacts_path)),
                )
            except asyncio.CancelledError:
                raise
            except Exception as error:
                # `CancelledError` inherits from `BaseException` in 3.12, so this `except
                # Exception` already misses it and the `raise` above is redundant in
                # principle — kept explicit because the conversion is a third-party call
                # whose exception types are not enumerable, and a reader must not have to
                # rediscover that fact to trust this clause.
                return Failed(reason=f"could not read {doc.uri}: {error}")
            if not text.strip():
                continue
            nodes.append(
                Node.synthetic(
                    content=text,
                    media_type=MediaType.TEXT,
                    reason="root node produced by the pdf-layout-model extractor",
                    sources=frozenset({doc.source_id}),
                )
            )

        if not nodes:
            return NothingToProduce(reason="every document in this batch read as empty")
        return Produced(value=nodes)
