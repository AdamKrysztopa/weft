"""Materialises and verifies the named corpus that prerequisite V1 requires.

`docs/09-release.md` §4.3 accepts a corpus that is *"either redistributable or
fetched by a pinned, checksummed script"*, and fails one where *"a fetch is not
reproducible byte-for-byte"*. This is that script, and the whole design follows
from that one clause.

**The bytes are not in this repository and must not be.** Five of the papers an
operator supplied are published under publisher copyright, so committing them
would be redistribution this project has no right to perform. What is tracked is
`corpus/manifest.toml`: every document named, with the sha256 that identifies it.
That is what makes the corpus *bounded and named* without the bytes being here.

**Pins are revisions, not titles.** A Wikipedia article fetched by title returns
whatever it says today; fetched by `oldid` it returns one immutable revision. An
arXiv paper fetched as `1304.7717` returns the latest version; fetched as
`1304.7717v2` it returns one. Every fetchable document in the manifest therefore
carries a *versioned* identifier, and the sha256 is checked against what arrives
— a pin that stops reproducing is a failure this script reports rather than a
difference it absorbs.

**What is fetched and what is kept are not always the same bytes.** A PDF is
stored as it is served. A Wikipedia revision is served as *wikitext* and stored
as prose, because a corpus of `{{Dopracować|źródła = 2025-11}}` would put that
markup into every chunk drawn from it. So such an entry declares a `render`, and
**both halves are pinned**: `source_sha256` is the revision that was fetched and
`sha256` is the document that was written. Only pinning the second would let a
hand-made file stand in for a fetch — which is precisely what happened here once,
and it survived a green gate because nothing in it ever ran a fetch.

**Three tiers, and only two are fetchable.** `fetch` documents are retrieved here.
`gate` documents are tracked in the repository and need no network. `operator`
documents are the copyrighted papers: named and checksummed so a local
materialisation can be *verified*, never fetched. `verify` therefore reports an
absent operator document as **missing**, not as an error — that tier is outside
V1's reproducibility clause by construction, which `docs/build-ledger.md` task
**2.1** states outright, along with the fact that no waiver of V1 is taken: the
reproducible tiers cover every claimed format and both languages on their own.

**What is checked here and what is checked in the gate are different jobs.** This
script answers "does the corpus on this machine match the manifest?", which needs
the bytes. `tests/docs/test_corpus_manifest.py` answers V1's coverage clause,
which needs only the tracked manifest and the registry — and it imports this
module rather than re-reading the manifest, so there is one reader of that file
and not two to drift apart.
"""

import argparse
import hashlib
import sys
import time
import tomllib
import urllib.error
import urllib.request
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Final

from wikitext import Rendering, render

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = REPO_ROOT / "corpus" / "manifest.toml"

#: Wikipedia asks for a contact address in the agent string and rate-limits
#: anonymous loops; a bare fetch of nine articles earned HTTP 429 during the
#: build. Identifying the client is the courtesy that keeps the pin fetchable.
USER_AGENT = "weft-corpus/1.0 (https://github.com/AdamKrysztopa/weft; corpus materialisation)"

#: Seconds between requests. arXiv asks for one request every three seconds and
#: Wikipedia throttles faster loops. This is deliberately not configurable: a
#: knob here would only ever be turned down, and the failure it buys is a ban.
POLITE_DELAY_SECONDS = 3.5


class Tier(StrEnum):
    """Where a document comes from, and therefore what may be done with it."""

    GATE = "gate"
    FETCH = "fetch"
    OPERATOR = "operator"

    @property
    def reproducible(self) -> bool:
        """Whether somebody who is not us can obtain these bytes.

        V1's second clause — *"either redistributable or fetched by a pinned, checksummed
        script"* — is a property of the tier and of nothing else: `gate` is tracked here,
        `fetch` is materialised by this script against a versioned pin, and an `operator`
        document is held under publisher copyright and cannot be had at any price.

        It lives on the enum because three places need the same answer — the manifest's
        format coverage, the question subset a published baseline is measured over, and the
        baseline run's own `reproducible` flag — and a fact copied into three files is the
        one `docs/README.md` opens by describing.
        """
        return self is not Tier.OPERATOR


