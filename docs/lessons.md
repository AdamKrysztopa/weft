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

### L8.10 — the check passed because it was not yet part of its own subject

**What happened.** Fitness function 17 walks **tracked** files, enumerated from `git ls-files`. Its
own test fixtures necessarily contain the shapes it refuses — a citation of a file that does not
exist, and a citation naming its own filename. It passed six-for-six and the full gate ran green
(1,955 tests). The gate run happened *before* `git add`, so the file was untracked, so it was not
in `git ls-files`, so **the check excluded itself from its own population**. The moment it was
committed it failed on its own fixtures. Nothing between those two states changed except
membership.

**Generalises to.** *A check whose population is defined by a repository predicate — tracked,
staged, published, installed — does not include itself until it satisfies that predicate, so its
first green is meaningless. Run it once more after committing, or arrange for it to be in its own
subject before you believe it.* The near-miss version is worse than the miss: had the fixtures
happened not to trip it, the check would have shipped with a permanent blind spot at its own file
and nobody would have had a reason to look.

**And a second, sharper form of the same thing:** the fix is not to exclude the check's own file —
that is the carve-out that makes the blind spot permanent and deliberate. It is to build the
fixtures from parts so the literal never appears, leaving the file genuinely inside its own
subject. **A check that cannot survive being pointed at itself is not finished.**

**Candidate home.** `phase-step` → *Finish* item 3 already requires watching a new check fail on a
planted case. This adds a clause with teeth: **run the new check once after `git add`**, because
until then it may not be looking at itself. Cheap, mechanical, and it generalises to every
`git ls-files`-derived check this project has.

---

### L8.9 — the citation named this very file, and described a different one

**What happened.** While removing citations that pointed into another codebase, three were found
that pointed *at a filename this repository also has*. `weft_clean/unicode_normalizer.py` carried
**"Verified at source: `unicode_normalizer.py:12-37`'s `process` calls…"** — inside
`unicode_normalizer.py`. There is no `process` method in this file and never was: the citation was
quoting the other project's file of the same name, and read for three phases as an ordinary
self-reference. `weft_clean/property.py:27` and `weft_retrieve/iterative.py` carried the same shape.
The words *"verified at source"* were attached to a claim that was not true of the source they
appeared to name.

**Why nothing caught it.** Every check that could have run passes: the path exists, the file is
real, the line range is in range, and no word-search for the other project's name matches — the
citation is bare. It survives a "does this path resolve?" check precisely *because* the basename
collides, which makes it the one form of dangling citation that a path-existence check is
structurally blind to.

**Generalises to.** *A citation's basename matching a real local file is not evidence that it refers
to that file — and a **self**-citation is the case to distrust most, because it is the one every
mechanical check waves through.* Where a comment says "verified at source", the thing to verify is
that the source says it, not that the source exists.

