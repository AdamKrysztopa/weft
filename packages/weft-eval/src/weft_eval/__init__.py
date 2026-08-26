"""First-party evaluation pack.

Publishes the `RetrievalMetric`/`GenerationMetric` contracts, in `contract.py` — task 4.2's own
split of task 4.1's single `Metric`/`Sample`, argued in `contract.py`'s own module docstring — and
ships every one of the 21 metrics `docs/build-ledger.md` task 4.2 owns: 4 IR (`ir_metrics.py`), 11
traditional generation (`lexical.py`, `qa_metrics.py`, `embedding_metrics.py`) and 6 LLM judges
(`judges.py`, asking the 6 prompts `prompts.py` registers under `weft_prompts.contract.Prompt`).
`aggregate.py` (task 4.3) folds many per-sample `Outcome[MetricScore]` observations from any one
of these into a `MetricAggregate` — exclusion counts, dispersion, and a reported-name check run
against the name a report key actually publishes, not just a metric's own `metric_name` property;
see that module's own docstring for the full argument. `run_record.py` (task 4.4) persists a run —
its resolved pipeline, corpus identity, model versions and active distribution set — as a file, so
two runs can be diffed after the fact; see that module's own docstring for Q1 and how fitness
function 8(c) is checked. `offline.py` and `pricing.py` (task 4.7) answer V5: which registered
metrics run in the gate with no credentials and no network (Q6, settled in `contract.py`'s own
module docstring), and what one run costs in money, a per-model rate table shipped as data rather
than a closed key space. Neither `aggregate.py`, `run_record.py`, `offline.py` nor `pricing.py`
is a registered capability of its own — nothing under this file's `register()` call publishes any
of them — because folding observations into a report, folding a run's own facts into a record,
reading which metrics are gate-safe, and pricing a set of calls are not themselves plugin points
any pack or third party needs to swap.

**No unregistered category, no dummy, no silent skip.** The reference's own five defects
(`docs/04-reference-inventory.md`'s metric-suite correction block) are fixed by this file's own shape
rather than patched afterwards: every metric this pack ships is registered in the one `register()`
call below, so there is no second import path a caller could miss the way the reference's two
docstring-only `llm_judge/__init__.py` files silently dropped all six judges
(`.phase4-reference-recon.md` §1). Nothing here is a test double — a stranger's own metric lives
entirely outside this pack, never in this pack's own `register()`. And an unknown name asked of
the registry raises `weft_kernel.registry.UnknownPluginError`, naming every registered
alternative — the same mechanism task 4.1 already proved for `Metric`, now proving it again for
`RetrievalMetric`/`GenerationMetric`.
"""

from pydantic import BaseModel, ConfigDict

from weft_eval.aggregate import (
    MetricAggregate,
    MismatchedMetricNameError,
    ReportedNameMismatchError,
    aggregate,
    aggregate_report,
)
from weft_eval.at_threshold import AtThresholdConfig, OverlapAtThreshold
from weft_eval.contract import (
    GENERATION_METRIC_CONTRACT_VERSION,
    RETRIEVAL_METRIC_CONTRACT_VERSION,
    GenerationMetric,
    GenerationSample,
    MetricScore,
    RetrievalMetric,
    RetrievalSample,
    RetrievedPassage,
)
from weft_eval.embedding_metrics import BERT_SCORE_AVAILABLE, BERTScore, EmbeddingSimilarity
from weft_eval.harness import score_retrieval_gate_subset
from weft_eval.ir_metrics import MeanAveragePrecision, NDCGAtK, PrecisionAtK, RecallAtK
from weft_eval.judges import (
    AnswerCompleteness,
    AnswerCorrectness,
    AnswerRelevance,
    ContextRecall,
    ContextRelevance,
    Faithfulness,
)
from weft_eval.lexical import KeyTermsPrecision, Rouge1, Rouge2, RougeL, TokenOverlap, TokenRecall
from weft_eval.offline import (
    GateSubset,
    MetricNeedsCredentialsError,
    UnknownMetricNameError,
    gate_subset,
    require_gate_safe,
    resolve_metric,
)
from weft_eval.pricing import (
    DEFAULT_RATES,
    RATES_AS_OF,
    PricedCall,
    RunPrice,
    TokenRate,
    price_calls,
)
from weft_eval.prompts import (
    AnswerCompletenessJudgePrompt,
    AnswerCorrectnessJudgePrompt,
    AnswerRelevanceJudgePrompt,
    ContextRecallJudgePrompt,
    ContextRelevanceJudgePrompt,
    FaithfulnessJudgePrompt,
)
from weft_eval.qa_metrics import Accuracy, ExactMatch, F1Score
from weft_eval.run_record import (
    CorpusIdentity,
    MetricRunResult,
    NotAggregated,
    RunRecord,
    active_distribution_set,
    build_run_record,
    corpus_identity,
    load_run_record,
    write_run_record,
)
from weft_kernel.discovery import PackRegistrar
from weft_prompts.contract import Prompt