class Status(StrEnum):
    """What was found on disk, per document."""

    OK = "ok"
    MISSING = "missing"
    CORRUPT = "corrupt"
    FETCHED = "fetched"


@dataclass(frozen=True)
class Document:
    """One corpus document as the manifest declares it."""

    id: str
    path: Path
    fmt: str
    language: str
    sha256: str
    tier: Tier
    source: str
    #: The digest of what the source serves, when that is not what is stored. Empty when the two
    #: are the same bytes, which is every document that is not rendered on the way in.
    source_sha256: str = ""
    render: Rendering | None = None
    #: What the rendering cost, checked against what it actually dropped. `None` where nothing is
    #: rendered — an unrendered document has no loss to state, which is not the same as zero loss.
    math_blocks_dropped: int | None = None


@dataclass(frozen=True)
class Result:
    """What happened to one document."""

    document: Document
    status: Status
    detail: str = ""


#: What every `[[document]]` table must carry. `source` is deliberately absent: an `operator`
#: document has no URL to state, and requiring one would push a placeholder into the manifest.
REQUIRED_KEYS: Final[tuple[str, ...]] = ("id", "path", "format", "language", "sha256", "tier")


def load_manifest(manifest: Path) -> tuple[str, list[Document]]:
    """Reads the manifest, or fails naming the file, the entry and the key that is wrong."""
    if not manifest.exists():
        message = f"no corpus manifest at {manifest}. The corpus is defined by that file."
        raise FileNotFoundError(message)
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
        raise ValueError(message) from exc
    root = manifest.parent.resolve()
    return name, [_read_entry(entry, root=root, manifest=manifest) for entry in entries]


def _read_entry(entry: dict[str, object], *, root: Path, manifest: Path) -> Document:
    """One `[[document]]` table, or a refusal that names the entry and not only the key.

    A bare `KeyError: 'language'` out of a comprehension over twenty-five entries names the key and
    leaves the reader to work out which entry dropped it, which in a hand-edited manifest is most
    of the job still to do. The id is read first so every refusal below can carry it.
    """
    identifier = str(entry.get("id", "<an entry with no id>"))

    absent = [key for key in REQUIRED_KEYS if key not in entry]
    if absent:
        message = (
            f"document {identifier!r} in {manifest} is missing {absent}. Every entry needs "
            f"{list(REQUIRED_KEYS)}."
        )
        raise ValueError(message)

    declared_tier = str(entry["tier"])
    if declared_tier not in {member.value for member in Tier}:
        message = (
            f"document {identifier!r} in {manifest} declares tier {declared_tier!r}, which is not "
            f"a tier. Valid tiers are: {', '.join(member.value for member in Tier)}."
        )
        raise ValueError(message)

    # `fetch` writes retrieved bytes to this path, so the path decides where a network response
    # lands. The manifest is a tracked, reviewed artefact rather than user input — which is a
    # reason to check this once, here, rather than a reason to trust it everywhere.
    declared_path = str(entry["path"])
    path = (root / declared_path).resolve()
    if not path.is_relative_to(root):
        message = (
            f"document {identifier!r} in {manifest} declares path {declared_path!r}, which "
            f"resolves outside {root}. A corpus document lives under the manifest's own directory."
        )
        raise ValueError(message)

    tier = Tier(declared_tier)
    source = str(entry.get("source", ""))
    if tier is Tier.FETCH and not source:
        message = (
            f"document {identifier!r} in {manifest} is in the {Tier.FETCH.value!r} tier and "
            f"declares no source. That tier means 'retrieved by a pinned, checksummed script', so "
            f"an entry with nothing to retrieve claims a reproducibility nobody can honour."
        )
        raise ValueError(message)

    rendering = _read_rendering(entry, identifier=identifier, manifest=manifest)
    if rendering is not None and not entry.get("source_sha256"):
        message = (
            f"document {identifier!r} in {manifest} declares render {rendering.value!r} and no "
            f"source_sha256. A rendered document pins two things — the revision that was fetched "
            f"and the document that was written — and pinning only the second lets a file made by "
            f"hand pass for a fetch."
        )
        raise ValueError(message)

    return Document(
        id=identifier,
        path=path,
        fmt=str(entry["format"]),
        language=str(entry["language"]),
        sha256=str(entry["sha256"]),
        tier=tier,
        source=source,
        source_sha256=str(entry.get("source_sha256", "")),
        render=rendering,
        math_blocks_dropped=_read_optional_count(entry, "math_blocks_dropped"),
    )


