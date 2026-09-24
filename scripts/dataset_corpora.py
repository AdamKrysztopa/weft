"""Materialise the TechQA and Amazon ESCI documents this repository indexed — Phase 39 **39.7**.

TechQA (IBM, CDLA-Permissive) and Amazon ESCI (Apache-2.0) were first converted to one text file per
document by throwaway scripts. `corpus/techqa.toml` and `corpus/esci.toml` pin every file's sha256,
so this script's output must be byte-identical to what was indexed then. Reading the source parquet
needs `pandas` and `pyarrow`, so it is run as
`uv run --with pyarrow python scripts/dataset_corpora.py ...`; the `pandas` import lives inside the
functions that touch parquet, so the module — and its unit tests — import with no `pyarrow` at all.
"""

from __future__ import annotations

import argparse
import importlib
import re
import sys
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

#: The BEIR `text` field is `"Title: <title>\n\nText:\n<body>"`; split at the first marker only, a
#: second occurrence belongs to the body.
_TECHQA_MARKER: Final[str] = "\n\nText:\n"
_TECHQA_TITLE_PREFIX: Final[str] = "Title:"

_HTML_TAG: Final[re.Pattern[str]] = re.compile(r"<[^>]+>")

#: Kept in this order when a product row is rendered.
_ESCI_FIELDS: Final[tuple[str, ...]] = (
    "product_title",
    "product_brand",
    "product_bullet_point",
    "product_description",
)


def techqa_document_id(beir_id: str) -> str:
    """The corpus id `corpus/techqa.toml` pins, from a BEIR corpus id like `"swg21996508.txt"`."""
    return beir_id.removesuffix(".txt")


def techqa_document(text: str) -> str:
    """The BEIR `text` field, rendered as `corpus/techqa.toml` pins it: title then body."""
    title, marker, body = text.partition(_TECHQA_MARKER)
    if not marker:
        return f"\n{text}"
    title = title.removeprefix(_TECHQA_TITLE_PREFIX).strip()
    return f"{title}\n{body}"


def esci_document(row: Mapping[str, object]) -> str:
    """One ESCI product row, rendered as `corpus/esci.toml` pins it: its non-empty fields, one per
    line, markup stripped, in `_ESCI_FIELDS` order.
    """
    lines: list[str] = []
    for field in _ESCI_FIELDS:
        value = row.get(field)
        if not isinstance(value, str) or not value.strip():
            continue
        lines.append(_HTML_TAG.sub(" ", value).strip())
    return "\n".join(lines) + "\n"


def _manifest_document_ids(manifest: Path) -> set[str]:
    with manifest.open("rb") as handle:
        data = tomllib.load(handle)
    return {str(document["id"]) for document in data.get("document", [])}


def _read_parquet_records(path: Path) -> list[dict[str, Any]]:
    """`pandas.read_parquet` as a list of row dicts.

    Imported dynamically — via `importlib` rather than a static `import pandas` — because pandas
    ships no type stubs and this tree's `pyright` runs in strict mode; a dynamically resolved module
    carries no stub obligation.
    """
    pandas: Any = importlib.import_module("pandas")
    frame: Any = pandas.read_parquet(path)
    records: list[dict[str, Any]] = frame.to_dict(orient="records")
    return records


def _write_techqa(corpus_parquet: Path, out: Path) -> int:
    out.mkdir(parents=True, exist_ok=True)
    count = 0
    for row in _read_parquet_records(corpus_parquet):
        document_id = techqa_document_id(str(row["_id"]))
        (out / f"{document_id}.txt").write_text(techqa_document(str(row["text"])), encoding="utf-8")
        count += 1
    return count


def _write_esci(products_parquet: Path, manifest: Path, out: Path) -> int:
    wanted = _manifest_document_ids(manifest)
    out.mkdir(parents=True, exist_ok=True)
    written: set[str] = set()
    for row in _read_parquet_records(products_parquet):
        if row.get("product_locale") != "us":
            continue
        product_id = str(row["product_id"])
        if product_id not in wanted:
            continue
        (out / f"{product_id}.txt").write_text(esci_document(row), encoding="utf-8")
        written.add(product_id)
    missing = sorted(wanted - written)
    if missing:
        raise SystemExit(
            f"missing {len(missing)} manifest id(s) among us-locale products: {missing}"
        )
    return len(written)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    subcommands = parser.add_subparsers(dest="action", required=True)

    techqa = subcommands.add_parser("techqa", help="write TechQA's corpus as one file per document")
    techqa.add_argument("--corpus-parquet", type=Path, required=True)
    techqa.add_argument("--out", type=Path, required=True)

    esci = subcommands.add_parser(
        "esci", help="write ESCI's us-locale products pinned by a manifest"
    )
    esci.add_argument("--products-parquet", type=Path, required=True)
    esci.add_argument("--manifest", type=Path, required=True)
    esci.add_argument("--out", type=Path, required=True)

    arguments = parser.parse_args(argv)

    if arguments.action == "techqa":
        count = _write_techqa(arguments.corpus_parquet, arguments.out)
    else:
        count = _write_esci(arguments.products_parquet, arguments.manifest, arguments.out)

    print(f"wrote {count} documents to {arguments.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
