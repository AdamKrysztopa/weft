"""`CrossEncoderSettings` — one TEI deployment, and the one number every request waits on.

The same shape `weft_qdrant.settings.QdrantSettings` documents for its own deployment
setting: **every field has a default, and that is load-bearing rather than tidy.** Pack
settings are validated *before* `register()` runs, so a required field here would turn a
machine with no TEI server configured into a pack that fails to register at all, rather
than one that registers and refuses at first use, naming the address. The model this
stage actually scores against is not here — it is a stage's own `with: {model: …}`,
checked against the server's `/info` on every `run` — because a deployment can be
restarted under a different model without a settings edit.
"""

from pydantic import BaseModel, ConfigDict, Field


class CrossEncoderSettings(BaseModel):
    """Where the TEI server `cross-encoder-rerank` scores through runs, and how long to wait."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: The default matches no shipped `compose.yaml` service — TEI is nobody's own
    #: container here — but names the address the manual's every example uses, so a
    #: reader who starts `text-embeddings-router` locally needs no `weft.toml` at all.
    url: str = "http://localhost:8080"

    #: Whole seconds is `QdrantSettings.timeout_seconds`'s own reasoning for wholeness;
    #: this field is a `float` instead because `httpx.Timeout` already accepts one and
    #: scoring fifty passages on a CPU measures to about a second, not a whole second.
    timeout_seconds: float = Field(default=30.0, gt=0)
