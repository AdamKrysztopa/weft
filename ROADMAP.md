# What to build next

A working shortlist, ordered by **effect ÷ effort**. Written 2026-09-05.

**This is not a source of truth and it holds no state.** `docs/README.md` is both. The evidence
behind every row is in `docs/product-direction.md` and the two audits
(`docs/audit-a prior project-2026-09-05.md`, `docs/audit-graph-study-2026-09-05.md`); this file exists so
the ordering is not lost between sessions. `ADAM_TODO.md` is the separate list of what needs an
account, an authority or a decision — nothing here is on it.

| # | Feature | Wow | Effort | Why it ranks here |
|---|---|---|---|---|
| 1 | **Ship the pipeline ladder** | ★★★★★ | ▁ | Four pipeline documents exist in the whole tree. The engine already expresses far more than it ships, and pipelines are *data* — this is YAML, not code. For a library whose promise is "naive to advanced, quickly", the ladder **is** the product. |
| 2 | **Hybrid retriever: vector plus text** | ★★★★★ | ▂ | `search_text` is implemented in pgvector and has **no caller**; RRF already fuses without asking where a list came from. The headline "several bases at once" claim, mostly wiring. `vector-top-k`'s own error message already advertises `hybrid` to users who cannot install it. |
| 3 | **Cap concurrent LLM fan-out** | ★★☆☆☆ | ▁ | `asyncio.gather` unbounded at `raptor.py:191` and `hypothetical_questions.py:93`. A 700-node corpus is 700 concurrent calls today. Hours of nobody's time, one semaphore. |
| 4 | **Falsification instrument for eval** | ★★★★☆ | ▂▂ | Show a claimed improvement is *not* real. `weft-eval` and a corpus both exist, no gate blocks it, and it discharges an open 1.0 precondition. The graph audit would schedule this ahead of all graph work. |
| 5 | **Reranker over fused results** | ★★★☆☆ | ▂ | `llm-rerank` exists; what's missing is it being on a shipped pipeline where anyone meets it. Falls out of #1 almost free. |
| 6 | **Graph as shipped pack** | ★★★★★ | ▂▂▂▂ | The one base that isn't real — 2,249 lines of *example* pack. Biggest wow on the list and **blocked on three decisions** (is a graph store in the G4 family; where may a corpus-wide revisable pass run; where does per-corpus curated config live). |

## How to read the ordering

**1 and 2 are one story and should ship together.** The ladder is what you demonstrate, hybrid is
the rung that makes the demonstration impressive, and 3 is what stops the impressive thing
saturating somebody's rate limit on their first real corpus. None of the three touches an open gate.

**4 outranks 6 despite the lower wow.** A falsification instrument — the ability to show a claimed
improvement is not real — is what makes every later claim about 2, 5 and 6 worth anything. Both
audits reached that independently.

**6 is not schedulable yet.** Its three decisions are listed above and the first two touch G2, G4,
G5 and S5 at once. Do not start it by writing code.

## The structural thing that has to be decided first

`docs/01-high-level-plan.md` stops at **Phase 7**, and **G12 blocks Phase 7 entirely**. Every row in
this table that is not a repair to already-shipped code therefore has **no phase to belong to** —
which also means the lessons queue has no phase close to drain against.

Two ways out, and it is a decision rather than a task: open a **Phase 8** with an exit criterion, or
carry rows 1–5 as additions inside Phase 6's already-closed scope and record that in the ledger.
`ADAM_TODO.md` item 1 carries it.
