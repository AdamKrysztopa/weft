"""Unit tests for `weft_cli.argparse_gen`.

Mirrors `packages/weft-rag/src/weft_cli/argparse_gen.py`. Covers the one convention this module
promises — a required field becomes a positional, a defaulted field becomes a `--flag` with
underscores turned to hyphens, and a `StrEnum` becomes a `choices=`-bounded argument — plus the
one refusal it deliberately makes: a field type nothing here knows how to parse.
"""

from __future__ import annotations

import argparse
from enum import StrEnum

import pytest
from pydantic import BaseModel, ConfigDict, Field

from weft_cli.argparse_gen import UnsupportedArgumentTypeError, add_model_arguments


class _Format(StrEnum):
    TEXT = "text"
    JSON = "json"


class _Args(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    question: str = Field(description="the question to ask")
    top_k: int = Field(default=5, description="how many to retrieve")
    extract: str | None = Field(default=None, description="optional extractor name")
    format: _Format = Field(default=_Format.TEXT, description="how to render")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="test")
    add_model_arguments(parser, _Args)
    return parser


def test_required_field_becomes_a_positional() -> None:
    args = _parser().parse_args(["what changed?"])
    assert args.question == "what changed?"


def test_defaulted_int_field_becomes_a_hyphenated_flag() -> None:
    args = _parser().parse_args(["q", "--top-k", "3"])
    assert args.top_k == 3
    assert isinstance(args.top_k, int)


def test_defaulted_field_keeps_its_default_when_omitted() -> None:
    args = _parser().parse_args(["q"])
    assert args.top_k == 5
    assert args.extract is None


def test_str_or_none_field_becomes_a_plain_string_flag() -> None:
    args = _parser().parse_args(["q", "--extract", "docx"])
    assert args.extract == "docx"


def test_strenum_field_becomes_a_choices_bounded_flag() -> None:
    args = _parser().parse_args(["q", "--format", "json"])
    assert args.format is _Format.JSON


def test_strenum_field_rejects_a_spelling_outside_the_enum() -> None:
    with pytest.raises(SystemExit):
        _parser().parse_args(["q", "--format", "yaml"])


def test_unsupported_annotation_is_refused_loudly() -> None:
    class _Unsupported(BaseModel):
        model_config = ConfigDict(frozen=True, extra="forbid")

        paths: tuple[str, ...] = ()

    with pytest.raises(UnsupportedArgumentTypeError):
        add_model_arguments(argparse.ArgumentParser(), _Unsupported)


# --- bool support (task 3.7, `weft config get --origin`) ------------------------------


class _BoolArgs(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    origin: bool = Field(default=False, description="show where each value came from")


def test_false_defaulting_bool_field_becomes_a_store_true_flag() -> None:
    parser = argparse.ArgumentParser(prog="test")
    add_model_arguments(parser, _BoolArgs)

    assert parser.parse_args([]).origin is False
    assert parser.parse_args(["--origin"]).origin is True


def test_required_bool_field_is_refused_loudly() -> None:
    class _RequiredBool(BaseModel):
        model_config = ConfigDict(frozen=True, extra="forbid")

        flag: bool

    with pytest.raises(UnsupportedArgumentTypeError):
        add_model_arguments(argparse.ArgumentParser(), _RequiredBool)


def test_true_defaulting_bool_field_is_refused_loudly() -> None:
    class _TrueDefaultBool(BaseModel):
        model_config = ConfigDict(frozen=True, extra="forbid")

        flag: bool = True

    with pytest.raises(UnsupportedArgumentTypeError):
        add_model_arguments(argparse.ArgumentParser(), _TrueDefaultBool)