def _read_rendering(
    entry: dict[str, object], *, identifier: str, manifest: Path
) -> Rendering | None:
    """The declared rendering, or a refusal that lists the renderings that exist."""
    declared = entry.get("render")
    if declared is None:
        return None
    if str(declared) not in {member.value for member in Rendering}:
        message = (
            f"document {identifier!r} in {manifest} declares render {str(declared)!r}, which is "
            f"not a rendering. Valid renderings are: "
            f"{', '.join(member.value for member in Rendering)}."
        )
        raise ValueError(message)
    return Rendering(str(declared))


def _read_optional_count(entry: dict[str, object], key: str) -> int | None:
    """An integer the manifest may omit, read as an integer rather than as whatever TOML gave."""
    value = entry.get(key)
    return None if value is None else int(str(value))


def digest(path: Path) -> str:
    """sha256 of a file, read in chunks so a large PDF does not sit in memory."""
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1 << 20):
            hasher.update(chunk)
    return hasher.hexdigest()


def verify_one(document: Document) -> Result:
    """Checks one document against the digest the manifest declares for it."""
    # `is_file`, not `exists`: a directory at the declared path is a manifest that describes a
    # document nobody has, and `exists()` would send it on to `digest` to raise `IsADirectoryError`
    # with no document id anywhere in the traceback.
    if not document.path.is_file():
        return Result(document, Status.MISSING, f"not at {document.path}")
    found = digest(document.path)
    if found != document.sha256:
        return Result(
            document,
            Status.CORRUPT,
            f"expected {document.sha256[:16]}…, found {found[:16]}…",
        )
    return Result(document, Status.OK)


def fetch_one(document: Document) -> Result:
    """Fetches one document and refuses to keep bytes that do not match the pin.

    The digest check is the point of the exercise, not a safety net: V1 fails if
    a fetch is not reproducible byte-for-byte, so a pin that returns different
    bytes than it did when the manifest was written is exactly the condition this
    script exists to surface. The file is written only after the check passes,
    so a failed fetch cannot leave a plausible-looking wrong document behind.
    """
    if not document.source.startswith("https://"):
        return Result(document, Status.MISSING, f"source is not an https URL: {document.source!r}")
    request = urllib.request.Request(document.source, headers={"User-Agent": USER_AGENT})  # noqa: S310
    try:
        # noqa S310 above: the scheme is checked immediately above this call, which
        # is the audit S310 asks for. The URL is manifest data, not user input.
        with urllib.request.urlopen(request, timeout=120) as response:  # noqa: S310
            body = response.read()
    except (urllib.error.URLError, TimeoutError) as exc:
        return Result(document, Status.MISSING, f"fetch failed: {type(exc).__name__}: {exc}")

    if document.render is not None:
        rendered = _rendered(document, body, document.render)
        if isinstance(rendered, Result):
            return rendered
        body = rendered

    found = hashlib.sha256(body).hexdigest()
    if found != document.sha256:
        return Result(
            document,
            Status.CORRUPT,
            f"the pin no longer reproduces: expected {document.sha256[:16]}…, "
            f"produced {found[:16]}… from {document.source}",
        )
    document.path.parent.mkdir(parents=True, exist_ok=True)
    document.path.write_bytes(body)
    return Result(document, Status.FETCHED)


