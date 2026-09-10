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
embed = "openai-embeddings"
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
here. Which *pack settings* a store takes (`[packs.qdrant] collection`,
`vector_size`) was already configuration; only the selection was missing.

**A key nothing reads is refused, not ignored.** The Phase 2 design record's
`[services]` block also names an `llm`, which arrives with the task that builds
it. Until then a `weft.toml` naming one gets a refusal saying so, because the
alternative is an operator setting a key, seeing no error, and getting a run
assembled from something other than what they named.

**Repair, 2026-08-20** (`docs/01-high-level-plan.md` item 12's own dated paragraph carries the
argument in full): the unknown-key refusal below used to be a bare `WeftError` computing the
valid keys and interpolating them into the message only — invisible to fitness function 12's
family walk, which looks for a typed `valid_options` field, never message text.
`UnknownServiceKeyError` now carries it, the identical shape `weft_cli.config_surface.
UnknownConfigKeyError` already gives `config get`/`config set`'s own vocabulary. The malformed-
value check just below it (a value that is not the name of a registered plugin at all, checked
here only for shape) is **not** brought into the family — it reports a type mismatch, not a
name failing to resolve against an enumerable set; whether the name actually resolves is left to
the registry lookup a caller performs later, which is where `weft_kernel.registry.
UnknownPluginError` already carries its own `valid_options`.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final, cast

from pydantic import BaseModel, ConfigDict

from weft_cli.service_roles import RoleTable
from weft_kernel.errors import UnresolvedNameError, WeftError

#: `weft-embed`'s deterministic embedder — see the module docstring on why the offline
#: one is the default rather than merely available.
DEFAULT_EMBEDDER: Final[str] = "hash"

#: `weft-store`'s pgvector backend. The default because `01` → *Runtime shape* makes it the
#: floor — "one container is the floor, and it is pgvector" — not because it is privileged:
#: it is resolved by name through the same registry every other store is.
DEFAULT_STORE: Final[str] = "pgvector"

#: `weft-retrieve`'s own `route.yaml`. **Added by ledger task 8.3, and it is a repair rather
#: than a feature.** Until it existed, `weft_cli.route_ask` held `"route"` as a module constant
#: — "the one pipeline name this module ever writes itself" — and that made the router the only
#: privileged pipeline in the tree: a pack cannot contribute a second document under a name
#: another pack already contributed, and a project cannot ship its own `route.yaml` either,
#: because `weft_cli.pipeline_catalogue.full_catalogue` refuses a name declared by both sources
#: and takes every `weft pipeline` command down with it until the file is renamed. So
#: `threshold-ladder` and `always` were registered, listed, catalogued in `10` §1.5 — and
#: placeable by nobody, which is requirement 4 broken in exactly the shape `01` item 11 names:
#: a strategy that registers, is listed, is described to a model, and can never run. Here it
#: is a name resolved by the same mechanism `embed` and `store` already use.
DEFAULT_ROUTER: Final[str] = "route"


class UnknownServiceKeyError(WeftError, UnresolvedNameError):
    """`[services]` names a key this module does not read.

    Repair, 2026-08-20: the identical rule `weft_cli.config_surface.UnknownConfigKeyError`
    already gives `config get`/`config set`'s own sibling refusal, applied here — `01`
    requirement 5 and fitness function 12 require the valid keys as a typed field a caller can
    read, not only text inside the message a reviewer has to notice.
    """

    def __init__(self, message: str, *, valid_options: tuple[str, ...]) -> None:
        super().__init__(message)
        self.valid_options = valid_options


