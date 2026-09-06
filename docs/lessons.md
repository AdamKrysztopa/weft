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

### L8.39 — the handler caught a type and its comment described a cause

**What happened.** `weft_cli.cli.main` wraps `build_dependencies` in `except WeftError`, and its
comment explains the handler exists for *"`weft.toml` is not valid TOML, `[packs] allow`/`[plugins]`
is malformed"*. Those two sections are parsed by hand and raise `WeftError`. `[llm]` is validated by
pydantic, whose `ValidationError` is not a `WeftError` — so **one mistyped key in `[llm.roles]` gave
an operator a full Python traceback ending in a pydantic documentation URL, and exit `1`**, on the
one file every operator edits. Found by running the binary at ledger task 7.4, from a directory
outside the repository.

**The comment was not wrong about anything it named.** It listed the causes somebody had in mind
when the `except` was written, and the `except` catches a *type*. Those two descriptions agreed
then and drifted apart the moment a config reader started validating with a model instead of by
hand — with nothing to notice, because the handler still catches everything it ever caught.

**Generalises to.** Where a handler catches a **type** and its comment describes **causes**, the
comment is a claim about which causes produce that type — and nothing checks it, because both halves
go on being individually true. Either enumerate the causes as a test (one malformed input per
reader, asserting the refusal rather than the traceback), or say in the comment which type each
named cause actually raises. Measured while fixing this: of the three model-validated sections,
`[services]` and `[permissions]` already refused correctly, so the drift was in exactly one reader
and no reading of the comment would have told anybody which.

**Candidate home.** `tests/unit/weft_cli/test_malformed_config_refuses.py`, written for this task —
one parametrised case per config section, asserting a named refusal at exit 4 and the absence of a
traceback. A new `weft.toml` section joins the list or its reader is unguarded.

### L8.38 — a docstring told third parties to call something nothing had registered

