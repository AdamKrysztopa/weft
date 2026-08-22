"""Where `weft-cli` opens a pipeline document — the second file this distribution reads.

`docs/02-extension-model.md` §3 → *One model, two directions*: "The kernel publishes the
model and opens no file... whoever opened the file brought the parser." `weft_kernel.
pipeline.Pipeline` is that model; this module is that parser, on the exact footing
`weft_cli.registry_bootstrap` already established for `weft.toml`'s TOML — `yaml.safe_load`
here, `tomllib.load` there, one caller each, neither reachable from `weft-kernel`, which
G1 fixes at `pydantic` and `opentelemetry-api` and nothing else. Pipelines are YAML;
operator policy stays TOML — `02` §3 states the split, this module is where it is kept.

**A catalogue is `resolve()`'s `parents: Mapping[str, Pipeline]` argument, built from real
files.** `weft_kernel.resolution.resolve` was built at task 1.3 to take that lookup as a
plain mapping precisely so nothing about *where* a pipeline's ancestors come from is
baked into the kernel — a directory of `*.yaml` documents is one obvious way to supply
it, not the only one a caller could choose. `docs/build-ledger.md` 1.9: "Keep it small and
obvious; do not invent a package format" — so `load_pipeline_catalogue` does the one
obvious thing: read every `*.yaml` file in a directory, non-recursively, and key each
parsed `Pipeline` by its own `name:` field rather than by the filename it happened to be
saved under, so a document renamed on disk keeps resolving under the name it declares —
and so does the catalogue's caller, who names a pipeline, never a path.

**The translation task 1.1 left open, closed here.** `docs/build-ledger.md`, right after
1.1: "a malformed pipeline document has no exit code and no manual entry yet... nothing
opens a pipeline file until 1.9. Whichever task first hands a document to the CLI owns the
translation and the manual/troubleshooting.md entry — a note here rather than a fix at
1.1, because the kernel decides no exit codes." This is that task. `Pipeline.model_
validate`'s own error set is `pydantic.ValidationError` — deliberately, per `weft_kernel.
pipeline`'s own module docstring, because a document that will not validate has no
resolved parent and no distributions to name, so it is not one of `weft_kernel.resolution`'s
`PipelineResolutionError` subclasses. But `pydantic.ValidationError` is also not a
`WeftError`, so left alone it would reach nothing that knows `docs/03-cli.md`'s exit 4 is
"fix the pipeline" and it would be invisible to the 0.14 coverage ratchet, which derives
its required set from `WeftError` subclass names. `MalformedPipelineError` below is that
translation — caught here, at the one seam that calls `Pipeline.model_validate` on text a
person wrote, and raised as a `WeftError` a caller (Phase 3's `weft pipeline validate`,
once it exists) can map to exit 4 exactly the way `weft_cli.registry_bootstrap.
ConfigFileError` already lets `dispatch` map a broken `weft.toml` there today.
"""

from __future__ import annotations

import importlib.resources
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Final

import yaml
from pydantic import ValidationError

from weft_kernel.discovery import PackReport
from weft_kernel.errors import UnresolvedNameError, WeftError
from weft_kernel.pipeline import Pipeline
from weft_kernel.runner import PipelineResolutionError, UnresolvedNameInPipelineResolutionError

#: Task **3.7**: `weft pipeline list|show|derive|validate|diff` need somewhere project-local
#: documents live, on `weft_cli.registry_bootstrap.DEFAULT_CONFIG_PATH`'s own footing — a
#: single, obvious, cwd-relative default rather than a new `weft.toml` key nothing yet reads.
#: `load_pipeline_catalogue` already tolerates an absent directory (`Path.glob` on one yields
#: nothing, never an error), so a project with no `pipelines/` directory at all still has a
#: full catalogue — just one built entirely from installed packs' own contributions.
DEFAULT_PIPELINES_DIR: Final[Path] = Path("pipelines")


class PipelineDocumentError(WeftError):
    """A pipeline document's file cannot be read, or its contents are not valid YAML at all.

    Mirrors `weft_cli.registry_bootstrap.ConfigFileError`'s split exactly: an *absent* file
    is not this — `load_pipeline_catalogue` simply finds nothing to glob — this is a file
    that exists but a permissions problem stops it being read, or whose contents are not
    even well-formed YAML (an unterminated flow mapping, a bad indent). Distinct from
    `MalformedPipelineError` below: this fires before a document exists to check the
    `Pipeline` model against at all.
    """


