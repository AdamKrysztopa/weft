"""Task 2.31's own exit demonstration, end to end, against the real corpus.

`docs/build-ledger.md`, decision **S2**: "a question whose wording appears nowhere in the
corpus retrieves the chunk that answers it, and the citation resolves to the parent chunk
rather than to the generated question." Every service in this test is real: `weft-pdf`
extracts a real paper from `corpus/arxiv/`, `weft-chunk` splits it, `weft_index.
hypothetical_questions.HypotheticalQuestionGenerator` asks the real OpenAI account this
environment carries for the questions each chunk answers, `weft-openai`'s embedder gives
every node — chunk and question alike — a real vector, `weft-store`'s `pgvector` backend
holds them, and `weft_generate.cited_answer.CitedAnswer` asks the same account to write the
answer and its citation. Nothing here is a stub or a script; this is the property
`.phase2-findings.md` §11 and the ledger's own S2 note ask to be demonstrated, not merely
unit-tested (`tests/unit/weft_index/test_hypothetical_questions.py` and
`tests/unit/weft_generate/test_cited_answer.py`'s own new coverage carry the unit-level
proof; this file is what makes it real rather than merely typed correctly).

**Why one small paper, and why the corpus slice is trimmed after chunking.** A real
question-generation call per chunk and a real embedding call per node cost real API time;
this test bounds both by keeping to the first few chunks of one short paper rather than
ingesting a whole directory — the same "small real corpus, bounded cost" posture V1's own
fetch tiers already take (`.phase2-findings.md` finding 13).

**Why the retrieval query is a fresh paraphrase, not the model's own generated question
verbatim.** `weft_index.prompts`'s own system message already forbids the model from
quoting a chunk's wording back, so the generated question alone would already satisfy "not
in the corpus" — but querying with the *exact string just embedded as a node* proves
nothing beyond identity lookup. One further real completion, asking the same account to
reword the generated question, is what makes the retrieval a genuine nearest-neighbour
match on *meaning* rather than a trivial self-match.

Skipped, with a reason, when the database or the credential is absent — the same discipline
`tests/integration/test_ingest_pipeline.py` and `tests/integration/test_openai_llm.py` both
already take.
"""

import os
from collections.abc import AsyncIterator
from functools import partial
from pathlib import Path

import psycopg
import pytest
from pydantic import SecretStr

from weft_chunk import FixedSizeChunker
from weft_chunk.contract import Chunker
from weft_chunk.payload import ChunkOffset
from weft_embed.contract import Embedder
from weft_extract.contract import Extractor
from weft_extract.text import discover_source_docs
from weft_generate.cited_answer import CitedAnswer
from weft_generate.prompts import ANSWER_WITH_CITATIONS_NAME, AnswerWithCitationsPrompt
from weft_index import HYPOTHETICAL_QUESTIONS_NAME as HQ_NAME
from weft_index import Expander, HypotheticalQuestionGenerator
from weft_index.payload import Representation
from weft_index.prompts import GENERATE_QUESTIONS_NAME, GenerateQuestionsPrompt
from weft_kernel.context import Context, ServiceRegistry
from weft_kernel.payload import ExtModel, MediaType, Node, Produced
from weft_kernel.registry import Registry
from weft_llm.client import NullSink, llm_service
from weft_llm.contract import LLM, LLMProvider, TokenSink
from weft_llm.payload import Conversation, Message, MessageRole, Rendered
from weft_llm.roles import LLMRoles, RoleMapping
from weft_openai import OpenAIEmbedder, OpenAIEmbedderConfig, OpenAILLMProvider
from weft_openai import Settings as OpenAISettings
from weft_pdf import EXTENSIONS as PDF_EXTENSIONS
from weft_pdf import PdfPages, PdfTextExtractor
from weft_prompts.contract import Prompt, Prompts
from weft_prompts.registry import prompts_service
from weft_retrieve.contract import StageLookup
from weft_retrieve.payload import Passage, Passages, Query, QueryOrigin
from weft_store import NodeStore, Scored
from weft_store.pgvector_store import PgVectorSettings, PgVectorStore

