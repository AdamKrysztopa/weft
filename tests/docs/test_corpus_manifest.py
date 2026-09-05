"""Prerequisite **V1** (`docs/09-release.md` §4.3) as a machine check rather than a claim.

V1 wants a corpus that is *"bounded and named; either redistributable or fetched by a pinned,
checksummed script; covering every format an installed extractor claims; at least one
non-English body"*, and it states its own failure condition: *"Any declared format has no
document in the corpus, or a fetch is not reproducible byte-for-byte."* Both halves are checked
here — the first against the registry, the second against `scripts/fetch_corpus.py`'s refusal to
keep bytes that miss their digest.

**The claimed format set is derived, never listed.** `weft_extract.accept.claimed_extensions`
already answers "what can ingest read?" from the plugins that actually resolved, and asking it
again here is the whole point: installing `weft-pdf` widened the requirement without anyone
editing this file, and a hand-written `{".txt", ".md", ".pdf"}` would be the second copy
`docs/README.md` opens by describing — right on the day it was typed and wrong on the day a
fourth extractor ships.

**Nothing here can pass because a walk found nothing** (task 1.18). The corpus payload is
deliberately untracked — the papers are under publisher copyright — so a checkout with no
materialised corpus is normal, and a suite that quietly measured an empty directory would report
V1 as satisfied on a machine holding no documents at all. Every check therefore walks the
**tracked manifest**, which an absent corpus cannot empty, and the two sets being compared each
carry a floor asserting they are non-empty before the comparison is allowed to mean anything.

**The `operator` tier is outside V1's second clause and that is recorded, not assumed** —
`docs/build-ledger.md` → task **2.1** states it, along with the fact that no waiver of V1 is
taken: the reproducible tiers cover every claimed format and both languages on their own.

**A tier label is not evidence, and this file used to treat it as if it were.** `tier = "fetch"`
is a word in a hand-edited TOML file; the coverage check below reads it and calls the result
*reproducible*. It was wrong once — nine entries pointed at a rendered HTML page while their
digest belonged to a hand-derived rendering no tracked code produced, so every one of them would
have failed on a stranger's first `fetch` while this suite stayed green. So the label is now tied
to behaviour from two sides: the loader refuses a `fetch` entry that carries nothing fetchable,
and `test_one_real_pin_per_format_still_reproduces` runs the real thing against the network when
`WEFT_CORPUS_NETWORK` is set. The checks in between use a stub, because a gate that needs the
internet is a gate that fails on a train.
"""

from __future__ import annotations

import hashlib
import os
import time
import tomllib
import urllib.request
from collections.abc import Callable, Iterable
from dataclasses import replace
from pathlib import Path
from typing import Final

import pytest
from fetch_corpus import (
    POLITE_DELAY_SECONDS,
    Document,
    Result,
    Status,
    Tier,
    fetch_one,
    load_manifest,
    verify_one,
)
from wikitext import Rendering, render

from tests.discovery import discover_for_tests
from weft_extract.accept import claimed_extensions

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
MANIFEST: Final[Path] = REPO_ROOT / "corpus" / "manifest.toml"

#: The ratchet. A format an installed extractor claims but the corpus does not cover is V1's own
#: failure condition, so waiving one is a decision about the release prerequisite and belongs in a
#: diff where someone has to justify it. **Pinned empty**, and it stays that way while the corpus
#: carries `.txt`, `.md` and `.pdf` in two languages.
FORMATS_WAIVED_FROM_CORPUS: Final[frozenset[str]] = frozenset()

#: The tiers V1's second clause reaches: `gate` is redistributable and tracked, `fetch` is
#: retrieved by a pinned, checksummed script. `operator` is neither — those documents are held
#: under publisher copyright, recorded with a digest so a local copy can be *verified*, and never
#: counted toward coverage, because a stranger reproducing the published baseline cannot obtain
#: them.
REPRODUCIBLE_TIERS: Final[frozenset[Tier]] = frozenset(tier for tier in Tier if tier.reproducible)


