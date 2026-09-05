"""First-party retrieval pack.

Publishes the query-path contracts (`contract.py`) and the query vocabulary they are
written in (`payload.py`). Task **2.4** left this distribution registering nothing,
deliberately — `docs/build-ledger.md` calls that task "the mechanism", and says in the same
breath that "without 2.13–2.26 the mechanism is empty." **`no-retrieval` (task 2.13) is the
first plugin to arrive**, and it brings `Settings`, `register` and the `weft.packs` entry
point together in the same commit, through the same public group any third-party pack uses —
fitness function 2, with no shortcut for being first-party. **`vector-top-k` (task 2.14) is
the second**, and it is why this distribution now depends on `weft-embed`: a query has to
become a vector before it can be searched for, and `weft_embed.contract.Embedder` is where
that already happens for ingest. **`single-list` and `llm-rerank` (task 2.7) are the third and
fourth**, and they are why this distribution now also depends on `weft-llm` and
`weft-prompts`: fusion and reranking are two positions in a document rather than two steps
inside a strategy, and the reranker asks a model a *registered* prompt — shipped here, under
`weft_prompts.contract.Prompt`, because a prompt belongs to the plugin that asks the question.
**`contextual-query-rewrite` (task 2.15) is the fifth**, and it is the first plugin
registered under `weft_retrieve.contract.QueryTransform` — the position `hyde` (2.16) and
`step-back` (2.17) register into next. It brings a second registered `Prompt`,
`standalone-question`, for the same reason `passage-relevance` arrived with `llm-rerank`.
**`hyde` (task 2.16) is the sixth**, the second `QueryTransform` and the third registered
`Prompt` (`hyde-document`) — for the same reason the first two arrived with their own
plugins. **`step-back` (task 2.17) is the seventh**, the third `QueryTransform` and the
fourth registered `Prompt` — named `step-back-question`, not `step-back`, because the
transform itself already claims `step-back` and `.phase2-design.md` §5's own derived rule
forbids one plugin name answering to two contracts (see `weft_retrieve.prompts.
STEP_BACK_QUESTION_NAME`'s own docstring). **`multi-query` (task 2.18a) is the eighth**, the
fourth `QueryTransform` and the fifth registered `Prompt` (`multi-query-variants`, for the
same collision reason `step-back-question` is not `step-back`). **`reciprocal-rank-fusion`
(task 2.18b) is the ninth**, the second `Fuser` beside `single-list` — the plugin ledger
2.18's own line is about: `multi-query` is the `QueryTransform` half of "one query becomes
n," and this is the one `Fuser` implementation that fuses what it produces exactly as it
fuses `vector-top-k` searched on two channels, with no branch anywhere asking which kind of
multiplicity it was handed. **`repack` (task 2.19) is the tenth**, the first
`ContextPacker` and the position `weft_generate.cited_answer`'s own `Passages` labels come
from — see `weft_retrieve.repack`'s module docstring for the defect its default
method (`reverse`, not `sides`) refuses to launder through a citation. **`iterative-retrieval`
(task 2.20) is the eleventh**, the second `Retriever` to own its own loop rather than a single
pass — `weft_retrieve.contract.StageLookup`'s own docstring names the concession this plugin
is built on: "a looping technique is one plugin that owns its loop and reaches a sibling
through here." It resolves `leaf` (another `Retriever`) and `sufficiency` (the `Sufficiency`
contract, also published in `contract.py` since task 2.4) both by name, so neither is imported
or constructed in this pack. The router's two halves land under their own ledger task, 2.25.
**`graded-retrieval` (task 2.21a) is the twelfth**, a second `Reranker` beside `llm-rerank`
and the sixth registered `Prompt` (`relevance-grade`) — a per-document filter reusable by any
pipeline with a `Ranking`, whether or not anything downstream of it ever reaches a second
retriever. **`corrective` (task 2.21b) is the thirteenth**, a third `Retriever` that owns its
own decision the same way `iterative-retrieval` owns its own loop: it resolves `primary`, then
`graded-retrieval` (or whichever `Reranker` a document names as `grader`), and — only when too
few hits survive grading — a `knowledge_action` distinct from `primary`, all three resolved by
name through `StageLookup`. `docs/10-technique-catalogue.md` §1.1's own condition is what makes
the name earned rather than borrowed; see `weft_retrieve.corrective`'s own module docstring.
**`boolean-retrieval` (task 2.23a) is the fourteenth**, a fifth `QueryTransform`, and
**`boolean-combine` (task 2.23b) is the fifteenth**, a third `Fuser` beside `single-list` and
`reciprocal-rank-fusion` — the two-plugin technique `weft_retrieve.boolean`'s own module
docstring describes: a Boolean query parsed to a typed, precedence-respecting `BoolExpr` by the
first, evaluated by set algebra against what was actually retrieved by the second, with the
tree itself carried between them as data (`BooleanPlan`, `requires`/`provides`) rather than as
two halves of one plugin. The seventh registered `Prompt`, `boolean-parse`, arrives with
`boolean-retrieval`, the same split every model-backed plugin in this pack already makes.
**`llm-sufficiency` and `hedge-phrases` (task 2.24) are the sixteenth and seventeenth**, and
the first two registered under `weft_retrieve.contract.Sufficiency` — a contract with no
pipeline position of its own, reached only by name through `StageLookup` from inside a
looping technique (`iterative-retrieval`, already shipped) or a refining one
(`weft_generate.refine.RefineOnUncertainty`, task 2.24's other half). `weft_retrieve.
sufficiency`'s own module docstring states the ledger line these two exist to satisfy: a
draft's uncertainty is a named, swappable signal rather than an English phrase list one
generator hard-codes. The eighth registered `Prompt`, `sufficiency-check`, arrives with
`llm-sufficiency`.
**`query-scorer` and `threshold-ladder` / `nearest-description` / `always` (task 2.25) are
the eighteenth through twenty-first**, the first names registered under `weft_retrieve.
contract.QueryScorer` and `weft_retrieve.contract.RoutingPolicy` — the router's two halves,
split so a threshold ladder can be replaced by a trained classifier without touching the
scorer (`weft_retrieve.routing`'s own module docstring). The ninth registered `Prompt`,
`route-query`, arrives with `query-scorer`.
**`collapse-to-parent` (task 2.33) is the twenty-second**, a third `Reranker` beside
`llm-rerank` and `graded-retrieval` — `weft_retrieve.collapse`'s own module docstring is why
this registers into `Reranker`'s existing slot rather than growing a fifth query-path
contract: same `Stage[Ranking, Ranking]` signature, same "no fourth query-path contract"
reading `.phase2-findings.md` §11's closing note asks for. It groups a `Ranking`'s hits by
parent — a `hypothetical-questions` (2.31) or `raptor` (2.32) derived node collapses into
the one parent it stands in for — so a chunk indexed several ways cannot occupy several of
a ranking's own slots, the measurement artefact `.phase2-findings.md` §11 names by name.
"""

