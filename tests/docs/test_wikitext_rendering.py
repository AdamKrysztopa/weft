"""The rendering that stands between a pinned Wikipedia revision and a corpus document.

V1 fails when *"a fetch is not reproducible byte-for-byte"* (`docs/09-release.md` §4.3), and the
Polish subset is not the bytes MediaWiki serves: `action=raw` returns **wikitext**, and what the
corpus holds is prose. That gap is where reproducibility was lost once already — the digests were
taken over a hand-derived rendering no tracked code produced, so `fetch` on a stranger's machine
retrieved markup, missed every pin, and wrote nothing.

So the rendering is code, and this is the file that says what it must do: drop what a reader of
prose cannot use, keep what carries meaning, and be a **function of the fetched bytes alone** —
no clock, no locale, no dictionary order. `scripts/fetch_corpus.py` then hashes what this
produced, which is what makes the manifest's digest a claim about a pin rather than about one
laptop.

**Mathematics is dropped rather than mangled, and counted.** `.phase2-findings.md` §4 measured
MediaWiki's own plaintext renderer flattening a single formula into 350 characters, one glyph per
line; that would go into the corpus and then into every chunk drawn from it. The count travels
with the document so the loss is stated rather than hidden.
"""

from __future__ import annotations

import pytest
from wikitext import Rendering, render

_ARTICLE = """\
'''Entropia''' – wielkość z [[teoria informacji|teorii informacji]].<ref>Shannon 1948.</ref>

== Definicja ==
Dla zmiennej ''X'' zachodzi:
: <math>H(X) = -\\sum p(x) \\log p(x)</math>

gdzie <math>p(x)</math> jest rozkładem.
"""


def test_markdown_keeps_the_structure_a_reader_of_prose_uses() -> None:
    # Arrange / Act
    rendered = render(_ARTICLE, Rendering.MARKDOWN)

    # Assert
    assert "## Definicja" in rendered.text, "a section heading is structure, not decoration"
    assert "**Entropia**" in rendered.text
    assert "*X*" in rendered.text
    assert "teorii informacji" in rendered.text, (
        "a piped link must leave its label behind; dropping it loses the words the sentence was "
        "written around"
    )
    assert "[[" not in rendered.text and "<ref>" not in rendered.text


def test_plain_text_strips_exactly_what_markdown_keeps() -> None:
    # Arrange / Act
    plain = render(_ARTICLE, Rendering.PLAIN_TEXT)

    # Assert
    assert "Definicja" in plain.text
    assert "#" not in plain.text, "`.txt` is the same document with the markup taken off"
    assert "**" not in plain.text
    assert "teorii informacji" in plain.text


def test_math_is_dropped_and_counted_rather_than_mangled() -> None:
    # `.phase2-findings.md` §4: the alternative is 350 characters of one glyph per line in the
    # corpus. The count is the honesty half — a document that lost 58 formulas says so.
    # Arrange / Act
    rendered = render(_ARTICLE, Rendering.MARKDOWN)

    # Assert
    assert rendered.math_blocks_dropped == 2
    assert "\\sum" not in rendered.text and "<math" not in rendered.text
    assert "gdzie jest rozkładem." in rendered.text, (
        "dropping inline mathematics must not leave the sentence around it holding a hole where "
        "the spaces used to be"
    )


def test_a_nested_template_is_removed_whole() -> None:
    # Templates nest — an infobox holds a citation holds a date — and a scanner that stopped at the
    # first `}}` would emit the tail of the outer one as prose.
    # Arrange
    source = "{{Infobox|data = {{cytuj|rok = 2017}}|opis = x}}Prose survives."

    # Act
    rendered = render(source, Rendering.PLAIN_TEXT)

    # Assert
    assert rendered.text.strip() == "Prose survives."


def test_a_section_whose_body_is_entirely_dropped_takes_its_heading_with_it() -> None:
    # `== Przypisy ==` over a `<references />` tag, or a bibliography that is one template, renders
    # to a heading with nothing under it. Left in, it is a section of a document that does not
    # exist, and every retrieval over the corpus can return it.
    # Arrange
    source = "Prose.\n\n== Przypisy ==\n{{Przypisy}}\n\n== Bibliografia ==\nMitchell T., 1997.\n"

    # Act
    rendered = render(source, Rendering.MARKDOWN)

    # Assert
    assert "Przypisy" not in rendered.text
    assert "## Bibliografia" in rendered.text


def test_an_unclosed_template_is_refused_rather_than_swallowing_the_article() -> None:
    # A scanner that ran to the end of the input looking for `}}` would return an empty document,
    # and an empty document has a perfectly good sha256. The failure has to be loud here or it is
    # a corpus entry that verifies and holds nothing.
    # Arrange
    source = "Prose.\n{{Infobox|opis = never closed\nMore prose.\n"

    # Act / Assert
    with pytest.raises(ValueError, match="template"):
        render(source, Rendering.MARKDOWN)
