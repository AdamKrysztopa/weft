# What to build next

**Retired 2026-09-05. This file holds nothing.** Its rows are now **Phase 8 — From engine to
product**, and they are tracked like every other task in this project:

- **`docs/build-ledger.md` → Phase 8** — the tasks, with ticks and shas.
- **`docs/01-high-level-plan.md` → Phase 8** — what the phase is, its exit criterion, and the
  ordering argument that used to live here.
- **`docs/README.md`** — which task is next. That file is the single source of truth, as it always
  was; this one never held state and said so.

**Why it was retired rather than kept alongside.** It was a working shortlist ordered by effect ÷
effort, written because the ordering kept being re-derived between sessions, and it explicitly held
no state because nothing could tick a row on it. That was the right shape for a list whose rows had
no phase to belong to, and the wrong one the moment a row got built: `rerank-then-generate` shipped
as a side effect of row 1, closing row 5, and **there was nowhere to record it**. A list that cannot
say what has been done starts describing a tree that no longer exists — which is the same defect,
one level up, that `docs/README.md`'s own opening paragraph is about.

**One row did not go to Phase 8**, deliberately: the graph as a shipped pack. It is blocked on three
decisions — whether a graph store is in the G4 family, where a corpus-wide revisable pass may run,
and where per-corpus curated configuration lives — the first two of which touch G2, G4, G5 and `S5`
at once. A phase does not absorb work that is not schedulable, so it stays unscheduled and is named
here and in Phase 8's own preamble rather than filed somewhere it would look ready.

The evidence behind the ordering is unchanged and still lives in `docs/product-direction.md` and
`docs/audit-graph-study-2026-09-05.md`.
`ADAM_TODO.md` remains the separate list of what needs an account, an authority or a decision.
