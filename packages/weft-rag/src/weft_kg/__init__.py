"""`weft_kg` — publishes the graph traversal contract and registers a Postgres-backed
implementation of it. Ledger tasks **11.4** (the contract) and **11.5** (this file).

**Registers now, and that is this task's whole point.** `11.4` published `GraphTraversal` and
deliberately registered nothing — "a `register()` here, with nothing yet to register, would be a
producing side with no consuming side." `store.py` and `traversal.py` are that consuming side:
`GraphStore` (`NodeStore`, `SourceDeletable`, `Reconcilable`, structurally) and `GraphWalk`
(`GraphTraversal`), both over one Postgres schema, both reached through the one `weft.packs = graph
= "weft_kg:register"` entry point below and nothing else.

**Two plugin names for the two contracts, and two classes behind them — `docs/lessons.md`
`L11.23`.** `pgvector-graph` (`NodeStore`) and `pgvector-traversal` (`GraphTraversal`) are
qualified rather than bare, per `10` §2.1 rule 6: `01`'s family-membership deferral names
`weft-neo4j` as the sibling this pack is waiting for, so an unqualified `graph` would be the first
implementation seizing a namespace more than one is meant to share. `GraphStore` and `GraphWalk`
are two classes, not one registered twice, because `weft_cli.fanout.participants_for` deduplicates
its participants by class — see `store.py` and `traversal.py`'s own module docstrings for the
failure a single class would reintroduce.

**Ledger `11.10` makes this pack a query-path pack too.** `graph-walk` is a `Retriever`,
registered under that contract exactly the way `vector-top-k` and `hybrid` are, from a different
pack — and the four pipeline resources appended after it are what fitness function 16 needs to
call it a rung rather than a dead registration: see `retrieval.py`'s own module docstring for the
technique and the four `pipelines/graph-*.yaml` documents for the rungs.

**Ledger `11.11` makes this pack a `Command`-contributing pack, its first.** `weft graph
propose|activate|show` register against `weft_command.contract.Command` exactly as `weft config
get|set` do from a different pack — see `weft_kg.commands`'s own module docstring for the three
and `weft_kg.schema`'s for the curated-schema model `propose`/`activate` read and write.
`LlmFactExtractor` also gains a `settings` binding here it did not need before: a curated schema,
once activated, constrains and stamps every fact `llm-facts` extracts — see that module's own
docstring for the "constrain and verify" pair this task adds to its existing five-rule filter.

**Ledger `11.13` adds a fourth `Command`, `weft graph bridges` — the falsification instrument
`11.10`'s own measured run argued for.** Registered last, after the three `11.11` shipped and
their renderers, so `test_register.py`'s asserted pipeline-resource ordering is untouched — this
task adds no pipeline resource at all. See `weft_kg.commands`'s own module docstring for what the
command does and `weft_kg.bridges`'s for the pure half: a bridge is a two-hop path whose endpoints
share no chunk, so no single-passage retriever can ever answer the question it stands for,
whatever its embedder.
"""

from functools import partial

from weft_command.contract import Command
from weft_enhance.contract import Enhancer
from weft_index.contract import Expander
from weft_kernel.discovery import Disclosure, PackRegistrar
from weft_kg.commands import (
    GraphActivateCommand,
    GraphActivateResult,
    GraphBridgesCommand,
    GraphBridgesResult,
    GraphProposeCommand,
    GraphProposeResult,
    GraphShowCommand,
    GraphShowResult,
    render_graph_activate,
    render_graph_bridges,
    render_graph_propose,
    render_graph_show,
)
from weft_kg.contract import (
    GRAPH_ROLE,
    GRAPH_TRAVERSAL_CONTRACT_VERSION,
    Entity,
    EntityId,
    GraphTraversal,
)
from weft_kg.cooccurrence import CooccurrenceGraphBuilder, CooccurrenceSettings
from weft_kg.extraction import NAME as LLM_FACTS_NAME
from weft_kg.extraction import LlmFactExtractor, LlmFactsConfig
from weft_kg.payload import (
    CooccurrenceEdge,
    CooccurrenceGraph,
    EntityMention,
    ExtractedFact,
    ExtractionTally,
    MentionedEntity,
)
from weft_kg.prompts import (
    ADJUDICATE_ENTITIES_NAME,
    EXTRACT_FACTS_NAME,
    AdjudicateEntitiesPrompt,
    ExtractFactsPrompt,
)
from weft_kg.retrieval import NAME as GRAPH_WALK_NAME
from weft_kg.retrieval import GraphWalkRetriever
from weft_kg.store import ActiveSchema, GraphSettings, GraphStore, SchemaPresence
from weft_kg.traversal import GraphWalk
from weft_prompts.contract import Prompt
from weft_retrieve.contract import Retriever
from weft_store.contract import NodeStore

