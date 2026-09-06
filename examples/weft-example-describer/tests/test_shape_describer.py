"""This pack's own tests — the fourth canonical file `docs/07-extension-cost.md` names.

Collected by weft's own gate through its `examples-tests` step, and still runnable on its own with
`uv run pytest` from inside this directory, which is how a stranger runs it.
"""

import io

from weft_example_describer.shape_describer import ShapeDescriber

from weft_kernel.payload import NothingToProduce, Produced


def _png(width: int, height: int) -> bytes:
    """A minimal PNG header — enough for `_png_size`, without an imaging dependency."""
    import struct
    import zlib

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    chunk = struct.pack(">I", len(ihdr)) + b"IHDR" + ihdr
    chunk += struct.pack(">I", zlib.crc32(b"IHDR" + ihdr))
    return b"\x89PNG\r\n\x1a\n" + chunk


async def test_it_describes_an_image_by_its_dimensions() -> None:
    # Act
    outcome = await ShapeDescriber().describe(_png(640, 480), "image/png", "What is this?")

    # Assert
    assert isinstance(outcome, Produced)
    assert "640" in outcome.value
    assert "480" in outcome.value


async def test_the_instruction_reaches_the_answer() -> None:
    """It cannot obey one, and says so rather than answering plausibly and wrongly."""
    # Act
    outcome = await ShapeDescriber().describe(_png(8, 8), "image/png", "Name the axes.")

    # Assert
    assert isinstance(outcome, Produced)
    assert "Name the axes." in outcome.value
    assert "cannot say what the picture shows" in outcome.value


async def test_bytes_it_cannot_read_are_nothing_to_produce_rather_than_an_error() -> None:
    """An absence, not a failure: a caller with forty more figures should keep going."""
    # Act
    outcome = await ShapeDescriber().describe(b"not an image", "image/jpeg", "What is this?")

    # Assert
    assert isinstance(outcome, NothingToProduce)


async def test_a_truncated_png_is_refused_rather_than_guessed_at() -> None:
    """The edge case a hand-written header parser has to get right."""
    # Act
    outcome = await ShapeDescriber().describe(b"\x89PNG\r\n\x1a\n", "image/png", "What?")

    # Assert
    assert isinstance(outcome, NothingToProduce)


def test_the_reader_needs_no_imaging_library() -> None:
    """The point of the example: its dependencies are weft and nothing else."""
    # Arrange
    from pathlib import Path

    import weft_example_describer.shape_describer as module

    source = Path(str(module.__file__)).read_text(encoding="utf-8")

    # Act / Assert
    for library in ("PIL", "Pillow", "cv2", "numpy"):
        assert library not in source
    assert io is not None
