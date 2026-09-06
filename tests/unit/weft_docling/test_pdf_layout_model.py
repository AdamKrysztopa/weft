"""`pdf-layout-model` — the learned layout rung. Ledger `9.13`.

The ledger states the property in one sentence and every clause of it is a separate
assertion here: *"a scanned or multi-column PDF is readable through a learned layout rung
shipped as its own distribution for its dependency weight, selectable by name in a pipeline
document, exposing four typed decisions and no vendor dict, reporting itself partial when its
weights are not on disk without touching the network, and honouring cancellation at document
granularity with that weakening written down."*

**No real conversion runs in this file, and that is a property rather than a shortcut.**
docling's layout model is 897 MB of weights that are not on disk in this environment — which is
exactly the state `missing_weights` exists to report. So the conversion itself is reached
through one named module-level seam, `convert_pdf`, and these tests replace it. What that
leaves untested is the docling call itself; what it makes testable is every decision this pack
actually owns. `tests/unit/weft_docling/test_init.py` covers the registration half.
"""

import asyncio
import threading
from collections.abc import Mapping
from pathlib import Path
from typing import get_args, get_origin

import pytest

from weft_docling import pdf_layout_model
from weft_docling.pdf_layout_model import (
    NAME,
    Device,
    PdfLayoutModelConfig,
    PdfLayoutModelExtractor,
    TableMode,
)
from weft_docling.weights import artifacts_dir
from weft_extract.contract import Extractor, SourceDoc
from weft_kernel.context import Context
from weft_kernel.payload import Failed, MediaType, NothingToProduce, Produced, SourceId

#: The four decisions the ledger line requires this rung to expose, and no fifth. Where the
#: weights live is a *pack* setting rather than a stage one — registration is what has to read
#: it, and registration sees only pack settings. `test_init.py` owns that half.
FOUR_DECISIONS = frozenset({"ocr", "table_mode", "device", "page_separator"})


def _ctx() -> Context:
    return Context(tenant_id="t", run_id="r", trace_id="tr", locale="en")


def _doc(uri: str = "/corpus/scanned.pdf") -> SourceDoc:
    return SourceDoc(source_id=SourceId(uri), uri=uri, content=b"%PDF-1.7 not really")


def test_the_rung_is_selectable_by_the_name_the_catalogue_reserved() -> None:
    # `docs/10-technique-catalogue.md` §4 reserved this name before the code existed, and
    # `pdf-layout` is already taken by the shipped pdfplumber rung.
    assert NAME == "pdf-layout-model"


def test_it_satisfies_the_extractor_contract_structurally() -> None:
    # Never by subclassing it — the same path a third-party pack takes.
    assert isinstance(PdfLayoutModelExtractor(None, PdfLayoutModelConfig()), Extractor)


def test_the_config_exposes_exactly_the_four_decisions() -> None:
    assert frozenset(PdfLayoutModelConfig.model_fields) == FOUR_DECISIONS


def test_no_decision_is_a_vendor_dict() -> None:
    # "and no vendor dict" — a raw options mapping handed through to the library would satisfy
    # requirement 6's letter and none of its point. `pdf_layout.PdfLayoutExtractorConfig`
    # refuses `laparams` for this reason and says so.
    for name, field in PdfLayoutModelConfig.model_fields.items():
        annotation = field.annotation
        origin = get_origin(annotation) or annotation
        assert not (isinstance(origin, type) and issubclass(origin, Mapping)), (
            f"{name} is a mapping"
        )
        for arg in get_args(annotation):
            arg_origin = get_origin(arg) or arg
            assert not (isinstance(arg_origin, type) and issubclass(arg_origin, Mapping)), (
                f"{name} carries a mapping"
            )


def test_the_two_multi_valued_decisions_are_enums() -> None:
    # `Enum` over `Literal`, and both are choices docling itself validates — so a typo in a
    # pipeline document fails at config validation naming the valid values, rather than inside
    # a worker thread halfway through a corpus.
    assert PdfLayoutModelConfig.model_fields["table_mode"].annotation is TableMode
    assert PdfLayoutModelConfig.model_fields["device"].annotation is Device


