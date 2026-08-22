"""Task 2.32's own exit demonstration, end to end, against the real corpus.

`docs/build-ledger.md`: "a query no single chunk answers is answered from a summary node,
and a chunk whose summary could not be generated stays retrievable — the tree degrades
rather than the run failing." Every service in this test is real: `weft-pdf` extracts a
real paper from `corpus/arxiv/`, `weft-chunk` splits it, `weft_index.raptor.
RaptorSummarizer` clusters the real chunks by embedding similarity and asks the real OpenAI
account this environment carries for one abstractive summary over the cluster, `weft-
openai`'s embedder gives every node — chunk and summary alike — a real vector, `weft-
store`'s `pgvector` backend holds them, and `weft_generate.cited_answer.CitedAnswer` runs
over the summary hit to prove it is cited as itself rather than crashing on a node with
more than one parent (`weft_generate.representation`'s own multi-parent branch, written for
this task before this task existed).

**Why a purpose-built broad question, not a paraphrase of the generated summary.**
`tests/integration/test_hypothetical_questions_pipeline.py`'s own paraphrase device proves a
*different* property — that a query nowhere in the corpus still finds the right node — and
reusing it here by paraphrasing the summary's own wording would prove only that a paraphrase
of node X's text finds node X, which is true of any node and not what this task is about.
What this task's own exit demonstration asks for is a query *no single chunk answers*, so
the query here is built independently of `raptor`'s own summary: a fresh completion is
handed every kept chunk's own content and asked for one question whose answer needs *all*
of them together, never `raptor`'s own generated summary text as a starting point. If the
resulting query's nearest neighbour is still the summary node rather than any one narrow
chunk, that is because the summary is the one node actually built to answer a question that
wide — not because the query happens to echo one node's own wording back at it.

**Why `similarity_threshold=0.0` and every kept chunk in one cluster.** A tight,
deterministic cluster boundary is not this test's own subject — `tests/unit/weft_index/
test_raptor.py` already covers clustering with a scripted embedder. What this test needs
is *a* real cluster to summarise, reliably, without depending on how similar four
consecutive real chunks of one paper happen to be under a live embedding model: real text
embeddings of related passages are essentially never negatively correlated, so a floor of
`0.0` against the one open cluster (`cluster_size` set to the whole kept slice) merges all
of them deterministically.

Skipped, with a reason, when the database or the credential is absent — the same discipline
`tests/integration/test_hypothetical_questions_pipeline.py` already takes.
"""

import os
from collections.abc import AsyncIterator, Sequence
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
from weft_index.contract import Expander
from weft_index.payload import Representation
from weft_index.prompts import SUMMARIZE_CLUSTER_NAME, SummarizeClusterPrompt
from weft_index.raptor import NAME as RAPTOR_NAME
from weft_index.raptor import RaptorConfig, RaptorSummarizer
from weft_kernel.context import Context, ServiceRegistry
from weft_kernel.payload import ExtModel, MediaType, Node, Produced, SourceId
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
#: The same short, real arXiv paper `test_hypothetical_questions_pipeline.py` uses — small
#: enough that a four-chunk slice stays representative rather than contrived.
_PAPER = Path("corpus/arxiv/1706.07535v1.pdf")
#: Four widely separated chunks, each covering a distinct technical point of the paper's
#: body — conditional mutual information's own definition, the BQP/LP problem formulation,
#: related global feature selectors, and the cross-validation evaluation procedure. Chosen
#: by reading the real extraction once while writing this test, not asserted blind, and
#: deliberately *not* the paper's title or abstract: an abstract is already a broad,
#: whole-paper overview, which would make "the summary beats a narrow chunk" trivially true
#: for the wrong reason rather than because clustering and summarising actually happened.
_CHUNK_INDICES = (15, 25, 35, 45)


def _ctx(services: ServiceRegistry) -> Context:
    return Context(
        tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en", services=services
    )


