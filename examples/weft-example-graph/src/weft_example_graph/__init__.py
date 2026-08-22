"""`weft-example-graph` — the graph add-on `docs/02-extension-model.md` section 4
specifies, built for
real by task 5.4: a capability spanning several extension points, still one package, one entry
point, one `register()`, one settings model.

**Six extension points, from one install.** `docs/02-extension-model.md` section 4's own
table has five rows plus two G7 added. Counted honestly rather than by row: the "Against
contract" column names six distinct contracts once "—" (the pipeline-as-data row) is
excluded — `Enhancer`, `NodeStore` (the table's "`Store`"), `Retriever`, `Command` (its row
lists two commands, but one contract), `SourceDeletable` and `Reconcilable`. Four of those
six come from an explicit `registrar.add()` call below (`Enhancer`, `NodeStore`, `Retriever`,
`Command` twice); `SourceDeletable` and `Reconcilable` arrive with **no further `.add()`
call**, because `GraphStore` (registered once, under `NodeStore`) satisfies both
structurally — the identical "eighth and ninth capability arrive with no ninth
`registrar.add` call" shape `examples/weft-example-ingest`'s own `register()` already
demonstrates. `registrar.add_ext_model(GraphData)` is a seventh registrar call, on a
separate axis again (a payload primitive, never a contract) — not one of the six, and not
omitted either: see `docs/02-extension-model.md` section 1's "Call it only for an
`ExtModel` that attaches to `Node.ext`" rule, which `GraphData` does.

The pipeline-as-data row ("A named pipeline, and a slot contribution") is deliberately not
among the six: `docs/02-extension-model.md` section 4's own table marks that row's "Against
contract" column "—", because a pipeline resource and a slot contribution are not
registrations against a *contract* at all. **Task 5.5** is that row's own commit:
`registrar.add_pipeline_resource("weft_example_graph", "pipelines/kg.yaml")` ships the named,
derivable-further pipeline; `registrar.add_contribution("enrich", ...)` offers the same
`graph-entities` plugin already registered above into any pipeline that declares an `enrich`
slot — the identical "offering a plugin as both an ordinary stage and a slot contribution
costs nothing extra" shape `examples/weft-example-ingest`'s own `register()` already
demonstrates, reusing its own slot name rather than inventing a second convention for the
identical kind of position (`docs/02-extension-model.md` section 3 → *Slots*).

Everything below is one settings model (`weft_example_graph.store.GraphSettings`,
imported rather than
redeclared — the identical connection setting `GraphStore`, `GraphWalkRetriever` and both
commands all share, `functools.partial`-bound at registration exactly as `weft_store.
pgvector_store.PgVectorStore` wires its own `PgVectorSettings` in) and one `register()`.
"""

from functools import partial

from weft_command.contract import Command
from weft_enhance.contract import Enhancer
from weft_example_graph.commands import GraphBuildCommand, GraphShowCommand
from weft_example_graph.enhancer import GraphEntityEnhancer
from weft_example_graph.payload import GraphData
from weft_example_graph.retriever import GraphWalkRetriever
from weft_example_graph.store import GraphSettings, GraphStore
from weft_kernel.discovery import PackRegistrar
from weft_kernel.pipeline import StageDeclaration
from weft_retrieve.contract import Retriever
from weft_store.contract import NodeStore

#: The slot this pack offers `graph-entities` into — `docs/02-extension-model.md` section 3's
#: own worked example (`weft-example-graph:entities`) targets a slot named `enrich`;
#: reused here rather
#: than inventing a second convention for the identical kind of position, on
#: `examples/weft-example-ingest`'s own precedent.
ENRICH_SLOT = "enrich"

#: This pack's own local id for the stage it contributes into `ENRICH_SLOT` — unqualified;
#: `Contribution.stage.id` is a pack's local name, qualified by distribution only once
#: actually placed (`weft_kernel.resolution.Contribution`'s own docstring).
_ENRICH_STAGE_ID = "entities"

#: Re-exported so a caller can write `from weft_example_graph import Settings`, the name every other
#: pack in this tree's own guide uses — `GraphSettings` (the name this module actually
#: declares, in `store.py`, beside the connection logic it configures) is the same class.
Settings = GraphSettings


def register(registrar: PackRegistrar, settings: Settings) -> None:
    """Register this pack's six extension points from one entry point, per the module
    docstring's own accounting — `SourceDeletable` and `Reconcilable` arrive structurally,
    with no `.add()` call of their own, the identical shape `examples/weft-example-ingest`'s
    own `register()` already demonstrates for its "eighth and ninth capability."

    Every factory is `functools.partial`-bound to this run's `settings` — a database
    connection is a pack-owned resource shared by everything this pack registers, never a
    per-stage `with:` tuning knob (`docs/02-extension-model.md` section 2's own distinction,
    drawn for `weft-store`'s identical `dsn` setting).
    """
    registrar.add(Enhancer, "example-graph-entities", GraphEntityEnhancer)
    registrar.add(NodeStore, "example-graph", partial(GraphStore, settings))
    registrar.add(Retriever, "example-graph-walk", partial(GraphWalkRetriever, settings))
    registrar.add(Command, "example-graph build", partial(GraphBuildCommand, settings))
    registrar.add(Command, "example-graph show", partial(GraphShowCommand, settings))
    registrar.add_ext_model(GraphData)
    registrar.add_pipeline_resource("weft_example_graph", "pipelines/kg.yaml")
    registrar.add_contribution(
        ENRICH_SLOT, StageDeclaration(id=_ENRICH_STAGE_ID, use="example-graph-entities")
    )


__all__ = ["ENRICH_SLOT", "Settings", "register"]
