"""A stranger's whole query path — the independence proof for `weft-retrieve` and `weft-generate`.

`docs/07-extension-cost.md` §2 clause (c), the task 2.11 backfill: `QueryTransform`,
`Retriever`, `Fuser`, `Reranker`, `ContextPacker`, `Sufficiency`, `QueryScorer`,
`RoutingPolicy` and `Generator`, all nine, one distribution — `.phase2-design.md` §9's "one
multi-contract pack per publishing half", the same reasoning `weft-example-ingest` applies
to the pipeline's first half. `examples/weft-example-chunker` is the precedent this pack's
file shape copies exactly.

`tests/architecture/test_ff9c_every_contract_has_a_stranger.py` installs this distribution
(built as a real wheel) into a throwaway environment and asks the resulting registry which
contracts it registered under.
"""

from pydantic import BaseModel, ConfigDict

from weft_example_query.fuser import ExampleFuser
from weft_example_query.generator import NAME as GENERATOR_NAME
from weft_example_query.generator import ExampleGenerator
from weft_example_query.packer import ExampleContextPacker
from weft_example_query.reranker import ExampleReranker
from weft_example_query.retriever import NAME as RETRIEVER_NAME
from weft_example_query.retriever import ExampleFixedRetriever
from weft_example_query.router import ExampleRoutingPolicy
from weft_example_query.scorer import ExampleQueryScorer
from weft_example_query.sufficiency import ExampleSufficiency
from weft_example_query.transform import NAME as TRANSFORM_NAME
from weft_example_query.transform import ExampleQueryTransform
from weft_generate.contract import Generator
from weft_kernel.discovery import PackRegistrar
from weft_retrieve.contract import (
    ContextPacker,
    Fuser,
    QueryScorer,
    QueryTransform,
    Reranker,
    Retriever,
    RoutingPolicy,
    Sufficiency,
)


class Settings(BaseModel):
    """This pack takes no settings — an empty model is still the required shape."""

    model_config = ConfigDict(frozen=True, extra="forbid")


def register(registrar: PackRegistrar, settings: Settings) -> None:
    """Register this pack's nine plugins — one per contract it implements."""
    del settings
    registrar.add(QueryTransform, TRANSFORM_NAME, ExampleQueryTransform)
    registrar.add(Retriever, RETRIEVER_NAME, ExampleFixedRetriever)
    registrar.add(Fuser, "example-concat-dedupe", ExampleFuser)
    registrar.add(Reranker, "example-overlap-rerank", ExampleReranker)
    registrar.add(ContextPacker, "example-top-n", ExampleContextPacker)
    registrar.add(Sufficiency, "example-any-evidence", ExampleSufficiency)
    registrar.add(QueryScorer, "example-length-heuristic", ExampleQueryScorer)
    registrar.add(RoutingPolicy, "example-always", ExampleRoutingPolicy)
    registrar.add(Generator, GENERATOR_NAME, ExampleGenerator)


__all__ = ["Settings", "register"]
