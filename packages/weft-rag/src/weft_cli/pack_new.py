"""`weft pack new` — scaffold the canonical four-file pack. Ledger task **26.7**.

`12-roadmap.md` §7 item 2 is the complaint this answers: ten example packs exist and every one was
written by hand inside this checkout, so *"writing a pack is cheap"* is a claim this project makes
and has never let anybody else test. `07` §2 states the unit of measure — **the canonical pack,
four files** — and this command produces exactly it.

**A registered `Command`, not a script under `scripts/`.** `Command` is a published contract, so
this is an entry point and zero edits to core: requirement 1's own property, demonstrated by the
thing that teaches it rather than asserted beside it. A scaffolder living outside the extension
mechanism would be a poor advertisement for the extension mechanism.

**It touches nothing but the filesystem, under the directory it was given.** No network, no
`pip`, no `git`. A scaffolder that shells out is a dependency declaration nobody wrote (`L6.24`),
and the value of the first minute of writing a pack is that it has no moving parts.

**`write`-class, and an existing target is refused.** `InitCommand`'s own repair from `overwrite`
to `write` is the precedent: scaffolding into a directory that already exists is a *create* that
cannot proceed, refused loudly by name, never merged — a half-written template over somebody's
work is not recoverable and not detectable.

**What the generated pack implements, and why a `Chunker`.** It needs a contract to register
against, and `Chunker` is the cheapest real one: no store, no model call, no credential, no
container. The generated implementation is a real one that a reader improves rather than a stub
they delete, which is the difference between a template and a placeholder.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import ClassVar, Final, cast

from pydantic import BaseModel, ConfigDict, Field, field_validator

from weft_command.contract import CommandResult
from weft_command.permission import PermissionClass
from weft_kernel.context import Context
from weft_kernel.errors import WeftError
from weft_kernel.payload import Outcome, Produced

_HELP: Final[str] = (
    "scaffold a new pack — the four files `07` §2 calls the canonical pack, ready to "
    "`pip install -e .` and appear in `weft plugins doctor`"
)

#: A distribution name as PyPI accepts it, which is also what makes the module name derivable.
#: Refused at the flag rather than at `pip install`, because a name with a space produces a
#: directory and a package that cannot be imported and nothing says so until much later.
_NAME: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")


class PackTargetExistsError(WeftError):
    """`weft pack new` was pointed at a directory that already exists.

    Refused rather than merged, on `weft_cli.commands.TargetAlreadyExistsError`'s own footing:
    writing a template over a directory somebody already has leaves a half-pack that is neither
    theirs nor ours, and nothing in the result says which files were overwritten.
    """


class PackNewArgs(BaseModel):
    """`weft pack new <name> [--into DIR]`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(description="the distribution name, e.g. acme-shouty")
    into: str = Field(default=".", description="the directory to create the pack in")

    @field_validator("name")
    @classmethod
    def _a_real_distribution_name(cls, value: str) -> str:
        if not _NAME.match(value):
            raise ValueError(
                f"'{value}' is not a distribution name. Use lowercase letters, digits and single "
                "hyphens, starting with a letter — 'acme-shouty'. The Python package name is "
                "derived from it by replacing hyphens with underscores, so a name with a space, a "
                "slash or a capital produces a directory that cannot be imported."
            )
        return value


class PackNewCommandResult(CommandResult):
    """Where the pack was written, and the four files it holds."""

    path: str
    files: tuple[str, ...]