@pytest.fixture(scope="module")
def documents() -> tuple[Document, ...]:
    """Every document the tracked manifest declares."""
    _, entries = load_manifest(MANIFEST)
    return tuple(entries)


@pytest.fixture(scope="module")
def claimed() -> frozenset[str]:
    """Every file suffix an installed extractor claims, asked of the registry at run time."""
    return frozenset(claimed_extensions(discover_for_tests()))


# --- The two floors, which is what stops an empty walk reporting success ---------------------


def test_the_manifest_declares_a_named_non_empty_corpus() -> None:
    # Floor A. The walk is over the tracked manifest and never over `corpus/`'s directory listing:
    # an absent corpus cannot empty a tracked file, which is what lets this fail rather than skip.
    # Arrange
    name, entries = load_manifest(MANIFEST)

    # Act
    identifiers = [entry.id for entry in entries]

    # Assert
    assert name, f"{MANIFEST} declares no corpus name; V1 wants a corpus that is *named*"
    assert entries, f"{MANIFEST} declares no documents; every check below would then be vacuous"
    repeated = sorted({one for one in identifiers if identifiers.count(one) > 1})
    assert not repeated, (
        f"duplicate document ids in {MANIFEST}: {repeated}. An id is how a question's ground truth "
        f"names its source, so two documents sharing one is a corpus that cannot be judged against."
    )


def test_installed_extractors_claim_at_least_one_format(claimed: frozenset[str]) -> None:
    # Floor B. Coverage is a subset test, and the subset test every set passes is the empty one:
    # if discovery ever returned no extractors, "every claimed format is covered" would be true of
    # a corpus of nothing. This is the assertion that makes the next two tests mean something.
    assert claimed, (
        "no installed extractor claims any file suffix, so the coverage checks below would pass "
        "over an empty set. Either discovery is broken or no extractor pack is installed."
    )


# --- V1's coverage clause, in both directions -------------------------------------------------


def test_every_claimed_format_has_a_reproducible_document(
    documents: tuple[Document, ...], claimed: frozenset[str]
) -> None:
    # Arrange
    reproducible = [entry for entry in documents if entry.tier in REPRODUCIBLE_TIERS]

    # Act
    covered = {entry.path.suffix for entry in reproducible}
    uncovered = sorted(claimed - covered - FORMATS_WAIVED_FROM_CORPUS)

    # Assert
    assert not uncovered, (
        f"installed extractors claim {uncovered} and no reproducible corpus document has that "
        f"suffix — V1's own failure condition, 'any declared format has no document in the "
        f"corpus'. Shipping an extractor pack widens this requirement, so add a document in the "
        f"same commit or name the format in FORMATS_WAIVED_FROM_CORPUS and say why."
    )


def test_every_fetch_document_declares_a_pinned_https_source(
    documents: tuple[Document, ...],
) -> None:
    # The half of "reproducible" the tier label does not carry. `fetch_one` already refuses a
    # source that is not an https URL, but nothing in the gate ever calls it, so a `fetch` entry
    # over a prose source — `"held by the operator; no open version located"` reads perfectly well
    # in a diff — counted toward coverage above while being unobtainable by anyone.
    # Arrange
    fetchable = [entry for entry in documents if entry.tier is Tier.FETCH]

    # Act
    unfetchable = sorted(
        f"{entry.id}: {entry.source!r}"
        for entry in fetchable
        if not entry.source.startswith("https://")
    )

    # Assert
    assert fetchable, "no document is in the fetch tier, so this check walked an empty set"
    assert not unfetchable, (
        f"fetch-tier documents whose source is not an https URL: {unfetchable}. The tier means "
        f"'retrieved by a pinned, checksummed script'; an entry the script cannot retrieve is "
        f"counted toward V1's coverage and cannot be obtained by the stranger V1 is written for."
    )


