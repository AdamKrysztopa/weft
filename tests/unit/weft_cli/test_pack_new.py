"""Starting a pack is an artefact a user re-runs — ledger task **26.7**.

`12-roadmap.md` §7 item 2 is the complaint: *"Twenty-eight pipeline documents and no examples
directory. Every phase Exit says 'from outside this repository' and each is a one-off act by the
builder rather than an artefact a user re-runs."* Ten example packs exist now, and every one of
them was written by hand here, inside this checkout — so *"writing a pack is cheap"* is a claim
this project makes and has never let anybody else test.

`07` §2 states the unit of measure, and the template's job is to produce exactly it — **the
canonical pack, four files**: a `pyproject.toml` with one `weft.packs` entry point, a
`src/<pkg>/__init__.py` holding `Settings` and `register`, a `src/<pkg>/<impl>.py` with the
implementation and its `with:` model, and a `tests/test_<impl>.py`. Anything fewer is not a pack;
anything more is this template having an opinion it has not earned.

**A registered `Command`, not a script.** `Command` is a published contract, so this is an entry
point and zero edits to core — requirement 1's own property, and the template teaching it by being
it. A `scripts/new_pack.py` would sit outside the mechanism it exists to demonstrate.

**What it may not do.** Reach the network, install anything, or run `git`. A scaffolder that runs a
subprocess is a dependency declaration nobody wrote (`L6.24`), and the whole value here is that a
pack author's first minute has no moving parts.
"""

from __future__ import annotations

import importlib
import tomllib
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest
from pydantic import ValidationError

from weft_command.contract import CommandResult
from weft_kernel.context import Context
from weft_kernel.payload import Outcome, Produced


def _result(outcome: Outcome[CommandResult]) -> CommandResult:
    assert isinstance(outcome, Produced)
    return outcome.value


async def test_it_writes_the_canonical_four_files(tmp_path: Path) -> None:
    """The happy path, asserted against `07` §2's own list rather than against a count.

    A count would pass for four files of the wrong kind, which is the shape this template exists
    to get right.
    """
    # Arrange
    from weft_cli.pack_new import PackNewArgs, PackNewCommand

    # Act
    outcome = await PackNewCommand().run(
        PackNewArgs(name="acme-shouty", into=str(tmp_path)), _ctx()
    )

    # Assert
    _result(outcome)
    root = tmp_path / "acme-shouty"
    assert (root / "pyproject.toml").is_file()
    assert (root / "src" / "acme_shouty" / "__init__.py").is_file()
    assert (root / "tests").is_dir()
    written = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
    assert len(written) == 4, written


async def test_the_generated_pyproject_declares_one_weft_packs_entry_point(tmp_path: Path) -> None:
    """The entry point is the whole mechanism — `02` §2 — so it is parsed rather than grepped.

    A pack whose `pyproject.toml` is well-formed prose and declares nothing is exactly the failure
    a template should be incapable of producing.
    """
    # Arrange
    from weft_cli.pack_new import PackNewArgs, PackNewCommand

    await PackNewCommand().run(PackNewArgs(name="acme-shouty", into=str(tmp_path)), _ctx())

    # Act
    manifest = tomllib.loads((tmp_path / "acme-shouty" / "pyproject.toml").read_text())

    # Assert
    entry_points = manifest["project"]["entry-points"]["weft.packs"]
    assert len(entry_points) == 1, entry_points
    assert next(iter(entry_points.values())).startswith("acme_shouty")


async def test_the_generated_pack_imports_and_registers_a_plugin(tmp_path: Path) -> None:
    """The generated code runs, which no amount of reading the files can show.

    `L6.24`: installing a distribution and importing it proves its import-time dependencies and
    nothing else — so this executes `register` against a real `Registry` and asserts a name
    arrives, which is the property a pack author is actually buying.
    """
    # Arrange
    import sys

    from weft_cli.pack_new import PackNewArgs, PackNewCommand

    await PackNewCommand().run(PackNewArgs(name="acme-shouty", into=str(tmp_path)), _ctx())
    sys.path.insert(0, str(tmp_path / "acme-shouty" / "src"))
    try:
        # Act
        # `importlib` rather than an `import` statement: the module does not exist until the
        # command under test writes it, so a static import is unresolvable by construction and a
        # suppression on it would be hiding a fact rather than stating one.
        generated = importlib.import_module("acme_shouty")
        registry, registered = _recording_registrar()
        register = cast("Callable[[object, object], None]", generated.register)
        settings = cast("Callable[[], object]", generated.Settings)
        register(registry, settings())
    finally:
        sys.path.remove(str(tmp_path / "acme-shouty" / "src"))
        sys.modules.pop("acme_shouty", None)

    # Assert
    assert registered, "the generated register() registered nothing"


async def test_a_name_that_is_not_a_distribution_name_is_refused(tmp_path: Path) -> None:
    """The error case.

    A name with a space or a slash produces a directory and a package that cannot be imported, and
    finding that out at `pip install` time is finding it out too late.
    """
    # Arrange
    from weft_cli.pack_new import PackNewArgs

    # Act / Assert
    with pytest.raises(ValidationError):
        PackNewArgs(name="not a name", into=str(tmp_path))


async def test_an_existing_directory_is_refused_rather_than_written_into(tmp_path: Path) -> None:
    """A `write`-class command creates; it does not replace.

    `InitCommand`'s own repair from `overwrite` to `write` is the precedent: scaffolding into a
    target that already exists is refused outright, loudly, naming the path — never silently
    merged, which would leave a half-template over somebody's work with no way to tell.
    """
    # Arrange
    from weft_cli.pack_new import PackNewArgs, PackNewCommand, PackTargetExistsError

    (tmp_path / "acme-shouty").mkdir()

    # Act / Assert
    with pytest.raises(PackTargetExistsError) as caught:
        await PackNewCommand().run(PackNewArgs(name="acme-shouty", into=str(tmp_path)), _ctx())
    assert "acme-shouty" in str(caught.value)


def _ctx() -> Context:
    return Context(tenant_id="t", run_id="r", trace_id="tr", locale="en")


def _recording_registrar() -> tuple[_Recorder, list[str]]:
    """A registrar that records the names a pack registers, rather than a real `Registry`.

    The generated pack registers against whatever `register(registry, settings)` is handed, so the
    double records names — which is the fact under test — instead of reproducing the registry's own
    validation, which is `weft_kernel`'s to test and not this template's.
    """
    recorder = _Recorder()
    return recorder, recorder.names


class _Recorder:
    """Records the names a generated pack registers.

    A double rather than a real `Registry`, because the fact under test is *that the generated
    `register` registers something* — the registry's own validation is `weft_kernel`'s to test and
    not this template's.
    """

    def __init__(self) -> None:
        self.names: list[str] = []

    def add(self, contract: type, name: str, factory: object, **kwargs: object) -> None:
        del contract, factory, kwargs
        self.names.append(name)
