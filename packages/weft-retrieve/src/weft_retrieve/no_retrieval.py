"""`no-retrieval` — the null case on the query path. `Retriever`, contributing nothing.

Task **2.13**, `docs/build-ledger.md`: "the null case is a plugin like any other, and an
empty source list is a *stated property* of it rather than a retrieval failure a consumer
has to guess at." `docs/10-technique-catalogue.md` §1.1's own row on this technique names
what the reference got wrong: `strategies/basic.py:56-75` implemented the null case faithfully,
but its emptiness was a *consequence of which helper it called* — nothing anywhere declared
it. `sources_are_empty_by_design` is the fix: a class attribute a caller reads, never a fact
inferred from `Candidates.lists` happening to be empty. `weft_retrieve.payload.Candidates`'s
own module docstring draws the line this plugin sits on: `Candidates(lists=())` means
*nothing was ever asked*, which is a different fact from a retriever that searched and found
nothing (`Candidates(lists=(RankedList(hits=()),))`).

**The name.** *Closed-book QA* is Roberts, Raffel & Shazeer's name for the setting itself —
answering from a model's parametric memory alone, with no retrieval step at all (Adam
Roberts, Colin Raffel, Noam Shazeer, *How Much Knowledge Can You Pack Into the Parameters of
a Language Model?*, EMNLP 2020, arXiv:2002.08910). `no-retrieval` is Adaptive-RAG's label for
the *branch* that takes this path — Soyeong Jeong, Jinheon Baek, Sukmin Cho, Sung Ju Hwang,
Jong C. Park, *Adaptive-RAG: Learning to Adapt Retrieval-Augmented Large Language Models
through Question Complexity*, NAACL 2024, arXiv:2403.14403, §A.2 and the Types column of its
results tables, which write it "No Retrieval". Adaptive-RAG is cited for the *name* alone:
this plugin is the null case, verbatim, and claims nothing about Adaptive-RAG's own
contribution — a trained classifier that routes a question between this branch and two
deeper ones. That routing is a separate mechanism (`weft_retrieve.contract.QueryScorer` and
`RoutingPolicy`, ledger 2.25); whether it ever selects this branch is a question for the
router, not for this plugin, which needs no citation of its own because it is the null case.
"""

from typing import ClassVar

from weft_kernel.context import Context
from weft_kernel.payload import Outcome, Produced
from weft_retrieve.payload import Candidates, QuerySet

#: The name this retriever is registered and selectable under — see `weft_retrieve.register`.
NAME = "no-retrieval"


class NoRetrieval:
    """Retrieves nothing, always. Satisfies `weft_retrieve.contract.Retriever` structurally.

    No `config_model`: the null case has nothing to parameterise, and inventing a knob to
    say "no, really, retrieve nothing" would be worse than declaring the fact plainly as a
    class attribute. `cost_bound = (0, 0)` is the name's own claim about cost — it calls no
    model and opens no store connection, which is the whole point of the branch.
    """

    sources_are_empty_by_design: ClassVar[bool] = True
    cost_bound: ClassVar[tuple[int, int]] = (0, 0)

    def __init__(self, config: object = None) -> None:
        del config  # nothing here is configurable — see the class docstring

    async def run(self, payload: QuerySet, ctx: Context) -> Outcome[Candidates]:
        """`Candidates(lists=())` — never asked, structurally distinct from an empty search.

        Reads only `payload.origin`; `payload.queries` is not inspected, because how many
        queries a caller assembled changes nothing about a branch that searches none of
        them. No service, no store, no model call — the whole reason the branch exists.
        """
        del ctx
        return Produced(value=Candidates(origin=payload.origin, lists=()))
