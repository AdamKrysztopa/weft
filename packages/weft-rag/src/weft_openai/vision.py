"""`openai-vision` — the first `Describer`. Ledger task `9.9`.

It lives in this pack rather than in `weft-vision` for the reason `9.9` states: *"its first
implementation lives in the pack that already holds the provider's client"*. A distribution of its
own, for one plugin, would need `weft-openai` as a dependency to reach `build_client` — the
inverted-dependency shape `weft_command.contract`'s own docstring refuses one layer up.

**One resize invariant: always PNG, bounded max pixels — and it is this pack's, not the
contract's.** A page crop from a 600-DPI scan is megabytes, and both the bill and the latency are
linear in it; that is a fact about *this provider's pricing and limits*, not about describing
images, so putting it on `Describer` would make every future implementation inherit one vendor's
economics. Always PNG rather than "whatever arrived" so a provider quirk about JPEG chroma
subsampling cannot reach a caller who only ever asked for a description.

**The resize runs off the event loop.** Pillow decodes and resamples on the CPU and holds the loop
while it does; G6 settles that a CPU-bound stage is still `async def` and offloads its own blocking
work, and `weft_pdf.pdf_layout`'s module docstring is the shape. Fitness function 7(b) cannot see
CPU-bound work, and a *service* passes through no seam wrap at all, so nothing catches this
automatically — `weft_kernel.blocking.guard` is armed directly in this module's own tests instead.

**A missing credential is refused at use, naming the line that fixes it.** `weft_openai.embedder.
MissingApiKeyError`'s docstring carries the full argument and it applies here unchanged: pack
settings are validated before `register()` runs, so a *required* credential would turn a machine
without one into a pack that contributed nothing — and a plugin absent from the registry is absent
from `manual/contract-reference.md`, from fitness function 11(b)'s resolution check, and from
everything else that walks what is installed. Nothing fails; the capability simply is not there.
"""

import asyncio
import io
from typing import Any, Final, Protocol, cast

from PIL import Image
from pydantic import BaseModel, ConfigDict, Field

from weft_kernel.errors import WeftError
from weft_kernel.payload import Failed, NothingToProduce, Outcome, Produced
from weft_openai.settings import Settings

#: The ceiling `prepared_image` resizes down to. **This provider's cost and limit, not a fact about
#: describing images** — which is why it is a constant in this module rather than a field on the
#: contract. Two million pixels is roughly a 1600x1250 crop: comfortably above what a figure on a
#: printed page occupies at any sane render scale, and far below what a 600-DPI full-page scan
#: produces, where the bill and the round trip both grow linearly with the pixels sent.
MAX_PIXELS: Final[int] = 2_000_000

#: What this plugin always sends, whatever it was handed. See the module docstring.
_WIRE_FORMAT: Final[str] = "PNG"
_WIRE_MEDIA_TYPE: Final[str] = "image/png"


class MissingApiKeyError(WeftError):
    """No credential is configured, and something asked this describer to describe.

    Raised at use rather than at registration, for the reason
    `weft_openai.embedder.MissingApiKeyError`'s own docstring gives in full. The message names the
    `weft.toml` line that fixes it, because *"authentication failed"* from a vendor SDK tells an
    operator that a key is wrong and nothing about where this project reads one from.
    """


