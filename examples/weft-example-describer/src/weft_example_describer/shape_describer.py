"""`ShapeDescriber` — a stranger's `Describer` that calls no model at all.

Satisfies `weft_vision.contract.Describer` **structurally**: this module never imports the
Protocol, the same path `weft_example_chunker.WordChunker` takes for `Chunker`.

**Deliberately not a second API client.** weft's own `openai-vision` is a hosted vision model, and
a second one would prove only that two packs can hold two credentials. What the contract actually
claims is that it *names the medium and not the model* — so the cheapest way to test that claim is
an implementation with no model in it whatsoever. This one reports the image's own dimensions and
format, which is a true description, requires no network, no key and no weights, and could not be
written at all against a contract that had a `model=` argument or a provider in its name.

It is also what a local implementation looks like from the outside: weft's `9.9` line says *"a
local or hosted VLM is the same plugin with a different `base_url`"*, and a describer that reaches
neither is the limiting case of that.
"""

import io
import struct

from weft_kernel.payload import NothingToProduce, Outcome, Produced


class ShapeDescriber:
    """Describes an image by what can be read from its own header, and nothing more."""

    def __init__(self, config: object = None) -> None:
        del config  # a service takes no stage configuration; it has no pipeline position

    async def describe(self, data: bytes, media_type: str, instruction: str) -> Outcome[str]:
        """The image's format and dimensions, in a sentence.

        `instruction` is echoed rather than obeyed — this describer has no way to answer a
        question about content, and pretending otherwise would be the kind of plausible-but-wrong
        answer weft's own rules refuse. An unreadable image is `NothingToProduce`: an absence, not
        an error, because a caller with forty more figures should keep going.
        """
        size = _png_size(data)
        if size is None:
            return NothingToProduce(
                reason=f"this describer reads PNG headers only, and {media_type!r} is not one"
            )
        width, height = size
        return Produced(
            value=(
                f"A {width} by {height} pixel image. Asked: {instruction!r}. This describer "
                f"reads image headers and cannot say what the picture shows."
            )
        )


def _png_size(data: bytes) -> tuple[int, int] | None:
    """`(width, height)` from a PNG's IHDR chunk, or `None` if these are not PNG bytes.

    Hand-parsed rather than through an imaging library, so this pack depends on nothing but weft
    itself — an example whose dependencies are its own point would be a worse example.
    """
    header = data[:8]
    if header != b"\x89PNG\r\n\x1a\n":
        return None
    reader = io.BytesIO(data[8:])
    length_and_type = reader.read(8)
    if len(length_and_type) < 8 or length_and_type[4:] != b"IHDR":
        return None
    dimensions = reader.read(8)
    if len(dimensions) < 8:
        return None
    width, height = struct.unpack(">II", dimensions)
    return width, height
