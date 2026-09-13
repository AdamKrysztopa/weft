"""One sentence about the default embedder, on every surface a first hour touches — task **28.8**.

**G21**, settled 2026-09-12: the account-free semantic path is *a server the operator runs*, never
a model Weft downloads. That answer is only worth having if the person who needs it meets it, and
the three places they can meet it had three different sentences — `weft index`'s stderr line
(`R17.6`), `weft.toml` as `weft init` scaffolds it, and `weft.toml.example`. `weft plugins doctor`,
the command an operator runs when something looks wrong, said nothing at all.

**Why one sentence rather than three good ones.** Three wordings of one fact are three things that
can drift, and two of them had already: the `init` template said *"Switch to openai-embeddings for
relevance"* — the vendor, an account — while G21 had settled that the account-free path is a local
server, and the example file said something else again. `docs/02-extension-model.md`'s two-lists
argument, applied to prose a user reads rather than to a list a program reads.

The comparison normalises whitespace and comment markers, because a sentence wrapped at 70 columns
in a TOML comment and the same sentence in a Python string are the same sentence. It does not
normalise words.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

import pytest

from weft_cli import commands
from weft_cli.commands import IndexCommandResult
from weft_cli.plugins_report import render_doctor
from weft_cli.render import render_outcome
from weft_engine.registry_bootstrap import Dependencies
from weft_engine.services import DEFAULT_EMBEDDER_MEANING, ServiceSelection
from weft_kernel.context import Context, ServiceRegistry
from weft_kernel.discovery import PackReport, PackStatus
from weft_kernel.payload import Produced
from weft_kernel.registry import Registry
from weft_kernel.runner import RunSummary

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
CONFIG_EXAMPLE: Final[Path] = REPO_ROOT / "weft.toml.example"


def _normalised(text: str) -> str:
    """`text` with comment markers and line breaks removed — the same sentence, one line."""
    return re.sub(r"\s+", " ", re.sub(r"^\s*#\s?", "", text, flags=re.MULTILINE)).strip()


def test_the_sentence_is_worth_single_sourcing() -> None:
    """The floor: an empty or trivial constant would make every assertion below vacuous."""
    # Assert
    assert len(DEFAULT_EMBEDDER_MEANING) > 80, (
        "the shared sentence is too short to be saying what a first-hour user needs — that the "
        "default carries no meaning, and what to set instead"
    )
    assert "hash" in DEFAULT_EMBEDDER_MEANING
    assert "[services] embed" in DEFAULT_EMBEDDER_MEANING


def test_weft_index_says_it() -> None:
    """`R17.6`'s stderr line, which now quotes the shared sentence rather than restating it.

    Asserted through `render_outcome`, the seam `weft index` actually renders through, rather
    than through the private helper that builds the line — the wiring between the two is part of
    what this task is about.
    """
    # Arrange
    result = IndexCommandResult(
        summary=RunSummary(produced=1, nothing_to_produce=0, failed=0),
        stored_count=2,
        documents_discovered=2,
        documents_indexed=2,
        defaulted_embedder="hash",
    )

    # Act
    rendered = render_outcome(Produced(value=result))

    # Assert
    assert rendered.stderr is not None
    assert _normalised(DEFAULT_EMBEDDER_MEANING) in _normalised(rendered.stderr)


def test_plugins_doctor_says_it_when_nobody_chose_an_embedder() -> None:
    """The surface that said nothing — and the one an operator runs when something looks wrong."""
    # Arrange
    reports = (PackReport(pack="store", distribution="weft-rag", status=PackStatus.ACTIVE),)

    # Act
    rendered = render_doctor(reports, defaulted_embedder="hash")

    # Assert
    assert _normalised(DEFAULT_EMBEDDER_MEANING) in _normalised(rendered)


def test_plugins_doctor_is_silent_when_an_embedder_was_chosen() -> None:
    """A choice made is not a choice to warn about — `R17.6`'s rule, held one surface over.

    This is the assertion that keeps the block from becoming noise every operator learns to
    scroll past, which is how a warning stops being read.
    """
    # Arrange
    reports = (PackReport(pack="store", distribution="weft-rag", status=PackStatus.ACTIVE),)

    # Act
    rendered = render_doctor(reports)

    # Assert
    assert _normalised(DEFAULT_EMBEDDER_MEANING) not in _normalised(rendered)


def test_the_example_configuration_says_it() -> None:
    """`weft.toml.example` — the file a reader opens to find out what they may set."""
    # Act
    example = _normalised(CONFIG_EXAMPLE.read_text(encoding="utf-8"))

    # Assert
    assert _normalised(DEFAULT_EMBEDDER_MEANING) in example


async def test_weft_init_scaffolds_it(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The `weft.toml` a first-hour user actually gets, which is not the example file.

    Its own wording said *"Switch to openai-embeddings for relevance"* until 2026-09-13 — the
    vendor, which needs an account, on a page whose whole argument is that the first hour does
    not. Read off the file the command writes, the same way
    `tests/unit/weft_cli/test_commands.py` drives it, rather than off the template constant.
    """
    # Arrange
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(commands, "DEFAULT_CONFIG_PATH", tmp_path / "weft.toml")
    deps = Dependencies(registry=Registry(), reports=(), services=ServiceSelection())
    services = ServiceRegistry()
    services.add(Dependencies, deps)
    ctx = Context(tenant_id="t", run_id="r", trace_id="tr", locale="en", services=services)

    # Act
    await commands.InitCommand().run(commands.NoArgs(), ctx)

    # Assert
    scaffolded = _normalised((tmp_path / "weft.toml").read_text(encoding="utf-8"))
    assert _normalised(DEFAULT_EMBEDDER_MEANING) in scaffolded
