"""Turn a `Command.args_model` into argparse arguments.

Turning a `Command.args_model` into argparse arguments — the mechanism that keeps
`weft --help` and every subcommand's own grammar from drifting out of sync with what a
`Command` actually declares.

Task **3.2**: "Argument parsing feeds a command's `args_model`, so `run` receives a
validated model rather than an `argparse.Namespace`." One convention, applied mechanically
to every field of every registered command's `args_model`, first-party or a stranger's:

- **A field with no default is a required positional**, named for the field itself —
  `path: str` becomes `weft index <path>`, exactly the grammar `weft index` already had.
- **A field with a default is an optional flag**, `--` plus the field's own name with every
  underscore turned to a hyphen (`top_k` becomes `--top-k`) — the identical spelling the
  hand-written grammar already used for every flag Phase 0–2 shipped, so no existing
  invocation's flags change.
- **A `StrEnum` field becomes a `choices=`-bounded flag or positional**, `argparse`'s own
  loud-refusal-with-valid-options behaviour for a spelling nothing in the enum matches — `01`
  requirement 5, for free, the same way `AskFormat`'s hand-written `choices=tuple(AskFormat)`
  already worked before this task.

**What this deliberately does not support.** A field whose annotation is not `str`, `int`,
`bool`, `list[str]`, an `X | None` wrapping any of those, or a `StrEnum`, refuses loudly at
parser-construction time — a `UnsupportedArgumentTypeError` naming the field and its
annotation — rather than guessing a `type=str` and silently mis-parsing whatever a future
command's richer `args_model` needs. This is the honest floor for the five commands task 3.2
shipped (every field is one of the three shapes that existed then); a `Command` whose grammar
needs a `Path` or a nested model is outside this task's brief and gets a named refusal instead
of a wrong parse.

**`list[str]`, added ledger task 34.8, for `weft target promote --evidence <live-run>
<candidate-run>`.** The one shape this generator gives a `list[str]` field: an optional flag
taking exactly `nargs=2` values, never a required positional (there is no honest single-token
spelling for "a list, required"), and never a variable count — `TargetPromoteCommand.run`'s own
"exactly two run ids" is what the grammar enforces, not a runtime length check.

**`bool`, added task 3.7, for `weft config get --origin`.** `docs/03-cli.md` → *Project
context* needs one boolean flag and none of the three existing shapes can express it — a
`StrEnum` of two members would work mechanically but would make `--origin true`/`--origin
false` the spelling instead of the ordinary `--origin` presence/absence every other CLI
flag in this generated grammar already uses (`--yes`, `--json`, `--quiet`, all hand-declared
on `weft_cli.cli`'s own parsers, never through this module, because none of them was a
`Command.args_model` field until now). A `bool` field is a required-`False`-default flag,
`action="store_true"` — the only shape a boolean CLI argument honestly has when nothing
downstream needs to *set* it back to `False` for one invocation. A `bool` field with no
default, or one defaulting to `True`, is refused rather than guessed at: a required
boolean positional is not a shape `argparse` gives an honest spelling to, and a
`True`-defaulting flag would need `action="store_false"`, a real but currently unneeded
shape left for whichever field first asks for it.
"""

from __future__ import annotations

import argparse
import types
import typing
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ValidationError
from pydantic.fields import FieldInfo

from weft_kernel.errors import WeftError


class UnsupportedArgumentTypeError(WeftError):
    """Names the pack-author field that keeps `weft --help` from building its grammar.

    A `Command.args_model` field's annotation has no generic argparse mapping — see the
    module docstring's *"What this deliberately does not support."*
    """


class CommandArgumentsError(WeftError):
    """Raised when a parsed `Namespace` breaks its `Command.args_model`'s constraints.

    A parsed `Namespace` broke its `Command.args_model`'s own constraint — a `Field` bound
    or a `field_validator`/`model_validator` — reported as a usage error rather than the raw
    `pydantic.ValidationError`. See `build_command_arguments_error` for how the message is built.
    """


def add_model_arguments(parser: argparse.ArgumentParser, model: type[BaseModel]) -> None:
    """Every field of `model` becomes one argument on `parser` — see the module docstring."""
    for field_name, field_info in model.model_fields.items():
        _add_field(parser, field_name, field_info)


def field_spelling(field_name: str, field_info: FieldInfo) -> str:
    """Keep the parser and its refusal messages naming each argument identically.

    How `field_name` is spelled on the generated command line — the bare name for a
    required positional, `--` plus the name with `_` -> `-` for a defaulted flag. The one
    function `_add_field`, `_add_bool_field` and `build_command_arguments_error` all call, so
    the grammar and a refused argument's own name cannot drift apart.
    """
    if field_info.is_required():
        return field_name
    return "--" + field_name.replace("_", "-")


