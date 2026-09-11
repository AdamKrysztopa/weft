"""A command quoted in a shipped pipeline comment is one that runs — ledger task **8.17**.

`docs/internal/lessons-archive.md` `L8.14`. `index-text.yaml`'s own comment told an operator to run
`weft pipeline derive index-text --set embed.use=openai`. There is no `--set` flag and never has
been; the comment was hand-repaired and nothing stopped the next one. `docs/08-manuals.md` §3's
tagged-sample harness is scoped to `manual/`, and a pipeline document carries more operator-facing
advice per line than anything else this project ships — every one of the twenty-six is read by
somebody deciding what to type next.

**The verdict comes from the real parser, not from a reimplementation of it.** `weft_cli.cli`'s own
docstring commits the CLI to generating its grammar from the registry — "core has no list of
commands to edit" — so the only honest question to ask of a quoted command is the one a shell asks:
hand the tokens to `build_parser(...)` and see what argparse says. Walking `parser._actions` to
rebuild the subcommand tree here would be a second opinion about a grammar that already has a first
one, and it would go on agreeing with itself after `argparse_gen` changed.

**What is checked is the vocabulary, not the completeness**, and the three failure shapes argparse
produces are what makes that distinction available rather than invented:

- `unrecognized arguments: --pipeline` — the command exists and that flag does not. **A failure.**
- `invalid choice: 'nosuchcmd'` — no such subcommand. **A failure.**
- `the following arguments are required: path` — the command and every flag named are real, and
  the comment simply did not spell out a positional. **Not a failure**: `` `weft index`'s four
  stages `` is possessive prose, and a check that demanded a runnable invocation there would force
  twenty-six documents to stop referring to commands by name.

That line is drawn at what a reader can *copy wrongly*. A name they must complete themselves they
will complete against `--help`; a flag that does not exist they will type verbatim and meet exit 2.
"""

from __future__ import annotations

import contextlib
import io
import re
import shlex
from argparse import ArgumentParser
from functools import cache
from pathlib import Path
from typing import Final

#: Spans this check cannot return a verdict on. **Pinned empty**, and an entry is a visible act in
#: a diff rather than a silent edit — the ratchet `docs/01-high-level-plan.md` → *Fitness functions*
#: uses throughout. A span belongs here only if argparse cannot answer for it at all; a span that
#: argparse says is wrong belongs in a repaired comment.
UNVERIFIABLE_COMMANDS: Final[frozenset[str]] = frozenset()

#: A backticked span in a comment whose content is the CLI binary followed by anything, or the
#: binary alone. `weft.toml`, `weft-embed` and `weft_cli.ingest` are deliberately excluded by the
#: boundary: a settings file, a distribution and a module path are not commands, and the sweep that
#: produced this task found all three quoted in these same comments.
_QUOTED_COMMAND: Final[re.Pattern[str]] = re.compile(r"`(weft(?:\s+[^`]*)?)`")

#: argparse's own words for "this token is not part of my grammar", either of which means the
#: comment names something that does not exist. Read off the live parser rather than assumed —
#: `docs/internal/lessons.md` L6.4, read the population and not the declaration.
_VOCABULARY_FAILURES: Final[tuple[str, ...]] = ("unrecognized arguments:", "invalid choice:")


def _shipped_pipeline_documents() -> list[Path]:
    """Every pipeline document the installed `weft_retrieve` ships, from the package itself.

    Not a repository glob: the subject of this check is what an operator's installation contains,
    and reading it off `weft_retrieve.__file__` is the same fact asked of the same artefact. A
    checkout-relative path would answer for the checkout and be asked in the artefact environment
    anyway (`docs/internal/lessons.md` L6.25's distinction, applied one file down).
    """
    import weft_retrieve

    return sorted((Path(weft_retrieve.__file__).parent / "pipelines").glob("*.yaml"))


def _comment_blocks(yaml_text: str) -> list[str]:
    """Consecutive comment lines, joined into one string each.

    Joined because these documents wrap at the house width and a quoted command routinely straddles
    a line — `preview-plain.yaml`'s own does. `docs/internal/lessons.md` L6.16: a sweep that cannot
    cross a line break has a false negative built into the house style.
    """
    blocks: list[str] = []
    current: list[str] = []
    for line in yaml_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            current.append(stripped.lstrip("#").strip())
        elif current:
            blocks.append(" ".join(current))
            current = []
    if current:
        blocks.append(" ".join(current))
    return blocks


