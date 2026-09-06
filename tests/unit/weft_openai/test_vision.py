"""`openai-vision` — the first `Describer`, ledger task `9.9`.

It lives here, in the pack that already holds the provider's client, for the reason `9.9` states:
*"its first implementation lives in the pack that already holds the provider's client"*. A second
distribution for one plugin would need `weft-openai` as a dependency to reach `build_client`, which
is the inverted-dependency shape this tree refuses elsewhere.

**Three properties beyond "it calls the API", and each is in the ledger line.**

*Resizes off the event loop.* Pillow's decode-and-resize is CPU-bound and holds the loop; G6 settles
that a CPU-bound stage is still `async def` and offloads its own work, and `weft_pdf.pdf_layout` is
the shape. FF7(b) cannot see CPU-bound work, so `weft_kernel.blocking.guard` is armed directly here
— a *service* passes through no seam wrap and nothing catches this for it.

*One resize invariant: always PNG, bounded max pixels.* In the plugin, not the contract, because it
is this provider's cost and limit rather than a fact about describing images. A page crop from a
600-DPI scan is megabytes, and the bill and the latency are both linear in it.

*Natively cancellable.* `CancelledError` propagates untouched, which for an `httpx`-backed SDK means
not wrapping the call in a bare `except Exception`.

**A missing credential is refused at use, naming the line that fixes it.** `weft_openai.embedder`'s
own `MissingApiKeyError` reasoning applies unchanged: pack settings validate before `register()`, so
a required credential would make a machine without one report a pack that contributed nothing —
and a plugin absent from the registry is absent from the contract reference, from FF11's resolution
check, and from everything else that walks what is installed.
"""

from typing import Any

import pytest

from weft_kernel.blocking import guard
from weft_kernel.payload import Failed, NothingToProduce, Produced
from weft_openai.settings import Settings
from weft_openai.vision import (
    MAX_PIXELS,
    OpenAIVisionConfig,
    OpenAIVisionDescriber,
    prepared_image,
)
from weft_vision.contract import Describer


def _png(width: int = 8, height: int = 8) -> bytes:
    """A real PNG of `width` x `height`, built with Pillow — the library the plugin resizes with."""
    import io

    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (128, 128, 128)).save(buffer, format="PNG")
    return buffer.getvalue()


class _RecordingClient:
    """Stands in for the vendor SDK's chat surface, recording what it was handed."""

    def __init__(self, reply: str = "A bar chart of revenue by region.") -> None:
        self.reply = reply
        self.calls: list[dict[str, Any]] = []

    async def describe(self, **kwargs: Any) -> str:
        self.calls.append(kwargs)
        return self.reply


def _describer(client: object, **config: Any) -> OpenAIVisionDescriber:
    return OpenAIVisionDescriber(
        Settings(api_key="sk-test"),  # type: ignore[arg-type]
        OpenAIVisionConfig(**config),
        client=client,
    )


async def test_it_satisfies_the_describer_contract() -> None:
    # Act / Assert
    assert isinstance(_describer(_RecordingClient()), Describer)


async def test_a_description_comes_back_as_produced() -> None:
    """The happy path: bytes in, one string out, wrapped in the outcome the contract names."""
    # Arrange
    describer = _describer(_RecordingClient("A bar chart of revenue by region."))

    # Act
    outcome = await describer.describe(_png(), "image/png", "Describe this figure.")

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value == "A bar chart of revenue by region."


async def test_an_empty_reply_is_nothing_to_produce_rather_than_an_empty_string() -> None:
    """A model that returned nothing has not described the image, and `""` in a node's content
    would be indistinguishable from a caption that happened to be blank — `02` §1's `Outcome` rule.
    """
    # Act
    outcome = await _describer(_RecordingClient("   ")).describe(_png(), "image/png", "Describe.")

    # Assert
    assert isinstance(outcome, NothingToProduce)


async def test_a_provider_error_is_failed_and_names_what_happened() -> None:
    """One figure the provider refused must not end a run that has forty more to describe."""

    # Arrange
    class _Refusing:
        async def describe(self, **kwargs: Any) -> str:
            del kwargs
            raise RuntimeError("rate limited")

    # Act
    outcome = await _describer(_Refusing()).describe(_png(), "image/png", "Describe.")

    # Assert
    assert isinstance(outcome, Failed)
    assert "rate limited" in outcome.reason


