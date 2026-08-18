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

from pathlib import Path

import yaml
from pydantic import ValidationError

from weft_kernel.errors import WeftError
from weft_kernel.pipeline import Pipeline


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

    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise PipelineDocumentError(f"{path} is not valid YAML: {exc}") from exc

    if not isinstance(document, dict):
        raise PipelineDocumentError(
            f"{path} does not parse to a mapping — a pipeline document is a set of "
            f"top-level keys (name, extends, stages, ...), and this file's top-level YAML "
            f"value is a {type(document).__name__}."
        )

    try:
        return Pipeline.model_validate(document)
    except ValidationError as exc:
        raise MalformedPipelineError(f"{path} is not a valid pipeline document: {exc}") from exc


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