def _rendered(document: Document, body: bytes, rendering: Rendering) -> bytes | Result:
    """The stored bytes for a document that is rendered on the way in, or why there are none.

    The fetched revision is checked *before* it is rendered, so the two ways this can fail stay
    told apart: bytes that miss `source_sha256` are the source having moved under the pin, and
    bytes that miss `sha256` afterwards are this repository's rendering having changed. Reported
    as one failure they would send the reader to the wrong file.
    """
    fetched = hashlib.sha256(body).hexdigest()
    if fetched != document.source_sha256:
        return Result(
            document,
            Status.CORRUPT,
            f"the pin no longer reproduces before rendering: expected "
            f"{document.source_sha256[:16]}…, fetched {fetched[:16]}… from {document.source}",
        )
    # The digest above already proved these are the pinned bytes, so a decoding failure here would
    # mean the pin itself is not UTF-8 — worth a traceback rather than a status.
    result = render(body.decode("utf-8"), rendering)
    if (
        document.math_blocks_dropped is not None
        and result.math_blocks_dropped != document.math_blocks_dropped
    ):
        return Result(
            document,
            Status.CORRUPT,
            f"the manifest records {document.math_blocks_dropped} dropped math block(s) and the "
            f"rendering dropped {result.math_blocks_dropped}. That count is the document's own "
            f"statement of what rendering cost it, so it is checked rather than trusted.",
        )
    return result.text.encode("utf-8")


def report(results: list[Result], name: str) -> int:
    """Prints one line per document and returns the exit code.

    An absent `operator` document is reported and does not fail the run: that
    tier is outside V1's reproducibility clause and an operator who does not
    hold those papers still has a usable corpus. Anything else missing, and any
    digest mismatch anywhere, is a failure.
    """
    by_status: dict[Status, list[Result]] = {}
    for result in results:
        by_status.setdefault(result.status, []).append(result)

    for result in results:
        if result.status is Status.OK:
            continue
        print(f"  {result.status.value:8s} {result.document.id:34s} {result.detail}")

    ok = len(by_status.get(Status.OK, ()))
    fetched = len(by_status.get(Status.FETCHED, ()))
    corrupt = by_status.get(Status.CORRUPT, [])
    missing = by_status.get(Status.MISSING, [])
    absent_operator = [r for r in missing if r.document.tier is Tier.OPERATOR]
    absent_required = [r for r in missing if r.document.tier is not Tier.OPERATOR]

    print(
        f"\ncorpus {name}: {len(results)} documents — "
        f"{ok} verified, {fetched} fetched, {len(corrupt)} corrupt, {len(missing)} missing "
        f"({len(absent_operator)} of them operator-tier and therefore permitted)"
    )
    if corrupt or absent_required:
        print(
            "\nFAILED. A corrupt document means its pin no longer reproduces the bytes the "
            "manifest was written against, which is V1's own failure condition. A missing "
            "document outside the operator tier means the corpus is incomplete."
        )
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "action",
        choices=("verify", "fetch"),
        help="verify checks what is on disk against the manifest; fetch retrieves the fetch tier",
    )
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    arguments = parser.parse_args(argv)

    name, documents = load_manifest(arguments.manifest)

    if arguments.action == "verify":
        return report([verify_one(document) for document in documents], name)

    # The delay goes *before* each request after the first, and is counted over requests actually
    # made rather than over a position in the manifest. Pacing that depended on where the fetch
    # tier happened to sit in the file would vanish the day someone reordered an entry, and its
    # failure mode is being rate-limited out of the pins the corpus is defined by.
    results: list[Result] = []
    requested = 0
    for document in documents:
        if document.tier is not Tier.FETCH:
            results.append(verify_one(document))
            continue
        existing = verify_one(document)
        if existing.status is Status.OK:
            results.append(existing)
            continue
        if requested:
            time.sleep(POLITE_DELAY_SECONDS)
        requested += 1
        print(f"  fetching {document.id} from {document.source}")
        results.append(fetch_one(document))
    return report(results, name)


if __name__ == "__main__":
    sys.exit(main())