#: Re-exported so a caller can write `from weft_kg import Settings`, the name every other pack in
#: this tree's own guide uses — `GraphSettings` (declared in `store.py`, beside the connection
#: logic it configures) is the same class.
Settings = GraphSettings

#: What this pack touches — `docs/02-extension-model.md` §2 → *The trust model*. The setting is
#: named, never its value: `dsn` is a `SecretStr` and the credential inside it is not this pack's
#: to print.
DISCLOSURE = Disclosure(
    network=("the PostgreSQL server [packs.graph] dsn names (WEFT_DATABASE_URL by default)",),
    #: **Ledger `11.11`, and it was `()` until the task that made it false.** `02` §2 → *The
    #: trust model*: a `Disclosure` an operator reads has to name what the pack actually touches,
    #: and a pack that reads and writes files while declaring none is worse than one that
    #: declares nothing — it answers the question wrongly rather than not at all. Both paths are
    #: an operator's own project files, named as settings and paths rather than as contents.
    filesystem=(
        "the curated schema file [packs.graph] schema_file names, read at extraction time",
        "weft.toml, read and written by `weft graph activate` to record the activated schema",
        "the path `weft graph bridges --write PATH` names, written with the JSON "
        "`weft eval run --questions` reads",
    ),
    subprocess=(),
    note=(
        "Reads and writes node, entity and relation rows in PostgreSQL with pgvector, "
        "creating its own tables on first use. Sits beside the vector store: a document naming "
        "both store: pgvector and store: graph hands the identical batch to each. The "
        "llm-facts stage sends a chunk's own text to whichever provider the LLM role it is "
        "configured with (role: index by default) resolves to — egress is a property of that "
        "selected provider, not of this pack, so no import rule can state it here. Under weft "
        "reconcile --mode full, the same provider is sent two entity names at a time, one "
        "ambiguous pair per call, so it can judge whether they name the same thing; weft "
        "reconcile --mode repair sends nothing. On the query side, graph-walk reads entity "
        "and node rows back from the same PostgreSQL server and sends nothing anywhere — "
        "seeding a question's entities is a regular expression, and the walk itself is SQL. "
        "When [packs.graph] schema_file names an active curated schema, its admitted "
        "arrangements travel to the same provider with every chunk llm-facts sends: the "
        "vocabulary an operator curated leaves the machine beside the passage, not only the "
        "passage itself."
    ),
)

#: Ledger task **9.0**'s form — read by `weft_kernel.discovery._read_service_roles` at import
#: time, before settings are validated, exactly where `DISCLOSURE` above is read. This is what
#: makes `[services] graph` exist at all, with no kernel line naming it.
SERVICE_ROLES = (GRAPH_ROLE,)


