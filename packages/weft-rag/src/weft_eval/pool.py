"""`runs/pools/<run_id>.json` — ledger task **40.2**: a retrieval pool, captured once.

One level below the records, because every reader of `runs/` takes each `*.json` there for a
`RunRecord`.

A pool two phases share has to be written down rather than re-derived: under HNSW a search's own
depth depends on settings — `ef_search`, the index's own build state — a later run may not share,
so asking the store again is not the same measurement a second time. This module is the manifest
alone: what one arm's retrieval rung actually packed, per question, in ranking order, plus enough
identity (the experiment's digest, the corpus's, the question set's, the query pipeline's) for a
replay to trust the file without re-retrieving. Replay — reading this manifest back to score
against it, and the integrity refusals that need — is ledger task 40.2's second half, dispatched
separately; this module writes and reads the file and nothing else.

**A schema this release cannot read is refused loudly, naming both versions** — the identical
reasoning `weft_eval.question_set`/`weft_eval.corpus_manifest`/`weft_eval.experiment` already give
for the files they read: a document declaring a different schema is refused before its fields are
even inspected, rather than misread as this release's own shape.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Final, cast

from pydantic import BaseModel, ConfigDict, ValidationError

from weft_kernel.errors import WeftError

#: The schema this release of `weft-rag` reads and writes. A manifest naming a different number
#: was written by, or is meant for, a different `weft-rag` release — see `PoolManifestSchemaError`.
POOL_MANIFEST_SCHEMA_VERSION: Final[int] = 1


class PoolManifestError(WeftError):
    """A pool manifest could not be read as stated — missing, malformed JSON, or a shape this
    release does not recognise. The message names the path.
    """


class PoolManifestSchemaError(PoolManifestError):
    """The manifest names a schema this release does not read — the message names the path, the
    schema it declares and the schema this release reads.
    """


class PoolChunk(BaseModel):
    """One packed chunk, in the ranking's own order — `score` is the retrieval score it was
    packed with, never re-derived from a later search.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    node_id: str
    document_id: str
    content_sha256: str
    score: float


class PoolQuestion(BaseModel):
    """One question's captured pool. `text_sha256`/`relevant_sha256` are hashes of the *facts*,
    never their spelling, so a replay can tell a question file that still asks the same thing from
    one that has drifted, whatever whitespace or field order it is written with. `rule_fires` is
    whether `weft_retrieve.intent_and_anchors.find_anchors` matched this question's text at
    capture time, carried so a replay can tell a rule change from a retrieval change.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    text_sha256: str
    relevant_sha256: str
    rule_fires: bool
    chunks: tuple[PoolChunk, ...]


class PoolManifest(BaseModel):
    """A pool, captured once — see the module docstring. `store_rows` is the store's row count at
    capture; a replay refuses a store that no longer holds it (`L8.30`).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: int
    experiment: str
    experiment_digest: str
    arm: str
    corpus_digest: str
    question_set_digest: str
    query_pipeline: str
    query_pipeline_identity: str
    model_versions: Mapping[str, str]
    store: str
    store_rows: int
    questions: tuple[PoolQuestion, ...]


class LoadedPool(BaseModel):
    """A `PoolManifest` as read back off disk, plus the sha256 of the file's own bytes — the
    identity a replay pins its own trust to, since the manifest's fields could otherwise be
    reconstructed byte-differently and still validate.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    manifest: PoolManifest
    sha256: str


def text_sha256(text: str) -> str:
    """The sha256 of `text`'s own utf-8 bytes."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def relevant_set_sha256(ids: Iterable[str]) -> str:
    """The sha256 of a relevant-document set — order-independent and deduplicated, `weft_eval.
    run_record.corpus_identity`'s own construction one layer down: sorted, joined with `\\n`,
    hashed as utf-8.
    """
    joined = "\n".join(sorted(set(ids)))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def write_pool_manifest(manifest: PoolManifest, path: Path) -> None:
    """Write `manifest` to `path` as indented JSON, creating parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(manifest.model_dump_json(indent=2) + "\n", encoding="utf-8")


def load_pool_manifest(path: Path) -> LoadedPool:
    """Read `path` back as a `LoadedPool` — see the module docstring.

    Raises `PoolManifestSchemaError` when the declared `schema_version` is not
    `POOL_MANIFEST_SCHEMA_VERSION`, checked before the rest of the document is validated, so a
    newer manifest carrying fields this release does not know is refused as a schema mismatch
    rather than an unknown-field error. Raises `PoolManifestError` for anything else malformed —
    missing file, invalid JSON, or a document that fails the model's own validation.
    """
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise PoolManifestError(f"no pool manifest at '{path}': {exc}") from exc
    digest = hashlib.sha256(raw).hexdigest()
    try:
        document = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise PoolManifestError(f"'{path}': not valid JSON: {exc}") from exc
    if not isinstance(document, dict) or "schema_version" not in document:
        raise PoolManifestError(f"'{path}': not a pool manifest — no 'schema_version'")
    fields = cast("dict[str, object]", document)
    declared = fields["schema_version"]
    if declared != POOL_MANIFEST_SCHEMA_VERSION:
        raise PoolManifestSchemaError(
            f"'{path}': schema_version {declared!r} is not the "
            f"{POOL_MANIFEST_SCHEMA_VERSION} this weft-rag reads."
        )
    try:
        manifest = PoolManifest.model_validate(document)
    except ValidationError as exc:
        raise PoolManifestError(f"'{path}': {exc}") from exc
    return LoadedPool(manifest=manifest, sha256=digest)


__all__ = [
    "LoadedPool",
    "POOL_MANIFEST_SCHEMA_VERSION",
    "PoolChunk",
    "PoolManifest",
    "PoolManifestError",
    "PoolManifestSchemaError",
    "PoolQuestion",
    "load_pool_manifest",
    "relevant_set_sha256",
    "text_sha256",
    "write_pool_manifest",
]