class ServiceSelection(BaseModel):
    """What `[services]` decides. Three fields today; the block is designed to grow.

    Two of them name a **plugin** and the third names a **pipeline**, which is a difference
    worth stating rather than smoothing over: `embed` and `store` are resolved through the
    registry and fail with `weft_kernel.registry.UnknownPluginError`, while `route` is looked up
    in the contributed pipeline catalogue and fails with `weft_cli.route_ask.
    NoRouterPipelineError`. They belong in one block anyway because the question each answers is
    the same one — *which of the installed things fills this role for this project* — and
    splitting them by how the lookup happens would put an implementation detail in a user's
    configuration file.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: The `Embedder` plugin name `weft index` and `weft ask` resolve.
    embed: str = DEFAULT_EMBEDDER

    #: The `NodeStore` plugin name `weft index` writes to and `weft ask` searches. Both, from
    #: one key, deliberately: an index written to one store and a question asked of another
    #: is a run that returns nothing and reports no error.
    store: str = DEFAULT_STORE

    #: The pipeline document `weft ask` runs to choose a pipeline — see `DEFAULT_ROUTER` for
    #: why this is a key rather than a constant. Since ledger task **8.12**, a project-local
    #: document may be named here too: `run_routed_ask` searches `weft_cli.pipeline_catalogue.
    #: full_catalogue`, the identical merged catalogue every `weft pipeline` command and
    #: `run_named_ask` already resolve against, not `load_contributed` alone. The narrower
    #: search set 8.3 shipped this with was a Phase 2 implementation gap carried forward —
    #: `02` §2's trust model is about installed *packs*, and a project's own `pipelines/`
    #: document is text its own author wrote, not a boundary to defend — so widening it
    #: introduces no new trust the project did not already have over its own files. A name
    #: both a project document and a pack contribution declare is refused outright
    #: (`weft_cli.pipeline_catalogue.ProjectPipelineNameCollisionError`), never resolved to
    #: one of the two in silence.
    route: str = DEFAULT_ROUTER

    #: The plugin name selected for every declared role other than `embed`/`store` —
    #: ledger task **9.0**. Keyed by the same `key` a `weft_kernel.context.ServiceRole`
    #: declared; a key with nothing selected for it is simply absent, never guessed
    #: (`weft_cli.service_roles.RoleTable`'s own module docstring).
    roles: Mapping[str, str] = {}

    def plugin_for(self, key: str) -> str:
        """The plugin name selected for role `key`.

        `embed` and `store` predate the mechanism and keep their own fields; every other
        declared role is read from `roles`. A `key` this selection holds nothing for raises
        `UnknownServiceKeyError` naming the keys it does hold — `roles` is never guessed at,
        so an unresolved role is a refusal, not a silent default.
        """
        if key == "embed":
            return self.embed
        if key == "store":
            return self.store
        if key not in self.roles:
            raise UnknownServiceKeyError(
                f"[services] holds no selection for {key!r}. Selected: "
                f"{', '.join(sorted(self.roles)) or '(none)'}.",
                valid_options=tuple(sorted(self.roles)),
            )
        return self.roles[key]


def service_selection_from_config(
    document: dict[str, object] | None, *, table: RoleTable
) -> ServiceSelection:
    """`[services]` from a parsed `weft.toml`, or every default if it says nothing.

    The key set this validates against is `set(table.declared) | {"route"}` — every role a
    trusted, installed pack declared, plus `route`, which names a pipeline rather than a
    plugin and so is never a role (`docs/03-cli.md:925-930 'weft_cli.co'`). Never `ServiceSelection.
    model_fields`: that set is closed to `embed`, `store` and `route`, which is exactly the
    hole ledger task 9.0 closes — `weft_cli.service_roles`'s own module docstring.

    `table` is **required and has no default**, deliberately. A default naming `embed` and
    `store` would put back, one layer down, the closed key space this task exists to delete —
    and it would fail *silently*: a caller that forgot the table would get a plausible key set
    rather than a refusal, which `CLAUDE.md` names as strictly worse than a crash.
    `weft_cli.registry_bootstrap.build_dependencies` builds the real one from what discovery
    actually found, and every other caller says which set it means.

    Refuses an unknown key by naming it *and* the keys that exist, the same
    rule `weft_kernel.pipeline` applies to a pipeline document — `01`
    requirement 5. A `services` key that is present but is not a table is
    refused exactly as `weft_cli.registry_bootstrap.pack_settings_from_config`
    refuses a malformed `[packs]`: two readers of one file must not disagree
    about what a broken block means.
    """
    known = tuple(sorted(set(table.declared) | {"route"}))
    if document is None or "services" not in document:
        return ServiceSelection()
    services = document["services"]
    if not isinstance(services, dict):
        raise WeftError(
            f"weft.toml's [services] must be a table, not {type(services).__name__} — found "
            f'`services = {services!r}`. Did you mean `[services]\\nembed = "openai-embeddings"`?'
        )
    written = cast("dict[str, object]", services)
    unknown = sorted(key for key in written if key not in known)
    if unknown:
        raise UnknownServiceKeyError(
            f"unknown [services] key(s) in weft.toml: {', '.join(repr(key) for key in unknown)}. "
            f"[services] accepts {', '.join(known)}. A key nothing reads is refused rather than "
            f"ignored — a service Weft did not select is one you would have to notice by the "
            f"answers being wrong.",
            valid_options=known,
        )
    for key, value in written.items():
        if not isinstance(value, str) or not value:
            raise WeftError(
                f"weft.toml's [services] {key} must be the name of a registered plugin, not "
                f"{value!r}. `weft plugins doctor` lists what every installed pack registered."
            )
    role_selections = {
        key: value for key, value in written.items() if key not in ("embed", "store", "route")
    }
    base = {key: value for key, value in written.items() if key in ("embed", "store", "route")}
    return ServiceSelection.model_validate({**base, "roles": role_selections})
