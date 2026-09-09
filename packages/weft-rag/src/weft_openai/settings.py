"""`weft-openai`'s pack settings: one account, shared by everything this pack registers.

The same distinction `weft_store.pgvector_store` draws for its connection
string, and `docs/02-extension-model.md` §2 draws for the graph pack's
`endpoint`/`api_key`: an account is one resource every plugin in the pack
reaches through, not a per-pipeline-stage tuning knob. What model to call and
how wide its vectors should be *is* per-stage, and lives on
`weft_openai.embedder.OpenAIEmbedderConfig` instead.

**Every field has a default, and that is load-bearing rather than tidy.**
Pack settings are validated *before* `register()` is called, so one required
field turns a machine with no credential into a pack that reports `failed`
with nothing contributed — and a plugin that is not in the registry is not in
`manual/contract-reference.md`, not in fitness function 11(b)'s resolution
check, and not in anything else that walks what is installed. Nothing fails;
the capability simply is not there. So the credential defaults to empty and
the refusal happens at use, where it can name the line that fixes it — see
`weft_openai.embedder.MissingApiKeyError`.

A settings module of its own, rather than the package's `__init__`, so
`embedder.py` can name this type without importing the module that imports
it.
"""

from pydantic import BaseModel, ConfigDict, Field, SecretStr

#: The SDK's own default, restated because this pack never lets the SDK read its
#: own defaults from the environment — see `weft_openai.embedder.build_client`.
_DEFAULT_MAX_RETRIES = 2


class Settings(BaseModel):
    """One OpenAI account: the credential, where to reach it, and how patient to be."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: `${env:OPENAI_API_KEY}` is the spelling `weft.toml.example` shows: the settings
    #: loader interpolates it, so the secret stays in the environment and the project
    #: can still commit the file that names which variable it wants.
    api_key: SecretStr = SecretStr("")
    #: Any API that speaks the same protocol — a gateway, a proxy, a compatible local
    #: server. Unset means `weft_openai.embedder.VENDOR_BASE_URL`, passed explicitly:
    #: the SDK reads `OPENAI_BASE_URL` for itself when it is handed nothing, and an
    #: endpoint this file did not name is an endpoint this file cannot be trusted about.
    #: The same holds for the two below and `OPENAI_ORG_ID` / `OPENAI_PROJECT_ID`.
    base_url: str | None = None
    organization: str | None = None
    project: str | None = None
    #: Seconds. Unset leaves the SDK's own default in force — which is *not* the same as
    #: passing it `None`, a value it honours as "no timeout at all". See `build_client`.
    timeout_seconds: float | None = Field(default=None, gt=0.0)
    #: The SDK retries transient failures itself, at the transport, below anything Weft
    #: can see. Zero turns that off for an operator who wants the failure immediately.
    max_retries: int = Field(default=_DEFAULT_MAX_RETRIES, ge=0)