def register(registrar: PackRegistrar, settings: Settings) -> None:
    """Register this pack's two capabilities and the document that makes the store reachable.

    Every factory is `functools.partial`-bound to this run's `settings` — a database connection is
    a pack-owned resource shared by everything this pack registers, never a per-stage `with:`
    tuning knob (`docs/02-extension-model.md` §2's own distinction).
    """
    registrar.add(NodeStore, "pgvector-graph", partial(GraphStore, settings))
    registrar.add(GraphTraversal, "pgvector-traversal", partial(GraphWalk, settings))
    # No pack settings of its own — the enhancer's constructor argument is a stage's `with:`
    # config, exactly `CooccurrenceSettings`, so it registers as the bare class rather than a
    # `partial`, unlike the two above which close over this run's connection settings.
    registrar.add(Enhancer, "cooccurrence-graph", CooccurrenceGraphBuilder)
    registrar.add_ext_model(CooccurrenceGraph)
    registrar.add_pipeline_resource("weft_kg", "pipelines/index-with-graph.yaml")
    registrar.add_pipeline_resource("weft_kg", "pipelines/index-with-cooccurrence.yaml")
    # Ledger 11.7 — the model-calling rung. `add_pipeline_resource` for this document comes
    # last: `test_register.py` asserts the exact resource order, and this is the rung that
    # builds on `index-with-graph`, which must already be registered above it.
    #
    # `settings=settings`, ledger `11.11` — a `functools.keyword`-bound `partial`, unlike this
    # module's other two `partial(..., settings)` calls: `LlmFactExtractor.__init__` takes
    # `settings` keyword-only and last, deliberately unlike `GraphStore(settings, config)` — see
    # that constructor's own comment for why.
    registrar.add(Expander, LLM_FACTS_NAME, partial(LlmFactExtractor, settings=settings))
    registrar.add(Prompt, EXTRACT_FACTS_NAME, ExtractFactsPrompt)
    # Ledger 11.9 — the reconcile pass's own prompt, registered beside the ingest one it sits
    # next to in `weft_kg.prompts`, and before the `add_ext_model` calls that follow so the
    # pipeline-resource ordering `test_register.py` asserts stays untouched.
    registrar.add(Prompt, ADJUDICATE_ENTITIES_NAME, AdjudicateEntitiesPrompt)
    registrar.add_ext_model(ExtractedFact)
    registrar.add_ext_model(MentionedEntity)
    registrar.add_ext_model(ExtractionTally)
    registrar.add_pipeline_resource("weft_kg", "pipelines/index-with-facts.yaml")
    # Ledger 11.10 — the query side. `graph-walk` registers as the bare class, exactly like
    # `cooccurrence-graph` above: its constructor argument is a stage's `with:` config, not a
    # pack-owned connection. The four documents below are what makes it reachable at all — a
    # rung no shipped document names is a rung with no floor, fitness function 16's property.
    registrar.add(Retriever, GRAPH_WALK_NAME, GraphWalkRetriever)
    registrar.add_pipeline_resource("weft_kg", "pipelines/graph-then-generate.yaml")
    registrar.add_pipeline_resource("weft_kg", "pipelines/graph-2hop-then-generate.yaml")
    registrar.add_pipeline_resource("weft_kg", "pipelines/graph-and-vector-rrf.yaml")
    registrar.add_pipeline_resource("weft_kg", "pipelines/graph-then-rerank.yaml")
    # Ledger 11.11 — the first `Command`s this pack ships. Schema curation is a per-project
    # decision an operator makes once in a while, not a pipeline position, so these register
    # against `Command` rather than joining any stage list above; see `weft_kg.commands`'s own
    # module docstring for why the three answer three different questions and only one writes.
    registrar.add(Command, "graph propose", partial(GraphProposeCommand, settings))
    registrar.add(Command, "graph activate", partial(GraphActivateCommand, settings))
    registrar.add(Command, "graph show", partial(GraphShowCommand, settings))
    registrar.add_renderer(GraphProposeResult, render_graph_propose)
    registrar.add_renderer(GraphActivateResult, render_graph_activate)
    registrar.add_renderer(GraphShowResult, render_graph_show)
    # Ledger 11.13 — the fourth Command, registered last: it adds no pipeline resource, so its
    # position here cannot disturb test_register.py's own asserted resource ordering above.
    registrar.add(Command, "graph bridges", partial(GraphBridgesCommand, settings))
    registrar.add_renderer(GraphBridgesResult, render_graph_bridges)


__all__ = [
    "ADJUDICATE_ENTITIES_NAME",
    "DISCLOSURE",
    "EXTRACT_FACTS_NAME",
    "GRAPH_ROLE",
    "GRAPH_TRAVERSAL_CONTRACT_VERSION",
    "GRAPH_WALK_NAME",
    "LLM_FACTS_NAME",
    "SERVICE_ROLES",
    "AdjudicateEntitiesPrompt",
    "CooccurrenceEdge",
    "CooccurrenceGraph",
    "CooccurrenceGraphBuilder",
    "CooccurrenceSettings",
    "ActiveSchema",
    "Entity",
    "EntityId",
    "EntityMention",
    "ExtractFactsPrompt",
    "ExtractedFact",
    "ExtractionTally",
    "GraphActivateCommand",
    "GraphActivateResult",
    "GraphBridgesCommand",
    "GraphBridgesResult",
    "GraphProposeCommand",
    "GraphProposeResult",
    "GraphSettings",
    "GraphShowCommand",
    "GraphShowResult",
    "GraphTraversal",
    "GraphWalkRetriever",
    "LlmFactExtractor",
    "LlmFactsConfig",
    "MentionedEntity",
    "SchemaPresence",
    "Settings",
    "register",
    "render_graph_activate",
    "render_graph_bridges",
    "render_graph_propose",
    "render_graph_show",
]