def _add_field(parser: argparse.ArgumentParser, field_name: str, field_info: FieldInfo) -> None:
    # `dict[str, Any]`, not `dict[str, object]`: this dict's values feed `add_argument`'s own
    # `**kwargs`, whose keyword parameters (`type`, `choices`, `default`, ...) each have their
    # own, different static type — `Any` is what lets one dynamically-built mapping cross that
    # boundary at all; `object` would make every one of them a type error at the call site
    # below, for a shape `argparse` itself only checks at runtime.
    kwargs: dict[str, Any] = {}
    if field_info.description:
        kwargs["help"] = field_info.description

    if _is_str_list(field_info.annotation):
        _add_str_list_field(parser, field_name, field_info, help_kwargs=kwargs)
        return

    scalar = _scalar_type(field_info.annotation, field_name=field_name)

    if scalar is bool:
        _add_bool_field(parser, field_name, field_info, help_kwargs=kwargs)
        return

    if issubclass(scalar, StrEnum):
        kwargs["type"] = scalar
        kwargs["choices"] = tuple(scalar)
    elif scalar is int:
        kwargs["type"] = int
    elif scalar is not str:
        raise UnsupportedArgumentTypeError(
            f"field '{field_name}' has type {scalar!r}, which no generated argument grammar "
            f"knows how to parse from the command line. Supported: str, int, bool, a "
            f"StrEnum, or any of those wrapped in `| None`."
        )

    if field_info.is_required():
        parser.add_argument(field_spelling(field_name, field_info), **kwargs)
        return

    default = field_info.get_default(call_default_factory=True)
    parser.add_argument(
        field_spelling(field_name, field_info), dest=field_name, default=default, **kwargs
    )


def _is_str_list(annotation: object) -> bool:
    """Tell whether `annotation` is exactly `list[str]`.

    `annotation` is exactly `list[str]` — never `list[int]` or any other element type, which
    this generator has no spelling for and refuses on `_scalar_type`'s own footing once this
    returns `False` and `_add_field` falls through to it.
    """
    return typing.get_origin(annotation) is list and typing.get_args(annotation) == (str,)


def _add_str_list_field(
    parser: argparse.ArgumentParser,
    field_name: str,
    field_info: FieldInfo,
    *,
    help_kwargs: dict[str, Any],
) -> None:
    """Add `field_name` to `parser` as an `nargs=2` flag.

    `field_name` as an `nargs=2` flag — see the module docstring's own paragraph on why two
    is the one count this generator commits to, and why a `list[str]` field is never a required
    positional.
    """
    if field_info.is_required():
        raise UnsupportedArgumentTypeError(
            f"field '{field_name}' is a list[str] with no default — a list argument must be "
            f"an optional flag taking two values (`--{field_name.replace('_', '-')} A B`), "
            f"never a required positional. Give it a default of `[]`."
        )
    default = field_info.get_default(call_default_factory=True)
    parser.add_argument(
        field_spelling(field_name, field_info),
        dest=field_name,
        nargs=2,
        default=default,
        **help_kwargs,
    )


def _add_bool_field(
    parser: argparse.ArgumentParser,
    field_name: str,
    field_info: FieldInfo,
    *,
    help_kwargs: dict[str, Any],
) -> None:
    """Add `field_name` to `parser` as an `action="store_true"` flag.

    `field_name` as an `action="store_true"` flag — see the module docstring's own
    paragraph on why this is the one shape a generated boolean flag has today.
    """
    if field_info.is_required():
        raise UnsupportedArgumentTypeError(
            f"field '{field_name}' is a bool with no default — a boolean argument must be "
            f"an optional flag (`--{field_name.replace('_', '-')}`), never a required "
            f"positional. Give it a default of `False`."
        )
    default = field_info.get_default(call_default_factory=True)
    if default is not False:
        raise UnsupportedArgumentTypeError(
            f"field '{field_name}' is a bool defaulting to {default!r} — only a "
            f"`False`-defaulting bool (`action='store_true'`) is supported today."
        )
    parser.add_argument(
        field_spelling(field_name, field_info), dest=field_name, action="store_true", **help_kwargs
    )


def _scalar_type(annotation: object, *, field_name: str) -> type:
    """`annotation` with any `X | None` wrapper removed, refusing anything else union-shaped."""
    origin = typing.get_origin(annotation)
    if origin is typing.Union or origin is types.UnionType:
        members = [arg for arg in typing.get_args(annotation) if arg is not type(None)]
        if len(members) == 1:
            return _scalar_type(members[0], field_name=field_name)
        raise UnsupportedArgumentTypeError(
            f"field '{field_name}' has annotation {annotation!r}, a union of more than one "
            f"non-`None` type — no generated argument grammar knows how to parse that from "
            f"the command line."
        )
    if isinstance(annotation, type):
        return annotation
    raise UnsupportedArgumentTypeError(
        f"field '{field_name}' has annotation {annotation!r}, which is not a class — no "
        f"generated argument grammar knows how to parse that from the command line."
    )


def build_command_arguments_error(
    model: type[BaseModel], exc: ValidationError
) -> CommandArgumentsError:
    """Translate a `model(**payload)` validation error into a `CommandArgumentsError`.

    `exc`, raised by `model(**payload)`, translated into a `CommandArgumentsError` — one
    line per pydantic error, `argument <spelling>: <msg>`, `<spelling>` from `field_spelling`
    so it cannot say anything `add_model_arguments` did not also generate. An error whose
    `loc` names no field — a `model_validator` — is reported as `arguments: <msg>` instead.
    """
    lines: list[str] = []
    for error in exc.errors():
        msg = error["msg"].removeprefix("Value error, ")
        loc = error["loc"]
        if not loc:
            lines.append(f"arguments: {msg}")
            continue
        field_name = str(loc[0])
        field_info = model.model_fields.get(field_name)
        spelling = field_spelling(field_name, field_info) if field_info is not None else field_name
        lines.append(f"argument {spelling}: {msg}")
    return CommandArgumentsError("\n".join(lines))
