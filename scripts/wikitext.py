"""Turns one pinned Wikipedia revision into one corpus document, deterministically.

**Why this file exists at all.** `docs/09-release.md` §4.3 fails V1 when *"a fetch is not
reproducible byte-for-byte"*, and `action=raw&oldid=…` returns wikitext — markup, not prose. A
corpus of wikitext would put `{{Dopracować|źródła = 2025-11}}` and
`[[Plik:GaussianScatterPCA.svg|thumb|…]]` into chunks and then into retrieval. Something has to
render it, and the only rendering V1 accepts is one a stranger can run: *this* module, hashed by
`fetch_corpus.py` immediately afterwards. A hand-derived rendering has a digest too, and the
manifest cannot tell the two apart — which is exactly how the nine Polish documents were once
pinned to bytes no tracked code produced.

**MediaWiki's own plaintext renderer is not an option.** `.phase2-findings.md` §4 measured
`action=query&prop=extracts&explaintext` flattening one formula into 350 characters at one glyph
per line. So mathematics is **dropped and counted** rather than mangled, and the count travels in
the manifest so a document that lost fifty-eight formulas says so.

**Two renderings, one fetch.** `.md` keeps the structure a reader of prose uses — headings,
emphasis, lists; `.txt` is the same document with that markup taken off. They differ only in the
last step, because two independent renderers would be two documents claiming to be one revision.

**Determinism is the whole contract.** Everything here is a function of the input string: no
clock, no locale, no iteration over a set. Wikitext's grammar is published by MediaWiki and this
handles the constructs the nine pinned revisions actually contain; a construct it does not know
is refused loudly (see `_without_paired`) rather than half-rendered, because a silently truncated
article still hashes to something.
"""

import html
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

#: Link namespaces whose content is not prose about the subject. A file link carries a caption,
#: but the caption describes a picture the corpus does not have, and a category is navigation.
_DROPPED_NAMESPACES: Final[tuple[str, ...]] = (
    "plik:",
    "file:",
    "image:",
    "grafika:",
    "kategoria:",
    "category:",
)

_COMMENT: Final[re.Pattern[str]] = re.compile(r"<!--.*?-->", re.DOTALL)
_REFERENCE: Final[re.Pattern[str]] = re.compile(r"<ref\b[^>]*/>|<ref\b[^>]*>.*?</ref>", re.DOTALL)
_MATH: Final[re.Pattern[str]] = re.compile(r"<math\b[^>]*/>|<math\b[^>]*>.*?</math>", re.DOTALL)
_TAG: Final[re.Pattern[str]] = re.compile(r"</?[A-Za-z][A-Za-z0-9]*(?:\s[^<>]*)?/?>")
_EXTERNAL_LINK: Final[re.Pattern[str]] = re.compile(r"\[(?:https?:|//)[^\s\]]*(?:\s+([^\]]*))?\]")
_HEADING: Final[re.Pattern[str]] = re.compile(r"^(={2,6})\s*(.+?)\s*\1\s*$")
_LIST_ITEM: Final[re.Pattern[str]] = re.compile(r"^([*#:;]+)\s*(.*)$")
_BOLD_ITALIC: Final[re.Pattern[str]] = re.compile(r"'''''(.+?)'''''", re.DOTALL)
_BOLD: Final[re.Pattern[str]] = re.compile(r"'''(.+?)'''", re.DOTALL)
_ITALIC: Final[re.Pattern[str]] = re.compile(r"''(.+?)''", re.DOTALL)
_RUN_OF_SPACES: Final[re.Pattern[str]] = re.compile(r"[ \t]{2,}")
_SPACE_BEFORE_PUNCTUATION: Final[re.Pattern[str]] = re.compile(r" +([,.;:!?)])")
_EMPTIED_PARENTHESES: Final[re.Pattern[str]] = re.compile(r" ?\(\s*\)")
_BLANK_RUN: Final[re.Pattern[str]] = re.compile(r"\n{3,}")


