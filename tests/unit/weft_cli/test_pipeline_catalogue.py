"""Unit tests for `weft_cli.pipeline_catalogue`.

Mirrors `packages/weft-cli/src/weft_cli/pipeline_catalogue.py`. Task **1.9**:
`weft-cli` is the only distribution allowed to open a pipeline document — G1 fixes the
kernel's dependencies at `pydantic` and `opentelemetry-api`, so the YAML parser lives
here, on the same footing `weft_cli.registry_bootstrap` already established for
`weft.toml`'s TOML. Covers the happy path (one document parses into the `Pipeline` the
kernel already validates, and a directory of documents becomes a `resolve()`-ready
catalogue keyed by each document's own `name:`), the edge case of two catalogue files
declaring the same name, and the error cases of unreadable YAML and a document that
parses as YAML but fails `Pipeline`'s own validation.
"""

import importlib.util
import sys
from collections.abc import Generator
from pathlib import Path

import pytest

from weft_cli.pipeline_catalogue import (
    ContributedPipelineNameCollisionError,
    DuplicatePipelineNameError,
    MalformedPipelineError,
    PipelineDocumentError,
    load_contributed,
    load_pipeline_catalogue,
    load_pipeline_document,
)
from weft_kernel.discovery import PackReport, PackStatus, PipelineResource
from weft_kernel.pipeline import Pipeline, StageDeclaration


def test_load_pipeline_document_parses_yaml_into_a_validated_pipeline(tmp_path: Path) -> None:
    # Arrange
    path = tmp_path / "base.yaml"
    path.write_text(
        "name: base\n"
        "stages:\n"
        "  - id: chunk\n"
        "    use: fixed-size\n"
        "    with: {size: 200, overlap: 20}\n"
    )

    # Act
    pipeline = load_pipeline_document(path)

    # Assert
    assert pipeline == Pipeline(
        name="base",
        stages=(
            StageDeclaration(id="chunk", use="fixed-size", config={"size": 200, "overlap": 20}),
        ),
    )


def test_load_pipeline_catalogue_keys_every_document_by_its_own_name_field(
    tmp_path: Path,
) -> None:
    # Arrange — the filename is deliberately not the pipeline's name, to prove the key
    # comes from the document's own `name:` field, never the path it was read from.
    (tmp_path / "root.yaml").write_text("name: base\nstages: [{id: chunk, use: fixed-size}]\n")
    (tmp_path / "child.yaml").write_text(
        "name: specific\nextends: base\ninsert: [{after: chunk, stage: {id: kw, use: keybert}}]\n"
    )

    # Act
    catalogue = load_pipeline_catalogue(tmp_path)

    # Assert
    assert set(catalogue) == {"base", "specific"}
    assert catalogue["specific"].extends == "base"


def test_load_pipeline_catalogue_refuses_two_documents_sharing_one_name(tmp_path: Path) -> None:
    # Arrange
    (tmp_path / "a.yaml").write_text("name: base\nstages: [{id: chunk, use: fixed-size}]\n")
    (tmp_path / "b.yaml").write_text("name: base\nstages: [{id: chunk, use: fixed-size}]\n")

    # Act / Assert
    with pytest.raises(DuplicatePipelineNameError, match="base"):
        load_pipeline_catalogue(tmp_path)


def test_load_pipeline_document_raises_for_yaml_that_does_not_parse(tmp_path: Path) -> None:
    # Arrange — an unterminated flow mapping: invalid YAML, not merely an invalid pipeline.
    path = tmp_path / "broken.yaml"
    path.write_text("name: base\nstages: [{id: chunk, use: fixed-size\n")

    # Act / Assert
    with pytest.raises(PipelineDocumentError, match="broken.yaml"):
        load_pipeline_document(path)


def test_load_pipeline_document_raises_for_valid_yaml_that_fails_pipeline_validation(
    tmp_path: Path,
) -> None:
    # Arrange — valid YAML, but `extends` and a non-empty `stages:` together have no
    # meaning to `Pipeline` itself (`weft_kernel.pipeline`'s own mutual-exclusivity rule).
    path = tmp_path / "confused.yaml"
    path.write_text("name: confused\nextends: base\nstages: [{id: chunk, use: fixed-size}]\n")

    # Act / Assert
    with pytest.raises(MalformedPipelineError, match="confused.yaml"):
        load_pipeline_document(path)


