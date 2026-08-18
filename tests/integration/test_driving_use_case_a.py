"""Task **1.9** — the Phase 1 exit test: driving use case A, entirely from configuration.

`docs/02-extension-model.md` §3 → *Derivation — driving use case A*: *"I need to add
KeyBERT to the `specific` pipeline — that pipeline is created from an existing one but
with KeyBERT added."* `docs/01-high-level-plan.md` → Phase 1 **Exit**: "a `specific`
pipeline derived from `base` with KeyBERT inserted after chunking, expressed as
configuration, with no change to core and no copy of the parent." This is that exit,
proved rather than narrated — the three properties below are each its own assertion, and
each is chosen so the test fails if that property alone stops holding.

**Real files, real YAML, the real CLI-side loader.** `weft_cli.pipeline_catalogue` is
where `weft-cli` opens the two documents below — `weft_kernel.pipeline.Pipeline` never
parses a file itself (`02` §3 → *One model, two directions*: "the kernel publishes the
model and opens no file"). This test plays the part a `weft pipeline` command will play
once Phase 3 wires one; nothing here reaches `weft_cli.cli` or `argparse`, because task
1.9 owns the loader and the translation (see `pipeline_catalogue.py`'s own docstring),
not the command surface — `docs/build-ledger.md` 3.7 owns `pipeline list|show|derive|
validate|diff`.

**Property 1 — no copy of the parent.** `weft_kernel.pipeline.Pipeline`'s own mutual-
exclusivity rule already guarantees a pipeline naming `extends` carries no `stages:` of
its own; what is left for `specific.yaml` to smuggle a copy through is the other three
operator blocks (`replace`/`remove`/`set`). `test_specific_is_defined_by_nothing_but_the_
insert_operator` asserts all three are empty and `insert` holds exactly the one KeyBERT
entry `02` §3 prints — the whole authored diff between the two files, checked, not read
by eye.

**Property 2 — resolution reads `base` live.** `test_editing_base_on_disk_reaches_
specific_on_the_next_resolve` resolves `specific` once, then rewrites `base.yaml`'s
`chunk` stage on disk, reloads the catalogue, and resolves `specific` again — no code
path in `weft_kernel.resolution.resolve` retains anything from the first call, so the
second resolution can only see the edit if the parent really was read again rather than
copied at derivation time. `weft_kernel.resolution`'s own module docstring makes the same
claim purely in-memory (`parents` is "read fresh on every call and never copied"); this
test is that claim carried one layer further out, through the file the parent actually
lives in.

**Property 3 — KeyBERT does not download a model.** No test here mocks a network call or
asserts an absence of one — the proof is structural: `weft_enhance.keybert_stand_in.
KeyBertKeywordExtractor` never runs (this test only calls `resolve()`, which reads class
attributes off a registered factory and instantiates nothing — see `weft_kernel.
resolution`'s own module docstring, *"read off the registered factory class, never an
instance"*), and `tests/unit/weft_enhance/test_keybert_stand_in.py` is where the plugin
actually runs, deterministically, with pytest's own network-free sandbox as the only
proof needed that nothing there reaches out. What this test adds on top: `weft.toml` is
never opened, no credential or endpoint is configured anywhere in it, and resolution
still succeeds — a model-backed plugin would have nowhere to get one from.

No container is needed — nothing here reaches a store. `resolve()` is pure computation
over a registry and two YAML files, so this belongs beside the other integration proofs
without inheriting `test_ingest_pipeline.py`'s skip discipline; there is nothing to skip.
"""

from pathlib import Path
from typing import Final

from weft_chunk import Chunker, FixedSizeChunker, FixedSizeChunkerConfig
from weft_cli.pipeline_catalogue import load_pipeline_catalogue
from weft_embed import Embedder, HashEmbedder
from weft_enhance import Enhancer, KeyBertKeywordExtractor
from weft_extract import Extractor, TextExtractor
from weft_kernel.registry import Registry
from weft_kernel.resolution import ResolvedPipeline, resolve

# `02` §3's own base.yaml, trimmed to the built-ins this task needs (extract, chunk,
# embed) — `clean` and `store` are omitted on purpose: this test proves *derivation*,
# and neither the cleaning chain's ordering constraints nor a real container has
# anything to add to that proof. See "No canonical ingest order" — this is an example,
# never the canonical one.
_BASE_YAML_V1 = """\
name: base
stages:
  - id: extract
    use: text
  - id: chunk
    use: fixed-size
    with: {size: 200, overlap: 20}
  - id: embed
    use: hash
"""

# The only edit: `chunk`'s `size` moves from 200 to 300. Nothing else in the file changes.
_BASE_YAML_V2 = _BASE_YAML_V1.replace("size: 200", "size: 300")

# `02` §3's own specific.yaml, verbatim in shape: one `extends:`, one `insert:`.
_SPECIFIC_YAML = """\
name: specific
extends: base
insert:
  - after: chunk
    stage: {id: keywords, use: keybert, with: {top_n: 8}}
"""

