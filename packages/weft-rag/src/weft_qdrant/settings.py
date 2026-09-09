"""`weft-qdrant`'s pack settings: one Qdrant deployment, and the two facts it fixes in advance.

The same distinction `weft_store.pgvector_store` draws for its connection string
and `docs/02-extension-model.md` §2 draws for the graph pack's
`endpoint`/`api_key`: a deployment is one resource everything this pack registers
reaches through, not a per-pipeline-stage tuning knob.

**Every field has a default, and that is load-bearing rather than tidy.** Pack
settings are validated *before* `register()` runs, so one required field turns a
machine with no Qdrant configured into a pack that reports `failed` with nothing
contributed — and a plugin that is not in the registry is not in
`manual/contract-reference.md`, not in fitness function 11(b)'s resolution check,
and not in anything else that walks what is installed. Nothing fails; the
capability simply is not there. So the URL defaults to the one `compose.yaml`
publishes and a deployment that is not running is discovered at *use*, by the
driver, naming the address it could not reach.
"""

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class QdrantSettings(BaseModel):
    """Where Qdrant is, what to call the collections, and how wide a vector is."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: The default is what `compose.yaml`'s `qdrant` service publishes, so a developer who
    #: brought the conformance profile up needs no `weft.toml` at all.
    url: str = "http://localhost:6333"

    #: Empty means an unauthenticated deployment, which is what a local container is. A
    #: managed one wants `${env:QDRANT_API_KEY}` here, the spelling `weft.toml.example`
    #: shows — the secret stays in the environment and the file names the variable.
    api_key: SecretStr = SecretStr("")

    #: The collection holding nodes. Source records live in a second collection named after
    #: it (see `weft_qdrant.store.QdrantStore`) — Qdrant has no second table inside one
    #: collection, and a `SourceRecord` is not a `Node`.
    collection: str = Field(default="weft_nodes", min_length=1)

    #: **The one place this backend's shape is visibly different from Postgres's, and it is
    #: a setting because it has to be.** A pgvector column is declared without a dimension;
    #: a Qdrant collection fixes its vector width at creation and cannot change it. So the
    #: width the configured embedder produces has to be stated *before* the first node is
    #: written, rather than discovered from it. The default is `weft-embed`'s hash
    #: embedder's, which is what a laptop run uses; `text-embedding-3-small` is 1536, and a
    #: node whose embedding disagrees with this is refused by name rather than truncated.
    vector_size: int = Field(default=64, ge=1)

    #: Whole seconds the driver waits on one request — whole because the driver's own
    #: parameter is an `int`, and accepting a fraction here would mean silently rounding
    #: an operator's number. Unset leaves the driver's default in force, which is not the
    #: same as passing `None` — that would mean no timeout at all.
    timeout_seconds: int | None = Field(default=None, gt=0)