# --- load_contributed (task 2.8) -------------------------------------------------------


def _install_fake_resource_package(tmp_path: Path, *, name: str, files: dict[str, str]) -> None:
    """A real, importable package under `tmp_path`, so `importlib.resources` resolves it
    exactly the way it resolves an installed wheel — the property `load_contributed`
    exists for. `files` maps a resource path (`"pipelines/route.yaml"`) to its text.
    """
    pkg_dir = tmp_path / name
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text("")
    for relative, text in files.items():
        target = pkg_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
    spec = importlib.util.spec_from_file_location(
        name, pkg_dir / "__init__.py", submodule_search_locations=[str(pkg_dir)]
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)


@pytest.fixture(autouse=True)
def uninstall_fake_resource_packages() -> Generator[None]:
    yield
    for name in [n for n in sys.modules if n.startswith("_weft_test_resource_pkg")]:
        del sys.modules[name]


def test_load_contributed_reads_a_pipeline_resource_through_importlib(tmp_path: Path) -> None:
    # Arrange — the mechanism `weft_retrieve.contract.RouteCatalogue`'s own docstring
    # promises: a pipeline reachable from an *installed package*, never a filesystem path
    # relative to this repository.
    _install_fake_resource_package(
        tmp_path,
        name="_weft_test_resource_pkg_happy",
        files={"pipelines/route.yaml": "name: route\nstages: []\n"},
    )
    report = PackReport(
        distribution="weft-happy",
        status=PackStatus.ACTIVE,
        pipeline_resources=(
            PipelineResource(
                distribution="weft-happy",
                package="_weft_test_resource_pkg_happy",
                resource="pipelines/route.yaml",
            ),
        ),
    )

    # Act
    catalogue = load_contributed([report])

    # Assert
    assert set(catalogue) == {"route"}
    assert catalogue["route"].stages == ()


def test_load_contributed_refuses_two_resources_declaring_the_same_name(tmp_path: Path) -> None:
    # Arrange
    _install_fake_resource_package(
        tmp_path,
        name="_weft_test_resource_pkg_a",
        files={"pipelines/one.yaml": "name: shared\nstages: []\n"},
    )
    _install_fake_resource_package(
        tmp_path,
        name="_weft_test_resource_pkg_b",
        files={"pipelines/two.yaml": "name: shared\nstages: []\n"},
    )
    reports = [
        PackReport(
            distribution="weft-a",
            status=PackStatus.ACTIVE,
            pipeline_resources=(
                PipelineResource(
                    distribution="weft-a",
                    package="_weft_test_resource_pkg_a",
                    resource="pipelines/one.yaml",
                ),
            ),
        ),
        PackReport(
            distribution="weft-b",
            status=PackStatus.ACTIVE,
            pipeline_resources=(
                PipelineResource(
                    distribution="weft-b",
                    package="_weft_test_resource_pkg_b",
                    resource="pipelines/two.yaml",
                ),
            ),
        ),
    ]

    # Act / Assert
    with pytest.raises(ContributedPipelineNameCollisionError, match="shared"):
        load_contributed(reports)


def test_load_contributed_raises_for_a_resource_no_installed_package_provides() -> None:
    # Arrange — no `add_pipeline_resource` call could ever name an uninstalled package in
    # production (a pack names its own), but a stale resource path after a rename must
    # still be diagnosable rather than a bare `ModuleNotFoundError` traceback.
    report = PackReport(
        distribution="weft-ghost",
        status=PackStatus.ACTIVE,
        pipeline_resources=(
            PipelineResource(
                distribution="weft-ghost",
                package="_weft_test_resource_pkg_never_installed",
                resource="pipelines/route.yaml",
            ),
        ),
    )

    # Act / Assert
    with pytest.raises(PipelineDocumentError, match="weft-ghost"):
        load_contributed([report])