def test_ocr_is_on_by_default_because_a_scanned_pdf_is_the_reason_this_rung_exists() -> None:
    # The property names *scanned* first. A default of `False` would make the headline case
    # need configuration to work at all, which is the wrong way round for this rung
    # specifically — `pdf-text` and `pdf-layout` already cover born-digital.
    assert PdfLayoutModelConfig().ocr is True


async def test_a_document_becomes_one_root_node_carrying_what_the_model_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def read(content: bytes, **kwargs: object) -> str:
        del content, kwargs
        return "# Heading\n\nTwo columns."

    monkeypatch.setattr(pdf_layout_model, "convert_pdf", read)

    outcome = await PdfLayoutModelExtractor(None, PdfLayoutModelConfig()).run([_doc()], _ctx())

    assert isinstance(outcome, Produced)
    (node,) = outcome.value
    assert node.content == "# Heading\n\nTwo columns."
    assert node.media_type is MediaType.TEXT
    assert node.lineage.sources == frozenset({SourceId("/corpus/scanned.pdf")})


async def test_several_documents_each_become_their_own_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def read(content: bytes, **kwargs: object) -> str:
        del content, kwargs
        return "text"

    monkeypatch.setattr(pdf_layout_model, "convert_pdf", read)

    outcome = await PdfLayoutModelExtractor(None, PdfLayoutModelConfig()).run(
        [_doc("/a.pdf"), _doc("/b.pdf")], _ctx()
    )

    assert isinstance(outcome, Produced)
    assert [n.lineage.sources for n in outcome.value] == [
        frozenset({SourceId("/a.pdf")}),
        frozenset({SourceId("/b.pdf")}),
    ]