from pydantic import BaseModel, ConfigDict

from weft_kernel.discovery import PackRegistrar
from weft_prompts.contract import Prompt
from weft_retrieve.boolean import NAME as BOOLEAN_RETRIEVAL_NAME
from weft_retrieve.boolean import (
    BooleanPlan,
    BooleanRetrieval,
    BooleanRetrievalConfig,
    BoolExpr,
    BoolOp,
)
from weft_retrieve.collapse import NAME as COLLAPSE_TO_PARENT_NAME
from weft_retrieve.collapse import CollapsePolicy, CollapseToParent, CollapseToParentConfig
from weft_retrieve.contract import (
    RETRIEVE_CONTRACT_VERSION,
    ContextPacker,
    Fuser,
    QueryScorer,
    QueryTransform,
    Reranker,
    Retriever,
    RouteCatalogue,
    RoutingPolicy,
    StageLookup,
    Sufficiency,
)
from weft_retrieve.corrective import NAME as CORRECTIVE_NAME
from weft_retrieve.corrective import Corrective, CorrectiveConfig, CorrectiveTrace
from weft_retrieve.fusion import (
    BOOLEAN_COMBINE_NAME,
    RRF_NAME,
    BooleanCombine,
    BooleanCombineConfig,
    EmptyConjunction,
    ReciprocalRankFusion,
    ReciprocalRankFusionConfig,
    SingleList,
    contributor_label,
)
from weft_retrieve.fusion import NAME as SINGLE_LIST_NAME
from weft_retrieve.graded import NAME as GRADED_RETRIEVAL_NAME
from weft_retrieve.graded import GradedRetrieval, GradedRetrievalConfig
from weft_retrieve.hybrid import NAME as HYBRID_NAME
from weft_retrieve.hybrid import Hybrid, HybridConfig
from weft_retrieve.iterative import NAME as ITERATIVE_RETRIEVAL_NAME
from weft_retrieve.iterative import (
    IterativeRetrieval,
    IterativeRetrievalConfig,
    IterativeRetrievalTrace,
    LoopState,
    StopReason,
    stop_reason,
)
from weft_retrieve.multi_arm import NAME as MULTI_ARM_NAME
from weft_retrieve.multi_arm import MultiArm
from weft_retrieve.no_retrieval import NAME as NO_RETRIEVAL_NAME
from weft_retrieve.no_retrieval import NoRetrieval
from weft_retrieve.payload import (
    Assessment,
    Candidates,
    Channel,
    Passage,
    Passages,
    Query,
    QueryOrigin,
    QuerySet,
    RankedList,
    Ranking,
    Route,
    RouteCandidate,
    RuleOutcome,
    Scorecard,
    Turn,
    TurnRole,
)
from weft_retrieve.prompts import (
    BOOLEAN_PARSE_NAME,
    HYDE_DOCUMENT_NAME,
    MULTI_QUERY_VARIANTS_NAME,
    PASSAGE_RELEVANCE_NAME,
    RELEVANCE_GRADE_NAME,
    ROUTE_QUERY_NAME,
    STANDALONE_QUESTION_NAME,
    STEP_BACK_QUESTION_NAME,
    SUFFICIENCY_CHECK_NAME,
    BooleanParsePrompt,
    BooleanQueryRequest,
    BooleanToken,
    BooleanTokenKind,
    BooleanTokens,
    DimensionScore,
    Grade,
    GradedPassages,
    HydeDocumentPrompt,
    HydeDocumentRequest,
    HydeDocuments,
    MultiQueryVariants,
    MultiQueryVariantsPrompt,
    MultiQueryVariantsRequest,
    PassageGrade,
    PassageGradeRequest,
    PassageJudgement,
    PassageRelevance,
    PassageRelevancePrompt,
    PassageRelevanceRequest,
    RelevanceGradePrompt,
    RouteQueryPrompt,
    RouteQueryRequest,
    RouteQueryScores,
    SeedVariants,
    StandaloneQuestion,
    StandaloneQuestionPrompt,
    StandaloneQuestionRequest,
    StepBackPrompt,
    StepBackQuestion,
    StepBackRequest,
    SufficiencyCheckPrompt,
    SufficiencyCheckRequest,
    SufficiencyJudgement,
)
from weft_retrieve.repack import NAME as REPACK_NAME
from weft_retrieve.repack import Repack, RepackConfig, RepackMethod
from weft_retrieve.rerank import NAME as LLM_RERANK_NAME
from weft_retrieve.rerank import LlmRerank, LlmRerankConfig
from weft_retrieve.routing import (
    ALWAYS_NAME,
    NEAREST_DESCRIPTION_NAME,
    QUERY_SCORER_NAME,
    THRESHOLD_LADDER_NAME,
    Always,
    AlwaysConfig,
    Comparison,
    Condition,
    Dimension,
    LlmQueryScorer,
    NearestDescription,
    NearestDescriptionConfig,
    QueryScorerConfig,
    Rule,
    ThresholdLadder,
    ThresholdLadderConfig,
)
from weft_retrieve.sufficiency import (
    DEFAULT_HEDGE_MARKERS,
    HEDGE_PHRASES_NAME,
    LLM_SUFFICIENCY_NAME,
    HedgePhrases,
    HedgePhrasesConfig,
    LlmSufficiency,
    LlmSufficiencyConfig,
)
from weft_retrieve.transforms import (
    HYDE_NAME,
    MULTI_QUERY_NAME,
    STEP_BACK_NAME,
    ContextualQueryRewrite,
    ContextualQueryRewriteConfig,
    ExpansionKind,
    Hyde,
    HydeConfig,
    MultiQuery,
    MultiQueryConfig,
    StepBack,
    StepBackConfig,
)
from weft_retrieve.transforms import NAME as CONTEXTUAL_QUERY_REWRITE_NAME
from weft_retrieve.vector_top_k import NAME as VECTOR_TOP_K_NAME
from weft_retrieve.vector_top_k import VectorTopK