**What happened.** `weft_cli.commands`' module docstring, explaining that built-ins hold no
privileged path, tells a pack author their command is free "to read
`ctx.require(weft_kernel.registry.Registry)` directly if all it needs is plugin resolution".
Nothing registered a `Registry` into any run's `ServiceRegistry`. The sentence was written to
reassure a stranger that the seam was open, and it named the one call that would have proved it
closed. Found by running `weft agent` from outside the repository at task 7.4 — the refusal was
perfect (*"no service is registered for Registry on this run. Services available: Dependencies,
LLM, Prompts, TokenSink"*), which is requirement 5 doing its job on a gap requirement 1 had left.

**It survived because nothing first-party ever took the advice.** Every built-in reads
`ctx.require(Dependencies)`, which *is* registered, and `Dependencies` carries a registry — so the
five commands the docstring was written beside all had one, by a route the docstring explicitly
told strangers not to use. The advice was correct about what a stranger *should* do and wrong about
whether it worked, and no first-party caller could ever have discovered that.

**Generalises to.** A docstring that tells somebody else how to use a seam is a claim about a path
the author is not on, and it is worth exactly as much as the last time somebody walked it. This is
`L8.24`'s shape — a claim about the *other* call sites — with the other call sites being **outside
the repository**, where no test in this tree will ever be. The tell is any sentence of the form
*"a third party may instead ..."*: it describes an untaken path, and the tree's own callers cannot
falsify it.

**Candidate home.** `weft-canary` is this repository's answer to exactly this problem — a test-only
distribution existing to be the stranger. A canary command that reaches for every service the
documentation promises a pack author would have caught this the day the sentence was written, and
it is the same shape as fitness function 8's own use of that pack.

### L8.37 — a lint exemption justified for tests is switched on for the whole tree

**What happened.** Task 7.3's implementation reached me containing
`assert isinstance(outcome, Failed)` in shipped code, to keep an import used. `ruff` did not object,
because `pyproject.toml` carries `ignore = ["S101"]  # assert is the point in tests` — a tree-wide
exemption whose stated reason is about `tests/` alone. Measured at the moment of noticing:
**7 asserts live in `packages/*/src`**, across five modules including `weft-kernel`.

**This project has already been bitten by exactly this, and says so in two places.** `CLAUDE.md`
and `phase-step` → *When to stop* both cite `weft_cli.route_ask`'s
`assert isinstance(answer, Answer)  # every shipped routable pipeline ends in a Generator` as the
worked example of settled text written over a population the author does not control — *"it sat
there through Phase 5 and most of Phase 6 failing with no message at all"*. The rule was written;
the lint setting that lets the shape recur was not looked at, because the lesson was filed as being
about **claims** and the exemption reads as being about **style**.

An assert in shipped code is not a check: it is stripped under `-O`, so the failure it was written
to catch becomes an `AttributeError` somewhere else. In this instance it was also proving something
`pyright` already proves — the branch was flagged `reportUnnecessaryIsInstance` the moment the
`assert` became an `if`, so the type checker had the exhaustiveness the whole time.

**Generalises to.** An exemption's *scope* and its *stated reason* must match, and where they do not
the reason is the honest one — so narrow the scope to it. A comment naming a narrower case than the
setting covers is not documentation, it is a claim nobody re-reads when the setting starts applying
somewhere else.

**Candidate home.** `pyproject.toml` — `S101` scoped to `tests/` and `testing/` through
`[tool.ruff.lint.per-file-ignores]`, with the seven existing instances either removed or waived
individually. That is a mechanical change and it makes the next one visible at the moment it is
typed, which is where `implement-ll` says a rule of this shape belongs.

### L8.36 — a brief that forbids every option has decided nothing, and says so only by contradicting itself

**What happened.** Task 7.2's dispatch brief told the implementer, of the branch where the cascade
returns something other than `Produced`: *"Do not invent a `StopReason` member for it; use
`BUDGET_EXHAUSTED` only for the budget."* Those two clauses have no value between them that is
true — the branch is neither an answer nor an exhausted budget, and the third member was forbidden.
The brief also said *"if you find you need a third member to be honest, stop and report"*, and the
implementer did the strongest available thing: it reused `BUDGET_EXHAUSTED`, wrote the reuse and
the contradiction into the module docstring **and** into its report, and shipped green. Nothing was
hidden, and I would still not have looked at that branch if the report had not named it — none of
the six tests reach it, because the stub always answers.

The resolution, once looked at, took one enum member and was not close: `stopped_because` is a
field an operator reads to decide what to do next, and `BUDGET_EXHAUSTED` on a run that stopped
after one step of ten tells them to raise the budget — which would change nothing, because the
model never returned a usable decision.

**Generalises to.** A brief's constraints are a specification and can be **jointly unsatisfiable**
while each one reads as reasonable alone — and the author is exactly the person who cannot see it,
because they wrote them one at a time. Before dispatching, take each branch the brief constrains
and name the value it is supposed to produce; a branch with no nameable value is a decision still
owed, not a constraint. The tell in this instance was already in the brief's own text: an escape
hatch (*"stop and report"*) written for a fork the author had noticed and had not settled.

**Candidate home.** `references/implementer-brief.md`, which owns the brief template — the *Already
decided* section should be read once per constrained branch rather than once per file, and an
escape hatch in a brief is a signal the author left something open, not a safety net that makes
leaving it open fine.

### L8.35 — the expected red hid an unexpected one, and it cost a dispatch

**What happened.** Writing task 7.0's test, I ran `uv run poe ci-no-tests` before dispatching the
implementer — the check `phase-step` → *Green* requires, because a brief's *done when* names the
gate and that is a promise the gate currently reports on the agent's diff and nothing else
(`L6.30`). `pyright` reported **16 errors**. I read all sixteen as *"the module the implementer is
about to write does not exist yet"*, which was true of ten of them. **Six were mine**: the test
doubles declared `permission_class`/`help`/`args_model` as `Final` and omitted `version`,
`required_declarations` and `result_model`, so they did not statically satisfy the `Command`
Protocol the seam's parameter is typed against. The `_context()` helper also called
`Context(tenant_id=..., registry=...)`, and `Context` has no `registry` field — every other test
file in the tree constructs it correctly. The brief then told the implementer *"the tree is green
right now apart from this module being absent, so anything else that goes red is yours."* That was
false, it was the one sentence the agent had to trust, and it returned **blocked** with both defects
correctly diagnosed and correctly refused as not its to fix.

**Generalises to.** When a red is *expected*, the expected red is camouflage for an unexpected one:
a count of failures is not a reading of them, and "these are all the same cause" is a hypothesis
that costs nothing to check and a whole dispatch to skip. Before dispatching against a deliberately
red tree, attribute **each** failure to the absent artefact by name — and where a test constructs a
type it did not define, copy the construction from an existing use rather than inventing it, because
the tree has already written down what that constructor takes.

**It happened again one task later, which changes where this should land.** Task 7.1's test called
`registrar.flush()`; `PackRegistrar` has `commit()` and has never had a `flush`. Same dispatch
wasted, same agent correctly blocked, same cause: a call written from memory rather than copied from
one of the four existing uses in `tests/unit/*/test_init.py` — which also show that `PackRegistrar`
takes its registry **positionally** and that `register` is handed a real settings object, two more
things I had guessed. A recurrence inside one phase means the prose form will not bite.

**The sharper rule, and it is mechanical enough to follow.** Before a test calls anything it did not
itself define, `grep` for one existing call and copy its shape. The tree has already written down
what every constructor takes, and *"I know what that takes"* is precisely the belief both failures
were made of. Pair it with: attribute every failure in a deliberately-red run to the absent artefact
**by name** before dispatching — a count of failures is not a reading of them.

**Candidate home.** `phase-step` → *Red*, where the test is written, rather than *Green*, where it is
dispatched — the mistake is made at authoring time and only *detected* at dispatch time, and
`L6.18` says to route a rule to the artefact that performs the falsifying act rather than the one
that notices afterwards.

### L8.31 — the gate lived where the first caller was, and the second caller gets none

**What happened.** Found by all three of G12's independent reviews, and confirmed directly:
`weft_cli.confirm.gate` is called from exactly one place — inside `weft_cli.cli.run_command` — and
that function takes an `argparse.Namespace` and returns a `Rendered`. The typed result a library
caller needs comes from `Command.run`, and **nothing gates `Command.run`**; the CLI test double's
own docstring states it outright. `confirm.py`'s docstring calls itself *"the invocation seam"* and
says it refuses a pack's `destroy` command *"with no cooperation from its author"* — true for every
caller that goes through `run_command`, and `run_command` was the only caller when it was written.
Phase 7 is the first second caller, and it silently gets no gate at all. `03` also says every
operation the CLI performs is a library call an HTTP route could make identically, and does not say
the gate is not one of them.

**Generalises to.** When a concern is placed at *"the one place that calls X"*, the placement is a
bet that there will never be a second caller — and the bet's expiry date is written down nowhere.
`CLAUDE.md` already says cross-cutting concerns live at the registration seam and never in a rule a
caller must remember; the sharper form is that **"the one caller" is not a seam, it is a coincidence
of the current call graph**, and a docstring calling it a seam is the tell rather than the defence.

**Candidate home.** A fitness function: a `Command` invoked anywhere outside the one gated path
fails. Ledger task 7.0 moves the gate; this is what keeps it moved.

### L8.32 — a gate was one grep from being argued on a false population

**What happened.** G12's brief was written believing there might be no `overwrite`/`destroy`-class
command in the tree at all, and `docs/03-cli.md` said so in two dated blockquotes. Both were true
when written — the 2026-08-20 repair did empty those rows — and neither was re-measured after tasks
5.1a and 5.1b refilled `destroy` the following day with `weft delete` and `weft reconcile`. The same
document records those two commands elsewhere. One registry dump settles it: nineteen commands,
twelve `read`, five `write`, two `destroy`, **zero `overwrite`**.

**Generalises to.** A dated note stating a *count* becomes a false claim the moment a later task
changes the population, and nothing in this tree re-reads it — so a document that reasons from its
own count must re-measure at the point of reasoning, not cite itself. This is `L6.4` in a document
rather than in a marker, and `L6.11` applied to a brief's numbers rather than to its list of sites.

**Candidate home.** A check that a stated count in `docs/` is derivable, or `phase-step` → *Orient*,
which already says to read the population and should say that a document's own count is a
declaration.

### L8.33 — a gate's deciding fact was a query, and its Bring list asked for a judgement

**What happened.** G12's *positions to attack* said of the ceiling: *"establish whether end-to-end is
reachable inside the ceiling before accepting it."* That is not an opinion to form — it is
`weft index`'s permission class, which is `write`, so the answer is yes and one registry dump
produces it. The session's **Bring** list named five documents to read and no measurement to take,
and two of the three reviews spent their first effort finding the same number independently.

**Generalises to.** Where a gate's position turns on a fact about the tree, its brief should name the
**measurement to take**, not only the documents to read — otherwise every participant re-derives it,
and a session can be argued from whichever stale prose it happens to open first.

**Candidate home.** The **Bring** section's own shape in `docs/05-grilling-sessions.md`, which every
future session inherits.

### L8.34 — a table row with no live instance is a rule nobody has tested

**What happened.** `PermissionClass.overwrite` has **zero** registered commands, and `03`'s worked
example for it — *"reindex an existing collection"* — turns out to land as `write`, because node ids
are content digests and the store upserts. So the class whose behaviour G12 spent a session
reasoning about has never been exercised by anything shipped. `confirm.py`'s docstring had already
recorded the identical gap for `destroy` at task 3.3, and 5.1a closed that one by shipping
`weft delete`; the `overwrite` half was never revisited.

**Generalises to.** An enum member with no live instance is a branch whose meaning is whatever its
docstring last claimed — `L6.4` pointed at a rung of a vocabulary rather than at a marker. Either
something declares it, or the vocabulary should say plainly that nothing does and why, so the next
person reasoning about it knows they are reasoning about prose.

**Candidate home.** `03` → *Permissions*, whose table lists the class; or a ratchet over
`PermissionClass` members with no registration, pinned to the ones deliberately unused.


## When the queue is empty

That is the healthy state, and it means the last drain finished. What was learned lives in
`lessons-archive.md`, session by session, with the edges between entries — which is where the
question *have we been here before?* is answered, and where an on/off cycle becomes visible.
