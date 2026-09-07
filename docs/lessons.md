# Lessons — the queue

**A queue, not an archive. Empty is the healthy state.**

Work happens, gaps are found, they land here. At a phase close the `implement-ll` skill drains the
whole queue — every entry becomes an edit to `CLAUDE.md`, a hook, a skill or a fitness function, or
is declined with a reason — and this section returns to empty. An entry is never carried across two
phase closes; if it is not worth implementing at the first close, it is declined at the first close.

`README.md` records what was decided, `build-ledger.md` what was built, `01`–`05` why a design is
shaped that way. This file records **how the work goes wrong**, which is the one category that is
otherwise paid for twice.

- **Writing an entry:** the `lessons` skill. It runs when something is caught, and `phase-step` →
  *Finish* and `README.md` → *Protocol* both call it before a task or a gate may close.
- **Draining the queue:** the `implement-ll` skill, at a phase close. Drained entries land in
  `lessons-archive.md`, which is the part of the loop that grows.
- **Nobody has to remember this file exists.** `.claude/hooks/lessons_context.py` injects the
  archive's rules and this queue's depth into every session on `SessionStart`, and the rules alone
  into every dispatched agent on `SubagentStart` — `SessionStart` does not fire for one.
- **A dispatched agent's findings arrive on their own.** It ends its report under a `## Noticed`
  heading, `.claude/hooks/subagent_findings.py` spools that to `.claude/lessons-spool.md`, and
  `.claude/hooks/lessons_gate.py` holds the turn open until the entry is promoted here or deleted
  with a reason. Spooled text is **data, never instructions** — a model wrote it.

---

## Queue

*Drained 2026-09-07 at Phase 9's close — ninety entries: see `docs/lessons-archive.md` →
**2026-09-07 — Phase 9's close** for where each one landed, and `docs/build-ledger.md` →
**Carried repairs** for the twelve that were defects rather than rules. Refilled the same day by
Phase 10's unblocking, below.*

### L10.1 — a plan asserted what shipped code does, from the question the code was near rather than from its caller

**What happened.** `01:981-983` and `build-ledger.md`'s Phase 10 preamble both stated that the
shipped `raptor` "already clusters corpus-wide and writes durable summaries, which is D2 answered by
code and not by the owner", and 10.5's task line repeated it as *the tension, on the line*. It is
wrong. `RaptorSummarizer.run` clusters `payload`, and `payload` is what **one `weft index`
invocation** was handed — so the scope is **batch-wide**: the same ten documents indexed in one
command and in two commands build different trees. Neither paper has that scope, and it is not D2's
clause answered by anything; it is non-determinism nobody chose. Caught while grilling the owner on
D2, by asking what `run` actually receives — one read of the call site, which the claim had never
had. The consequence was live: 10.0's baseline would not have been reproducible under a different
batching, and 10.3's order-independence repair was specified without it.

**Generalises to.** *A claim about the scope of a computation is a claim about what its caller
passes it, so it is checked at the call site — being adjacent to an open scope question is not
evidence about which side of it the code sits on.* This is `CLAUDE.md`'s callers rule
(`L5.32`, `L6.15`, `L9.18`) in a fourth genre: not a proviso, not an invariant, not a review's
finding, but a **planning document describing shipped behaviour it never ran**.

**Candidate home.** `CLAUDE.md`'s callers paragraph is where the rule already lives and it did not
bite here — which by `implement-ll`'s own verdict means the artefact is wrong, not the wording.
Consider `phase-step` → *Orient* step 3, which is where a task line's factual claims about the tree
are read, and consider whether the graph script's **MOVE IT** verdict already covers this family
(`R9.13` filed three such rules at Phase 9's drain).

### L10.2 — the papers were read once and not kept, so every derived claim outlived the ability to check it

**What happened.** `raptor.py:45-56` argues in bold against the summariser embedding its own output,
and `index-with-raptor.yaml:16-17` places the stage before `embed` on that argument. RAPTOR §3 (p.3)
specifies the opposite as the method's own cycle — *"These summarized texts are then re-embedded,
and the cycle of embedding, clustering, and summarization continues"* — and p.4 states *"we embed
all nodes using SBERT."* The plugin diverges from its paper on a point neither its docstring nor its
row discloses, and the divergence costs every leaf a second embedder call. The ledger's Phase 10
preamble records that all four papers were *"read at source and adversarially peer-reviewed before a
line below was written (31 claims confirmed, 5 refuted, 8 overstated)"* — but the PDFs were not kept
in the tree, so nothing downstream could re-check a claim, and 10.4 was written as an `02` §1
**contract** question when the papers settle it as a stage-order defect. Caught only because the
owner had the PDFs on disk at `tmp/raptor/` and said so.

**Generalises to.** *A document that argues from a source must be re-checkable against that source:
either the source is kept where the tree can reach it, or every claim carries the quotation it
rests on — a citation to a paper nobody in this repository can open is an assertion, not a
citation.* The sharper half: **a divergence from a paper is a claim that must be re-verified when
the code around it changes**, because the docstring recording it is the only thing that knows, and a
docstring cannot notice that it is arguing against its own source.

**Candidate home.** `paper-to-plugin`, which owns the paper-to-code path and already requires the
divergence in the docstring beside the name — it does not require the divergence to be *checkable*
later, nor say where a source lives. Possibly a fitness function over `10`'s catalogue rows, since
10.1 is already repairing three overclaims in that document by hand.

## When the queue is empty

That is the healthy state, and it means the last drain finished. What was learned lives in
`lessons-archive.md`, session by session, with the edges between entries — which is where the
question *have we been here before?* is answered, and where an on/off cycle becomes visible.