async def test_a_document_the_model_read_nothing_from_is_not_a_node(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # An empty parse is an absence, not an error, and it must not reach the store as a node
    # with empty content — `weft_pdf.document` makes the same distinction.
    def read_blank(content: bytes, **kwargs: object) -> str:
        del content, kwargs
        return "   "

    monkeypatch.setattr(pdf_layout_model, "convert_pdf", read_blank)

    outcome = await PdfLayoutModelExtractor(None, PdfLayoutModelConfig()).run([_doc()], _ctx())

    assert isinstance(outcome, NothingToProduce)


async def test_an_unreadable_document_fails_naming_the_document(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def explode(content: bytes, **kwargs: object) -> str:
        raise RuntimeError("malformed xref table")

    monkeypatch.setattr(pdf_layout_model, "convert_pdf", explode)

    outcome = await PdfLayoutModelExtractor(None, PdfLayoutModelConfig()).run([_doc()], _ctx())

    assert isinstance(outcome, Failed)
    assert "/corpus/scanned.pdf" in outcome.reason


async def test_cancellation_propagates_and_is_never_swallowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # `01` → *Colour*: `CancelledError` propagates untouched. A broad `except Exception` around
    # the conversion would turn a cancelled run into a `Failed` document, which reads in the
    # store as a corpus that parsed badly rather than one that was stopped.
    def cancel(content: bytes, **kwargs: object) -> str:
        raise asyncio.CancelledError

    monkeypatch.setattr(pdf_layout_model, "convert_pdf", cancel)

    with pytest.raises(asyncio.CancelledError):
        await PdfLayoutModelExtractor(None, PdfLayoutModelConfig()).run([_doc()], _ctx())


async def test_the_conversion_runs_off_the_event_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    # Fitness function 7(b) cannot see CPU-bound work, so this is where the rule is checked:
    # the layout model is seconds of pure computation per document and must not hold the loop.
    # The assertion is the fact rather than the mechanism — the conversion is observed running
    # on a thread that is not the loop's — so a future change from `to_thread` to a pool still
    # satisfies it.
    loop_thread = threading.get_ident()
    seen: list[int] = []

    def record(content: bytes, **kwargs: object) -> str:
        seen.append(threading.get_ident())
        return "text"

    monkeypatch.setattr(pdf_layout_model, "convert_pdf", record)

    await PdfLayoutModelExtractor(None, PdfLayoutModelConfig()).run([_doc()], _ctx())

    assert seen and seen[0] != loop_thread


async def test_the_configured_artifacts_path_is_the_one_the_conversion_reads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The weights directory registration checked must be the one the conversion loads from.

    Found by reading the implementation rather than by any test above, which is the finding:
    every other test in this file replaces `convert_pdf`, so all of them pass while the value
    handed to it is hard-coded. An operator who sets `[packs.docling] artifacts_path` would
    have had their directory checked at registration and ignored at conversion — the pack
    reporting `ACTIVE` off one directory and then failing to load weights from another. A
    split like that is worse than either failure alone, because the status says it cannot
    happen.
    """
    seen: list[str | None] = []

    def record(content: bytes, **kwargs: object) -> str:
        del content
        artifacts_path = kwargs["artifacts_path"]
        seen.append(artifacts_path if artifacts_path is None else str(artifacts_path))
        return "text"

    monkeypatch.setattr(pdf_layout_model, "convert_pdf", record)

    extractor = PdfLayoutModelExtractor("/models/docling", PdfLayoutModelConfig())
    await extractor.run([_doc()], _ctx())

    assert seen == ["/models/docling"]


async def test_the_conversion_is_never_handed_none_to_resolve_for_itself(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unset `artifacts_path` still reaches docling as a concrete directory.

    **Found by running the binary, and it had already cost 593 MB.** `artifacts_path=None`
    does not mean "docling's model cache" to docling — it means *"resolve the models
    yourself"*, and docling resolves them by calling `snapshot_download`, which fetches from
    the Hugging Face hub into `~/.cache/huggingface`. So the pack reported `PARTIAL` from
    `weights.py` looking in one directory while a run quietly downloaded half a gigabyte into
    another: the status said the rung could not work, and then it worked, over the network,
    having been disclosed as touching neither.

    Passing the resolved directory always is what closes both halves at once — the check and
    the conversion read the same place, and docling given a local path loads from it instead
    of reaching for the hub.
    """
    seen: list[object] = []

    def record(content: bytes, **kwargs: object) -> str:
        del content
        seen.append(kwargs["artifacts_path"])
        return "text"

    monkeypatch.setattr(pdf_layout_model, "convert_pdf", record)

    await PdfLayoutModelExtractor(None, PdfLayoutModelConfig()).run([_doc()], _ctx())

    assert seen == [str(artifacts_dir(None))]
    assert seen[0] is not None


def test_the_weakening_cancellation_leaves_is_written_down() -> None:
    # `phase-step` → *Finish* and the ledger both ask for the weakening to be *stated*, not
    # merely true: a thread cannot be interrupted, so cancellation takes effect at the end of
    # the current document rather than immediately. `pdf_layout.py` states the same thing.
    doc = pdf_layout_model.__doc__ or ""
    assert "cancel" in doc.lower()
    assert "document" in doc.lower()


def test_it_declares_the_extensions_it_reads() -> None:
    assert PdfLayoutModelExtractor.extensions == (".pdf",)


def test_the_config_model_is_reachable_from_the_class() -> None:
    # How a pipeline document's `with:` block is validated before the stage ever runs.
    assert PdfLayoutModelExtractor.config_model is PdfLayoutModelConfig


def test_the_config_is_frozen_and_refuses_an_unknown_key() -> None:
    with pytest.raises(ValueError, match="extra_forbidden|frozen|Extra inputs"):
        PdfLayoutModelConfig(laparams={"detect_vertical": True})  # type: ignore[call-arg]


async def test_run_accepts_an_empty_batch_without_reaching_the_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def never(content: bytes, **kwargs: object) -> str:
        raise AssertionError("the model was reached for an empty batch")

    monkeypatch.setattr(pdf_layout_model, "convert_pdf", never)

    outcome = await PdfLayoutModelExtractor(None, PdfLayoutModelConfig()).run([], _ctx())

    assert isinstance(outcome, NothingToProduce)


def test_the_module_names_no_path_it_does_not_own() -> None:
    # A guard against the shape this pack is most likely to grow wrong: a hard-coded model
    # directory drifting from the one docling actually reads. `weights.py` derives it.
    source = Path(pdf_layout_model.__file__).read_text(encoding="utf-8")
    assert ".cache/docling" not in source