class Rendering(StrEnum):
    """The two shapes one fetched revision is written in."""

    MARKDOWN = "wikitext-md"
    PLAIN_TEXT = "wikitext-txt"


@dataclass(frozen=True)
class Rendered:
    """One rendered document, and an honest account of what the rendering cost."""

    text: str
    math_blocks_dropped: int


@dataclass(frozen=True)
class _Line:
    """One output line, carrying the heading level that produced it (0 when it is body text)."""

    text: str
    heading_level: int


def render(source: str, rendering: Rendering) -> Rendered:
    """Renders wikitext to one corpus document, or refuses naming the construct it could not read.

    The order is not incidental. References are removed before templates because a citation is a
    template inside a reference; templates before mathematics so a formula that only ever existed
    inside a dropped infobox is not counted as a formula the reader lost; links after both,
    because a template argument can be a link.
    """
    text = source.replace("\r\n", "\n")
    text = _COMMENT.sub("", text)
    text = _REFERENCE.sub("", text)
    text = _without_paired(text, "{{", "}}", construct="template")
    text = _without_paired(text, "{|", "|}", construct="table")
    text, math_blocks_dropped = _MATH.subn("", text)
    text = _with_links_resolved(text)
    text = _EXTERNAL_LINK.sub(lambda match: match.group(1) or "", text)
    text = _TAG.sub("", text)
    text = html.unescape(text)

    lines = [_line(raw, rendering) for raw in text.split("\n")]
    body = "\n".join(line.text for line in _without_empty_sections(lines))
    return Rendered(text=_tidied(body), math_blocks_dropped=math_blocks_dropped)


def _without_paired(text: str, opening: str, closing: str, *, construct: str) -> str:
    """Removes every `opening…closing` region, counting nesting, or refuses if one never closes.

    Wikitext nests these — an infobox holds a citation holds a date — so a scan that stopped at
    the first `}}` would emit the tail of the outer one as prose. An *unclosed* one is refused
    rather than absorbed: running to the end of the input looking for the close would return an
    article-shaped nothing, and nothing hashes just as well as prose does.
    """
    kept: list[str] = []
    depth = 0
    index = 0
    opened_at = 0
    while index < len(text):
        if text.startswith(opening, index):
            if not depth:
                opened_at = index
            depth += 1
            index += len(opening)
        elif depth and text.startswith(closing, index):
            depth -= 1
            index += len(closing)
        else:
            if not depth:
                kept.append(text[index])
            index += 1
    if depth:
        line = text.count("\n", 0, opened_at) + 1
        message = (
            f"unclosed {construct} ({opening}…{closing}) opened on line {line} of the fetched "
            f"wikitext. Rendering it would silently drop everything after it, so the fetch fails "
            f"here instead."
        )
        raise ValueError(message)
    return "".join(kept)


def _with_links_resolved(text: str) -> str:
    """`[[target|label]]` becomes its label; a file or category link goes entirely.

    Scanned rather than matched by regular expression, because link targets nest: a thumbnail
    caption is prose that itself contains links, and the inner `]]` closes the wrong one.
    """
    kept: list[str] = []
    index = 0
    while index < len(text):
        if not text.startswith("[[", index):
            kept.append(text[index])
            index += 1
            continue
        inner, index = _paired_content(text, index, "[[", "]]")
        if inner.strip().lower().startswith(_DROPPED_NAMESPACES):
            continue
        label = inner.split("|", 1)[1] if "|" in inner else inner
        kept.append(_with_links_resolved(label))
    return "".join(kept)