#: The name `OverlapAtThreshold` is registered and selected under — task 4.1's own demonstration.
OVERLAP_AT_THRESHOLD_NAME = "overlap-at-threshold"

#: The 4 `RetrievalMetric` names — `docs/build-ledger.md` task 4.2.
PRECISION_AT_K_NAME = "precision-at-k"
RECALL_AT_K_NAME = "recall-at-k"
MEAN_AVERAGE_PRECISION_NAME = "mean-average-precision"
NDCG_AT_K_NAME = "ndcg"

#: The 11 traditional `GenerationMetric` names.
ROUGE_L_NAME = "rouge-l"
ROUGE_1_NAME = "rouge-1"
ROUGE_2_NAME = "rouge-2"
TOKENS_OVERLAP_NAME = "token-overlap"
TOKENS_RECALL_NAME = "token-recall"
KEY_TERMS_PRECISION_NAME = "key-terms-precision"
EXACT_MATCH_NAME = "exact-match"
F1_SCORE_NAME = "f1-score"
ACCURACY_NAME = "accuracy"
EMBEDDING_SIMILARITY_NAME = "embedding-similarity"
BERTSCORE_NAME = "bertscore"

#: The 6 LLM-judge names — `docs/10-technique-catalogue.md` §1.3 already settles every one of
#: these; none carries a `ragas_` prefix (`answer-completeness`'s own row: RAGAS has no
#: completeness metric in the paper or the library, so the prefix would be a false claim).
FAITHFULNESS_NAME = "faithfulness"
CONTEXT_RECALL_NAME = "context-recall"
CONTEXT_RELEVANCE_NAME = "context-relevance"
ANSWER_RELEVANCE_NAME = "answer-relevance"
ANSWER_CORRECTNESS_NAME = "answer-correctness"
ANSWER_COMPLETENESS_NAME = "answer-completeness"


class Settings(BaseModel):
    """`weft-eval` takes no pack settings — an empty model is still the required shape."""

    model_config = ConfigDict(frozen=True, extra="forbid")


def register(registrar: PackRegistrar, settings: Settings) -> None:
    """Register every metric and judge prompt this pack ships — one call, no privileged path.

    `RetrievalMetric`, `GenerationMetric` and `Prompt` are three different contracts; nothing
    about registering under three rather than one changes how any of them resolves, and a third
    party registering under any of the three uses `registrar.add` identically to this call.
    """
    del settings

    registrar.add(GenerationMetric, OVERLAP_AT_THRESHOLD_NAME, OverlapAtThreshold)

    registrar.add(RetrievalMetric, PRECISION_AT_K_NAME, PrecisionAtK)
    registrar.add(RetrievalMetric, RECALL_AT_K_NAME, RecallAtK)
    registrar.add(RetrievalMetric, MEAN_AVERAGE_PRECISION_NAME, MeanAveragePrecision)
    registrar.add(RetrievalMetric, NDCG_AT_K_NAME, NDCGAtK)

    registrar.add(GenerationMetric, ROUGE_L_NAME, RougeL)
    registrar.add(GenerationMetric, ROUGE_1_NAME, Rouge1)
    registrar.add(GenerationMetric, ROUGE_2_NAME, Rouge2)
    registrar.add(GenerationMetric, TOKENS_OVERLAP_NAME, TokenOverlap)
    registrar.add(GenerationMetric, TOKENS_RECALL_NAME, TokenRecall)
    registrar.add(GenerationMetric, KEY_TERMS_PRECISION_NAME, KeyTermsPrecision)
    registrar.add(GenerationMetric, EXACT_MATCH_NAME, ExactMatch)
    registrar.add(GenerationMetric, F1_SCORE_NAME, F1Score)
    registrar.add(GenerationMetric, ACCURACY_NAME, Accuracy)
    registrar.add(GenerationMetric, EMBEDDING_SIMILARITY_NAME, EmbeddingSimilarity)
    registrar.add(GenerationMetric, BERTSCORE_NAME, BERTScore)
    if not BERT_SCORE_AVAILABLE:
        # Ledger task **6.29**, and fitness function 5's second half: "a plugin must declare it
        # unavailable and say why", **at discovery time**. `bertscore` needs the optional
        # `bert-score` extra; without it this metric answers `Failed` when it is *run*, which is
        # saying why one moment too late — an operator running `weft plugins doctor` learned
        # nothing and found out when a scoring run failed. It stays registered on purpose, so
        # `weft eval` still refuses it by name with a reason rather than reporting it as an
        # unknown metric, and the pack now reports `PARTIAL` with this notice beside it.
        registrar.unavailable(
            BERTSCORE_NAME,
            reason=(
                "needs the optional 'bert_score' package, which is not installed. Install "
                "weft-eval's 'bertscore' extra to run this metric."
            ),
        )

    registrar.add(GenerationMetric, FAITHFULNESS_NAME, Faithfulness)
    registrar.add(RetrievalMetric, CONTEXT_RECALL_NAME, ContextRecall)
    registrar.add(RetrievalMetric, CONTEXT_RELEVANCE_NAME, ContextRelevance)
    registrar.add(GenerationMetric, ANSWER_RELEVANCE_NAME, AnswerRelevance)
    registrar.add(GenerationMetric, ANSWER_CORRECTNESS_NAME, AnswerCorrectness)
    registrar.add(GenerationMetric, ANSWER_COMPLETENESS_NAME, AnswerCompleteness)

    registrar.add(Prompt, FaithfulnessJudgePrompt.name, FaithfulnessJudgePrompt)
    registrar.add(Prompt, ContextRecallJudgePrompt.name, ContextRecallJudgePrompt)
    registrar.add(Prompt, ContextRelevanceJudgePrompt.name, ContextRelevanceJudgePrompt)
    registrar.add(Prompt, AnswerRelevanceJudgePrompt.name, AnswerRelevanceJudgePrompt)
    registrar.add(Prompt, AnswerCorrectnessJudgePrompt.name, AnswerCorrectnessJudgePrompt)
    registrar.add(Prompt, AnswerCompletenessJudgePrompt.name, AnswerCompletenessJudgePrompt)