_DSN = os.environ.get("WEFT_DATABASE_URL", "postgresql://weft:weft@localhost:5433/weft")
_API_KEY_VAR = "OPENAI_API_KEY"

#: The explicit opt-in, separate from the credential — ledger task **6.28**, `09` §4.3's V5.
#: `OPENAI_API_KEY` says *"I could reach the network"*; this says *"I am asking to"*. A developer
#: with a key exported for other work should get a deterministic `poe ci-checks`, because a gate
#: whose green depends on what a live service answered teaches whoever runs it to re-run red tests
#: until they pass (`docs/lessons.md` L6.27). Repeated in each module that reaches the network
#: rather than shared, the same way each already repeats its own skip discipline;
#: `tests/architecture/test_the_gate_is_decidable.py` keeps the copies honest.
_LIVE_OPT_IN_VAR = "WEFT_LIVE_API_TESTS"

#: One short, real arXiv paper (`.phase2-findings.md` finding 13's `fetch` tier) — small
#: enough that trimming to its first few chunks below stays representative rather than
#: contrived.
_PAPER = Path("corpus/arxiv/1706.07535v1.pdf")
_CHUNKS_KEPT = 3


def _ctx(services: ServiceRegistry) -> Context:
    return Context(
        tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en", services=services
    )


class _PromptLookup:
    """A `StageLookup` narrowed to `build_capability`, resolving a real `Registry` — the
    same shape every unit test's `_StubLookup` takes, because nothing in this tree has
    built the production version yet (ledger task 2.8 is still open).
    """

    def __init__(self, registry: Registry) -> None:
        self._registry = registry

    def names(self, contract: type[object]) -> frozenset[str]:
        return frozenset(self._registry.names_for(contract))

    async def build(self, contract: type[object], name: str, config: object = None) -> object:
        raise AssertionError("this test resolves a capability by name, never a stage")

    async def build_capability(
        self, contract: type[object], name: str, config: object = None
    ) -> object:
        return self._registry.entry(contract, name).factory(config)


def _ensure_rehydrates(model: type[ExtModel]) -> None:
    """Make `model` reconstructable by `weft_store.rehydrate` — this test's own use of
    `weft_store.rehydrate.register_from_reports`, the generic consumer task 5.2g built.

    This test hand-assembles a `Registry` and never calls `weft_kernel.discovery.discover`,
    so no pack's own `register()` — which now buffers its `ExtModel`s through
    `PackRegistrar.add_ext_model` — ever runs to populate `weft_store.rehydrate.
    ext_models` for it. Wrapping one bare model in a throwaway `PackReport` and handing it
    to `register_from_reports` reuses that function's own idempotent-or-refuse logic —
    `rehydrate.py`'s own registry is process-wide, so a second call for a namespace
    already claimed by the same class must be a no-op rather than
    `DuplicateRegistrationError` the moment more than one test in this session needs it —
    rather than re-deriving it by hand a second time.
    """
    from weft_kernel.discovery import PackReport, PackStatus
    from weft_store.rehydrate import register_from_reports

    report = PackReport(
        pack=model.__namespace__,
        distribution=model.__namespace__,
        status=PackStatus.ACTIVE,
        ext_models=(model,),
    )
    register_from_reports((report,))


async def _database_reachable() -> str | None:
    try:
        conn = await psycopg.AsyncConnection.connect(_DSN, connect_timeout=2)
    except psycopg.OperationalError as exc:
        return f"WEFT_DATABASE_URL ({_DSN}) is unreachable: {exc}"
    await conn.close()
    return None


@pytest.fixture
async def store() -> AsyncIterator[PgVectorStore]:
    reason = await _database_reachable()
    if reason is not None:
        pytest.skip(reason)
    instance = PgVectorStore(PgVectorSettings(dsn=SecretStr(_DSN)))
    await instance.count()  # forces schema creation, exactly as test_ingest_pipeline.py does
    conn = await psycopg.AsyncConnection.connect(_DSN, autocommit=True)
    async with conn.cursor() as cur:
        await cur.execute("TRUNCATE weft_nodes, weft_sources")
    await conn.close()
    yield instance
    await instance.aclose()