class Settings(BaseModel):
    """`weft-retrieve` takes no pack settings — an empty model is still the required shape."""

    model_config = ConfigDict(frozen=True, extra="forbid")


def register(registrar: PackRegistrar, settings: Settings) -> None:
    """Register every query-path plugin this pack ships so far, and the prompts they ask.

    Six contracts, one call, no ordering between them: `Fuser`, `Reranker` and
    `ContextPacker` are registered side by side rather than as a fused-reranked-packed
    unit, which is task 2.7's whole point —
    what runs, in what order, and how many times is a pipeline document's business, and this
    function only says which names exist. `QueryTransform` joins the same way at task 2.15:
    registering `contextual-query-rewrite` here says nothing about whether any document ever
    names it, which is the composable-and-omittable property task 2.15's own ledger line is
    about. `hyde` (task 2.16) registers into the same `QueryTransform` position beside it —
    two names under one contract is exactly what makes `hyde` insertable ahead of
    `contextual-query-rewrite`, or omitted entirely, by a document edit that changes nothing
    about either plugin. `multi-query` (task 2.18a) is a fourth `QueryTransform`, and
    `reciprocal-rank-fusion` (task 2.18b) is a second `Fuser` beside `single-list` — swapping
    `fuse:`'s `use:` line from one to the other, with no other edit, is what makes ledger
    2.18's own claim ("the fuser serves hybrid retrieval and fan-out from one implementation")
    a document-level fact rather than a sentence in a docstring. `iterative-retrieval`
    (task 2.20) is a second `Retriever` beside `vector-top-k` and `no-retrieval` — registering
    it here says nothing about which name a document's `retrieve:` position uses, the same
    contract-scoped choice every other position in this function already makes.
    `graded-retrieval` (task 2.21a) is a second `Reranker` beside `llm-rerank`, and
    `corrective` (task 2.21b) is a third `Retriever` — registered exactly like every other
    entry here, with no privileged path for the plugin whose own condition (`10` §1.1) is
    about what it resolves at run time, not about how it is registered. `boolean-retrieval`
    (task 2.23a) is a fifth `QueryTransform` and `boolean-combine` (task 2.23b) is a third
    `Fuser` beside `single-list` and `reciprocal-rank-fusion` — registering both here says
    nothing about the `requires`/`provides` ordering `weft_kernel.runner.Runner.resolve`
    checks once a document actually names them both, which is what lets that check refuse a
    `boolean-combine` with no `boolean-retrieval` upstream before either plugin runs.
    `llm-sufficiency` and `hedge-phrases` (task 2.24) are the first two names registered
    under `Sufficiency` — a contract with no `Stage` base and therefore no pipeline position
    of its own (`weft_retrieve.contract.Sufficiency`'s own docstring), reached only through
    `StageLookup.build_capability` by `iterative-retrieval`'s `sufficiency` field and
    `weft_generate.refine.RefineOnUncertainty`'s `signal` field. Registering two names under
    it here is what makes swapping one for the other a `with:` edit in whichever plugin
    resolves it, never a change to this file.

    `query-scorer` and `threshold-ladder` / `nearest-description` / `always` (task 2.25) are
    the first names registered under `QueryScorer` and `RoutingPolicy` — two contracts so a
    threshold ladder can be replaced by a trained classifier without touching the scorer
    (`weft_retrieve.routing`'s own module docstring). Registering three names under
    `RoutingPolicy` here says nothing about which one a `route.yaml` document's `decide:`
    stage names; that choice is the whole of the operator's own consent, exactly the same
    contract-scoped shape every other position in this function already takes.

    `collapse-to-parent` (task 2.33) is a third `Reranker` beside `llm-rerank` and
    `graded-retrieval`, registered here exactly like every other position in this function —
    the module's own reasoning for reusing `Reranker`'s existing slot rather than growing a
    fifth query-path contract is on `weft_retrieve.collapse`, not repeated in this function.

    Every `Prompt` goes through the same `registrar` as everything else. `weft-prompts`
    publishes that contract and registers nothing under it (its own `pyproject.toml` declares
    no `weft.packs` entry point), because a first-party prompt belongs to the pack whose
    plugin asks the question — so an operator can pin their own wording over
    `passage-relevance`, `standalone-question`, `hyde-document`, `multi-query-variants`,
    `relevance-grade`, `boolean-parse`, `sufficiency-check` or `route-query` in `[plugins]`
    exactly as they would pin a retriever.

    **`BooleanPlan`, `CorrectiveTrace` and `IterativeRetrievalTrace` are deliberately not
    passed to `registrar.add_ext_model` — task 5.2g's own finding, not an oversight.**
    They attach to `QuerySet.ext`/`Candidates.ext`, never to `Node.ext`, and only a `Node`
    is ever handed to a `NodeStore` — `weft_store.rehydrate.rehydrate_ext` reconstructs a
    *node's* `ext` map and is never called with a query-path payload's. Registering all
    three would not merely be pointless, it would break every real run the moment two of
    them are active together: all three declare `__namespace__ = "weft-retrieve"` (one
    namespace, three carriers, none of them a `Node`), so `weft_store.rehydrate.
    ext_models` — one class per namespace, globally, by design — would raise
    `DuplicateRegistrationError` on the second registration. `docs/lessons.md` L5.20
    records this as the reason `weft_kernel.discovery.PackRegistrar.add_ext_model` is for
    an `ExtModel` that reaches a `Node`, not for every `ExtModel` a pack happens to own.
    """
    del settings
    registrar.add(Retriever, NO_RETRIEVAL_NAME, NoRetrieval)
    registrar.add(Retriever, VECTOR_TOP_K_NAME, VectorTopK)
    registrar.add(Retriever, MULTI_ARM_NAME, MultiArm)
    registrar.add(Retriever, HYBRID_NAME, Hybrid)
    registrar.add(Retriever, ITERATIVE_RETRIEVAL_NAME, IterativeRetrieval)
    registrar.add(Retriever, CORRECTIVE_NAME, Corrective)
    registrar.add(Fuser, SINGLE_LIST_NAME, SingleList)
    registrar.add(Fuser, RRF_NAME, ReciprocalRankFusion)
    registrar.add(Fuser, BOOLEAN_COMBINE_NAME, BooleanCombine)
    registrar.add(Reranker, LLM_RERANK_NAME, LlmRerank)
    registrar.add(Reranker, GRADED_RETRIEVAL_NAME, GradedRetrieval)
    registrar.add(Reranker, COLLAPSE_TO_PARENT_NAME, CollapseToParent)
    registrar.add(Sufficiency, LLM_SUFFICIENCY_NAME, LlmSufficiency)
    registrar.add(Sufficiency, HEDGE_PHRASES_NAME, HedgePhrases)
    registrar.add(ContextPacker, REPACK_NAME, Repack)
    registrar.add(QueryTransform, CONTEXTUAL_QUERY_REWRITE_NAME, ContextualQueryRewrite)
    registrar.add(QueryTransform, HYDE_NAME, Hyde)
    registrar.add(QueryTransform, STEP_BACK_NAME, StepBack)
    registrar.add(QueryTransform, MULTI_QUERY_NAME, MultiQuery)
    registrar.add(QueryTransform, BOOLEAN_RETRIEVAL_NAME, BooleanRetrieval)
    registrar.add(Prompt, PASSAGE_RELEVANCE_NAME, PassageRelevancePrompt)
    registrar.add(Prompt, STANDALONE_QUESTION_NAME, StandaloneQuestionPrompt)
    registrar.add(Prompt, HYDE_DOCUMENT_NAME, HydeDocumentPrompt)
    registrar.add(Prompt, STEP_BACK_QUESTION_NAME, StepBackPrompt)
    registrar.add(Prompt, MULTI_QUERY_VARIANTS_NAME, MultiQueryVariantsPrompt)
    registrar.add(Prompt, RELEVANCE_GRADE_NAME, RelevanceGradePrompt)
    registrar.add(Prompt, BOOLEAN_PARSE_NAME, BooleanParsePrompt)
    registrar.add(Prompt, SUFFICIENCY_CHECK_NAME, SufficiencyCheckPrompt)
    registrar.add(QueryScorer, QUERY_SCORER_NAME, LlmQueryScorer)
    registrar.add(RoutingPolicy, THRESHOLD_LADDER_NAME, ThresholdLadder)
    registrar.add(RoutingPolicy, NEAREST_DESCRIPTION_NAME, NearestDescription)
    registrar.add(RoutingPolicy, ALWAYS_NAME, Always)
    registrar.add(Prompt, ROUTE_QUERY_NAME, RouteQueryPrompt)
    # Task 2.8: every pipeline this pack ships from inside its own installed package,
    # so `weft_cli.pipeline_catalogue.load_contributed` sees it from a real install —
    # `weft_retrieve.contract.RouteCatalogue`'s own docstring, "populated by the same
    # eager discovery pass that builds the registry." `route.yaml` carries no
    # `route.summary` of its own — it is the router, never a routing target.
    registrar.add_pipeline_resource("weft_retrieve", "pipelines/route.yaml")
    registrar.add_pipeline_resource("weft_retrieve", "pipelines/no-retrieval.yaml")
    registrar.add_pipeline_resource("weft_retrieve", "pipelines/retrieve-then-generate.yaml")
    # The first shipped document that searches **two bases at once** — the leaf chunks and the
    # RAPTOR summaries built over them — as one `vector-top-k` twice, narrowed by `filter` and
    # named apart by `arm`, then combined by `reciprocal-rank-fusion`. It ships because the
    # ladder from naive to advanced is the product: the engine could already express this and
    # no document did, so nobody arriving at Weft could see that it could.
    registrar.add_pipeline_resource("weft_retrieve", "pipelines/raptor-and-leaves-rrf.yaml")

    # **Phase 8 — the ladder.** Everything below this line is the same one-line contribution
    # every document above it makes, and that is the whole of the Python this phase needed: a
    # pipeline is data, so a rung is a file and a call, never a branch. Fitness function 16 is
    # what keeps the list honest from here — a plugin registered into a pipeline position that
    # no document below names fails the gate, so the next capability this pack registers arrives
    # with the rung that lets somebody run it, or with the fact that says why it cannot have one.
    #
    # **Eleven query rungs, each a derivation.** Every one carries `extends:
    # retrieve-then-generate` and one or two operator blocks, which is requirement 3 stated in
    # the shipped set rather than merely available in the model: before this phase, `extends`
    # was exercised by tests and by `manual/`'s worked example and by nothing a user could run.
    # Each restates its own `route.summary` and `route.cost` — `weft_retrieve.engine`'s own
    # docstring records that a derived document inherits its parent's `vars`, so a rung that
    # named none would advertise itself to `nearest-description` in its parent's words.
    registrar.add_pipeline_resource("weft_retrieve", "pipelines/rewrite-then-retrieve.yaml")
    registrar.add_pipeline_resource("weft_retrieve", "pipelines/hyde-then-retrieve.yaml")
    registrar.add_pipeline_resource("weft_retrieve", "pipelines/step-back-then-retrieve.yaml")
    registrar.add_pipeline_resource("weft_retrieve", "pipelines/multi-query-then-retrieve.yaml")
    registrar.add_pipeline_resource("weft_retrieve", "pipelines/boolean-then-retrieve.yaml")
    registrar.add_pipeline_resource("weft_retrieve", "pipelines/rerank-then-generate.yaml")
    registrar.add_pipeline_resource("weft_retrieve", "pipelines/grade-then-generate.yaml")
    registrar.add_pipeline_resource("weft_retrieve", "pipelines/iterative-retrieve.yaml")
    registrar.add_pipeline_resource("weft_retrieve", "pipelines/corrective-retrieve.yaml")
    registrar.add_pipeline_resource("weft_retrieve", "pipelines/contradiction-aware.yaml")
    registrar.add_pipeline_resource("weft_retrieve", "pipelines/draft-then-refine.yaml")
    # Task 8.6. `replace` swaps the retriever and `set` retunes the fuser it feeds — the one
    # rung whose delta changes *what is searched* rather than how the question is asked or what
    # becomes of the answer, and the reason `single-list` cannot stay: two arms are two lists.
    registrar.add_pipeline_resource("weft_retrieve", "pipelines/hybrid-then-generate.yaml")

    # **Six ingest rungs, and they are contributed from this pack rather than from `weft-index`
    # or `weft-clean` for one reason: a document has to name every plugin it places, and these
    # place plugins from five distributions' worth of packs at once** — `weft_extract`'s `text`,
    # `weft_clean`'s cleaners, `weft_chunk`'s `fixed-size`, `weft_index`'s expanders,
    # `weft_enhance`'s `keybert`, `weft_embed`'s `hash` and `weft_store`'s `pgvector`. They all
    # ship inside `weft-rag`, so any of those packs could hold the file; this one holds it
    # because this is where the query ladder already lives and a ladder split across two
    # `register()` functions is a ladder nobody can read end to end.
    #
    # **They carry no `route.summary` and must not.** An ingest document produces nodes, not an
    # `Answer`; `PipelineRouteCatalogue` reads `route.summary` to build the router's candidate
    # set, so an ingest rung that advertised one would be selectable by `weft ask` and would
    # fail `weft_cli.route_ask._require` at the end of a run it should never have started.
    registrar.add_pipeline_resource("weft_retrieve", "pipelines/index-text.yaml")
    registrar.add_pipeline_resource("weft_retrieve", "pipelines/index-messy-text.yaml")
    registrar.add_pipeline_resource("weft_retrieve", "pipelines/index-polish.yaml")
    registrar.add_pipeline_resource("weft_retrieve", "pipelines/index-with-keywords.yaml")
    registrar.add_pipeline_resource("weft_retrieve", "pipelines/index-with-questions.yaml")
    registrar.add_pipeline_resource("weft_retrieve", "pipelines/index-with-raptor.yaml")

    # **Two alternative routers, contributed because task 8.3 made a second one selectable.**
    # `weft ask` used to run the document named `route` and no other, because
    # `weft_cli.route_ask` held that name as a constant — so `threshold-ladder` and `always`
    # were registered, listed and documented in `10` §1.5 while being placeable by nobody. Both
    # of these carry no `route.summary`, exactly as `route.yaml` does not: a router selects
    # among routing targets and is never one itself.
    # Task 8.9. Two documents ending in a `Renderer` — the contract's first shipped placements,
    # and what `weft render` drives. `plain` and `markdown` were registered at task 2.27 and
    # placeable by nobody until now, which is why fitness function 16 waived them.
    registrar.add_pipeline_resource("weft_retrieve", "pipelines/preview-plain.yaml")
    registrar.add_pipeline_resource("weft_retrieve", "pipelines/preview-markdown.yaml")
    registrar.add_pipeline_resource("weft_retrieve", "pipelines/route-by-score.yaml")
    registrar.add_pipeline_resource("weft_retrieve", "pipelines/route-fixed.yaml")