def test_every_manifest_format_is_claimed_by_an_installed_extractor(
    documents: tuple[Document, ...], claimed: frozenset[str]
) -> None:
    # Act
    unreadable = sorted({entry.path.suffix for entry in documents} - claimed)

    # Assert
    assert not unreadable, (
        f"the manifest declares documents in {unreadable}, which no installed extractor claims. "
        f"A corpus holding a format nothing can read is a baseline measured over fewer documents "
        f"than it reports — either the extractor pack is missing from the workspace or the "
        f"documents do not belong in the corpus."
    )


def test_a_declared_format_agrees_with_its_own_path(documents: tuple[Document, ...]) -> None:
    # The coverage checks above read the suffix, because that is what an extractor claims. `format`
    # is the human-facing half of the same fact, and two spellings of one fact drift — an entry
    # reading `format = "md"` over a `.txt` path would leave the manifest describing a corpus
    # nobody has.
    # Act
    disagreeing = [
        f"{entry.id}: format={entry.fmt!r} but path {entry.path.name!r}"
        for entry in documents
        if entry.path.suffix != f".{entry.fmt}"
    ]

    # Assert
    assert not disagreeing, (
        f"manifest entries whose format does not match their path: {disagreeing}"
    )


def test_at_least_one_document_is_not_english(documents: tuple[Document, ...]) -> None:
    # V1 asks for a non-English body by name, and says why: Polish retrieval is shipped product
    # under requirement 6, and a language-specific branch nothing in the corpus ever exercises is
    # indistinguishable, in the test run, from a branch that was deleted.
    # Act
    other = sorted({entry.language for entry in documents if entry.language != "en"})

    # Assert
    assert other, (
        "every document in the manifest is English. V1 requires at least one non-English body "
        "because the cleaning chain and the chunker both branch on language."
    )


def test_the_declared_document_count_matches_the_entries() -> None:
    # Arrange
    with MANIFEST.open("rb") as handle:
        raw = tomllib.load(handle)

    # Act
    declared = raw["corpus"]["documents"]
    actual = len(raw["document"])

    # Assert
    assert declared == actual, (
        f"{MANIFEST} announces {declared} documents in its [corpus] table and carries {actual}. "
        f"The header is a summary of the entries, so it is either correct or it is misleading a "
        f"reader about the size of the set a baseline was measured over."
    )


# --- What is on disk, when anything is ---------------------------------------------------------


def test_a_materialised_tier_is_whole_and_verifies(documents: tuple[Document, ...]) -> None:
    # A tier is either fully present or fully absent. A half-fetched corpus silently shrinks the
    # set a baseline is measured over — catching a corrupt file and quietly skipping it turns a
    # fetch failure into a smaller, undocumented corpus — and "not fetched yet" is a fact about
    # this checkout, never a pass.
    # Arrange
    results = {entry.id: verify_one(entry) for entry in documents}

    # Act
    corrupt = sorted(i for i, r in results.items() if r.status is Status.CORRUPT)
    partial = _partially_materialised_tiers(results.values())

    # Assert
    assert not corrupt, (
        f"corpus documents whose bytes do not match their digest: {corrupt}. That is V1's second "
        f"failure condition — a fetch that is no longer reproducible byte-for-byte. Run "
        f"`python scripts/fetch_corpus.py verify` for the digests."
    )
    assert not partial, (
        f"partially materialised tier(s): {partial}. A tier is all present or all absent; a "
        f"corpus missing some of its documents measures a smaller set than it reports."
    )


