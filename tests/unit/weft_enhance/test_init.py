"""Unit tests for `weft_enhance`'s `register()`.

Mirrors `packages/weft-rag/src/weft_enhance/__init__.py`. Covers the happy path (`register`
adds `KeyBertKeywordExtractor` as `"term-frequency-keywords"` under `Enhancer`), and that an
unknown settings field is refused the way every pack settings model in this project
refuses one — `weft-enhance` takes no settings, so `extra` fields are the only shape its
`Settings` model can get wrong.
"""

import pytest
from pydantic import ValidationError

from weft_enhance import Settings, register
from weft_enhance.contract import Enhancer
from weft_enhance.keybert_stand_in import KeyBertKeywordExtractor
from weft_kernel.discovery import PackRegistrar
from weft_kernel.registry import Registry, UnknownPluginError


def test_settings_refuses_an_unknown_field() -> None:
    # Act / Assert
    with pytest.raises(ValidationError):
        Settings.model_validate({"bogus": "x"})


# --- task 21.10: the name stops claiming a technique the code does not implement --------------
#
# **`R19.15`.** `KeyBertKeywordExtractor` counts token frequency against a fixed stoplist. Real
# KeyBERT (Grootendorst, doi:10.5281/zenodo.4461265) ranks n-grams by cosine similarity to a
# transformer embedding of the document. The tell is in the shipped output: indexing this
# repository's own README under the old name stored
# `["microkernel", "every", "capability", "plugin", "pipeline"]`, and **"every"** is there because
# the ranking is word frequency.
#
# `10` §2.1 rule 4 forbids naming a technique for an outcome it does not achieve, and the
# catalogue row for this plugin **cited rule 4 to justify breaking it** — the only row in the
# catalogue that does. Its own neighbours show the obedient form: `cooccurrence-graph` is
# deliberately not `ner`, and `multi-arm` is deliberately not `hybrid` because that *"would have
# been the overclaim rule 4 forbids"*.
#
# **Settled by the owner 2026-09-13: rename, and keep the old name working until the next major.**
# `keybert` shipped in `weft-rag 2.4.0`, so it stayed registered and marked through 2.x. Its
# notice said "removed in weft-rag 3.0.0", and `43.38` removes it there: a 3.0.0 still carrying it
# would have silently moved that date to 4.0.0.


def test_the_canonical_name_describes_what_the_code_actually_does() -> None:
    # Arrange
    registry = Registry()
    registrar = PackRegistrar(registry, distribution="weft-enhance")

    # Act
    register(registrar, Settings())
    registrar.commit()

    # Assert
    entry = registry.entry(Enhancer, "term-frequency-keywords")
    assert entry.factory is KeyBertKeywordExtractor
    assert entry.distribution == "weft-enhance"


def test_the_retired_name_is_gone_at_the_major_its_notice_named() -> None:
    """Task 43.38: `keybert` is unregistered at `weft-rag` 3.0.0, as its notice promised.

    A configuration still naming it is refused by name, and the refusal lists the name to use.
    """
    # Arrange
    registry = Registry()
    registrar = PackRegistrar(registry, distribution="weft-enhance")

    # Act
    register(registrar, Settings())
    registrar.commit()

    # Assert
    with pytest.raises(UnknownPluginError) as refused:
        registry.entry(Enhancer, "keybert")
    assert "term-frequency-keywords" in refused.value.valid_options
    assert registrar.deprecations == ()
