"""Hand-assembled PDFs, small enough to read, for `tests/unit/weft_pdf`.

**Why these are built rather than checked in or taken from the corpus.** The two
outcomes `weft-pdf` has to keep apart — a page a backend *looked at* and found
empty, and a page a backend *could not see* — do not occur in `corpus/mrmr`:
all nine papers have a real text layer on every page, measured. A unit test for
that distinction therefore has to construct the inputs, and constructing them
here means the test states exactly which structural feature it is testing (a
text object drawing no glyphs; an image XObject with no text object at all)
rather than asserting against an opaque blob nobody can inspect.

The bytes are assembled from the PDF file structure directly — a header, a
numbered object per body, a cross-reference table of their byte offsets, and a
trailer naming the catalogue — because the alternative is a PDF-*writing*
dependency in the test tree to check a PDF-*reading* pack, which would make the
gate depend on two libraries agreeing rather than on one being correct.
"""

from collections.abc import Sequence

#: A one-pixel grey image. The value is never decoded by anything under test —
#: only the `/Subtype /Image` declaration is, which is what a backend counts.
_ONE_PIXEL = b"\x80"


def text_pages(*texts: str) -> bytes:
    """A PDF of one page per string, each drawing that string in Helvetica.

    An empty string still writes a complete text object, so `text_pages("")` is
    the "text layer, no glyphs" case rather than a page with nothing on it.
    """
    count = len(texts)
    font = 3 + 2 * count
    kids = b" ".join(b"%d 0 R" % (3 + 2 * index) for index in range(count))
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [" + kids + b"] /Count %d >>" % count,
    ]
    for index, text in enumerate(texts):
        contents = 4 + 2 * index
        objects.append(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] /Resources "
            b"<< /Font << /F1 %d 0 R >> >> /Contents %d 0 R >>" % (font, contents)
        )
        objects.append(_stream(b"", b"BT /F1 12 Tf 20 150 Td (" + _literal(text) + b") Tj ET"))
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    return _assemble(objects)


def text_columns(left: str, right: str) -> bytes:
    """A PDF of one page drawing two strings on one line, a hundred points apart.

    The gap is the point: it is what distinguishes a backend that reconstructs a
    page's geometry from one that concatenates its text operators, and therefore
    the only fixture on which a layout setting can be *observed* to have reached
    the library rather than merely been declared.
    """
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] /Resources "
        b"<< /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        _stream(
            b"",
            b"BT /F1 12 Tf 20 150 Td (" + _literal(left) + b") Tj ET "
            b"BT /F1 12 Tf 120 150 Td (" + _literal(right) + b") Tj ET",
        ),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    return _assemble(objects)


def image_without_text() -> bytes:
    """A PDF of one page that draws an image and declares no font and no text object."""
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] /Resources "
        b"<< /XObject << /Im1 5 0 R >> >> /Contents 4 0 R >>",
        _stream(b"", b"q 100 0 0 100 20 20 cm /Im1 Do Q"),
        _stream(
            b"/Type /XObject /Subtype /Image /Width 1 /Height 1 "
            b"/ColorSpace /DeviceGray /BitsPerComponent 8",
            _ONE_PIXEL,
        ),
    ]
    return _assemble(objects)


def image_inside_a_form() -> bytes:
    """A page whose only image is nested one level down, inside a Form XObject.

    Repair fixture for a reviewer finding, and it is not an exotic shape: a form
    is how a PDF producer reuses a piece of drawing, and generators emit them
    routinely. A backend that scans only the page's own `/Resources /XObject`
    finds nothing here and concludes the page is blank, while a backend that
    resolves the drawing sees the image — the two disagreeing about *exactly*
    the distinction the fallback chain rests on.
    """
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] /Resources "
        b"<< /XObject << /Fm1 5 0 R >> >> /Contents 4 0 R >>",
        _stream(b"", b"q 1 0 0 1 0 0 cm /Fm1 Do Q"),
        _stream(
            b"/Type /XObject /Subtype /Form /BBox [0 0 200 200] "
            b"/Resources << /XObject << /Im1 6 0 R >> >>",
            b"q 100 0 0 100 20 20 cm /Im1 Do Q",
        ),
        _stream(
            b"/Type /XObject /Subtype /Image /Width 1 /Height 1 "
            b"/ColorSpace /DeviceGray /BitsPerComponent 8",
            _ONE_PIXEL,
        ),
    ]
    return _assemble(objects)