def test_the_digest_check_can_fail(tmp_path: Path) -> None:
    # The self-test the on-disk check needs to be worth running. Every document verifying is only
    # evidence if a document that does not would be caught, and the corpus is untracked, so on a
    # fresh checkout the check above passes over an entirely absent set.
    # Arrange
    payload = tmp_path / "tampered.txt"
    payload.write_bytes(b"the bytes the manifest was written against")
    honest = Document(
        id="self-test",
        path=payload,
        fmt="txt",
        language="en",
        sha256=_digest_of(payload),
        tier=Tier.GATE,
        source="",
    )
    payload.write_bytes(b"the bytes the manifest was written agains!")

    # Act
    result = verify_one(honest)

    # Assert
    assert result.status is Status.CORRUPT
    assert honest.sha256[:16] in result.detail, (
        f"a corrupt document must name both digests so the reader can tell which is which; got "
        f"{result.detail!r}"
    )


# --- The script's refusals ---------------------------------------------------------------------


def test_an_unknown_tier_is_refused_naming_the_valid_tiers(tmp_path: Path) -> None:
    # Arrange
    manifest = _manifest_with(tmp_path, 'tier = "gate"', 'tier = "gold"')

    # Act
    with pytest.raises(ValueError, match="gold") as raised:
        load_manifest(manifest)

    # Assert
    assert "operator" in str(raised.value), (
        f"an unknown tier must list the tiers that exist, not just reject the one given; got "
        f"{raised.value}"
    )


def test_an_entry_missing_a_required_key_is_refused_by_id(tmp_path: Path) -> None:
    # Arrange — `language` dropped. A bare `KeyError: 'language'` from a comprehension names the
    # key and not the entry, which in a 25-document manifest is most of the work still to do.
    manifest = _manifest_with(tmp_path, 'language = "en"', "")

    # Act
    with pytest.raises(ValueError, match="language") as raised:
        load_manifest(manifest)

    # Assert
    assert "self-test" in str(raised.value)


def test_a_path_escaping_the_corpus_directory_is_refused(tmp_path: Path) -> None:
    # `fetch` writes fetched bytes to the declared path, so the path decides where a network
    # response lands. It is manifest data rather than user input, which is a reason to check it
    # once here rather than a reason to trust it.
    # Arrange
    manifest = _manifest_with(tmp_path, 'path = "sample.txt"', 'path = "../escaped.txt"')

    # Act / Assert
    with pytest.raises(ValueError, match="escaped.txt"):
        load_manifest(manifest)


def test_a_fetch_that_misses_the_pin_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # V1 fails when "a fetch is not reproducible byte-for-byte", so a pin returning different bytes
    # than the manifest was written against is the condition the script exists to surface. Writing
    # them anyway would leave a plausible-looking wrong document behind and a corpus that verifies
    # against nothing.
    # Arrange
    target = tmp_path / "moved-under-us.txt"
    document = Document(
        id="ax-moved",
        path=target,
        fmt="txt",
        language="en",
        sha256=64 * "0",
        tier=Tier.FETCH,
        source="https://example.invalid/paper",
    )
    monkeypatch.setattr(urllib.request, "urlopen", _serving(b"a different revision"))

    # Act
    result = fetch_one(document)

    # Assert
    assert result.status is Status.CORRUPT
    assert not target.exists(), (
        "bytes that missed their digest were written to disk; the next `verify` would then report "
        "a corrupt document rather than an absent one, which is a worse fact to act on"
    )


def test_a_fetch_entry_with_nothing_to_fetch_is_refused_by_id(tmp_path: Path) -> None:
    # `source` stays optional for the operator tier — those documents have no URL to state and a
    # placeholder would be worse than the absence. For a `fetch` entry it is the entry's whole
    # meaning, and an entry that declares the tier without it is a coverage claim nobody can honour.
    # Arrange
    manifest = _manifest_with(tmp_path, 'tier = "gate"', 'tier = "fetch"')

    # Act
    with pytest.raises(ValueError, match="source") as raised:
        load_manifest(manifest)

    # Assert
    assert "self-test" in str(raised.value)