**Candidate home.** Refines the fitness function `L8.8` and `L8.7` both route to. "Every `path:line`
citation resolves to a path that exists" would have passed all three of these. The check needs a
second clause with teeth: **a citation naming the file it appears in must be justified**, because a
module citing itself by name and line is either redundant (it is describing code the reader is
already looking at) or wrong (it is describing somebody else's file). Both are worth a failure.
Cheap to implement — the citation and the containing filename are both in hand at the same moment.

---

### L8.8 — the sweep was scoped by a grep, and inherited that grep's blind spot

**What happened.** Asked to remove every reference to another codebase from this repository, the
scope was measured with a grep requiring a two-segment path fragment, when the question was the
bare word that fragment starts with. Reported footprint for shipped source: **13
sites in 9 files**. Actual: **277 sites in 89 files**, a 20× undercount, and the number was then
used to size the whole plan, to write three agent briefs, and to tell the project's owner what the
work involved. A dispatched agent found it, not a check — its `## Noticed` asked whether the file
list was "a deliberate narrow first pass or an undercount".

The same agent found a class **no word-search could ever reach**: `weft_llm/loop_guard.py` carries
~15 line-citations naming a module that **exists nowhere in
this repository**. They were dangling pointers into a tree the reader does not have — the exact
defect the sweep existed to remove — and they contain no matchable word at all.

**Generalises to.** *A search term is a hypothesis about the answer, and a scope measured with one
grep inherits that grep's blind spot for the whole task. Before sizing work from a pattern, run the
widest plausible pattern too and compare the counts — a 20× gap between a word and a path fragment
beginning with that word is visible in one extra command and invisible in none.* And the sharper half: **the durable check is
not a better search, it is the property.** "No occurrence of this word" cannot see a dangling
`file.py:NNN`; "no tracked file cites a path that does not exist in this repository" catches both,
and catches the next form nobody has thought of.

**It happened three times in one session, and the third instance is the one that settles the
argument.** (1) The scope grep required a two-segment path fragment when the question was the bare
word: 13 sites reported, 277 actual. (2) The cleanup was then scoped by three *directory* names,
missing `.claude/`, `.github/`, `eval/`, `scripts/`, the dotfiles and seven `NOTICE` files — a
population only `git ls-files` could have enumerated. (3) Every grep in the whole exercise was
**case-sensitive**, so six bold worked-example headings in a skill file — the same word, capitalised
— were invisible to all of them until an agent working from a different angle reported them. Each miss was found by an agent or by the
project's owner; none was found by the person doing the searching, because a search cannot report
what its own pattern excludes. **Three misses, three different mechanisms — narrowness, scope, case
— and one shape: the searcher grading their own search.**

**Convergent evidence, worth stating because it is unusual.** Three agents working on disjoint
parts of this sweep, unable to see each other's findings, each independently reported the same gap
and each proposed the same remedy: make it a check on the property rather than a better search. A
recommendation reached three times from three different slices of the tree is not a preference.

**Candidate home.** A **fitness function** — every `path:line` citation in a tracked file resolves to
a path that exists in the tree, waiver pinned empty. It attaches to no new seam (it is a sweep over
tracked files, like FF16's), it subsumes the word-search this task actually needed, and it is the
answer to `L8.7` as well. Secondarily `phase-step` → *Orient*, which already says a list in a
document is where to start looking rather than a census (`L5.14`) — this is that rule applied to a
**grep**, which is the form it keeps coming back in.

---

### L8.7 — an arrangement that was safe while the repository was private, and nobody scheduled its end

**What happened.** This project was built while reading a sibling codebase for reference, and the
practice of citing that reading — `path:line`, measure-before-asserting — was written into
`CLAUDE.md` as a rule and followed diligently for eight phases. The result, counted on the day it
was finally questioned: **hundreds of citations across `packages/`, `tests/` and `docs/`, including
13 inside shipped wheels**, pointing at paths that resolve only through one developer's untracked
symlink. A stranger who installs `weft-rag` reads them. Nobody noticed because every individual
citation looked like diligence — it *was* diligence — and the rule that demanded the evidence is the
same rule that spread it. Raised by the project's owner, in anger, and correctly.

It was cheap to detect at any point — one `git ls-files | grep` for the name, at any moment in
eight phases — and nothing ever ran it.

**Generalises to.** *An arrangement that is safe while a project is private becomes a liability the
moment it ships, and its cleanup has to be scheduled when the arrangement is adopted — not when
somebody notices. A convention that produces a growing number of references to anything outside the
repository needs a stated end condition at the moment it is written down, because by the time it is
obviously wrong there are hundreds of them and removing them requires rewriting history.*

**Candidate home.** The same fitness function `L8.8` proposes — the two are one subject and should
be drained together. Beyond the check, `CLAUDE.md`'s own standing rules are where a convention with
a growing footprint should have to state what ends it: a rule that accumulates artefacts is not
finished until it says when it stops.

---

### L8.6 — the repair made a dormant restriction reachable, and I reviewed the repair without re-reading the restriction

**What happened.** Task 8.3 turned the router's name from a constant into `[services] route`, so an
operator can now select a router. `weft_cli.route_ask.run_routed_ask` searches `load_contributed`
— packs only — which is Phase 2's settled behaviour and which 8.3 deliberately did not reopen. The
consequence, measured under `weft-qualities` and not before: a project-local
`pipelines/my-router.yaml` resolves under `weft pipeline show` and runs under
`weft ask --pipeline`, and `[services] route = "my-router"` refuses it. I had read the restriction,
quoted it in three docstrings as *"Phase 2's settled behaviour, not reopened here"*, and never asked
what the *new* key did to it: while nobody could substitute the router at all the restriction was
invisible; the moment a key invites you to name one, half the ways of having one silently do not
count.

**Generalises to.** *Making something configurable does not preserve the restrictions around it —
it exposes them. When a change turns a constant into a choice, re-read every rule that scoped the
constant and ask what it now means to somebody exercising the choice, because a rule that was
unobservable is not the same rule once it can be hit.* Citing a restriction as unchanged is not the
same as checking it is still right.

**Candidate home.** `weft-qualities` lens 1's producing/consuming paragraph, which already asks
*"can a stranger reach both sides?"* and would have caught this if it also asked *which* stranger —
this seam is whole for a pack author and half-built for a project author, and the lens has no prompt
to try both. Possibly also `phase-step` → *Orient*, beside "read the population, not the
declaration": when a change makes a value configurable, the population to re-read is the rules that
assumed it was fixed.

---

### L8.5 — seven documented configuration surfaces, none of which had ever worked

**What happened.** `corrective`, `iterative-retrieval` and `refine-on-uncertainty` each resolve a
sibling plugin by name through `StageLookup` and each publishes `*_config` fields — seven between
them (`primary_config`, `grader_config`, `knowledge_action_config`, `leaf_config`,
`sufficiency_config`, `retriever_config`, `signal_config`), every one typed
`Mapping[str, object] | None` and documented in its own docstring as *the* way a pipeline document
retunes that sibling. `RegistryStageLookup.build` passed the mapping straight to `entry.factory`,
so the sibling was built with a raw `dict` where its config object belonged and died later inside
its own `run`: `'dict' object has no attribute 'channels'`. Requirement 6 — *"every piece of it is
parameterisable"* — was false at all seven, `10` §1.1 describes several of them as if they worked,
and the whole suite was green, because **every test that drove these plugins left the sibling's
config at `None`**. Found by running `weft ask --pipeline corrective-retrieve`, the first caller in
the tree's history to set one. `tests/unit/weft_retrieve/test_engine.py`'s own `_echo_factory` had
been written as `_Echo(config if isinstance(config, _EchoConfig) else None)` since the file was
created — the defect's own workaround, sitting in the test that was supposed to prove the seam.

**Generalises to.** *An optional parameter that every test leaves unset is an untested parameter,
and a test helper that defensively narrows a type the production caller does not narrow is a
recorded sighting of the bug.* The general move: where a field is documented as the way to
configure something, at least one test must actually set it — and an `isinstance` guard in a test
double is a question to ask, not a convenience to write.

**Candidate home.** Grouped with `L8.4` (both are "the gate agrees with itself and not with the
artefact"). Two candidate mechanisms: a check that every `Mapping[str, object]`-typed config field
on a registered plugin is set by at least one test or one shipped document — the ladder makes the
second half cheap now — and a note in `phase-step` → *Red*, beside the existing "assert the fact a
field means", that a defensive `isinstance` in a test double is evidence about production.

---

### L8.4 — two static checks agreed, and the binary said the feature had never run

**What happened.** Phase 8 shipped `index-with-raptor` and `index-with-questions`, the first
documents ever to place `raptor` and `hypothetical-questions` — tasks 2.31 and 2.32, shipped in
Phase 2. Both documents pass fitness function 11(b) (every shipped pipeline resolves) and fitness
function 16 (every registered pipeline position is placed). Running them from `/private/tmp` against
the real container: `no service is registered for Embedder on this run` and the same sentence for
`Prompts`. Both plugins reach an ambient service through `ctx.require`; `weft_cli.run_services.
build_services` builds those for the **query** path and `weft_cli.ingest.run_index` builds none at
all. So two index-path techniques have **never been runnable through the CLI** in the one place they
belong, for two phases, with every gate green — their exit demonstrations were unit tests handing
the context in directly.

**Generalises to.** *A contract's plugins are only proven runnable where a **driver** assembles what
they require — so a new contract's first task must name its driver, and a plugin whose only
execution evidence is a test that constructs its own `Context` has not been shown to run in
production at all.* Resolution proves a name binds; it says nothing about what the run will provide.

**Candidate home.** `phase-step` → *Finish* item 4 already requires running the binary and this
slipped past because the plugin had no shipped document to run it *through* — so the sharper
placement may be a check: every contract with a registered plugin has a driver that builds the
services those plugins `ctx.require`. Possibly a clause of fitness function 5 (*every declared
capability resolves*), which is the nearest existing neighbour and today asks a weaker question.

---

### L8.3 — the manual named two of three keys, and the whole gate was green

**What happened.** Task 8.3 added `route` to `[services]`. `manual/troubleshooting.md:1007-1028`
carried a worked transcript of the unknown-key refusal printing `accepts embed, store`, plus
`(exc.valid_options == ("embed", "store"))` and the sentence *"the only two keys `[services]`
reads"* — all three stale the moment the field landed, and `ci-checks` stayed green through the full
1,929-test run. The block is quoted prose, not a tagged executed sample, so nothing compares it to
anything. `L6.19` already says exactly this and is marked **Applied**; it did not bite, because what
was applied was a rule about writing new transcripts rather than a mechanism that finds the existing
ones a change falsifies.

**Generalises to.** *`L6.8` with a fresh instance — a rule that is re-learned did not bite, so it is
in the wrong artefact.* The specific move: a change to a typed surface an operator configures
(`ServiceSelection`, `LLMRoles`, a `valid_options` tuple) must be answerable by a **lookup** of
which pages quote that surface, the way `tests/docs/test_pack_guide_samples.py` already makes
"which guides quote this file" a lookup rather than a recollection — never by remembering to grep.

**Candidate home.** Extend the pack-guide sample index to `[services]`/`[llm.roles]` key lists, so a
manual page naming a key set is checked against the model the way a quoted file already is. Grouped
with `L8.4` under *the gate agrees with itself and not with the artefact*.

---

### L8.2 — a waiver reason that was true, and still the wrong answer

**What happened.** Writing fitness function 16, two registered `RoutingPolicy` plugins
(`threshold-ladder`, `always`) turned out to be placeable by no document anybody could ship: the
router's name was a constant in `weft_cli.route_ask`, a pack cannot contribute a second document
under a held name, and a project shipping its own `route.yaml` is refused by `full_catalogue` —
which does not merely lose the override, it fails every `weft pipeline` command. That is a true,
checked fact about what can be run, which is precisely the standard the new waiver's own docstring
sets, so the entry was drafted and would have passed review. The repair — `[services] route`,
resolved like `embed` and `store` — is four lines and one call site, and it turned the fact into a
former fact. What stopped the waiver was a `PreToolUse` guard firing on a waiver-shaped collection
gaining an entry, and a standing user preference for the strongest technical option; neither was the
check itself.

**Generalises to.** *A waiver reason must be a fact about the artefact — that is necessary and not
sufficient. The question after establishing it is whether the fact should hold, and a fact that a
short repair would remove is a defect wearing a waiver's clothes.*

**Candidate home.** `weft-qualities`, which reviews for exactly this class and would have asked
requirement 4's question of a registered plugin nothing can place. Possibly also the waiver
convention itself (`08` §3): a waiver entry states its fact **and** what would have to change for
the fact to stop holding, so the reader after next can price the repair instead of re-deriving it.

---

### L8.1 — `--check-live` compared two phase names by substring and reported agreement

**What happened.** `next_task.py`'s live check asserts the Status block's phase and the first
unticked task's phase are the same, via
`task.phase.split("—")[0].strip() not in stated` — a **substring** test over a prose table cell.
Phase 8 is the project's first phase that deliberately runs out of ledger order (no gate; Phase 7 is
blocked by G12), so `docs/README.md`'s Phase cell now reads *"Phase 8 … It runs before **Phase 7**,
which G12 still gates"* while the first unticked box is `7.1`. The two genuinely disagree, the cell
contains the string `Phase 7` because explaining the ordering requires naming it, and the check
printed *"live check ok — its phase agrees with 7.1"*. Its **premise** is also now false: the two
phases can legitimately differ, which is what the Next action row exists to carry.

**Generalises to.** *A containment test between a prose field and an identifier reports agreement
whenever the prose mentions the identifier for any reason — including to say it does **not** apply;
and a check whose premise is "these two must name the same thing" needs re-argued the first time the
project makes them legitimately differ, rather than loosened until it passes.*

**Candidate home.** `.claude/skills/phase-step/scripts/next_task.py` → `live_checks`. The repair is
two things, not one: compare the Status cell's **first** phase identifier for equality rather than
containment, and replace the premise — the real invariant is *the Next action row names a task that
exists in the ledger*, which holds whether or not the phases match, and which nothing checks today.
Sits beside `L6.3` and `L6.4`, both of which are this same script.

---

### L7.9 — the precondition was written down, in this repository, and not checked before acting

**What happened.** `v2.1.0` was tagged and every publish job was refused with
`429 Too many new projects created`. Nothing reached PyPI; `weft-rag` never ran, because its job
needs the five before it.

The precondition was already written, twice, by this repository: `L7.3` — *"the limiter counts
**attempts** over a rolling window rather than successes"* — and the task brief's own
*"no retry against PyPI until its window has been left alone for hours"*. What was reasoned about
before tagging was the **size** of the burst (six serialised creations instead of nineteen
parallel), which is a different variable from the one the limiter actually counts. The window was
still carrying roughly a hundred attempts fired earlier the same day.

**The measurement, since nobody had one.** The saturating run was `08:53Z`; this one was `13:04Z`
and was refused on its *first* request. So the window outlasts **four hours** at that volume —
"hours" was the guess, and it is at least that and possibly much longer.

**Generalises to.** When a rule names a cooling-off period, the check before acting is *how long
since the last attempt*, not *how much smaller this attempt is* — a rate limiter that counts
attempts is unaffected by making the next one smaller.

**Candidate home.** `.github/workflows/release.yml` — **built the same day**, before the drain: a
`cooling-off` job that every publish job needs, refusing when the previous Release run failed less
than twelve hours ago and naming the recovery, with a `workflow_dispatch` `force` override for the
case where PyPI has granted an exception. Built rather than queued because the rule had already
failed twice as prose and the third failure would have been a published version number. What is
still open for the drain is whether the same shape belongs anywhere else — `L7.3` and this entry
drain together.

**Found while building it, and worth as much as the entry above.** The workflow could not be
re-run after a partial failure at all: `v0.1.0` published four of twenty, so a full re-run would
have failed on `File already exists` for exactly the four that *succeeded*. `uv publish
--check-url` makes an upload idempotent and is now on both publish steps. A release job that
cannot be re-run turns every partial failure into hand-work, which is how the seven-attempt retry
loop L7.3 records became the only visible option.

### L7.8 — the gate I ran and the gate CI runs were not the same gate

**What happened.** The consolidation was declared done on a green `poe ci-checks`: 1,867 passed,
**93 skipped**. CI ran the same task and got 1,917 passed, **42 skipped**, and failed on
`tests/docs/test_quickstart.py:156` — a pattern anchored on `^weft-store\b[^:]*: active` against
`weft plugins doctor` output that now reads `store (weft-rag) 2.1.0: active`. Fifty-one tests need
the `compose.yaml` container and skip without it. I had brought the container up mid-task to drive
the shipped binary end to end, then run `docker compose down -v` to tidy up, and every gate run
after that silently covered fifty-one fewer tests than CI's.

The skip count was printed on every one of those runs and read past. It is the only signal that the
two gates differ, and `CLAUDE.md`'s "a green gate is not a working binary" does not cover this
case — the binary *was* run, and correctly; what was not run was a fifth of the suite.

The assertion itself had been broken the same way once before: task 6.4 put the installed version
between the name and the status, and the comment above the line already says *"the fact is
'weft-store is reported active', never the literal line"* — then anchors on `weft-store`, which is
the literal line one field further left.

**Generalises to.** A skip count is a coverage number: when a suite's skips depend on an external
service, the gate is not green until it has been run with that service up, and the count is what
says whether it was.

**Candidate home.** `CLAUDE.md` → *Quality gates* (`ci-checks` is only the canonical gate with the
container running), or a `poe` task that refuses to report success when a container-dependent suite
skipped — the number is already there, nothing reads it.

### L7.7 — a derivation that agrees with the tree until the tree changes shape

**What happened.** Five separate files derived a distribution's import package as
`project.name.replace("-", "_")` — `tests/architecture/test_ff12_unresolvable_name_carries_options.py`,
`test_ff12b_a_repack_keeps_valid_options.py`, `tests/docs/test_troubleshooting_coverage.py`,
`scripts/publish_set.py` and `tests/architecture/test_isolated_installs.py`. It was correct while
every distribution shipped exactly one package named after itself. `weft-rag` ships fourteen and is
named after none of them, so the derivation produced `weft_rag`, a module that does not exist. Three
of the five failed loudly. **`scripts/publish_set.py` did not**: `check_isolated_installs.py` builds
a probe from `member.module`, so it would have installed the bundle alone and imported nothing while
printing success — fitness function 1's generalisation passing by importing zero modules. It was
caught because a *different* test asserted the module was a directory on disk.

Four of the five carried a docstring explaining that the computation was deliberately **restated
rather than imported** across test modules ("one self-contained scenario"). That convention is what
turned one wrong line into a five-file repair, and it is worth knowing that is its price.

**Generalises to.** A structural derivation (`name` → path, `name` → module, one-of-X-per-Y) is an
assumption about the tree's shape, not a fact about a name — read the shape instead, and where the
derivation must be duplicated, duplicate a call rather than a rule.

**Candidate home.** `tests/architecture/conftest.py` now holds `first_party_source_roots()`; the
open question is whether the four restated copies should call it, which means deciding what the
"restate rather than import" convention is actually protecting.

### L7.6 — the plan named a mechanism that does not work where it is needed

**What happened.** The brief for deriving `weft --version`'s own distribution named
`importlib.metadata.packages_distributions()`, and it is the obvious answer. Run in this
repository's own venv it returns `None` for `weft_cli`: it maps import packages to distributions by
reading installed **file records**, and an editable install records only a `.pth`. The first
implementation was written, and the failure surfaced as a test asserting exit 0 and getting 1 — not
as anything the API's documentation would have suggested. The working derivation is the
`console_scripts` entry point pointing at `weft_cli.cli`, which is written for an editable install
and a wheel alike, and is also a better answer: it reports the version of the thing that actually
put `weft` on the reader's PATH.

**Generalises to.** Before building on a packaging or metadata API, run it in the environment the
code will actually run in — a dev checkout is an environment, and editable installs are where
metadata APIs most often answer differently.

**Candidate home.** `CLAUDE.md` → *Quality gates*, beside "a green gate is not a working binary";
this is the same rule one layer down, aimed at an API rather than at a command.

### L7.5 — the guide recorded a gap that had been closed for two weeks

**What happened.** `manual/pack-author-guide.md` §9.3 carried a paragraph headed "Honest gap, not a
pattern to copy", stating that every `examples/*/pyproject.toml` declared its `weft-*` dependencies
as bare names, with a worked example and a note that closing it was "one short follow-up task".
Ledger task **6.26** closed it, added `tests/architecture/test_example_packs_are_exemplars.py` to
keep it closed, and left the paragraph standing — so the guide went on telling pack authors that
the tree's own examples taught the wrong thing, while a fitness function enforced the right one.
Found only because this task happened to be editing the surrounding paragraph.

**Generalises to.** A documented gap needs the task that closes it to name the document — a
prose "honest gap" outlives its own repair by default, and no check in this tree can see one.

**Candidate home.** `phase-step` → *Finish*, or a check that every "gap"/"not yet"/"follow-up"
paragraph in `manual/` names a ledger task and fails when that task is ticked.

### L7.4 — a comparison that collapsed twelve rows into one and still passed a type check

**What happened.** Three separate readers indexed reports by distribution name:
`weft_cli.registry_bootstrap.require_active` (`{report.distribution: report}`),
`tests/architecture/test_ff2_no_privileged_builtins.py`'s contribution counter (a dict comprehension
keyed the same way), and `weft_eval.run_record.active_distribution_set` (a sorted list, not a set).
Every one of them was correct while each distribution shipped one pack, and every one of them
silently kept whichever report came last, or repeated a name twelve times, once one distribution
shipped twelve. FF2 was the only one that failed loudly, and only because it compared 102 written
registrations against the 1 the collapsed dict reported. `require_active` would have answered about
an arbitrary pack — the check that stops `weft index` running without an extractor.

**Generalises to.** A dict keyed on a field that is *currently* unique is an unstated uniqueness
assumption; where the key is an identity that may become shared, index on the identity that is
unique by construction and say which one that is.

**Candidate home.** `weft-qualities` — the identity a surface keys on is a design question, not a
coding one, and this is the second time in one task that the answer was "the entry-point name".

### L7.3 — the retry was the thing keeping the door shut

**What happened.** `v0.1.0` published 4 of 20 distributions; PyPI refused the rest with `429 Too
many new projects created`. It was read as a PyPI limitation and put on a 40-minute retry loop.
Seven attempts later the count was still 4. The limiter counts **attempts** over a rolling
window rather than successes, so every rerun of the fifteen failed jobs re-saturated it — on the
order of a hundred creation requests fired to achieve nothing. Retrying was not neutral; it was
the mechanism preventing recovery.

Underneath it, the actual defect was ours: `.github/workflows/release.yml` published a
nineteen-job matrix in parallel, which asks PyPI to create nineteen new projects within seconds.
Serialising (`max-parallel: 1`) removes the burst and costs wall-clock on a job that runs once
per release.

**Why it was invisible.** The flaw exists **only on a first publish**. Every later release
uploads a version to a project that already exists, which is not rate-limited the same way. So
the code was correct in every scenario except the single one it had never been run in — the same
shape as `L7.2` (a CI workflow that had executed zero times) and as the lockfile nothing had
needed until a clean checkout needed it. Three findings in one day, all of them a path taken for
the first time in production.

**Generalises to.** Two rules, and they are separable. *A retry against a rate limiter is only
safe when the limiter counts outcomes; when it counts attempts, retrying moves recovery further
away* — so before automating a retry, establish which kind of limiter it is, and treat "the
count did not move" as evidence of the attempt-counting kind rather than of bad luck. And: *a
burst is a design decision, not a scheduling detail* — fan-out against a shared external quota
needs a stated concurrency bound at the point the fan-out is written, not after the first refusal.

**Candidate home.** The retry half is the sharper one and has no natural artefact yet: it is not
a fitness function (nothing in the tree can test PyPI) and not `CLAUDE.md`'s gate section. It may
belong wherever this project writes about acting on external services — `ADAM_TODO.md` is where
the release obligations live, and `09-release.md` §5.2 owns the publish path. The burst half is
narrower and already fixed at the site; what would generalise is a rule that any matrix or
`gather` against a third-party service names its bound in the same diff that creates it — which
would also have caught `weft_index.raptor`'s unbounded `asyncio.gather`, found the same day by a
different route. That coincidence is the argument for one rule rather than two.

### L7.2 — the gate had never run anywhere but one laptop, and nobody could have noticed

**What happened.** The first CI run this repository has ever had failed three of its four jobs at
their first step: `error: Unable to find lockfile at uv.lock, but --frozen was provided`.
`.gitignore:17` listed `uv.lock` under `# Tooling`, between `.ruff_cache/` and `.pyright/`, and it
had never been committed in seventy commits. `ci.yml` runs `uv sync --frozen` in `gate` and
`sdists`, and `isolated-installs` needs a populated environment to import pydantic; only
`kernel-isolation` survived, because its script imports nothing outside the standard library.

**Why it was undiscoverable.** There was no git remote until 2026-09-05. `ci.yml` was written in
Phase 0, has been cited and maintained since, and had **executed zero times**. Meanwhile
`poe ci-checks` was green on every run — because a developer's `.venv` and their untracked
`uv.lock` were both already sitting there. The gate passed by a path CI does not have, and the two
paths could not be compared while only one of them was ever taken. `uv lock --check` resolves 145
packages unchanged, so nothing had drifted: the resolution was correct and merely unshared.

This is `01`'s own rule one level out. *A green gate is not a working binary* was learned about a
binary nobody ran; this is a gate nobody ran **elsewhere**. A CI workflow that has never executed is
prose in exactly the sense `L6.12` means it — a directory of tests no task runs — except that it
looks more like a check than prose does, because it is written in YAML and lives where CI would find
it.

**Generalises to.** *A workflow that has never executed is a claim, not a check — and an artefact
whose absence only breaks a path nobody takes is invisible until someone takes it.* Anything the
gate needs must be in the repository, not in the environment of whoever last ran the gate; the test
is whether a clean checkout on a machine that has never seen this project can run it.

**Candidate home.** Two candidates, and they answer different halves. A fitness function could
assert that everything `ci.yml` and `release.yml` reference exists as a tracked file — cheap,
runs locally, would have caught exactly this. `CLAUDE.md` → *Quality gates* is the other: it already
says a green gate is not a working binary and could say that a gate that has run in one environment
is not a gate. The deeper point may belong wherever a phase declares itself complete — Phase 0's
exit was ticked with its CI never having run once, and no check asked.

### L7.1 — a task filed with its remedy already chosen had chosen the wrong one

**What happened.** Phase 6's close filed **6.33** from a diagnosis made in the moment: FF8's canary
assertion was failing under `pytest tests/docs tests/architecture`, a bisect named five `tests/docs`
modules that import the canary through `discover_for_reference()`, and the task was written as
*"stop them"* — with the remedy named, and even a shortlist of candidate seams. Doing it did not
work. Four of the five could be pointed at a restricted helper; the fifth was
`tests/unit/weft_cli/test_contract_reference.py`, which calls the open function five times and
**cannot stop**, because testing that function is what those tests are for.

There was never a set of callers to discipline. Any session that tests open discovery imports the
canary, so an in-process `sys.modules` guard could not survive — and the real repair was to the
*mechanism*: run the probe in a fresh interpreter, which FF8's own docstring had already argued for
in the sibling test beside it. The filed remedy was not merely incomplete; it was impossible, and
the only way to learn that was to attempt it.

**Why the filing was confident and wrong.** The bisect answered *"which files, run before FF8, make
it fail?"* — a real question with a real answer. It did not answer *"can each of them stop?"*, and
nothing in the failing output distinguished the two. A close-out review is exactly where this is
likely: the diagnosis is made with the evidence in hand and the fix is written from the same glance.

**Generalises to.** *A ledger task states the property that must hold, not the repair that will make
it hold* — a filed remedy is a hypothesis formed before anyone tried it, and it arrives carrying the
authority of the ledger. Where a filing does name a candidate fix, it says so as a candidate and
names what would falsify it.

**Candidate home.** `implement-ll` → *The two traps*, which already says a task written from one
instance narrows to that instance (`L6.13`); this is its sibling — a task written with its cure
prescribed narrows to a cure that may not exist. Possibly also `phase-step` → *Orient*, where a task
is read: a remedy in a task line is the previous author's guess, and the property above it is the
part that binds.

---

*Last drained 2026-08-25 at Phase 6's close — seventeen entries, five subjects, in
`lessons-archive.md` under that date, with their edges and the loop's own check answered: three of
this phase's defects would have been caught by rules already **Applied**, so all three moved to the
step that executes them rather than being restated.*

---
## When the queue is empty

That is the healthy state, and it means the last drain finished. What was learned lives in
`lessons-archive.md`, session by session, with the edges between entries — which is where the
question *have we been here before?* is answered, and where an on/off cycle becomes visible.
