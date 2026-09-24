"""BM25 over Qdrant's sparse vectors — pure functions, no client, no I/O.

Ledger task **21.8**. Kept separate from `weft_qdrant.store` so the arithmetic that makes a
lexical ranking honestly BM25 can be read and tested with nothing running: no server, no
event loop, no fixture.

**Nothing here downloads a model.** `analyze` folds case and splits on word boundaries —
the same "fold case, split on word boundaries, stem nothing" `pgvector`'s `simple`
configuration performs for the other backend, and for the same reason
(`PgVectorSettings.text_search_config`'s own comment): the corpus is deliberately
bilingual, and an English stemmer run over Polish is confident nonsense, not a smaller win.
Term frequency and document length are computed here; collection IDF is applied by Qdrant
itself, via `modifier=IDF` on the sparse vector configuration — a per-document encoder has
no way to know how many other documents hold a term.
"""

import hashlib
import re

#: Okapi BM25's own constants, matching `pg_textsearch`'s index-build defaults
#: (`k1=1.20, b=0.75`, logged at index creation on the other backend). Deliberately not
#: settings: exposing them here and not there would be exactly the asymmetry `01`'s
#: two-backend rule exists to catch, one store tunable and the other not.
_K1 = 1.2
_B = 0.75


def analyze(text: str) -> list[str]:
    r"""Fold case and split on Unicode word boundaries — every token `text` carries.

    `\w` on a `str` pattern is Unicode-aware, which is what keeps a word like `gęślą`
    whole rather than cutting it at the diacritic; an ASCII-only tokenizer would fail
    silently on exactly the bilingual corpus this project is built against.
    """
    return re.findall(r"\w+", text.casefold())


def token_id(token: str) -> int:
    """A token's position in Qdrant's sparse index — an unsigned 32-bit integer.

    Not Python's `hash()`, which is salted per process (`PYTHONHASHSEED`) and would
    make every restart address a different vocabulary; a stored sparse vector has to
    mean the same thing to the process that reads it back as it did to the one that
    wrote it.
    """
    digest = hashlib.blake2b(token.encode("utf-8"), digest_size=4).digest()
    return int.from_bytes(digest, "big")


def document_weights(tokens: list[str], *, avg_doc_len: float) -> dict[int, float]:
    """BM25's document side: term frequency, saturated and length-normalised.

    The collection-wide half — inverse document frequency — is deliberately absent:
    Qdrant applies it at query time from its own `modifier=IDF`, over however many
    documents exist *when the query runs*, which is a fact this function is never in a
    position to know at write time.
    """
    counts: dict[int, int] = {}
    for token in tokens:
        identifier = token_id(token)
        counts[identifier] = counts.get(identifier, 0) + 1
    length = len(tokens)
    return {
        identifier: (tf * (_K1 + 1)) / (tf + _K1 * (1 - _B + _B * length / avg_doc_len))
        for identifier, tf in counts.items()
    }


def query_weights(tokens: list[str]) -> dict[int, float]:
    """One weight per distinct query token — the IDF half comes from the server, not here."""
    return {token_id(token): 1.0 for token in tokens}