def test_an_unknown_rendering_is_refused_naming_the_ones_that_exist(tmp_path: Path) -> None:
    # Arrange
    manifest = _manifest_with(
        tmp_path, 'tier = "gate"', 'tier = "gate"\nrender = "wikitext-markdown"'
    )

    # Act
    with pytest.raises(ValueError, match="wikitext-markdown") as raised:
        load_manifest(manifest)

    # Assert
    assert Rendering.PLAIN_TEXT.value in str(raised.value), (
        f"an unknown rendering must list the renderings that exist, not just reject the one given; "
        f"got {raised.value}"
    )


def test_a_fetch_renders_what_it_retrieved_before_hashing_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # What MediaWiki serves is wikitext and what the corpus holds is prose, so the digest in the
    # manifest is over the *rendered* bytes. This is the step whose absence made nine entries
    # unreproducible: the digests were right about a file on one laptop and wrong about every pin.
    # Arrange
    wikitext = "'''Test''' – zdanie z [[teoria|teorii]].\n"
    expected = render(wikitext, Rendering.PLAIN_TEXT).text.encode("utf-8")
    document = _fetchable(
        tmp_path / "rendered.txt",
        source_sha256=hashlib.sha256(wikitext.encode("utf-8")).hexdigest(),
        sha256=hashlib.sha256(expected).hexdigest(),
        rendering=Rendering.PLAIN_TEXT,
        math_blocks_dropped=0,
    )
    monkeypatch.setattr(urllib.request, "urlopen", _serving(wikitext.encode("utf-8")))

    # Act
    result = fetch_one(document)

    # Assert
    assert result.status is Status.FETCHED, result.detail
    assert document.path.read_bytes() == expected


def test_a_fetch_whose_wikitext_misses_its_own_pin_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Both halves are pinned, and this is the half that says *which* half moved. A revision that
    # came back different is a fact about Wikipedia; a rendering that came out different is a fact
    # about this repository, and reporting them as one failure would send the reader to the wrong
    # place.
    # Arrange
    document = _fetchable(
        tmp_path / "rendered.txt",
        source_sha256=64 * "0",
        sha256=64 * "1",
        rendering=Rendering.PLAIN_TEXT,
        math_blocks_dropped=0,
    )
    monkeypatch.setattr(urllib.request, "urlopen", _serving(b"a later revision"))

    # Act
    result = fetch_one(document)

    # Assert
    assert result.status is Status.CORRUPT
    assert "before rendering" in result.detail, (
        f"the failure must say which pin moved, the revision or the rendering; got "
        f"{result.detail!r}"
    )
    assert not document.path.exists()


def test_a_recorded_loss_that_the_rendering_disagrees_with_fails_the_fetch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # `math_blocks_dropped` is how a document states what rendering cost it (`.phase2-findings.md`
    # §4). A number nothing checks is a number that drifts, and this one is *why* the corpus is
    # allowed to hold documents with formulas missing from them.
    # Arrange
    wikitext = "Zdanie <math>x</math> ze wzorem.\n"
    rendered = render(wikitext, Rendering.PLAIN_TEXT).text.encode("utf-8")
    document = _fetchable(
        tmp_path / "rendered.txt",
        source_sha256=hashlib.sha256(wikitext.encode("utf-8")).hexdigest(),
        sha256=hashlib.sha256(rendered).hexdigest(),
        rendering=Rendering.PLAIN_TEXT,
        math_blocks_dropped=0,
    )
    monkeypatch.setattr(urllib.request, "urlopen", _serving(wikitext.encode("utf-8")))

    # Act
    result = fetch_one(document)

    # Assert
    assert result.status is Status.CORRUPT
    assert "1" in result.detail and "math" in result.detail
    assert not document.path.exists()


