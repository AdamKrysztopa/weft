"""`weft-docling`'s registration half — ledger `9.13`.

Two clauses of the property live here rather than in the extractor's own file, because both
are facts about *discovery* and not about a run: the rung is selectable by name in a pipeline
document, and the pack reports itself **partial** when its weights are not on disk — *"without
touching the network"*, which is the clause that makes this more than a status string.

**Why partial rather than absent, and why it is declared here rather than raised in `run`.**
Fitness function 5's second half —
`tests/architecture/test_ff5_declared_capability_resolves.py`'s
`PLUGINS_REPORTING_UNAVAILABILITY_TOO_LATE`, pinned empty since task `6.29` — forbids exactly
the shape where a plugin registers, looks healthy to `weft plugins doctor`, and only says why
it cannot work when somebody runs it. `bertscore` is that waiver's worked example and the
pattern is copied deliberately: the plugin **stays registered**, so a pipeline naming it is
refused *by name with a reason* rather than reported as an unknown plugin, and the pack's
status carries the notice an operator sees first.
"""

import socket
from pathlib import Path

import pytest

from weft_docling import Settings, register
from weft_docling.pdf_layout_model import NAME, PdfLayoutModelExtractor
from weft_docling.weights import REQUIRED_MODEL_FOLDERS, artifacts_dir, missing_weights
from weft_extract.contract import Extractor
from weft_kernel.discovery import PackRegistrar
from weft_kernel.registry import Registry, unwrap_factory


def _registrar() -> tuple[Registry, PackRegistrar]:
    registry = Registry()
    return registry, PackRegistrar(registry, distribution="weft-docling")


def _with_weights(root: Path) -> Path:
    """`root`, populated so that every folder `missing_weights` looks for is present."""
    for folder in REQUIRED_MODEL_FOLDERS:
        target = root / folder
        target.mkdir(parents=True)
        (target / "model.safetensors").write_bytes(b"not really weights")
    return root


def test_the_rung_registers_under_the_extractor_contract(tmp_path: Path) -> None:
    registry, registrar = _registrar()

    register(registrar, Settings(artifacts_path=str(_with_weights(tmp_path))))
    registrar.commit()

    # Through `unwrap_factory`, per `weft_kernel.registry`'s own rule: this pack binds its
    # settings with `partial`, and a `partial` has none of the class's attributes.
    assert unwrap_factory(registry.entry(Extractor, NAME).factory) is PdfLayoutModelExtractor
    assert registry.entry(Extractor, NAME).distribution == "weft-docling"


def test_weights_on_disk_make_the_pack_active(tmp_path: Path) -> None:
    _, registrar = _registrar()

    register(registrar, Settings(artifacts_path=str(_with_weights(tmp_path))))

    assert registrar.unavailable_surfaces == ()


def test_weights_absent_make_the_pack_partial(tmp_path: Path) -> None:
    _, registrar = _registrar()

    register(registrar, Settings(artifacts_path=str(tmp_path)))

    (notice,) = registrar.unavailable_surfaces
    assert notice.surface == NAME


def test_the_partial_notice_names_the_directory_it_looked_in(tmp_path: Path) -> None:
    # An operator whose weights are somewhere else needs to know where this looked, or the
    # remedy is a guess. `01` → requirement 5: name what was wanted and the valid options.
    _, registrar = _registrar()

    register(registrar, Settings(artifacts_path=str(tmp_path)))

    (notice,) = registrar.unavailable_surfaces
    assert str(tmp_path) in notice.reason


def test_the_partial_notice_names_a_remedy(tmp_path: Path) -> None:
    _, registrar = _registrar()

    register(registrar, Settings(artifacts_path=str(tmp_path)))

    (notice,) = registrar.unavailable_surfaces
    assert "artifacts_path" in notice.reason


def test_the_rung_stays_registered_when_its_weights_are_missing(tmp_path: Path) -> None:
    # The `bertscore` shape: refused by name with a reason beats reported as unknown.
    registry, registrar = _registrar()

    register(registrar, Settings(artifacts_path=str(tmp_path)))
    registrar.commit()

    assert unwrap_factory(registry.entry(Extractor, NAME).factory) is PdfLayoutModelExtractor


def test_the_weights_check_opens_no_socket(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # *"without touching the network"* is the clause that distinguishes this from asking
    # docling, which would resolve the model against a remote index and download it. The
    # check is a filesystem question and the assertion is that it stays one.
    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("the weights check reached the network")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)

    assert missing_weights(tmp_path) == REQUIRED_MODEL_FOLDERS


def test_registration_opens_no_socket(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # The same clause one level out: discovery imports and registers every allowed pack, so a
    # pack that reached the network at registration would put a network call on the startup
    # path of every command, including `weft plugins doctor`.
    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("registration reached the network")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)

    register(_registrar()[1], Settings(artifacts_path=str(tmp_path)))


def test_a_partly_populated_directory_is_still_missing_what_is_absent(tmp_path: Path) -> None:
    # An empty answer is not a fact about the world: the check reports *which* folders are
    # absent, so a half-downloaded cache is not read as a complete one.
    present, *rest = REQUIRED_MODEL_FOLDERS
    (tmp_path / present).mkdir(parents=True)
    (tmp_path / present / "model.safetensors").write_bytes(b"x")

    assert missing_weights(tmp_path) == tuple(rest)


def test_an_empty_model_folder_does_not_count_as_present(tmp_path: Path) -> None:
    # A directory `docling-tools` created and then failed to fill is the state most likely to
    # be read as success by a check that only asks `is_dir()`.
    for folder in REQUIRED_MODEL_FOLDERS:
        (tmp_path / folder).mkdir(parents=True)

    assert missing_weights(tmp_path) == REQUIRED_MODEL_FOLDERS


def test_the_required_folders_are_the_ones_docling_itself_declares() -> None:
    # Both sides of a check must not come from one source (`phase-step` → *Finish*). The
    # filesystem is one side; docling's own declared repository ids are the other. Reading
    # them from docling rather than pasting them means a release that renames a model makes
    # this pack report its weights missing, instead of looking in a directory nothing fills.
    from docling.datamodel.pipeline_options import LayoutObjectDetectionOptions

    layout_repo = LayoutObjectDetectionOptions().model_spec.repo_id
    assert layout_repo.replace("/", "--") in REQUIRED_MODEL_FOLDERS


def test_no_artifacts_path_falls_back_to_doclings_own_cache() -> None:
    # `None` means "wherever docling keeps them", which is the only answer that stays true
    # when an operator has already run docling's own downloader.
    assert artifacts_dir(None).name == "models"


def test_an_explicit_artifacts_path_is_used_verbatim(tmp_path: Path) -> None:
    assert artifacts_dir(str(tmp_path)) == tmp_path


def test_the_pack_settings_expose_only_where_the_weights_live() -> None:
    # Every other decision is a *stage* decision and belongs in the pipeline document, where
    # it can differ between two pipelines in one deployment. Where 897 MB of weights live
    # cannot: registration reads it, and registration happens once per process.
    assert frozenset(Settings.model_fields) == frozenset({"artifacts_path"})