#: Stage id -> contract, the shape `weft_kernel.resolution.resolve` documents itself as
#: needing from its caller (`02` §3: "a stage's contract is supplied by the caller, not
#: guessed from a bare `use:` name"). Phase 1 does not invent a mechanism that derives
#: this from a document — `weft_cli.ingest.INDEX_SPECS` states the identical kind of
#: mapping as a constant today, for the identical reason.
_CONTRACTS: Final[dict[str, type[object]]] = {
    "extract": Extractor,
    "chunk": Chunker,
    "keywords": Enhancer,
    "embed": Embedder,
}


def _registry() -> Registry:
    registry = Registry()
    registry.add(Extractor, "text", TextExtractor, distribution="weft-extract")
    registry.add(Chunker, "fixed-size", FixedSizeChunker, distribution="weft-chunk")
    registry.add(Enhancer, "keybert", KeyBertKeywordExtractor, distribution="weft-enhance")
    registry.add(Embedder, "hash", HashEmbedder, distribution="weft-embed")
    return registry


def _chunk_size(resolved: ResolvedPipeline) -> int:
    """The resolved `chunk` stage's `size` — a validated `FixedSizeChunkerConfig`, task 1.5.

    Not a raw mapping: `weft_kernel.resolution._validate_stage_config` hands back the
    *object* `FixedSizeChunkerConfig.model_validate(...)` built, never the `with:` block it
    validated — see that module's own docstring, *"Config validation runs last..."*.
    """
    (chunk,) = (stage for stage in resolved.stages if stage.id == "chunk")
    config = chunk.config
    assert isinstance(config, FixedSizeChunkerConfig)
    return config.size


def test_specific_is_defined_by_nothing_but_the_insert_operator(tmp_path: Path) -> None:
    """Property 1 — the entire authored diff between the two documents is one `insert`."""
    # Arrange
    (tmp_path / "base.yaml").write_text(_BASE_YAML_V1)
    (tmp_path / "specific.yaml").write_text(_SPECIFIC_YAML)

    # Act
    catalogue = load_pipeline_catalogue(tmp_path)
    specific = catalogue["specific"]

    # Assert — no stages of its own (Pipeline's own validator already forbids this
    # alongside `extends`), and none of the other three operators touched either: the
    # *only* content this document adds beyond naming its parent is the one `insert`.
    assert specific.extends == "base"
    assert specific.stages == ()
    assert specific.replace == ()
    assert specific.remove == ()
    assert specific.set == ()
    assert len(specific.insert) == 1
    (inserted,) = specific.insert
    assert inserted.after == "chunk"
    assert inserted.before is None
    assert inserted.stage.id == "keywords"
    assert inserted.stage.use == "keybert"
    assert dict(inserted.stage.config) == {"top_n": 8}


def test_specific_resolves_to_base_plus_keybert_after_chunk(tmp_path: Path) -> None:
    """The derived pipeline actually is base's three stages with keywords inserted."""
    # Arrange
    (tmp_path / "base.yaml").write_text(_BASE_YAML_V1)
    (tmp_path / "specific.yaml").write_text(_SPECIFIC_YAML)
    catalogue = load_pipeline_catalogue(tmp_path)

    # Act
    resolved = resolve(
        catalogue["specific"], registry=_registry(), contracts=_CONTRACTS, parents=catalogue
    )

    # Assert
    assert [stage.id for stage in resolved.stages] == ["extract", "chunk", "keywords", "embed"]
    (keywords,) = (stage for stage in resolved.stages if stage.id == "keywords")
    assert keywords.use == "keybert"
    assert keywords.provenance == "specific"  # inserted by the child, not inherited from base
    (extract,) = (stage for stage in resolved.stages if stage.id == "extract")
    assert extract.provenance == "base"  # untouched stages still credit their root
    assert _chunk_size(resolved) == 200


def test_editing_base_on_disk_reaches_specific_on_the_next_resolve(tmp_path: Path) -> None:
    """Property 2 — `base` is read live: an edit on disk reaches `specific` with no cache."""
    # Arrange
    base_path = tmp_path / "base.yaml"
    base_path.write_text(_BASE_YAML_V1)
    (tmp_path / "specific.yaml").write_text(_SPECIFIC_YAML)
    catalogue = load_pipeline_catalogue(tmp_path)
    before = resolve(
        catalogue["specific"], registry=_registry(), contracts=_CONTRACTS, parents=catalogue
    )
    assert _chunk_size(before) == 200  # the value this test is about to prove changes

    # Act — edit the parent only; `specific.yaml` is never touched.
    base_path.write_text(_BASE_YAML_V2)
    reloaded_catalogue = load_pipeline_catalogue(tmp_path)
    after = resolve(
        reloaded_catalogue["specific"],
        registry=_registry(),
        contracts=_CONTRACTS,
        parents=reloaded_catalogue,
    )

    # Assert
    assert _chunk_size(after) == 300