class _PromptLookup:
    """A `StageLookup` narrowed to `build_capability`, resolving a real `Registry` — the
    same stand-in `test_hypothetical_questions_pipeline.py` takes, because nothing in this
    tree has built the production version yet (ledger task 2.8 is still open).
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
    `weft_store.rehydrate.register_from_reports`, the generic consumer task 5.2g built,
    for the identical reason `test_hypothetical_questions_pipeline.py`'s own copy is: a
    node's `ext` cannot round-trip through a real store unless the namespace that reached
    it was registered first, and a second registration of a namespace already claimed by
    the same class must be a no-op rather than `DuplicateRegistrationError` once more than
    one test module in this session needs it.
    """
    from weft_kernel.discovery import PackReport, PackStatus
    from weft_store.rehydrate import register_from_reports

    report = PackReport(
        distribution=model.__namespace__, status=PackStatus.ACTIVE, ext_models=(model,)
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
    if not key:
        pytest.skip(f"{_API_KEY_VAR} is unset: this test needs a real OpenAI account")
    return SecretStr(key)


def _registry(*, openai_settings: OpenAISettings) -> Registry:
    """Every plugin this test drives, registered by hand — the same posture
    `test_hypothetical_questions_pipeline.py`'s own `_registry` takes, composing a specific
    slice of stages rather than a whole pipeline document.
    """
    registry = Registry()
    registry.add(Extractor, "pdf-text", PdfTextExtractor, distribution="weft-pdf")
    registry.add(Chunker, "fixed-size", FixedSizeChunker, distribution="weft-chunk")
    registry.add(Expander, RAPTOR_NAME, RaptorSummarizer, distribution="weft-index")
    registry.add(
        Embedder, "openai", partial(OpenAIEmbedder, openai_settings), distribution="weft-openai"
    )
    registry.add(
        LLMProvider,
        "openai",
        partial(OpenAILLMProvider, openai_settings),
        distribution="weft-openai",
    )
    registry.add(Prompt, SUMMARIZE_CLUSTER_NAME, SummarizeClusterPrompt, distribution="weft-index")
    registry.add(
        Prompt,
        ANSWER_WITH_CITATIONS_NAME,
        AnswerWithCitationsPrompt,
        distribution="weft-generate",
    )
    return registry


def _run_services(registry: Registry, *, embedder: object) -> ServiceRegistry:
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
    services.add(Embedder, embedder)
    return services


async def _broad_question(chunks: Sequence[Node], *, ctx: Context) -> str:
    """One real completion, built from `chunks`' own content rather than from `raptor`'s own
    generated summary — see the module docstring's *"Why a purpose-built broad question"*
    section for why that independence is what makes this test's own assertion meaningful.
    """
    llm = ctx.require(LLM)
    joined = "\n\n".join(f"{index}. {chunk.content}" for index, chunk in enumerate(chunks, 1))
    rendered = Rendered(
        conversation=Conversation(
            messages=(
                Message(
                    role=MessageRole.USER,
                    content=(
                        "Below are several passages from one paper. Write ONE broad "
                        "question whose answer requires combining information spread "
                        "across ALL of the passages together — a question that no single "
                        "one of the passages, read alone, could fully answer. Do not "
                        "quote the passages' own wording. Reply with the question alone, "
                        f"nothing else.\n\n{joined}"
                    ),
                ),
            )
        ),
        prompt="",
        prompt_version="",
    )
    outcome = await llm.complete(rendered, role="generate", ctx=ctx)
    assert isinstance(outcome, Produced), f"the broad-question call failed: {outcome}"
    return outcome.value.text.strip()


async def test_a_broad_query_is_answered_from_a_summary_node_cited_as_itself(
    store: PgVectorStore, api_key: SecretStr, tmp_path: Path
) -> None:
    # Arrange — one real paper, extracted, chunked, and trimmed to a bounded slice.
    _ensure_rehydrates(ChunkOffset)
    _ensure_rehydrates(PdfPages)
    _ensure_rehydrates(Representation)
    assert _PAPER.exists(), "corpus/arxiv/1706.07535v1.pdf must be materialised for this test"
    (tmp_path / _PAPER.name).write_bytes(_PAPER.read_bytes())
    docs = discover_source_docs(tmp_path, extensions=PDF_EXTENSIONS)
    assert docs

    openai_settings = OpenAISettings(api_key=api_key)
    registry = _registry(openai_settings=openai_settings)
    embedder = OpenAIEmbedder(openai_settings, OpenAIEmbedderConfig())
    services = _run_services(registry, embedder=embedder)
    ctx = _ctx(services)

    extracted = await PdfTextExtractor().run(docs, ctx)
    assert isinstance(extracted, Produced)
    chunk_outcome = await FixedSizeChunker().run(extracted.value, ctx)
    assert isinstance(chunk_outcome, Produced)
    all_chunks = tuple(chunk_outcome.value)
    assert len(all_chunks) > max(_CHUNK_INDICES), "the paper must chunk past every kept index"
    chunks = tuple(all_chunks[index] for index in _CHUNK_INDICES)

    # Act — cluster and summarise, all real: one open cluster, every kept chunk in it.
    raptor = RaptorSummarizer(
        RaptorConfig(cluster_size=len(chunks), min_cluster_size=2, similarity_threshold=0.0)
    )
    assert isinstance(raptor, Expander)
    expand_outcome = await raptor.run(chunks, ctx)
    assert isinstance(expand_outcome, Produced)
    expanded = expand_outcome.value
    summaries = [node for node in expanded if node.ext_as(Representation) is not None]
    assert len(summaries) == 1, "four mutually similar chunks must cluster into exactly one summary"
    summary = summaries[0]
    assert len(summary.lineage.parents) == len(chunks)
    expected_sources = frozenset[SourceId]().union(*(chunk.lineage.sources for chunk in chunks))
    assert summary.lineage.sources == expected_sources

    embed_outcome = await embedder.run(expanded, ctx)
    assert isinstance(embed_outcome, Produced)
    embedded = embed_outcome.value
    assert all(node.embedding is not None for node in embedded)

    await store.add(embedded)
    await store.flush()

    broad_question = await _broad_question(chunks, ctx=ctx)
    for chunk in chunks:
        assert broad_question.strip().casefold() not in chunk.content.casefold(), (
            "the broad query must not be a substring of any one chunk it is asked about"
        )

    query_node = Node.synthetic(
        content=broad_question, media_type=MediaType.TEXT, reason="query embedding"
    )
    embedded_query = await embedder.run((query_node,), ctx)
    assert isinstance(embedded_query, Produced)
    query_vector = embedded_query.value[0].embedding
    assert query_vector is not None

    hits = await store.search_vector(query_vector, 5)
    assert hits, "vector search must find something in a store that was just populated"

    # Assert — a question built to need every chunk together retrieves the summary node,
    # not a single narrow chunk: the summary is the one node actually built to answer
    # something that wide, which no individual chunk on its own can.
    top = hits[0].value
    assert top.id == summary.id, (
        "a question spanning every clustered chunk should retrieve the summary node, not "
        "one narrow chunk out of the four it was built from"
    )
    assert len(top.lineage.parents) > 1

    # A real `CitedAnswer` run over exactly this hit: `weft_generate.representation`'s own
    # multi-parent branch leaves a `Node.combine` summary cited as itself, never
    # misattributed to one of its several parents.
    lookup_services = _run_services(registry, embedder=embedder)
    lookup_services.add(StageLookup, _PromptLookup(registry))
    lookup_services.add(NodeStore, store)
    answer_ctx = _ctx(lookup_services)

    passage = Passage(
        scored=Scored(value=top, score=hits[0].score), rank=0, retrieved_by=RAPTOR_NAME, label="1"
    )
    payload = Passages(
        origin=Query(text=broad_question, origin=QueryOrigin.USER), passages=(passage,)
    )
    outcome = await CitedAnswer().run(payload, answer_ctx)
    assert isinstance(outcome, Produced)
    answer = outcome.value

    assert answer.used[0].node.id == summary.id
    if answer.citations:
        citation = answer.citations[0]
        assert citation.node_id == summary.id
