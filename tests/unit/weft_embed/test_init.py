"""Unit tests for `weft_embed`'s `register()`.

Mirrors `packages/weft-rag/src/weft_embed/__init__.py`. Covers the happy
path (`register` adds `HashEmbedder` as `"hash"` under `Embedder`), and that
an unknown settings field is refused the way every pack settings model in
this project refuses one — `weft-embed` takes no settings, so `extra` fields
are the only shape its `Settings` model can get wrong.
"""

import pytest
from pydantic import ValidationError

from weft_embed import Settings, register
from weft_embed.contract import Embedder
from weft_embed.hash_embedder import HashEmbedder
from weft_kernel.discovery import PackRegistrar
from weft_kernel.registry import Registry


def test_register_adds_hash_embedder_under_embedder() -> None:
    # Arrange
    registry = Registry()
    registrar = PackRegistrar(registry, distribution="weft-embed")

    # Act
    register(registrar, Settings())
    registrar.commit()

    # Assert
    entry = registry.entry(Embedder, "hash")
    assert entry.factory is HashEmbedder
    assert entry.distribution == "weft-embed"


def test_settings_refuses_an_unknown_field() -> None:
    # Act / Assert
    with pytest.raises(ValidationError):
        Settings.model_validate({"bogus": "x"})


def test_the_pack_discloses_what_its_default_embedder_is_not() -> None:
    """Carried repair `R17.2`.

    `hash` is the default embedder (`weft_cli.services.DEFAULT_EMBEDDER`), and it derives every
    vector from a SHA-256 digest, so the ranking it produces carries no meaning. Three documents
    say so — `manual/operations-guide.md`, `docs/10-technique-catalogue.md`,
    `manual/user-manual.md` — and **none of them is on the path a first-hour user walks**. The
    binary said nothing at all: this pack declared no `DISCLOSURE`, so `weft plugins doctor`
    printed `disclosure: not disclosed` for the one pack whose default needs a sentence.

    Asserted on the *claim* rather than on wording: the note must state that the vector comes
    from a hash of the content and that it carries no semantic similarity, because those are the
    two facts an operator needs to not trust a result. The empty access tuples are asserted too —
    they are what makes this an honest disclosure rather than a quality caveat wearing one: this
    pack genuinely touches nothing, and says so in the same breath.
    """
    # Arrange
    from weft_embed import DISCLOSURE

    note = DISCLOSURE.note.lower()

    # Assert
    assert DISCLOSURE.network == ()
    assert DISCLOSURE.filesystem == ()
    assert DISCLOSURE.subprocess == ()
    assert "hash" in note
    assert "no semantic" in note or "carries no meaning" in note
    assert "default" in note