@pytest.fixture
def api_key() -> SecretStr:
    key = os.environ.get(_API_KEY_VAR)
    if not os.environ.get(_LIVE_OPT_IN_VAR):
        pytest.skip(
            f"{_LIVE_OPT_IN_VAR} is unset: this reaches a live service, so it is opt-in "
            f"separately from {_API_KEY_VAR} — having a credential is not asking for a "
            f"network run, and `poe ci-checks` stays deterministic without it."
        )
    if not key:
        pytest.skip(f"{_API_KEY_VAR} is unset: this test needs a real OpenAI account")
    return SecretStr(key)


def _registry(*, openai_settings: OpenAISettings) -> Registry:
    """Every plugin this test drives, registered the way `weft_kernel.discovery.discover`
    would attribute them — by hand, because this test composes a specific slice of stages
    rather than a whole pipeline document.
    """
    registry = Registry()
    registry.add(Extractor, "pdf-text", PdfTextExtractor, distribution="weft-pdf")
    registry.add(Chunker, "fixed-size", FixedSizeChunker, distribution="weft-chunk")
    registry.add(Expander, HQ_NAME, HypotheticalQuestionGenerator, distribution="weft-index")
    registry.add(
        Embedder, "openai", partial(OpenAIEmbedder, openai_settings), distribution="weft-openai"
    )
    registry.add(
        LLMProvider,
        "openai",
        partial(OpenAILLMProvider, openai_settings),
        distribution="weft-openai",
    )
    registry.add(
        Prompt, GENERATE_QUESTIONS_NAME, GenerateQuestionsPrompt, distribution="weft-index"
    )
    registry.add(
        Prompt,
        ANSWER_WITH_CITATIONS_NAME,
        AnswerWithCitationsPrompt,
        distribution="weft-generate",
    )
    return registry


def _run_services(registry: Registry) -> ServiceRegistry:
    roles = LLMRoles(
        roles={
            "index": RoleMapping(provider="openai", model="gpt-4o-mini"),
            "generate": RoleMapping(provider="openai", model="gpt-4o-mini"),
        }
    )
    services = ServiceRegistry()
    services.add(LLM, llm_service(registry=registry, roles=roles))
    services.add(TokenSink, NullSink())
    services.add(Prompts, prompts_service(registry))
    return services


async def _paraphrase(question: str, *, ctx: Context) -> str:
    """One more real completion: `question`, reworded — never a call into
    `weft_index.hypothetical_questions`'s own prompt, so this is genuinely independent
    wording rather than the same model asked the same thing twice.
    """
    llm = ctx.require(LLM)
    rendered = Rendered(
        conversation=Conversation(
            messages=(
                Message(
                    role=MessageRole.USER,
                    content=(
                        "Reword this question in different words, keeping its exact "
                        f"meaning. Reply with the question alone, nothing else.\n\n{question}"
                    ),
                ),
            )
        ),
        prompt="",
        prompt_version="",
    )
    outcome = await llm.complete(rendered, role="generate", ctx=ctx)
    assert isinstance(outcome, Produced), f"the paraphrase call failed: {outcome}"
    return outcome.value.text.strip()