def _render(name: str) -> dict[str, str]:
    """The four files of `07` §2's canonical pack, as `{relative path: content}`.

    Modelled on the out-of-tree example packs fitness function 9(c) already proves a stranger can
    install, so the template teaches the shape that is checked rather than one invented here.
    **Deliberately without naming one**: fitness function 9(b) forbids anything under `packages/`
    from naming an example pack, because core anticipating a stranger it never imported is the
    coupling the whole example mechanism exists to avoid — and this file found that out by being
    refused.
    """
    package = name.replace("-", "_")
    impl = "shouty_chunker"
    cls = "ShoutyChunker"
    return {
        "pyproject.toml": f'''[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "{name}"
version = "0.1.0"
description = "A Weft pack."
requires-python = ">=3.12"
# The kernel, and the pack that publishes the contract being implemented. A contract is
# published by a pack and never by the kernel (`02` §1), so this is an ordinary dependency.
dependencies = ["weft-kernel>=0.1.0,<1.0.0", "weft-rag>=2.0.0,<3.0.0"]

# The whole mechanism. Discovery reads this group; nothing else here makes the pack a pack.
[project.entry-points."weft.packs"]
{name} = "{package}:register"

[tool.hatch.build.targets.wheel]
packages = ["src/{package}"]
''',
        f"src/{package}/__init__.py": f'''"""The pack: its settings model and its `register`."""

from pydantic import BaseModel, ConfigDict

from weft_chunk.contract import Chunker
from weft_kernel.discovery import PackRegistrar

from {package}.{impl} import {cls}


class Settings(BaseModel):
    """This pack's `[packs.{name}]` block in `weft.toml`.

    Empty is still the required shape: settings are *this installation of this
    pack*, and a pack that takes none says so with a model rather than by
    omitting one.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")


def register(registrar: PackRegistrar, settings: Settings) -> None:
    """Register every plugin this pack publishes. Called once, at discovery."""
    del settings
    registrar.add(Chunker, "{name}", {cls})


__all__ = ["Settings", "{cls}", "register"]
''',
        f"src/{package}/{impl}.py": f'''"""The implementation and its `with:` model."""

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field

from weft_kernel.context import Context
from weft_kernel.payload import Node, NothingToProduce, Outcome, Produced


class {cls}Config(BaseModel):
    """What a pipeline may set in this stage's `with:` block."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    suffix: str = Field(default="!", description="appended to every chunk")


class {cls}:
    """Uppercases each node's content — a real implementation to improve, not a stub to delete.

    `destroys` is not decoration: `Chunker` publishes a property vocabulary, so the registry
    refuses any implementation that never states it. An empty tuple is a statement; silence is not.
    """

    config_model = {cls}Config
    destroys: tuple[type, ...] = ()

    def __init__(self, config: {cls}Config | None = None) -> None:
        self._config = config if config is not None else {cls}Config()

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        del ctx
        if not payload:
            return NothingToProduce(reason="nothing to chunk")
        return Produced(
            value=tuple(
                node.derive(content=node.content.upper() + self._config.suffix) for node in payload
            )
        )
''',
        f"tests/test_{impl}.py": f'''"""The pack's own tests.

A store pack would run `weft_store.conformance` here against
`weft_store.memory.MemoryStore` — the published kit and the in-memory store, so no container is
needed. A chunker has no conformance kit of its own, so this asserts the property directly.
"""

import pytest

from weft_kernel.context import Context
from weft_kernel.payload import MediaType, Node, Produced

from {package}.{impl} import {cls}


def _node(content: str) -> Node:
    return Node.synthetic(content=content, media_type=MediaType.TEXT, reason="test")


@pytest.mark.asyncio
async def test_it_shouts() -> None:
    outcome = await {cls}().run([_node("hello")], _ctx())
    assert isinstance(outcome, Produced)
    assert outcome.value[0].content == "HELLO!"


def _ctx() -> Context:
    return Context(tenant_id="t", run_id="r", trace_id="tr", locale="en")
''',
    }


class PackNewCommand:
    """`weft pack new` — see this module's docstring."""

    args_model: ClassVar[type[BaseModel]] = PackNewArgs
    result_model: ClassVar[type[CommandResult]] = PackNewCommandResult
    permission_class: ClassVar[PermissionClass] = PermissionClass.WRITE
    help: ClassVar[str] = _HELP

    def __init__(self, config: object = None) -> None:
        del config

    async def run(self, args: BaseModel, ctx: Context) -> Outcome[CommandResult]:
        del ctx
        pack_args = cast("PackNewArgs", args)
        root = Path(pack_args.into) / pack_args.name
        if root.exists():
            raise PackTargetExistsError(
                f"'{root}' already exists, and scaffolding into it would leave a half-written "
                "pack over whatever is there with nothing saying which files moved. Choose "
                "another name, or another --into directory, or remove that path yourself."
            )
        written: list[str] = []
        for relative, content in sorted(_render(pack_args.name).items()):
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            written.append(relative)
        return Produced(
            value=PackNewCommandResult(path=str(root), files=tuple(written)),
        )
