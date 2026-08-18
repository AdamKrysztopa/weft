"""`docs/08-manuals.md` §3, clause (c) — the pack author guide's code samples are the file they
claim.

"Each fenced code block that claims to be part of `examples/weft-example-chunker/`... carries an
explicit source-path tag, and a test diffs the tagged block's content against the file it names."
This is that diff, run against `manual/pack-author-guide.md`'s Phase 0 section.

A tag is `path=<repo-relative-path>` on the fence's info string, e.g.
` ```python path=examples/weft-example-chunker/src/weft_example_chunker/word_chunker.py `. The
tagged block's content must equal the named file's content **exactly** — not a substring match —
so the guide can only ever show the whole file it claims to demonstrate, never a hand-trimmed
excerpt that could quietly diverge from the part left out.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
GUIDE: Final[Path] = REPO_ROOT / "manual" / "pack-author-guide.md"

#: `08` §3's ratchet for clause (c): "a fenced block that reads as a code sample but carries no
#: source-path tag is a failure unless named here." **Pinned empty.** Every code sample in the
#: Phase 0 section of this guide is the file it claims to be — the whole reason to write the
#: guide against a real, already-tested artifact instead of an invented example.
UNTAGGED_CODE_BLOCKS: Final[frozenset[str]] = frozenset()

#: Languages this check treats as "reads as a code sample" — the guide's shell commands and its
#: illustrative directory tree are not claims about a single file's exact bytes, so they are not
#: in this set and carry no tagging obligation.
_CODE_SAMPLE_LANGUAGES: Final[frozenset[str]] = frozenset({"python", "toml"})

_FENCE = re.compile(
    r"^```(?P<lang>\S+)(?:\s+path=(?P<path>\S+))?\n(?P<body>.*?)^```\s*$",
    re.MULTILINE | re.DOTALL,
)


def _fenced_blocks(markdown: str) -> list[tuple[str, str | None, str]]:
    """Every fenced block in `markdown`, as `(language, tagged_path_or_None, body)` triples."""
    return [
        (match.group("lang"), match.group("path"), match.group("body"))
        for match in _FENCE.finditer(markdown)
    ]


def _code_sample_blocks(markdown: str) -> list[tuple[str | None, str]]:
    return [
        (path, body)
        for lang, path, body in _fenced_blocks(markdown)
        if lang in _CODE_SAMPLE_LANGUAGES
    ]


def test_at_least_one_code_block_is_tagged() -> None:
    # Floor — `08` §3: "the count of tagged blocks is non-zero. A guide with zero tagged blocks
    # passes zero comparisons, which is exactly how a retyped, untagged sample drifts unnoticed."
    tagged = [path for path, _ in _code_sample_blocks(GUIDE.read_text(encoding="utf-8")) if path]
    assert tagged, "manual/pack-author-guide.md has no path=-tagged code samples to check"


def test_every_code_sample_carries_a_source_path_tag() -> None:
    # Arrange
    samples = _code_sample_blocks(GUIDE.read_text(encoding="utf-8"))

    # Act
    untagged = [
        f"block #{index} ({len(body.splitlines())} lines)"
        for index, (path, body) in enumerate(samples, start=1)
        if path is None
    ]

    # Assert
    waived = set(UNTAGGED_CODE_BLOCKS)
    surviving = [block for block in untagged if block not in waived]
    assert not surviving, (
        f"code sample(s) with no path= tag, not named in UNTAGGED_CODE_BLOCKS: {surviving}. "
        f"Either tag it against the real file it demonstrates, or waive it here by name."
    )


def test_tagged_code_samples_match_the_files_they_claim() -> None:
    # Arrange
    samples = [
        (path, body)
        for path, body in _code_sample_blocks(GUIDE.read_text(encoding="utf-8"))
        if path
    ]

    # Act / Assert
    for path, body in samples:
        target = REPO_ROOT / path
        assert target.is_file(), f"manual/pack-author-guide.md tags '{path}', which does not exist"
        actual = target.read_text(encoding="utf-8")
        expected = body.rstrip("\n") + "\n"
        assert actual == expected, (
            f"manual/pack-author-guide.md's sample tagged '{path}' has drifted from the file "
            f"it claims to be — the guide has not been kept in sync with the artifact it "
            f"demonstrates."
        )


def test_a_retyped_untagged_sample_would_fail(tmp_path: Path) -> None:
    # Arrange — the self-test `08` §3 requires of clause (c)'s own floor: plant an untagged code
    # sample and confirm the scanning helper actually reports it, so this check cannot pass
    # merely because it stopped being able to fail.
    planted = tmp_path / "planted-guide.md"
    planted.write_text(
        "```python\nprint('a retyped sample, no path= tag')\n```\n", encoding="utf-8"
    )

    # Act
    samples = _code_sample_blocks(planted.read_text(encoding="utf-8"))

    # Assert
    assert samples == [(None, "print('a retyped sample, no path= tag')\n")]