@pytest.mark.skipif(
    not os.environ.get("WEFT_CORPUS_NETWORK"),
    reason="reaches pl.wikipedia.org and arxiv.org; set WEFT_CORPUS_NETWORK=1 to run it",
)
def test_one_real_pin_per_format_still_reproduces(tmp_path: Path) -> None:
    # The only check here that would have caught the defect this file was repaired for: everything
    # else agrees with the manifest about the manifest. One document per format, because the
    # formats are what differ — a PDF is fetched as it is served and a Wikipedia revision is
    # rendered on the way in, and the second path is the one that broke.
    # Arrange
    per_format = {
        entry.path.suffix: entry
        for entry in reversed(load_manifest(MANIFEST)[1])
        if entry.tier is Tier.FETCH
    }

    # Act — paced by the script's own constant, because two of these hit one host and the module
    # comment on that constant records what an unpaced loop over these pins earned: HTTP 429.
    results: list[Result] = []
    for entry in per_format.values():
        if results:
            time.sleep(POLITE_DELAY_SECONDS)
        results.append(fetch_one(_landing_in(entry, tmp_path)))

    # Assert
    unreproduced = [
        f"{r.document.id}: {r.status.value} — {r.detail}"
        for r in results
        if r.status is not Status.FETCHED
    ]
    assert not unreproduced, (
        f"pins that no longer reproduce their declared bytes: {unreproduced}. That is V1's own "
        f"failure condition, and it is what a stranger running `fetch` on a clean checkout meets."
    )


# --- Helpers ------------------------------------------------------------------------------------


def _partially_materialised_tiers(results: Iterable[Result]) -> list[str]:
    """Tiers where some documents are present and some are not."""
    by_tier: dict[Tier, list[bool]] = {}
    for result in results:
        by_tier.setdefault(result.document.tier, []).append(result.status is not Status.MISSING)
    return sorted(tier.value for tier, found in by_tier.items() if any(found) and not all(found))


def _digest_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fetchable(
    path: Path,
    *,
    source_sha256: str,
    sha256: str,
    rendering: Rendering,
    math_blocks_dropped: int,
) -> Document:
    """One fetch-tier document with a rendering, built where a manifest entry would be read."""
    return Document(
        id="pl-self-test",
        path=path,
        fmt=path.suffix.lstrip("."),
        language="pl",
        sha256=sha256,
        tier=Tier.FETCH,
        source="https://example.invalid/w/index.php?action=raw&oldid=1",
        source_sha256=source_sha256,
        render=rendering,
        math_blocks_dropped=math_blocks_dropped,
    )


def _landing_in(document: Document, directory: Path) -> Document:
    """The same document, written somewhere a test may write.

    The network check must not overwrite an operator's materialised corpus — and must not be able
    to *repair* it either, because a `fetch` that quietly fixed the thing under test would make
    the second run of this test pass for a reason the first one did not.
    """
    return replace(document, path=directory / document.path.name)


_SELF_TEST_MANIFEST: Final[str] = """
[corpus]
name = "self-test"
documents = 1

[[document]]
id = "self-test"
tier = "gate"
path = "sample.txt"
format = "txt"
language = "en"
sha256 = "0000000000000000000000000000000000000000000000000000000000000000"
"""


def _manifest_with(directory: Path, line: str, replacement: str) -> Path:
    """A one-document manifest with `line` replaced, written where a real one would live.

    The substitution is asserted rather than attempted, because a `str.replace` that matched
    nothing would hand the test a perfectly valid manifest and it would fail for a reason that has
    nothing to do with what it is checking.
    """
    if line not in _SELF_TEST_MANIFEST:
        message = f"{line!r} is not in the self-test manifest; the substitution would be a no-op"
        raise AssertionError(message)
    manifest = directory / "manifest.toml"
    manifest.write_text(_SELF_TEST_MANIFEST.replace(line, replacement), encoding="utf-8")
    return manifest


class _StubResponse:
    """The two methods `fetch_one` uses of an `http.client.HTTPResponse`."""

    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> _StubResponse:
        return self

    def __exit__(self, *_: object) -> None:
        return None


def _serving(body: bytes) -> Callable[..., _StubResponse]:
    def urlopen(request: object, timeout: float = 0.0) -> _StubResponse:
        return _StubResponse(body)

    return urlopen
