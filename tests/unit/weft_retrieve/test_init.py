"""Unit tests for `weft_retrieve.__init__`.

Mirrors `packages/weft-retrieve/src/weft_retrieve/__init__.py`. Task 2.4 published the
query-path contracts and registered nothing under them — that emptiness was itself a
*stated* fact rather than an oversight, held here until task 2.13 shipped the first plugin
(`no-retrieval`) and, in the same commit, the `weft.packs` entry point fitness function 2
requires of a distribution that is active *and contributing*.
"""

import tomllib
from pathlib import Path

import pytest

import weft_retrieve
from weft_kernel.discovery import PackRegistrar
from weft_kernel.registry import Registry
from weft_kernel.runner import Runner, StageCompositionError, StageSpec, UnmetRequiresError
from weft_prompts.contract import Prompt
from weft_retrieve.boolean import BooleanRetrieval
from weft_retrieve.contract import ContextPacker, Fuser, QueryTransform, Reranker, Retriever
from weft_retrieve.fusion import BooleanCombine, ReciprocalRankFusion, SingleList
from weft_retrieve.no_retrieval import NoRetrieval
from weft_retrieve.prompts import (
    BOOLEAN_PARSE_NAME,
    MULTI_QUERY_VARIANTS_NAME,
    PASSAGE_RELEVANCE_NAME,
    STANDALONE_QUESTION_NAME,
    BooleanParsePrompt,
    MultiQueryVariantsPrompt,
    PassageRelevancePrompt,
    StandaloneQuestionPrompt,
)
from weft_retrieve.repack import Repack
from weft_retrieve.rerank import LlmRerank, LlmRerankConfig
from weft_retrieve.transforms import ContextualQueryRewrite, MultiQuery

_PYPROJECT = Path(__file__).resolve().parents[3] / "packages" / "weft-retrieve" / "pyproject.toml"


def test_the_contracts_this_distribution_publishes_are_exported() -> None:
    # Act / Assert — `weft_cli.contract_reference._capability_siblings` reads `__all__`, and a
    # published contract missing from it is silently absent from the generated reference.
    assert "Retriever" in weft_retrieve.__all__
    assert weft_retrieve.Retriever is Retriever


def test_the_pack_entry_point_is_declared_now_that_something_is_registered() -> None:
    # Arrange
    with _PYPROJECT.open("rb") as handle:
        document = tomllib.load(handle)

    # Act / Assert — the line landed in the commit that shipped the first plugin (2.13)
    assert document["project"]["entry-points"]["weft.packs"] == {
        "retrieve": "weft_retrieve:register"
    }


def test_register_adds_no_retrieval_under_the_retriever_contract() -> None:
    # Arrange
    registry = Registry()
    registrar = PackRegistrar(registry, distribution="weft-retrieve")

    # Act
    weft_retrieve.register(registrar, weft_retrieve.Settings())
    registrar.commit()

    # Assert
    entry = registry.entry(Retriever, "no-retrieval")
    assert entry.distribution == "weft-retrieve"
    assert isinstance(entry.factory(None), NoRetrieval)


def test_register_adds_vector_top_k_under_the_retriever_contract() -> None:
    # Arrange — task 2.14: a second `Retriever`, registered the same way as the first.
    registry = Registry()
    registrar = PackRegistrar(registry, distribution="weft-retrieve")

    # Act
    weft_retrieve.register(registrar, weft_retrieve.Settings())
    registrar.commit()

    # Assert
    entry = registry.entry(Retriever, "vector-top-k")
    assert entry.distribution == "weft-retrieve"
    assert isinstance(entry.factory(None), weft_retrieve.VectorTopK)


