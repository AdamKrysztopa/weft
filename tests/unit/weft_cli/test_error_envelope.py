"""Unit tests for `weft_cli.error_envelope`.

Mirrors `packages/weft-cli/src/weft_cli/error_envelope.py`. Task **5.2d**: the structured
error envelope `weft_cli.render.render_refusal` emits under `--json` — see that module's own
docstring for the full argument (S6/G9, `docs/09-release.md` §3).
"""

from __future__ import annotations

import json

from weft_cli.error_envelope import ENVELOPE_VERSION, build_error_envelope
from weft_cli.exit_codes import ExitCode
from weft_kernel.errors import WeftError
from weft_kernel.registry import UnknownPluginError


def test_build_error_envelope_carries_the_subclass_name_the_rendered_text_and_the_exit_code() -> (
    None
):
    # Arrange
    exc = WeftError("something in the library refused")

    # Act
    envelope = build_error_envelope(exc, exit_code=ExitCode.OPERATION_FAILED)

    # Assert
    assert envelope.error == "WeftError"
    assert envelope.rendered == "something in the library refused"
    assert envelope.exit_code is ExitCode.OPERATION_FAILED


def test_build_error_envelope_carries_valid_options_for_an_unresolved_name_error() -> None:
    # Arrange
    exc = UnknownPluginError(
        "unknown retriever: 'graf'", valid_options=("graph", "vector", "boolean")
    )

    # Act
    envelope = build_error_envelope(exc, exit_code=ExitCode.RESOLUTION_FAILED)

    # Assert
    assert envelope.error == "UnknownPluginError"
    assert envelope.valid_options == ("graph", "vector", "boolean")


def test_build_error_envelope_omits_valid_options_for_a_plain_weft_error() -> None:
    # Arrange
    exc = WeftError("no alternatives to offer here")

    # Act
    envelope = build_error_envelope(exc, exit_code=ExitCode.OPERATION_FAILED)

    # Assert
    assert envelope.valid_options is None


def test_build_error_envelope_carries_the_seam_s_own_attribution() -> None:
    # Arrange — the four fields `weft_kernel.seam.wrap` fills in on a caught `WeftError`,
    # set by hand here the way the seam itself would after attributing a real failure.
    exc = WeftError("boom")
    exc.pack = "acme-cmd"
    exc.contract = "Command"
    exc.plugin = "ask"
    exc.stage = "command:ask"

    # Act
    envelope = build_error_envelope(exc, exit_code=ExitCode.OPERATION_FAILED)

    # Assert
    assert (envelope.pack, envelope.contract, envelope.plugin, envelope.stage) == (
        "acme-cmd",
        "Command",
        "ask",
        "command:ask",
    )


def test_error_envelope_carries_its_own_version_in_the_dumped_bytes() -> None:
    # Arrange
    exc = WeftError("boom")
    envelope = build_error_envelope(exc, exit_code=ExitCode.OPERATION_FAILED)

    # Act
    dumped = json.loads(envelope.model_dump_json())

    # Assert — `ClassVar`s never reach `model_dump_json()`; this is a plain field, so it does.
    assert dumped["envelope_version"] == ENVELOPE_VERSION


def test_error_envelope_serialises_the_exit_code_as_a_plain_int_a_script_can_compare() -> None:
    # Arrange
    exc = WeftError("boom")
    envelope = build_error_envelope(exc, exit_code=ExitCode.RESOLUTION_FAILED)

    # Act
    dumped = json.loads(envelope.model_dump_json())

    # Assert
    assert dumped["exit_code"] == int(ExitCode.RESOLUTION_FAILED)