__all__ = [
    "ALWAYS_NAME",
    "BOOLEAN_COMBINE_NAME",
    "HYBRID_NAME",
    "Hybrid",
    "HybridConfig",
    "MULTI_ARM_NAME",
    "MultiArm",
    "BOOLEAN_PARSE_NAME",
    "BOOLEAN_RETRIEVAL_NAME",
    "COLLAPSE_TO_PARENT_NAME",
    "CONTEXTUAL_QUERY_REWRITE_NAME",
    "CORRECTIVE_NAME",
    "GRADED_RETRIEVAL_NAME",
    "HEDGE_PHRASES_NAME",
    "HYDE_DOCUMENT_NAME",
    "HYDE_NAME",
    "ITERATIVE_RETRIEVAL_NAME",
    "LLM_RERANK_NAME",
    "LLM_SUFFICIENCY_NAME",
    "MULTI_QUERY_NAME",
    "MULTI_QUERY_VARIANTS_NAME",
    "NEAREST_DESCRIPTION_NAME",
    "NO_RETRIEVAL_NAME",
    "PASSAGE_RELEVANCE_NAME",
    "QUERY_SCORER_NAME",
    "RELEVANCE_GRADE_NAME",
    "REPACK_NAME",
    "RETRIEVE_CONTRACT_VERSION",
    "ROUTE_QUERY_NAME",
    "RRF_NAME",
    "SINGLE_LIST_NAME",
    "STANDALONE_QUESTION_NAME",
    "STEP_BACK_NAME",
    "STEP_BACK_QUESTION_NAME",
    "SUFFICIENCY_CHECK_NAME",
    "THRESHOLD_LADDER_NAME",
    "VECTOR_TOP_K_NAME",
    "Always",
    "AlwaysConfig",
    "Assessment",
    "BoolExpr",
    "BoolOp",
    "BooleanCombine",
    "BooleanCombineConfig",
    "BooleanParsePrompt",
    "BooleanPlan",
    "BooleanQueryRequest",
    "BooleanRetrieval",
    "BooleanRetrievalConfig",
    "BooleanToken",
    "BooleanTokenKind",
    "BooleanTokens",
    "Candidates",
    "Channel",
    "CollapsePolicy",
    "CollapseToParent",
    "CollapseToParentConfig",
    "Comparison",
    "Condition",
    "ContextPacker",
    "ContextualQueryRewrite",
    "ContextualQueryRewriteConfig",
    "Corrective",
    "CorrectiveConfig",
    "CorrectiveTrace",
    "DEFAULT_HEDGE_MARKERS",
    "Dimension",
    "DimensionScore",
    "EmptyConjunction",
    "ExpansionKind",
    "Fuser",
    "Grade",
    "GradedPassages",
    "GradedRetrieval",
    "GradedRetrievalConfig",
    "HedgePhrases",
    "HedgePhrasesConfig",
    "Hyde",
    "HydeConfig",
    "HydeDocumentPrompt",
    "HydeDocumentRequest",
    "HydeDocuments",
    "IterativeRetrieval",
    "IterativeRetrievalConfig",
    "IterativeRetrievalTrace",
    "LlmQueryScorer",
    "LlmRerank",
    "LlmRerankConfig",
    "LlmSufficiency",
    "LlmSufficiencyConfig",
    "LoopState",
    "MultiQuery",
    "MultiQueryConfig",
    "MultiQueryVariants",
    "MultiQueryVariantsPrompt",
    "MultiQueryVariantsRequest",
    "NearestDescription",
    "NearestDescriptionConfig",
    "NoRetrieval",
    "Passage",
    "PassageGrade",
    "PassageGradeRequest",
    "PassageJudgement",
    "PassageRelevance",
    "PassageRelevancePrompt",
    "PassageRelevanceRequest",
    "Passages",
    "Query",
    "QueryOrigin",
    "QueryScorer",
    "QueryScorerConfig",
    "QuerySet",
    "QueryTransform",
    "RankedList",
    "Ranking",
    "ReciprocalRankFusion",
    "ReciprocalRankFusionConfig",
    "RelevanceGradePrompt",
    "Repack",
    "RepackConfig",
    "RepackMethod",
    "Reranker",
    "Retriever",
    "Route",
    "RouteCandidate",
    "RouteCatalogue",
    "RouteQueryPrompt",
    "RouteQueryRequest",
    "RouteQueryScores",
    "RoutingPolicy",
    "Rule",
    "RuleOutcome",
    "Scorecard",
    "SeedVariants",
    "Settings",
    "SingleList",
    "StageLookup",
    "StandaloneQuestion",
    "StandaloneQuestionPrompt",
    "StandaloneQuestionRequest",
    "StepBack",
    "StepBackConfig",
    "StepBackPrompt",
    "StepBackQuestion",
    "StepBackRequest",
    "StopReason",
    "Sufficiency",
    "SufficiencyCheckPrompt",
    "SufficiencyCheckRequest",
    "SufficiencyJudgement",
    "ThresholdLadder",
    "ThresholdLadderConfig",
    "Turn",
    "TurnRole",
    "VectorTopK",
    "contributor_label",
    "register",
    "stop_reason",
]
