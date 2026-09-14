"""`corpus/manifest.toml`, read from the installed wheel — ledger repair **R22.4a**.

`weft eval baseline` (R22.4c) needs the manifest's ids, digests, tiers and paths to select and
verify a corpus tier, and it needs them from a caller holding only the `weft-rag` wheel — no
checkout, no `sys.path` manipulation. `scripts/fetch_corpus.py` already reads this file, and it
must stay standard-library-only, because the release archive ships that script to people who hold
no wheel at all: this module is a **second, deliberately narrower reader** of the identical file,
not a replacement for the fetcher's own. It reads only what a baseline needs — `id`, `path`,
`format`, `language`, `sha256`, `tier` — and ignores `source`, `source_sha256`, `render` and
`math_blocks_dropped`, which are the fetcher's own business: what a document is fetched from and
how it is rendered on the way in is not a fact this reader's callers ever ask.

Two readers of one file is only safe if they agree, so `test_both_readers_agree_on_the_tracked_
manifest` reads the tracked manifest through both and asserts every field they share is identical.
Nothing here fetches a document or writes one — `scripts/fetch_corpus.py` keeps sole ownership of
the network and the render pipeline; this module only ever reads what is already on disk.
"""

from __future__ import annotations

import hashlib
import tomllib
from enum import StrEnum
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

from weft_kernel.errors import WeftError

#: What every `[[document]]` table must carry for this reader's purposes. A manifest entry may
#: carry more — `source`, `render`, `math_blocks_dropped` — and this reader ignores the rest.
_REQUIRED_KEYS: Final[tuple[str, ...]] = ("id", "path", "format", "language", "sha256", "tier")


class Tier(StrEnum):
    """Where a document comes from, and therefore what may be done with it."""

    GATE = "gate"
    FETCH = "fetch"
    OPERATOR = "operator"

    @property
    def reproducible(self) -> bool:
        """Whether somebody who is not us can obtain these bytes.

        V1's second clause — *"either redistributable or fetched by a pinned, checksummed
        script"* — is a property of the tier and of nothing else: `gate` is tracked in the
        repository, `fetch` is materialised by `scripts/fetch_corpus.py` against a versioned
        pin, and an `operator` document is held under publisher copyright and cannot be had at
        any price.
        """
        return self is not Tier.OPERATOR


class DocumentStatus(StrEnum):
    """What was found on disk, per document, against the manifest's own digest."""

    OK = "ok"
    MISSING = "missing"
    CORRUPT = "corrupt"


class ManifestDocument(BaseModel):
    """One corpus document, as this reader needs it — a subset of what the manifest declares."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1)
    path: Path
    format: str = Field(min_length=1)
    language: str = Field(min_length=1)
    sha256: str = Field(min_length=1)
    tier: Tier


class CorpusManifest(BaseModel):
    """The corpus this reader found: a name and its documents, in the manifest's own order."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1)
    documents: tuple[ManifestDocument, ...]


class CorpusManifestError(WeftError):
    """The manifest is absent, malformed, or declares something this reader cannot honour."""


def load_manifest(manifest: Path) -> CorpusManifest:
    """Reads `manifest`, or refuses naming the file, the entry and the key that is wrong."""
    if not manifest.exists():
        message = f"no corpus manifest at {manifest}. The corpus is defined by that file."
        raise CorpusManifestError(message)
    with manifest.open("rb") as handle:
        raw = tomllib.load(handle)
    try:
        name = str(raw["corpus"]["name"])
        entries = raw["document"]
    except KeyError as exc:
        message = (
            f"{manifest} is missing {exc}. A manifest needs a [corpus] table with a name, "
            "and one [[document]] table per document."
        )
        raise CorpusManifestError(message) from exc
    root = manifest.parent.resolve()
    documents = tuple(_read_entry(entry, root=root, manifest=manifest) for entry in entries)
    return CorpusManifest(name=name, documents=documents)


def _read_entry(entry: dict[str, object], *, root: Path, manifest: Path) -> ManifestDocument:
    """One `[[document]]` table, narrowed to what this reader needs, or a refusal naming it."""
    identifier = str(entry.get("id", "<an entry with no id>"))

    absent = [key for key in _REQUIRED_KEYS if key not in entry]
    if absent:
        message = (
            f"document {identifier!r} in {manifest} is missing {absent}. Every entry needs "
            f"{list(_REQUIRED_KEYS)}."
        )
        raise CorpusManifestError(message)

    declared_tier = str(entry["tier"])
    if declared_tier not in {member.value for member in Tier}:
        message = (
            f"document {identifier!r} in {manifest} declares tier {declared_tier!r}, which is "
            f"not a tier. Valid tiers are: {', '.join(member.value for member in Tier)}."
        )
        raise CorpusManifestError(message)

    declared_path = str(entry["path"])
    path = (root / declared_path).resolve()
    if not path.is_relative_to(root):
        message = (
            f"document {identifier!r} in {manifest} declares path {declared_path!r}, which "
            f"resolves outside {root}. A corpus document lives under the manifest's own directory."
        )
        raise CorpusManifestError(message)

    return ManifestDocument(
        id=identifier,
        path=path,
        format=str(entry["format"]),
        language=str(entry["language"]),
        sha256=str(entry["sha256"]),
        tier=Tier(declared_tier),
    )


def verify_document(document: ManifestDocument) -> DocumentStatus:
    """Checks one document on disk against the digest the manifest declares for it."""
    if not document.path.is_file():
        return DocumentStatus.MISSING
    hasher = hashlib.sha256()
    with document.path.open("rb") as handle:
        while chunk := handle.read(1 << 20):
            hasher.update(chunk)
    if hasher.hexdigest() != document.sha256:
        return DocumentStatus.CORRUPT
    return DocumentStatus.OK
