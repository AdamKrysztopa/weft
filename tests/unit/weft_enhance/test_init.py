"""Unit tests for `weft_enhance`'s `register()`.

Mirrors `packages/weft-rag/src/weft_enhance/__init__.py`. Covers the happy path
(`register` adds `KeyBertKeywordExtractor` as `"keybert"` under `Enhancer`), and that an
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
from weft_kernel.registry import Registry


def test_register_adds_keybert_stand_in_under_enhancer() -> None:
    # Arrange
    registry = Registry()
    registrar = PackRegistrar(registry, distribution="weft-enhance")

    # Act
    register(registrar, Settings())
    registrar.commit()

    # Assert
    entry = registry.entry(Enhancer, "keybert")
    assert entry.factory is KeyBertKeywordExtractor
    assert entry.distribution == "weft-enhance"


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
# **Settled by the owner 2026-09-13: rename, and keep the old name working.** `keybert` ships in
# the published `weft-rag 2.4.0` and `index-with-keywords.yaml` names it, so removing it would
# break a configuration somebody may already have written. `09` §2.2 is what governs that:
# *"inside 0.x a contract may move without a deprecation period, **but never silently**"* — so the
# old name stays registered and is **marked**, and `weft_kernel.seam.warn_deprecated` does the
# rest at the registration seam. Nobody writes the warning by hand.


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


def test_the_published_name_keeps_working_so_an_existing_config_does_not_break() -> None:
    """`keybert` is in `weft-rag 2.4.0` on PyPI. A rename that removed it would turn somebody
    else's working `weft.toml` into an `UnknownPluginError` on upgrade."""
    # Arrange
    registry = Registry()
    registrar = PackRegistrar(registry, distribution="weft-enhance")

    # Act
    register(registrar, Settings())
    registrar.commit()

    # Assert — the same plugin, reachable under both names.
    assert registry.entry(Enhancer, "keybert").factory is KeyBertKeywordExtractor


def test_the_old_name_is_marked_deprecated_rather_than_quietly_kept() -> None:
    """**The half that makes this a rename rather than an alias.** `09` §2.2: a contract may move
    inside 0.x, but never silently. An old name left registered and unmarked is exactly the silent
    case — it works forever, nothing says it is going away, and the misleading name outlives the
    decision to retire it. `PackRegistrar.deprecate` is the mechanism task 5.2e built for this, and
    the warning is emitted at the seam rather than written by hand."""
    # Arrange
    registry = Registry()
    registrar = PackRegistrar(registry, distribution="weft-enhance")

    # Act
    register(registrar, Settings())
    registrar.commit()

    # Assert
    marked = {deprecation.surface: deprecation.reason for deprecation in registrar.deprecations}
    assert "keybert" in marked, f"the retired name is not marked: {sorted(marked)}"
    assert "term-frequency-keywords" in marked["keybert"], (
        "a deprecation notice that does not name the replacement sends the reader looking"
    )
    assert "term-frequency-keywords" not in {
        deprecation.surface for deprecation in registrar.deprecations
    }, "the canonical name is not the deprecated one"