class MalformedPipelineError(WeftError):
    """A document parses as YAML, but the mapping it produced fails `Pipeline`'s own validation.

    See the module docstring, *"The translation task 1.1 left open, closed here."* Wraps
    whatever `pydantic.ValidationError` `Pipeline.model_validate` raised — its own message
    already names the offending key or value and, for an unknown key, every key the model
    does accept, per `weft_kernel.pipeline._known_keys_only`. This class exists so that
    message reaches a `WeftError` handler at all, not to improve on it.
    """


class DuplicatePipelineNameError(WeftError):
    """Two documents in one catalogue directory both declare the same `name:`.

    A catalogue is keyed by each document's own `name:` field, never by the filename it was
    read from (see the module docstring) — so two files agreeing on a name would silently
    let the second one read simply replace the first in the returned mapping, which is
    exactly the kind of silent collision `weft_kernel.registry.DuplicateRegistrationError`
    already refuses for a plugin name. Names both files and the name they share.
    """


class ContributedPipelineNameCollisionError(WeftError):
    """Two installed packs' `PipelineResource`s both declare the same `name:`.

    Task **2.8**. `.phase2-design.md` §5 describes a wider guarantee than this class
    enforces: "a contributed name colliding with a project-local one is refused naming
    both — the same rule as a duplicate plugin name, resolvable by an operator pin."
    **Narrowed on repair, 2.8's own line on `docs/build-ledger.md`:** `load_contributed`
    below takes no project-local catalogue as input, and the one live caller —
    `weft_cli.route_ask.run_routed_ask` — never merges one in either, because no CLI
    command yet wires a `load_pipeline_catalogue(directory)` result into a route decision.
    So what this class actually refuses today is two *contributed* resources, from any
    distributions, sharing one `name:` — a real check, just not the design record's fuller
    one. A separate class from `DuplicatePipelineNameError` all the same, because the two
    would disambiguate different sources in their own message if the wider check existed —
    a `Path` for a catalogue directory, a `distribution:package/resource` locator for a
    contributed one — and collapsing them now would make that future error's text lie
    about where to look. Neither is a plugin-name collision, so `weft_kernel.registry`'s
    `[plugins]` pin cannot arbitrate this one; the remedy is renaming one of the two
    pipeline documents.

    **The wider guarantee arrived at task 3.7 — `full_catalogue` below, not this class.**
    `weft pipeline list|show|derive|validate|diff` is the first caller that actually wires
    a `load_pipeline_catalogue(directory)` result together with `load_contributed(reports)`,
    so the project-local-versus-contributed collision `.phase2-design.md` §5 described is now
    real; it is `ProjectPipelineNameCollisionError` below, not folded into this class, for the
    identical disambiguation reason this docstring already gives — the two sources still need
    two different messages.
    """


class ProjectPipelineNameCollisionError(WeftError):
    """A project-local pipeline document and an installed pack's own contribution declare
    the same `name:` — task **3.7**, the wider guarantee `ContributedPipelineNameCollisionError`'s
    own docstring named as missing since task 2.8.

    Refused rather than arbitrated by picking a winner: `02` §3 → *Slots* draws the line for
    a pack's *stage* contributions ("it may never rewrite a pipeline that did not ask"), and
    a pack shipping a whole *pipeline* under a name a project already uses is the identical
    silent-override shape one level up — a project author who wrote `name: base` did not ask
    to have it shadowed the day some pack happens to ship its own `base.yaml`. Not a
    plugin-name collision, so `weft_kernel.registry`'s `[plugins]` pin cannot arbitrate this
    one either, the same reasoning `ContributedPipelineNameCollisionError` already gives — the
    remedy is renaming one of the two.
    """