def test_register_adds_the_fuser_the_reranker_and_the_prompt_it_asks() -> None:
    # Arrange — task 2.7. Three contracts, one `register()`, no privileged path: the `Prompt`
    # is registered through the same `PackRegistrar` the retrievers are, because a prompt
    # belongs to the pack whose plugin asks the question (the 2.10 ledger line).
    registry = Registry()
    registrar = PackRegistrar(registry, distribution="weft-retrieve")

    # Act
    weft_retrieve.register(registrar, weft_retrieve.Settings())
    registrar.commit()

    # Assert
    assert isinstance(registry.entry(Fuser, "single-list").factory(None), SingleList)
    assert isinstance(registry.entry(Reranker, "llm-rerank").factory(None), LlmRerank)
    assert isinstance(
        registry.entry(Prompt, PASSAGE_RELEVANCE_NAME).factory(None), PassageRelevancePrompt
    )


def test_register_adds_the_query_transform_and_the_prompt_it_asks() -> None:
    # Arrange — task 2.15: a fifth contract, `QueryTransform`, registered the same way as the
    # other four, and its own registered `Prompt`.
    registry = Registry()
    registrar = PackRegistrar(registry, distribution="weft-retrieve")

    # Act
    weft_retrieve.register(registrar, weft_retrieve.Settings())
    registrar.commit()

    # Assert
    assert isinstance(
        registry.entry(QueryTransform, "contextual-query-rewrite").factory(None),
        ContextualQueryRewrite,
    )
    assert isinstance(
        registry.entry(Prompt, STANDALONE_QUESTION_NAME).factory(None), StandaloneQuestionPrompt
    )


def test_a_query_transform_is_a_composable_stage_a_caller_can_omit() -> None:
    # Arrange — task 2.15's own sentence, resolved rather than asserted in prose: "a query
    # transform is a composable stage a caller can omit, so no strategy pays for a rewrite it
    # did not ask for." `QueryTransform` is `Stage[QuerySet, QuerySet]` (task 2.4), so a
    # document that inserts `contextual-query-rewrite` before `vector-top-k` and a document
    # that omits it entirely both resolve — the transform changes nothing about the seam
    # either side of where it sits.
    registry = Registry()
    registrar = PackRegistrar(registry, distribution="weft-retrieve")
    weft_retrieve.register(registrar, weft_retrieve.Settings())
    registrar.commit()
    runner = Runner(registry)
    rewrite = StageSpec(id="rewrite", contract=QueryTransform, name="contextual-query-rewrite")
    retrieve = StageSpec(id="retrieve", contract=Retriever, name="vector-top-k")

    # Act / Assert — with the transform, and without it: both compose with no other change.
    assert runner.resolve((retrieve,), tenant_id="tenant-a").stages
    assert runner.resolve((rewrite, retrieve), tenant_id="tenant-a").stages


def test_fusion_and_reranking_are_two_positions_a_document_fills_independently() -> None:
    # Arrange — task 2.7's own sentence, resolved rather than asserted in prose: "fusion and
    # reranking are composable plugins a third party can retune, **not a fixed ladder**." Four
    # documents, each a different arrangement of the same two registered names, and the only
    # one refused is the one that does not compose by type.
    registry = Registry()
    registrar = PackRegistrar(registry, distribution="weft-retrieve")
    weft_retrieve.register(registrar, weft_retrieve.Settings())
    registrar.commit()
    runner = Runner(registry)
    retrieve = StageSpec(id="retrieve", contract=Retriever, name="vector-top-k")
    fuse = StageSpec(id="fuse", contract=Fuser, name="single-list")
    rerank = StageSpec(id="rerank", contract=Reranker, name="llm-rerank")
    retuned = StageSpec(
        id="rerank-again", contract=Reranker, name="llm-rerank", config=LlmRerankConfig(top_n=3)
    )

    # Act / Assert — fusion with no reranking; fusion then reranking; two rerankers in a row,
    # the second retuned in its own `with:` block and needing no new type to follow the first.
    assert runner.resolve((retrieve, fuse), tenant_id="tenant-a").stages
    assert runner.resolve((retrieve, fuse, rerank), tenant_id="tenant-a").stages
    assert runner.resolve((retrieve, fuse, rerank, retuned), tenant_id="tenant-a").stages

    # ...and reranking before fusing is refused by the kernel's own composition check, naming
    # both types — the one ordering the type algebra rules out, and the only rung of this
    # non-ladder that is fixed.
    with pytest.raises(StageCompositionError, match="Ranking"):
        runner.resolve((retrieve, rerank, fuse), tenant_id="tenant-a")