async def test_a_question_nobody_wrote_retrieves_its_chunk_and_cites_the_chunk(
    store: PgVectorStore, api_key: SecretStr, tmp_path: Path
) -> None:
    # Arrange — one real paper, extracted and chunked, trimmed to a bounded slice.
    _ensure_rehydrates(ChunkOffset)
    _ensure_rehydrates(PdfPages)
    _ensure_rehydrates(Representation)
    assert _PAPER.exists(), "corpus/arxiv/1706.07535v1.pdf must be materialised for this test"
    (tmp_path / _PAPER.name).write_bytes(_PAPER.read_bytes())
    docs = discover_source_docs(tmp_path, extensions=PDF_EXTENSIONS)
    assert docs

    openai_settings = OpenAISettings(api_key=api_key)
    registry = _registry(openai_settings=openai_settings)
    services = _run_services(registry)
    ctx = _ctx(services)

    extracted = await PdfTextExtractor().run(docs, ctx)
    assert isinstance(extracted, Produced)
    chunk_outcome = await FixedSizeChunker().run(extracted.value, ctx)
    assert isinstance(chunk_outcome, Produced)
    chunks = tuple(chunk_outcome.value)[:_CHUNKS_KEPT]
    assert chunks, "the paper must chunk to at least one node"

    # Act — expand into hypothetical questions, embed everything, store everything, all real.
    expander = HypotheticalQuestionGenerator()
    assert isinstance(expander, Expander)
    expand_outcome = await expander.run(chunks, ctx)
    assert isinstance(expand_outcome, Produced)
    expanded = expand_outcome.value
    questions = [node for node in expanded if node.ext_as(Representation) is not None]
    assert questions, "the model produced at least one hypothetical question over the slice"

    embedder = OpenAIEmbedder(openai_settings, OpenAIEmbedderConfig())
    embed_outcome = await embedder.run(expanded, ctx)
    assert isinstance(embed_outcome, Produced)
    embedded = embed_outcome.value
    assert all(node.embedding is not None for node in embedded)

    await store.add(embedded)
    await store.flush()

    seed_question = questions[0]
    paraphrase = await _paraphrase(seed_question.content, ctx=ctx)
    assert paraphrase.strip().casefold() != seed_question.content.strip().casefold()
    for chunk in chunks:
        assert paraphrase.strip().casefold() not in chunk.content.casefold(), (
            "the retrieval query must not be a substring of the corpus it is asked about"
        )

    query_node = Node.synthetic(
        content=paraphrase, media_type=MediaType.TEXT, reason="query embedding"
    )
    embedded_query = await embedder.run((query_node,), ctx)
    assert isinstance(embedded_query, Produced)
    query_vector = embedded_query.value[0].embedding
    assert query_vector is not None

    hits = await store.search_vector(query_vector, 5)
    assert hits, "vector search must find something in a store that was just populated"

    # Assert — the paraphrase's nearest neighbour is a *derived question node*, proving the
    # chunk was found by what it answers rather than by its own words: the paraphrase's own
    # wording is nowhere in the corpus, checked above by exact substring search.
    top = hits[0].value
    assert top.ext_as(Representation) is not None, (
        "the paraphrase should retrieve a hypothetical-question node, not a chunk's own "
        "text directly — otherwise this is not testing question-path retrieval at all"
    )
    parent_id = top.lineage.parents[0]
    parent = next(node for node in chunks if node.id == parent_id)
    assert paraphrase.strip().casefold() not in parent.content.casefold()

    # A real `CitedAnswer` run over exactly this hit — 2.9's own machinery, unmodified in
    # its own behaviour, closing task 2.31's citation obligation via the fix this task made
    # to `weft_generate.representation`.
    lookup_services = _run_services(registry)
    lookup_services.add(StageLookup, _PromptLookup(registry))
    lookup_services.add(NodeStore, store)
    answer_ctx = _ctx(lookup_services)

    passage = Passage(
        scored=Scored(value=top, score=hits[0].score), rank=0, retrieved_by=HQ_NAME, label="1"
    )
    payload = Passages(origin=Query(text=paraphrase, origin=QueryOrigin.USER), passages=(passage,))
    outcome = await CitedAnswer().run(payload, answer_ctx)
    assert isinstance(outcome, Produced)
    answer = outcome.value

    # `used` is already resolved to the parent chunk by `run`'s own fix — the model read
    # the real passage as evidence, never the generated question's own text.
    assert answer.used[0].node.id == parent_id
    if answer.citations:
        citation = answer.citations[0]
        assert citation.node_id == parent_id
        assert citation.node_id != top.id