def _parse_pipeline_text(text: str, *, source: str) -> Pipeline:
    """`text` parsed as YAML and validated as a `Pipeline` — the one place both
    `load_pipeline_document` (a file on disk) and `load_contributed` (a resource inside an
    installed package) turn text into a document, so the two error classes below mean the
    same thing regardless of which kind of source produced them.
    """
    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise PipelineDocumentError(f"{source} is not valid YAML: {exc}") from exc

    if not isinstance(document, dict):
        raise PipelineDocumentError(
            f"{source} does not parse to a mapping — a pipeline document is a set of "
            f"top-level keys (name, extends, stages, ...), and this file's top-level YAML "
            f"value is a {type(document).__name__}."
        )

    try:
        return Pipeline.model_validate(document)
    except ValidationError as exc:
        raise MalformedPipelineError(f"{source} is not a valid pipeline document: {exc}") from exc


def load_pipeline_document(path: Path) -> Pipeline:
    """Parse and validate one pipeline document at `path`.

    Raises `PipelineDocumentError` if `path` cannot be read or does not parse as YAML at
    all (including as something other than a mapping — a bare list or scalar cannot be a
    pipeline document); `MalformedPipelineError` if it parses but `Pipeline.model_validate`
    refuses it.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PipelineDocumentError(f"{path} could not be read: {exc}") from exc
    return _parse_pipeline_text(text, source=str(path))


def load_contributed(reports: Sequence[PackReport]) -> dict[str, Pipeline]:
    """Every `PipelineResource` an `ACTIVE` pack contributed, parsed and keyed by its own
    `name:` field — `weft_retrieve.contract.RouteCatalogue`'s own promise made real:
    "populated by the same eager discovery pass that builds the registry."

    Reads each resource through `importlib.resources`, never through a filesystem path
    relative to this repository — the property that makes a stranger's pipeline routable
    once their wheel is installed, with no directory this project controls to place it in.
    `reports` is `Dependencies.reports` — every pack `discover()` saw, `FAILED` and
    `REFUSED` ones included; only `PackReport.pipeline_resources` from an `ACTIVE` pack is
    ever non-empty (see `weft_kernel.discovery.PackRegistrar.commit`'s own atomicity), so
    this function does not filter on `status` itself — there is nothing to filter that
    is not already true by construction.

    Raises `PipelineDocumentError` if a resource cannot be read at all — an uninstalled
    package, or a resource path a rename left stale; `MalformedPipelineError` if it reads
    but fails `Pipeline.model_validate`; `ContributedPipelineNameCollisionError` if two
    resources, from any distributions, declare the same `name:`.
    """
    catalogue: dict[str, Pipeline] = {}
    seen_at: dict[str, str] = {}
    for report in reports:
        for resource in report.pipeline_resources:
            source = (
                f"pipeline resource '{resource.resource}' from package "
                f"'{resource.package}' (distribution '{resource.distribution}')"
            )
            try:
                traversable = importlib.resources.files(resource.package)
                for part in resource.resource.split("/"):
                    traversable = traversable.joinpath(part)
                text = traversable.read_text(encoding="utf-8")
            except (ModuleNotFoundError, FileNotFoundError, NotADirectoryError, OSError) as exc:
                raise PipelineDocumentError(f"{source} could not be read: {exc}") from exc

            pipeline = _parse_pipeline_text(text, source=source)
            first_seen = seen_at.get(pipeline.name)
            if first_seen is not None:
                raise ContributedPipelineNameCollisionError(
                    f"both {first_seen} and {source} declare name '{pipeline.name}' — a "
                    f"catalogue key must be unique. Rename one of the two pipeline "
                    f"documents, or uninstall the distribution shipping the one you do "
                    f"not want routable."
                )
            seen_at[pipeline.name] = source
            catalogue[pipeline.name] = pipeline
    return catalogue


def load_pipeline_catalogue(directory: Path) -> dict[str, Pipeline]:
    """Every `*.yaml` document directly under `directory`, keyed by its own `name:` field.

    Not recursive — a catalogue is "small and obvious", per `docs/build-ledger.md` 1.9, and
    a directory tree invents exactly the package format that instruction rules out. Files
    are read in sorted order, so `DuplicatePipelineNameError` always blames the same file as
    "already read" across repeated runs. The returned mapping is `resolve()`'s own `parents`
    shape (`weft_kernel.resolution.resolve`) — pass it directly.
    """
    catalogue: dict[str, Pipeline] = {}
    seen_at: dict[str, Path] = {}
    for path in sorted(directory.glob("*.yaml")):
        pipeline = load_pipeline_document(path)
        first_seen = seen_at.get(pipeline.name)
        if first_seen is not None:
            raise DuplicatePipelineNameError(
                f"both {first_seen} and {path} declare name '{pipeline.name}' — a catalogue "
                f"key must be unique. Rename one pipeline, or one of the two files."
            )
        seen_at[pipeline.name] = path
        catalogue[pipeline.name] = pipeline
    return catalogue


class UnknownPipelineNameError(
    UnresolvedNameInPipelineResolutionError, PipelineResolutionError, UnresolvedNameError
):
    """A `weft pipeline` command names a pipeline `full_catalogue` does not hold.

    Task **3.7**. Not `weft_kernel.resolution.UnknownParentPipelineError` — that one is
    raised while *resolving* a document whose own `extends:` names a missing parent; this
    one is raised before resolution ever starts, for a bare name a person typed at the
    command line (`weft pipeline show <name>`, `derive <parent> <name>`, `diff <a> <b>`,
    `validate <name>`). Both are the identical failure *kind* — a name that did not resolve
    against the same enumerable catalogue — which is why this reuses `weft_kernel.runner.
    UnresolvedNameInPipelineResolutionError`'s shared `__init__` rather than writing a
    fifth copy of it: the shape task 2.36 built specifically so more than one module could
    construct the same family member without duplicating the body.

    Fitness function 12's family: `valid_options` is every pipeline name `full_catalogue`
    does hold — project-local and pack-contributed alike.
    """


def full_catalogue(
    *, directory: Path = DEFAULT_PIPELINES_DIR, reports: Sequence[PackReport]
) -> dict[str, Pipeline]:
    """Every pipeline a `weft pipeline` command can resolve against.

    Task **3.7** — the first caller that actually merges `load_pipeline_catalogue`'s
    project-local documents with `load_contributed`'s pack contributions, closing the gap
    `ContributedPipelineNameCollisionError`'s own docstring named since task 2.8. Neither
    source is preferred over the other: a name both declare is refused
    (`ProjectPipelineNameCollisionError`) rather than one silently shadowing the other,
    the identical "never silently override" rule `02` §3 → *Slots* already states for a
    pack's stage-level contributions.

    Raises `PipelineDocumentError`/`MalformedPipelineError`/`DuplicatePipelineNameError`
    from either loader, unchanged, and `ProjectPipelineNameCollisionError` for a name both
    sources declare. The returned mapping is `resolve()`'s own `parents` shape — pass it
    directly, exactly as `load_pipeline_catalogue`'s own docstring already says of itself.
    """
    project = load_pipeline_catalogue(directory)
    contributed = load_contributed(reports)
    shared = sorted(set(project) & set(contributed))
    if shared:
        name = shared[0]
        raise ProjectPipelineNameCollisionError(
            f"pipeline '{name}' is declared both by a project-local document under "
            f"'{directory}' and by an installed pack's own contribution. Rename one of "
            f"the two — `weft plugins doctor` names which pack contributed the other."
        )
    return {**contributed, **project}


def declared_slot_ids(catalogue: Mapping[str, Pipeline]) -> frozenset[str]:
    """Every slot id any pipeline in `catalogue` declares — task **5.3a** (`S8`).

    Only the root of an `extends` chain may carry `slots:` (`weft_kernel.pipeline.Pipeline.
    _extends_and_stages_are_mutually_exclusive_with_operators`), so walking every catalogue
    entry's own `.slots` — never resolving a single one — already covers the whole chain: a
    child pipeline contributes no slot of its own to miss. `weft_cli.plugins_report.
    render_doctor` reads this against `Dependencies.contributions` to flag a pack whose
    contribution names a slot no pipeline in the catalogue declares at all — `02` §3 →
    *Slots*: "`weft plugins doctor` flags a pack whose contributions land in no pipeline at
    all" — never a per-pipeline check, since a contribution unplaced in *this* pipeline but
    placed in another is exactly the "installed and doing nothing... here" case `02` §3
    already tells apart from contributing nowhere at all.
    """
    return frozenset(slot.id for pipeline in catalogue.values() for slot in pipeline.slots)