def test_the_distribution_declares_the_packs_whose_types_its_contracts_name() -> None:
    # Arrange
    with _PYPROJECT.open("rb") as handle:
        document = tomllib.load(handle)

    # Act / Assert — `Passage` wraps `weft_store.Scored[Node]`, so that dependency is real
    # rather than incidental, and an install of this distribution alone must carry it.
    # `weft-embed` joined at task 2.14: `vector-top-k` turns a query into a vector through
    # `weft_embed.contract.Embedder` before it can search for one. `weft-llm` and
    # `weft-prompts` joined at task 2.7: `llm-rerank` asks a model a registered prompt, and
    # both are upstream of this pack on `.phase2-design.md` §2's one-way chain.
    assert set(document["project"]["dependencies"]) == {
        "weft-kernel",
        "weft-store",
        "weft-embed",
        "weft-llm",
        "weft-prompts",
    }


def test_register_adds_multi_query_and_the_prompt_it_asks() -> None:
    # Arrange — task 2.18a: a fourth `QueryTransform`, registered beside the other three, and
    # its own registered `Prompt`.
    registry = Registry()
    registrar = PackRegistrar(registry, distribution="weft-retrieve")

    # Act
    weft_retrieve.register(registrar, weft_retrieve.Settings())
    registrar.commit()

    # Assert
    assert isinstance(registry.entry(QueryTransform, "multi-query").factory(None), MultiQuery)
    assert isinstance(
        registry.entry(Prompt, MULTI_QUERY_VARIANTS_NAME).factory(None), MultiQueryVariantsPrompt
    )


def test_register_adds_reciprocal_rank_fusion_under_the_fuser_contract() -> None:
    # Arrange — task 2.18b: a second `Fuser`, registered beside `single-list`.
    registry = Registry()
    registrar = PackRegistrar(registry, distribution="weft-retrieve")

    # Act
    weft_retrieve.register(registrar, weft_retrieve.Settings())
    registrar.commit()

    # Assert
    assert isinstance(
        registry.entry(Fuser, "reciprocal-rank-fusion").factory(None), ReciprocalRankFusion
    )


def test_the_fuse_position_is_a_one_line_delta_from_single_list_to_rrf() -> None:
    # Arrange — ledger 2.18's own claim, resolved rather than asserted in prose: swapping
    # `fuse:`'s `use:` line from `single-list` to `reciprocal-rank-fusion` is the only edit a
    # document needs to gain real fusion, because both fill the identical `Fuser` position.
    registry = Registry()
    registrar = PackRegistrar(registry, distribution="weft-retrieve")
    weft_retrieve.register(registrar, weft_retrieve.Settings())
    registrar.commit()
    runner = Runner(registry)
    retrieve = StageSpec(id="retrieve", contract=Retriever, name="vector-top-k")
    single_list = StageSpec(id="fuse", contract=Fuser, name="single-list")
    rrf = StageSpec(id="fuse", contract=Fuser, name="reciprocal-rank-fusion")

    # Act / Assert — both resolve; the document differs only in this one stage's `name`.
    assert runner.resolve((retrieve, single_list), tenant_id="tenant-a").stages
    assert runner.resolve((retrieve, rrf), tenant_id="tenant-a").stages


def test_register_adds_repack_under_the_context_packer_contract() -> None:
    # Arrange — task 2.19: the sixth contract, `ContextPacker`, registered the same way as
    # every other position in this pack.
    registry = Registry()
    registrar = PackRegistrar(registry, distribution="weft-retrieve")

    # Act
    weft_retrieve.register(registrar, weft_retrieve.Settings())
    registrar.commit()

    # Assert
    assert isinstance(registry.entry(ContextPacker, "repack").factory(None), Repack)


