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
"""

from functools import partial

from weft_enhance.contract import Enhancer
from weft_index.contract import Expander
from weft_kernel.discovery import Disclosure, PackRegistrar
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
from weft_kg.prompts import EXTRACT_FACTS_NAME, ExtractFactsPrompt
from weft_kg.store import GraphSettings, GraphStore
from weft_kg.traversal import GraphWalk
from weft_prompts.contract import Prompt
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
    filesystem=(),
    subprocess=(),
    note=(
        "Reads and writes node, entity and relation rows in PostgreSQL with pgvector, "
        "creating its own tables on first use. Sits beside the vector store: a document naming "
        "both store: pgvector and store: graph hands the identical batch to each. The "
        "llm-facts stage sends a chunk's own text to whichever provider the LLM role it is "
        "configured with (role: index by default) resolves to — egress is a property of that "
        "selected provider, not of this pack, so no import rule can state it here."
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
    registrar.add(Expander, LLM_FACTS_NAME, LlmFactExtractor)
    registrar.add(Prompt, EXTRACT_FACTS_NAME, ExtractFactsPrompt)
    registrar.add_ext_model(ExtractedFact)
    registrar.add_ext_model(MentionedEntity)
    registrar.add_ext_model(ExtractionTally)
    registrar.add_pipeline_resource("weft_kg", "pipelines/index-with-facts.yaml")


__all__ = [
    "DISCLOSURE",
    "EXTRACT_FACTS_NAME",
    "GRAPH_ROLE",
    "GRAPH_TRAVERSAL_CONTRACT_VERSION",
    "LLM_FACTS_NAME",
    "SERVICE_ROLES",
    "CooccurrenceEdge",
    "CooccurrenceGraph",
    "CooccurrenceGraphBuilder",
    "CooccurrenceSettings",
    "Entity",
    "EntityId",
    "EntityMention",
    "ExtractFactsPrompt",
    "ExtractedFact",
    "ExtractionTally",
    "GraphSettings",
    "GraphTraversal",
    "LlmFactExtractor",
    "LlmFactsConfig",
    "MentionedEntity",
    "Settings",
    "register",
]