__all__ = [
    "ACCURACY_NAME",
    "ANSWER_COMPLETENESS_NAME",
    "ANSWER_CORRECTNESS_NAME",
    "ANSWER_RELEVANCE_NAME",
    "BERTSCORE_NAME",
    "CONTEXT_RECALL_NAME",
    "CONTEXT_RELEVANCE_NAME",
    "DEFAULT_RATES",
    "EMBEDDING_SIMILARITY_NAME",
    "EXACT_MATCH_NAME",
    "FAITHFULNESS_NAME",
    "F1_SCORE_NAME",
    "GENERATION_METRIC_CONTRACT_VERSION",
    "KEY_TERMS_PRECISION_NAME",
    "MEAN_AVERAGE_PRECISION_NAME",
    "NDCG_AT_K_NAME",
    "OVERLAP_AT_THRESHOLD_NAME",
    "PRECISION_AT_K_NAME",
    "RATES_AS_OF",
    "RECALL_AT_K_NAME",
    "RETRIEVAL_METRIC_CONTRACT_VERSION",
    "ROUGE_1_NAME",
    "ROUGE_2_NAME",
    "ROUGE_L_NAME",
    "TOKENS_OVERLAP_NAME",
    "TOKENS_RECALL_NAME",
    "Accuracy",
    "AnswerCompleteness",
    "AnswerCorrectness",
    "AnswerRelevance",
    "AtThresholdConfig",
    "BERTScore",
    "ContextRecall",
    "ContextRelevance",
    "CorpusIdentity",
    "EmbeddingSimilarity",
    "ExactMatch",
    "F1Score",
    "Faithfulness",
    "GateSubset",
    "GenerationMetric",
    "GenerationSample",
    "KeyTermsPrecision",
    "MeanAveragePrecision",
    "MetricAggregate",
    "MetricNeedsCredentialsError",
    "MetricRunResult",
    "MetricScore",
    "MismatchedMetricNameError",
    "NDCGAtK",
    "NotAggregated",
    "OverlapAtThreshold",
    "PrecisionAtK",
    "PricedCall",
    "RecallAtK",
    "ReportedNameMismatchError",
    "RetrievalMetric",
    "RetrievalSample",
    "RetrievedPassage",
    "Rouge1",
    "Rouge2",
    "RougeL",
    "RunPrice",
    "RunRecord",
    "Settings",
    "TokenOverlap",
    "TokenRate",
    "TokenRecall",
    "UnknownMetricNameError",
    "active_distribution_set",
    "aggregate",
    "aggregate_report",
    "build_run_record",
    "corpus_identity",
    "gate_subset",
    "load_run_record",
    "price_calls",
    "register",
    "require_gate_safe",
    "resolve_metric",
    "score_retrieval_gate_subset",
    "write_run_record",
]