def _paired_content(text: str, start: int, opening: str, closing: str) -> tuple[str, int]:
    """The content between one balanced pair starting at `start`, and the index just past it.

    An unbalanced link is *not* a refusal the way an unbalanced template is: the rest of the input
    is returned as the content, so a stray `[[` costs the brackets and not the article.
    """
    depth = 0
    index = start
    content_from = start + len(opening)
    while index < len(text):
        if text.startswith(opening, index):
            depth += 1
            index += len(opening)
        elif text.startswith(closing, index):
            depth -= 1
            index += len(closing)
            if not depth:
                return text[content_from : index - len(closing)], index
        else:
            index += 1
    return text[content_from:], len(text)


def _line(raw: str, rendering: Rendering) -> _Line:
    """One source line as one output line: headings, list markers and emphasis, per rendering."""
    heading = _HEADING.match(raw)
    if heading:
        level = len(heading.group(1))
        title = _emphasised(heading.group(2), rendering)
        # `==` is a Wikipedia article's *top* section level, so it renders as `##`: an `.md`
        # document with several `#` headings claims to be several documents.
        marker = "#" * level if rendering is Rendering.MARKDOWN else ""
        return _Line(f"{marker} {title}".strip(), heading_level=level)

    item = _LIST_ITEM.match(raw)
    if item:
        markers, content = item.group(1), _emphasised(item.group(2), rendering)
        if rendering is Rendering.PLAIN_TEXT or markers[-1] in ":;":
            # `:` is an indent and `;` a definition term; neither is a list, and both are prose
            # once the markup is gone. In `.txt` a bullet is markup too.
            return _Line(content, heading_level=0)
        bullet = "- " if markers[-1] == "*" else "1. "
        return _Line(f"{'  ' * (len(markers) - 1)}{bullet}{content}" if content else "", 0)

    return _Line(_emphasised(raw, rendering), heading_level=0)


def _emphasised(text: str, rendering: Rendering) -> str:
    """Wikitext's quote-mark emphasis, in the target's spelling or not at all.

    Widest first, and it is not a preference: `''` is a prefix of `'''`, so an italic pass over
    `'''Entropia'''` consumes two of the three quotes and leaves the third in the middle of the
    word.
    """
    if rendering is Rendering.PLAIN_TEXT:
        return _ITALIC.sub(r"\1", _BOLD.sub(r"\1", _BOLD_ITALIC.sub(r"\1", text)))
    return _ITALIC.sub(r"*\1*", _BOLD.sub(r"**\1**", _BOLD_ITALIC.sub(r"***\1***", text)))


def _without_empty_sections(lines: list[_Line]) -> list[_Line]:
    """Drops any heading whose section holds no prose, and the heading with it.

    `== Przypisy ==` over a `<references />` tag renders to a heading and nothing else, as does a
    bibliography that is one template. A section of a document that does not exist is still a
    section every retrieval over the corpus can return, so it is not written.
    """
    kept: list[_Line] = []
    for position, line in enumerate(lines):
        if line.heading_level and not _section_has_prose(lines, position):
            continue
        kept.append(line)
    return kept


def _section_has_prose(lines: list[_Line], heading_at: int) -> bool:
    """Whether anything but further headings follows this heading before its section closes."""
    level = lines[heading_at].heading_level
    for line in lines[heading_at + 1 :]:
        if line.heading_level:
            if line.heading_level <= level:
                return False
            continue
        if line.text.strip():
            return True
    return False


def _tidied(text: str) -> str:
    """The whitespace left behind by everything removed above.

    Dropping an inline formula leaves the spaces that surrounded it on either side of the hole; a
    citation leaves one before the full stop; and a lead sentence that glossed its title through a
    template leaves `Uczenie maszynowe () – …`. All three are visible in a chunk, all three are
    deterministic to remove, so they are removed rather than shipped.
    """
    lines = [
        _SPACE_BEFORE_PUNCTUATION.sub(
            r"\1", _EMPTIED_PARENTHESES.sub("", _RUN_OF_SPACES.sub(" ", line))
        ).rstrip()
        for line in text.split("\n")
    ]
    return _BLANK_RUN.sub("\n\n", "\n".join(lines)).strip() + "\n"