def quoted_commands(yaml_text: str) -> list[str]:
    """Every backticked `weft ...` span in `yaml_text`'s comments, in order."""
    return [
        match.group(1).strip()
        for block in _comment_blocks(yaml_text)
        for match in _QUOTED_COMMAND.finditer(block)
    ]


@cache
def _parser() -> ArgumentParser:
    from weft_cli.cli import build_parser
    from weft_cli.contract_reference import discover_for_reference

    return build_parser(discover_for_reference())


def vocabulary_failure(command: str, parser: ArgumentParser) -> str | None:
    """What argparse objects to in `command`, or `None` when every name in it is real.

    A missing positional is not an objection — see this module's own docstring for where the line
    is drawn and why it is drawn there.
    """
    tokens = shlex.split(command)[1:]
    captured = io.StringIO()
    try:
        with contextlib.redirect_stderr(captured), contextlib.redirect_stdout(io.StringIO()):
            parser.parse_args(tokens)
    except SystemExit:
        message = captured.getvalue()
        if any(shape in message for shape in _VOCABULARY_FAILURES):
            return message.strip().splitlines()[-1].strip()
    return None


def test_at_least_one_pipeline_document_quotes_a_command() -> None:
    # The floor. A sweep matching nothing passes identically to one finding nothing wrong
    # (`docs/internal/lessons.md` L5.19), and this one's subject is a directory whose contents could
    # move.
    documents = _shipped_pipeline_documents()
    assert documents, "weft_retrieve ships no pipeline documents — the sweep read nothing"

    quoted = [
        command
        for document in documents
        for command in quoted_commands(document.read_text(encoding="utf-8"))
    ]
    assert quoted, (
        f"none of the {len(documents)} shipped pipeline documents quotes a `weft ...` command, so "
        f"this check compares nothing"
    )


def test_every_quoted_command_names_only_things_that_exist() -> None:
    # Arrange
    parser = _parser()

    # Act
    wrong = {
        f"{document.name}: {command}": objection
        for document in _shipped_pipeline_documents()
        for command in quoted_commands(document.read_text(encoding="utf-8"))
        if command not in UNVERIFIABLE_COMMANDS
        and (objection := vocabulary_failure(command, parser)) is not None
    }

    # Assert
    assert not wrong, (
        f"these shipped pipeline documents quote a command that names something the CLI does not "
        f"have: {wrong}. An operator copies the line and meets exit 2 (lessons-archive L8.14)."
    )


def test_a_missing_positional_is_not_reported() -> None:
    # The line this check draws, asserted rather than left to the failure list to imply. Both of
    # these are real prose in the shipped set, and neither is a defect.
    parser = _parser()
    assert vocabulary_failure("weft eval", parser) is None
    assert vocabulary_failure("weft index", parser) is None


def test_the_check_can_actually_fail() -> None:
    # Plant the exact shape task 8.17 was filed for, through the same helpers the sweep uses —
    # a flag that does not exist, and a subcommand that does not exist.
    planted = (
        "# one plain-text document — `weft render ./docs --pipeline preview-plain`. The\n"
        "# question it answers is\n"
    )
    assert quoted_commands(planted) == ["weft render ./docs --pipeline preview-plain"]

    parser = _parser()
    assert vocabulary_failure("weft render ./docs --pipeline preview-plain", parser) is not None
    assert vocabulary_failure("weft pipeline derive index-text --set embed.use=openai", parser)
    assert vocabulary_failure("weft nosuchcommand", parser) is not None
    assert vocabulary_failure("weft render ./docs preview-plain", parser) is None


def test_the_waiver_is_a_visible_act() -> None:
    # The two-way ratchet. An entry that no longer matches a real span is as much a defect as a
    # missing one: it is a waiver nobody can see has stopped applying.
    quoted = {
        command
        for document in _shipped_pipeline_documents()
        for command in quoted_commands(document.read_text(encoding="utf-8"))
    }
    stale = sorted(UNVERIFIABLE_COMMANDS - quoted)
    assert not stale, (
        f"UNVERIFIABLE_COMMANDS waives spans no shipped pipeline document quotes any more: {stale}"
    )