def test_the_pack_position_composes_after_fuse_and_after_rerank() -> None:
    # Arrange — the V3 baseline's own shape (`.phase2-design.md` §4):
    # retrieve -> fuse -> pack, and retrieve -> fuse -> rerank -> pack, both resolve because
    # `ContextPacker` is `Stage[Ranking, Ranking]`'s own `Out` consumer and both `Fuser` and
    # `Reranker` produce a `Ranking`.
    registry = Registry()
    registrar = PackRegistrar(registry, distribution="weft-retrieve")
    weft_retrieve.register(registrar, weft_retrieve.Settings())
    registrar.commit()
    runner = Runner(registry)
    retrieve = StageSpec(id="retrieve", contract=Retriever, name="vector-top-k")
    fuse = StageSpec(id="fuse", contract=Fuser, name="single-list")
    rerank = StageSpec(id="rerank", contract=Reranker, name="llm-rerank")
    pack = StageSpec(id="pack", contract=ContextPacker, name="repack")

    # Act / Assert
    assert runner.resolve((retrieve, fuse, pack), tenant_id="tenant-a").stages
    assert runner.resolve((retrieve, fuse, rerank, pack), tenant_id="tenant-a").stages

    # ...and packing before fusing is refused by the kernel's own composition check, naming
    # both types — `ContextPacker` consumes `Ranking`, and a `Retriever` produces `Candidates`.
    with pytest.raises(StageCompositionError, match="Candidates"):
        runner.resolve((retrieve, pack), tenant_id="tenant-a")


def test_register_adds_boolean_retrieval_and_boolean_combine_and_the_prompt_it_asks() -> None:
    # Arrange — task 2.23: a fifth `QueryTransform` and a third `Fuser`, registered exactly
    # like every other entry in `register`.
    registry = Registry()
    registrar = PackRegistrar(registry, distribution="weft-retrieve")

    # Act
    weft_retrieve.register(registrar, weft_retrieve.Settings())
    registrar.commit()

    # Assert
    assert isinstance(
        registry.entry(QueryTransform, "boolean-retrieval").factory(None), BooleanRetrieval
    )
    assert isinstance(registry.entry(Fuser, "boolean-combine").factory(None), BooleanCombine)
    assert isinstance(registry.entry(Prompt, BOOLEAN_PARSE_NAME).factory(None), BooleanParsePrompt)


def test_boolean_combine_with_no_boolean_retrieval_upstream_fails_resolution() -> None:
    # Arrange — the design record's own exit demonstration for `requires`/`provides` on this
    # task: `boolean-combine` declares `requires = (BooleanPlan,)`, `boolean-retrieval`
    # declares `provides = (BooleanPlan,)`, and a document naming the second without the
    # first is refused before a single query is asked — not discovered mid-run as a missing
    # key on `Candidates.ext`.
    registry = Registry()
    registrar = PackRegistrar(registry, distribution="weft-retrieve")
    weft_retrieve.register(registrar, weft_retrieve.Settings())
    registrar.commit()
    runner = Runner(registry)
    retrieve = StageSpec(id="retrieve", contract=Retriever, name="vector-top-k")
    combine = StageSpec(id="fuse", contract=Fuser, name="boolean-combine")

    # Act / Assert
    with pytest.raises(UnmetRequiresError, match="BooleanPlan"):
        runner.resolve((retrieve, combine), tenant_id="tenant-a")


def test_boolean_retrieval_then_boolean_combine_resolves() -> None:
    # Arrange — the positive half of the same claim: naming `boolean-retrieval` ahead of
    # `boolean-combine` in the same document is what satisfies the `requires`/`provides`
    # check the test above shows refusing its absence.
    registry = Registry()
    registrar = PackRegistrar(registry, distribution="weft-retrieve")
    weft_retrieve.register(registrar, weft_retrieve.Settings())
    registrar.commit()
    runner = Runner(registry)
    transform = StageSpec(id="transform", contract=QueryTransform, name="boolean-retrieval")
    retrieve = StageSpec(id="retrieve", contract=Retriever, name="vector-top-k")
    combine = StageSpec(id="fuse", contract=Fuser, name="boolean-combine")

    # Act / Assert
    assert runner.resolve((transform, retrieve, combine), tenant_id="tenant-a").stages
