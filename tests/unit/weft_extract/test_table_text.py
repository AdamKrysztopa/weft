"""The two table serialisations — ledger task `9.6`, and `11` §6 rank 10.

*"Triplets for the index, markdown or HTML for the prompt. A single linearisation cannot serve
both, which is the concrete reason the grid must survive extraction."* So there are two functions,
and they live in the pack that publishes `TableGrid` — `weft_extract` — rather than in whichever
extractor happened to need one first. `11` §6 rank 11 names that rule and calls this its canonical
example: *"if two extractors both need it, it belongs to the contract's pack"*. `9.13`'s
`weft-docling` is the second extractor, and it renders through this module without depending on
pdfplumber.

**The property `9.6` states, in its own words: *a cell containing a pipe cannot break one extractor
and not another*.** That is not a hypothetical about tidiness. Both renderings are delimited, a
financial table legitimately contains `|`, `\\` and newlines, and an extractor that escaped them
while another did not would produce two different node contents for the same table — different
digests, different chunks, and a retrieval difference nobody could attribute to the parser. One
module, one escape, both directions.

**What is asserted here is injectivity, not a format.** A serialiser is free to choose its
punctuation; what it is not free to do is render two different grids to the same string. The tests
below pin that, plus the facts a reader depends on — every cell reaches the output, the header
reaches every row of the index form, and a caption that exists is carried.
"""

import pytest

from weft_extract.payload import BoundingBox, TableGrid
from weft_extract.table_text import index_text, prompt_markdown


def _grid(
    *rows: tuple[str, ...], headers: tuple[str, ...], caption: str | None = None
) -> TableGrid:
    return TableGrid(
        headers=headers,
        rows=rows,
        caption=caption,
        page=1,
        bbox=BoundingBox(x0=0.0, y0=0.0, x1=1.0, y1=1.0),
    )


def test_the_index_form_carries_every_cell() -> None:
    """Nothing an extractor recovered may be dropped on the way to the index."""
    # Arrange
    grid = _grid(("EMEA", "1,204"), ("APAC", "988"), headers=("Region", "Revenue"))

    # Act
    text = index_text(grid)

    # Assert
    for cell in ("Region", "Revenue", "EMEA", "1,204", "APAC", "988"):
        assert cell in text


def test_the_index_form_repeats_the_header_on_every_row() -> None:
    """The measured reason this form exists — `11` §6 rank 3, corroborated by arXiv:2408.17008,
    is row-level retrieval with the header propagated. A row that reaches a retriever without its
    header is a row of numbers nobody can read.
    """
    # Arrange
    grid = _grid(("EMEA", "1,204"), ("APAC", "988"), headers=("Region", "Revenue"))

    # Act
    lines = [line for line in index_text(grid).splitlines() if "EMEA" in line or "APAC" in line]

    # Assert
    assert len(lines) == 2
    assert all("Region" in line and "Revenue" in line for line in lines)


def test_a_caption_reaches_the_index_form() -> None:
    """A caption is the one piece of prose a table has, and it is what a text query matches."""
    # Arrange
    grid = _grid(("EMEA", "1"), headers=("Region", "Revenue"), caption="Table 2. Revenue.")

    # Act / Assert
    assert "Table 2. Revenue." in index_text(grid)


def test_a_grid_with_no_caption_renders_without_inventing_one() -> None:
    """`11` §2.4 refuses a synthesised label outright — no `Table on page 1` filler."""
    # Arrange
    grid = _grid(("EMEA", "1"), headers=("Region", "Revenue"))

    # Act
    text = index_text(grid)

    # Assert
    assert "None" not in text
    assert "page 1" not in text


def test_the_prompt_form_is_a_markdown_table() -> None:
    """A generator reads this one, and a model reads markdown better than triplets."""
    # Arrange
    grid = _grid(("EMEA", "1,204"), headers=("Region", "Revenue"))

    # Act
    lines = prompt_markdown(grid).splitlines()

    # Assert — a header row, a delimiter row, then one row per data row.
    body = [line for line in lines if line.startswith("|")]
    assert len(body) == 3
    assert set(body[1].replace("|", "").replace(" ", "")) <= {"-", ":"}


@pytest.mark.parametrize("awkward", ["a|b", "a\\b", "a\nb", "|", "a|b\\c"])
def test_a_cell_containing_the_delimiter_does_not_collide_with_a_cell_that_does_not(
    awkward: str,
) -> None:
    """9.6's own words, made falsifiable: two different grids never render to one string.

    Injectivity rather than a literal escape sequence — what matters is that the reader can tell
    the two apart, not which punctuation the writer chose to do it with.

    Every case here contains at least one character the neutralising below actually changes, so
    the two grids genuinely differ. `"---"` was in this list until it was run: it contains no `|`,
    no backslash and no newline, so both sides were the same grid and the test asserted a string
    differed from itself. A parametrised case that cannot fail is `L5.6` in miniature.
    """
    # Arrange
    plain = _grid(
        (awkward.replace("|", "!").replace("\\", "/").replace("\n", " "), "x"), headers=("A", "B")
    )
    tricky = _grid((awkward, "x"), headers=("A", "B"))

    # Act / Assert
    assert index_text(plain) != index_text(tricky)
    assert prompt_markdown(plain) != prompt_markdown(tricky)


@pytest.mark.parametrize("awkward", ["a|b", "a\\b", "a\nb"])
def test_an_awkward_cell_never_adds_a_row_or_a_column(awkward: str) -> None:
    """The failure escaping exists to prevent: a newline or a pipe splitting one cell into two.

    Counted against the same grid with a harmless cell, so this measures the *cell*, not the
    format.
    """
    # Arrange
    harmless = _grid(("plain", "x"), headers=("A", "B"))
    tricky = _grid((awkward, "x"), headers=("A", "B"))

    # Act / Assert
    assert len(index_text(tricky).splitlines()) == len(index_text(harmless).splitlines())
    assert len(prompt_markdown(tricky).splitlines()) == len(prompt_markdown(harmless).splitlines())


def test_both_renderings_are_deterministic() -> None:
    """A node id is a digest of its content, so a serialiser that varied would re-index a corpus
    that had not changed — and `9.17` is the task that makes a real reparse visible, not this.
    """
    # Arrange
    grid = _grid(("EMEA", "1,204"), headers=("Region", "Revenue"), caption="c")

    # Act / Assert
    assert index_text(grid) == index_text(grid)
    assert prompt_markdown(grid) == prompt_markdown(grid)


def test_a_grid_with_no_rows_still_renders_its_headers() -> None:
    """The edge case: a table an extractor found and recovered no body from is still a table."""
    # Arrange
    grid = _grid(headers=("Region", "Revenue"))

    # Act / Assert
    assert "Region" in index_text(grid)
    assert "Region" in prompt_markdown(grid)