class OpenAIVisionConfig(BaseModel):
    """`OpenAIVisionDescriber`'s `with:` configuration — what to call and how much to let it say.

    **Both defaults are the vendor's own current ones**, so a pipeline that sets nothing gets what
    the provider's documentation describes rather than this pack's opinion of it.

    Two things an operator might expect are deliberately absent, so the omissions read as
    decisions. **`temperature`** is not here: a description that varies run to run makes a node's
    content non-deterministic, and a node id is a digest of its content — the same corpus would
    re-index into different nodes on every pass. **`prompt`** is not here either: the instruction is
    the *contract's* third argument, because two stages consume this service for different purposes
    and a prompt fixed at registration could serve only one of them.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    model: str = "gpt-4o-mini"
    #: A description is a sentence or two. The ceiling is here to stop a runaway response costing
    #: more than the image did, not to shape the answer — the instruction does that.
    max_output_tokens: int = Field(default=512, gt=0)


class _VisionClient(Protocol):
    """What this describer needs from a provider client, and nothing more.

    A `Protocol` rather than the SDK's own type so a test can hand over a double without importing
    the vendor package, and so the one place that knows the SDK's call shape is `_SdkClient` below.
    """

    async def describe(self, **kwargs: Any) -> str: ...


def prepared_image(data: bytes, media_type: str) -> bytes:
    """`data` as PNG bytes, downscaled if it exceeds `MAX_PIXELS` — see the module docstring.

    Synchronous and public: synchronous because it is pure CPU work its caller offloads, and public
    because the resize invariant is worth a test of its own rather than being observable only
    through a provider call.

    An image already within the ceiling keeps its **exact** pixel dimensions. The ceiling is a
    ceiling, not a resample of everything: re-sampling a small crop would cost quality for nothing.
    """
    del media_type  # Pillow reads the format from the bytes; what the caller called it is a hint.
    with Image.open(io.BytesIO(data)) as image:
        pixels = image.width * image.height
        prepared = image
        if pixels > MAX_PIXELS:
            scale = (MAX_PIXELS / pixels) ** 0.5
            size = (max(1, int(image.width * scale)), max(1, int(image.height * scale)))
            prepared = image.resize(size)
        buffer = io.BytesIO()
        prepared.convert("RGB").save(buffer, format=_WIRE_FORMAT)
    return buffer.getvalue()


class OpenAIVisionDescriber:
    """Describes an image through this provider's chat surface.

    Satisfies `weft_vision.contract.Describer` structurally — this class never imports it, the same
    path any third-party describer pack takes.
    """

    def __init__(
        self,
        settings: Settings,
        config: OpenAIVisionConfig | None = None,
        *,
        client: object | None = None,
    ) -> None:
        self._settings = settings
        self._config = config if config is not None else OpenAIVisionConfig()
        self._client = client

    async def describe(self, data: bytes, media_type: str, instruction: str) -> Outcome[str]:
        """Bytes in, one description out — or an honest account of why there is none.

        The credential is checked **before** any work: resizing a megabyte of pixels and then
        discovering there is nobody to send them to wastes the expensive half of the call.

        `CancelledError` is re-raised untouched ahead of the broad handler, per G6. It is not a
        fact about this image, and turning it into a `Failed` would make a cancelled run look like
        a corpus full of figures the provider refused.
        """
        if not self._settings.api_key.get_secret_value():
            raise MissingApiKeyError(
                "no OpenAI credential is configured, so the 'openai-vision' describer has nothing "
                "to authenticate with. Set [packs.openai] api_key in weft.toml (the usual "
                'spelling is api_key = "${env:OPENAI_API_KEY}"), or remove the stage that '
                "describes figures from this pipeline."
            )
        prepared = await asyncio.to_thread(prepared_image, data, media_type)
        try:
            reply = await self._provider().describe(
                model=self._config.model,
                max_output_tokens=self._config.max_output_tokens,
                instruction=instruction,
                image=prepared,
                media_type=_WIRE_MEDIA_TYPE,
            )
        except asyncio.CancelledError:
            raise
        except WeftError:
            # **A `WeftError` here is this project telling itself it is wrong, not the vendor
            # refusing an image.** `BlockingCallError` is the case that cost a phase: the seam
            # raised it correctly, the handler below turned it into a `Failed`, and a defect in
            # our own code arrived at the operator wearing the costume of ordinary provider
            # trouble. Re-raised alongside `CancelledError` and for the same reason — neither is
            # a fact about this figure.
            raise
        except Exception as exc:  # noqa: BLE001 — see the docstring: one refused figure is data
            return Failed(reason=f"{type(exc).__name__}: {exc}")
        if not reply.strip():
            return NothingToProduce(
                reason="the model returned no description for this image, only whitespace"
            )
        return Produced(value=reply)

    def _provider(self) -> _VisionClient:
        if self._client is None:
            self._client = _SdkClient(self._settings)
        return cast("_VisionClient", self._client)


class _SdkClient:
    """The vendor SDK's chat surface, reduced to the one call this describer makes.

    Built lazily rather than in `__init__` so that constructing a describer — which registration
    does, for every run, whether or not a pipeline names it — opens no client and reads no
    environment.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: Any = None

    async def describe(self, **kwargs: Any) -> str:
        import base64

        from weft_openai.embedder import build_client

        # **Off the loop thread, and this was a defect for a whole phase.** Constructing the vendor
        # client reaches httpx, which loads a CA bundle with a synchronous `open()` — so calling
        # `build_client` here directly made the registration seam's blocking-call detector fire
        # (fitness function 7(b)), and this module's own broad handler below turned that into a
        # `Failed` about the image. Net effect: `openai-vision` could never describe anything inside
        # a real pipeline, and said nothing. `build_client`'s two other callers already did this —
        # `embedder.py`'s `_client = await asyncio.to_thread(build_client, settings)` and
        # `llm.py`'s, whose docstring says *"The client is built off the event loop, for the same
        # measured reason."* This was the third caller and the only one that had not read them
        # (`docs/internal/lessons.md` L8.24). Cached, because paying a thread hop per figure to
        # rebuild an identical client is the other half of what `embedder.py` already avoids.
        if self._client is None:
            self._client = cast("Any", await asyncio.to_thread(build_client, self._settings))
        client = self._client
        encoded = base64.b64encode(cast("bytes", kwargs["image"])).decode("ascii")
        response = await client.chat.completions.create(
            model=kwargs["model"],
            max_tokens=kwargs["max_output_tokens"],
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": kwargs["instruction"]},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{kwargs['media_type']};base64,{encoded}"},
                        },
                    ],
                }
            ],
        )
        return cast("str", response.choices[0].message.content or "")
