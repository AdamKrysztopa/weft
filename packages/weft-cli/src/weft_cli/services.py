"""`[services]` — which registered plugin fills a role a command needs, read from `weft.toml`.

`weft index` and `weft ask` name their stages in Python, because Phase 0
built no route from a pipeline document to a command's stages
(`weft_cli.ingest`'s own module docstring, and `06`'s second G2 trap). That
is a fine place for `chunk` to sit for now and a bad place for `embed` and
`store` to sit at all: which embedder ran decides what a stored vector
*means*, an index built with one is not comparable to an index built with
another, and which store a run uses decides *where the corpus is*. An
operator who cannot change either without editing a package cannot change it
at all.

So both are selected here, from the project's own configuration file, one
line each:

```toml
[services]
embed = "openai"
store = "qdrant"
```

That is the whole operation. No package edited, no reinstall, and a plugin
some stranger's pack registered under the `Embedder` contract is selectable
the moment it is installed — the same property `--extract` gives extraction
and `use:` will give both once pipeline documents reach these commands.

**`hash` stays the default, and that is what keeps the gate offline.**
`weft-embed`'s deterministic embedder needs no credential, no network and no
model download, so a clean checkout runs `poe ci-checks` and the whole
quickstart with no account anywhere. Selecting a model is an explicit act in
a file, never a fallback and never an environment variable that happened to
be exported — `docs/09-release.md` §4's offline subset, held by construction
rather than retrofitted.

**`store` arrived as a repair, and the argument is the one the constraint
makes.** Task 2.6 shipped `weft-qdrant` — a second registered `NodeStore` —
while `weft_cli.ingest` still named `"pgvector"` in Python, so running against
it meant editing a package in this repository. `.phase2-findings.md` finding 9
is categorical about the general case ("the same argument applies to embedders,
providers, retrieval strategies"): swapping a backend is a configuration edit
and nothing else, and a third party's `weft-store-mystore` must cost zero files
here. Which *pack settings* a store takes (`[packs.weft-qdrant] collection`,
`vector_size`) was already configuration; only the selection was missing.

**A key nothing reads is refused, not ignored.** The Phase 2 design record's
`[services]` block also names an `llm`, which arrives with the task that builds
it. Until then a `weft.toml` naming one gets a refusal saying so, because the
alternative is an operator setting a key, seeing no error, and getting a run
assembled from something other than what they named.
"""

from __future__ import annotations

from typing import Final, cast

from pydantic import BaseModel, ConfigDict

from weft_kernel.errors import WeftError

#: `weft-embed`'s deterministic embedder — see the module docstring on why the offline
#: one is the default rather than merely available.
DEFAULT_EMBEDDER: Final[str] = "hash"

#: `weft-store`'s pgvector backend. The default because `01` → *Runtime shape* makes it the
#: floor — "one container is the floor, and it is pgvector" — not because it is privileged:
#: it is resolved by name through the same registry every other store is.
DEFAULT_STORE: Final[str] = "pgvector"


class ServiceSelection(BaseModel):
    """What `[services]` decides. Two fields today; the block is designed to grow."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: The `Embedder` plugin name `weft index` and `weft ask` resolve.
    embed: str = DEFAULT_EMBEDDER

    #: The `NodeStore` plugin name `weft index` writes to and `weft ask` searches. Both, from
    #: one key, deliberately: an index written to one store and a question asked of another
    #: is a run that returns nothing and reports no error.
    store: str = DEFAULT_STORE


def service_selection_from_config(document: dict[str, object] | None) -> ServiceSelection:
    """`[services]` from a parsed `weft.toml`, or every default if it says nothing.

    Refuses an unknown key by naming it *and* the keys that exist, the same
    rule `weft_kernel.pipeline` applies to a pipeline document — `01`
    requirement 5. A `services` key that is present but is not a table is
    refused exactly as `weft_cli.registry_bootstrap.pack_settings_from_config`
    refuses a malformed `[packs]`: two readers of one file must not disagree
    about what a broken block means.
    """
    if document is None or "services" not in document:
        return ServiceSelection()
    services = document["services"]
    if not isinstance(services, dict):
        raise WeftError(
            f"weft.toml's [services] must be a table, not {type(services).__name__} — found "
            f'`services = {services!r}`. Did you mean `[services]\\nembed = "openai"`?'
        )
    written = cast("dict[str, object]", services)
    known = sorted(ServiceSelection.model_fields)
    unknown = sorted(key for key in written if key not in ServiceSelection.model_fields)
    if unknown:
        raise WeftError(
            f"unknown [services] key(s) in weft.toml: {', '.join(repr(key) for key in unknown)}. "
            f"[services] accepts {', '.join(known)}. A key nothing reads is refused rather than "
            f"ignored — a service Weft did not select is one you would have to notice by the "
            f"answers being wrong."
        )
    for key, value in written.items():
        if not isinstance(value, str) or not value:
            raise WeftError(
                f"weft.toml's [services] {key} must be the name of a registered plugin, not "
                f"{value!r}. `weft plugins doctor` lists what every installed pack registered."
            )
    return ServiceSelection.model_validate(written)