def inline_image_without_text() -> bytes:
    """A page whose only image is inline (`BI … ID … EI`), declared in no dictionary at all.

    The second shape a resource-dictionary scan cannot see. An inline image is
    the ordinary encoding for a small bitmap, and there is no `/XObject` entry
    anywhere in the file to count.
    """
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] /Resources << >> /Contents 4 0 R >>",
        _stream(
            b"",
            b"q 100 0 0 100 20 20 cm BI /W 1 /H 1 /CS /G /BPC 8 ID " + _ONE_PIXEL + b" EI Q",
        ),
    ]
    return _assemble(objects)


def no_pages() -> bytes:
    """A structurally valid PDF whose page tree holds nothing.

    What a partial download looks like to a reader that recovers what it can:
    measured on three corpus papers truncated mid-file, `pdfplumber` answers
    zero pages rather than raising. A PDF is required to have at least one page,
    so zero pages means the reading is damaged, not that the document is empty —
    and that is a conclusion no backend may draw.
    """
    return _assemble(
        [
            b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [] /Count 0 >>",
        ]
    )


def truncated_tail(*texts: str) -> bytes:
    """`text_pages(*texts)` with its closing `%%EOF` marker cut off.

    **The one input measured to make the two backends genuinely disagree**, and it is
    what a file truncated in transit looks like — a mail gateway's size cap, an
    interrupted download, a copy that ran out of disk. Measured on this fixture:
    `pypdf` raises (`PdfStreamError` lenient, `PdfReadError` strict), while
    `pdfplumber` recovers every page and returns the text.

    Task 2.28's chain has nothing to demonstrate without a document like this. Every
    other fixture in this module is one the two backends *agree* on — that agreement is
    `test_backend_agreement.py`'s subject, and it is the property that keeps a chain
    from stopping on a document another backend would have read. This is the other half:
    a chain over two backends that never disagree buys nothing at all.
    """
    complete = text_pages(*texts)
    return complete[: complete.rindex(b"%%EOF")]


def encrypted(content: bytes, password: str) -> bytes:
    """`content` re-written with standard PDF encryption under `password`.

    **The one function here that does not assemble bytes by hand, and the
    reason is stated rather than hidden.** Encryption is a key derivation and a
    cipher, not a file structure: written out longhand it would be a hundred
    lines nobody can check by reading, which defeats the whole point of this
    module. The objection the module docstring raises — a gate that depends on
    two libraries agreeing rather than on one being correct — does not apply,
    because `pypdf` is a library already under test here, not a third one
    brought in to referee.
    """
    from io import BytesIO

    from pypdf import PdfWriter

    writer = PdfWriter(clone_from=BytesIO(content))
    writer.encrypt(password)
    out = BytesIO()
    writer.write(out)
    return out.getvalue()


def not_a_pdf() -> bytes:
    """Bytes that open like a PDF and then are not one, so a reader raises rather than guessing."""
    return b"%PDF-1.4\nthere is no catalogue, no pages and no cross-reference table here\n"


def _literal(text: str) -> bytes:
    """`text` as a PDF literal string body, with the three characters that end one escaped."""
    escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    return escaped.encode("ascii")


def _stream(attributes: bytes, data: bytes) -> bytes:
    """A stream object: its dictionary, `/Length` filled in from the data itself."""
    return b"<< " + attributes + b" /Length %d >>\nstream\n" % len(data) + data + b"\nendstream"


def _assemble(objects: Sequence[bytes]) -> bytes:
    """`objects` numbered from 1, with the cross-reference table their offsets require.

    The offsets are computed from the bytes actually written, never counted by
    hand: a cross-reference table that disagrees with the file is the one way a
    PDF this small can be malformed, and it would fail as "the backend is
    broken" rather than "the fixture is".
    """
    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    table = len(out)
    out += b"xref\n0 %d\n" % (len(objects) + 1)
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += b"%010d 00000 n \n" % offset
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        table,
    )
    return bytes(out)