async def test_cancellation_propagates_rather_than_becoming_a_failed_outcome() -> None:
    """G6, and the reason a bare `except Exception` is wrong here: `CancelledError` is not a fact
    about this image."""
    # Arrange
    import asyncio

    class _Cancelling:
        async def describe(self, **kwargs: Any) -> str:
            del kwargs
            raise asyncio.CancelledError

    # Act / Assert
    with pytest.raises(asyncio.CancelledError):
        await _describer(_Cancelling()).describe(_png(), "image/png", "Describe.")


async def test_no_credential_is_refused_at_use_naming_the_line_that_fixes_it() -> None:
    """`weft_openai.embedder.MissingApiKeyError`'s reasoning, unchanged."""
    # Arrange
    from weft_openai.vision import MissingApiKeyError

    describer = OpenAIVisionDescriber(Settings(), OpenAIVisionConfig(), client=_RecordingClient())

    # Act / Assert
    with pytest.raises(MissingApiKeyError, match=r"\[packs\.openai\]"):
        await describer.describe(_png(), "image/png", "Describe.")


def test_an_oversized_image_is_resized_and_re_encoded_as_png() -> None:
    """The one resize invariant: always PNG, bounded max pixels. In the plugin, not the contract."""
    # Arrange
    import io

    from PIL import Image

    big = _png(4000, 4000)

    # Act
    prepared = prepared_image(big, "image/png")

    # Assert
    with Image.open(io.BytesIO(prepared)) as image:
        assert image.format == "PNG"
        assert image.width * image.height <= MAX_PIXELS


def test_a_small_image_keeps_its_pixels() -> None:
    """The contrast: the invariant is a ceiling, not a resample of everything."""
    # Arrange
    import io

    from PIL import Image

    # Act
    prepared = prepared_image(_png(8, 8), "image/png")

    # Assert
    with Image.open(io.BytesIO(prepared)) as image:
        assert (image.width, image.height) == (8, 8)


def test_a_jpeg_becomes_a_png() -> None:
    """*Always* PNG — one wire format, so a provider quirk about JPEG cannot reach the caller."""
    # Arrange
    import io

    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), (10, 20, 30)).save(buffer, format="JPEG")

    # Act
    prepared = prepared_image(buffer.getvalue(), "image/jpeg")

    # Assert
    with Image.open(io.BytesIO(prepared)) as image:
        assert image.format == "PNG"


async def test_the_resize_runs_off_the_event_loop() -> None:
    """G6. A service passes through no seam wrap, so nothing catches a blocking call for it —
    `weft_kernel.blocking.guard` is the same detector the seam installs, armed here directly.
    """
    # Arrange
    describer = _describer(_RecordingClient())

    # Act / Assert — a blocking call inside the guard raises from the call itself.
    with guard("describe"):
        outcome = await describer.describe(_png(2000, 2000), "image/png", "Describe.")
    assert isinstance(outcome, Produced)


async def test_the_instruction_reaches_the_provider() -> None:
    """`instruction` is the contract's third argument and the caller's only control over what is
    said; a plugin that ignored it would satisfy every other test here."""
    # Arrange
    client = _RecordingClient()

    # Act
    await _describer(client).describe(_png(), "image/png", "Name the axes.")

    # Assert
    assert any("Name the axes." in str(call) for call in client.calls)


def test_the_pack_discloses_that_image_bytes_leave_the_process() -> None:
    """`02` §2 → *The trust model*, and `9.9`'s own clause: the `note` names the **content class**
    that leaves, not merely that the network is reached. `weft-openai`'s existing disclosure said
    completions and embeddings; page crops are a third thing and a more sensitive one.
    """
    # Arrange
    import weft_openai

    note = weft_openai.DISCLOSURE.note

    # Act / Assert
    assert "image" in note.lower()


def test_the_plugin_name_is_registered_under_the_describer_contract() -> None:
    """`10` §2.1's naming rule: the plugin names the role and the model is `with: model:`."""
    # Arrange
    import weft_openai
    from weft_kernel.discovery import PackRegistrar
    from weft_kernel.registry import Registry

    registry = Registry()
    registrar = PackRegistrar(registry, distribution="weft-openai")
    weft_openai.register(registrar, Settings(api_key="sk-test"))  # type: ignore[arg-type]
    registrar.commit()

    # Act / Assert
    assert "openai-vision" in registry.names_for(Describer)
