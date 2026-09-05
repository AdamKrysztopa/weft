# 09 — Release

**What this document owns:** the distribution and publishing model, the user-facing version policy,
the support and deprecation surface, the validation prerequisite, the production-readiness checklist,
and the protocol for adjusting the plan. It restates nothing that `01`, `02`, `03` or `05` already
owns; where it needs one of their statements it links to it.

**Why a new document rather than more of `01`.** `01` owns *the phase script and the fitness
functions*; it does not own policy about published artefacts, and adding a version policy, a support
window and a release checklist to it would make the largest document in the plan the owner of a sixth
unrelated subject. Phase 6's **Read** line points at this document, exactly as Phase 0's build order
points at `06`.

---

## 0. What this document deliberately does not decide

**G9 is open, and this document depends on it in five places.** Not one — five. Each is stated below as a
question in §2.3 and nowhere else; no section of this document answers any of them:

| # | The dependency | Where `05` → G9 already claims it |
|---|---|---|
| 1 | Whether version skew is **reported or refused** by `weft plugins doctor` | G9 *Done when*: *"a decision on whether `weft plugins doctor` reports version skew"* |
| 2 | What **0.x promises about published contracts** — whether a contract may move without a deprecation period | G9 *The question*: *"what is owed to a pack when one changes"* |
| 3 | The **deprecation clock and its unit** — releases or months, and how many | G9 *Positions to attack*: semver per contract *"with a stated support window"* is one of three positions, not the default |
| 4 | **Which published surfaces carry a compatibility promise at all** — the payload model, the store capability protocols, the filter AST, `Disclosure`, the `Command` permission `ClassVar`, `[packs] allow` | G9 *Bring* enumerates exactly these, which is the proof they are G9's and not this document's |
| 5 | What a **version bound** on an intra-repository dependency means — floor, compatible range, or exact pin | G9 *Positions to attack*: semver / single library version / capability negotiation |

That the dependency is structurally safe is a separate point and still true: G9 is already Phase 5's
gate, so it is settled before Phase 6 can begin. Safety is not licence — a section that assumed an
answer would settle G9 by implication rather than by argument, which is what §2.3 exists to prevent.

Fitness function 10 clause (b) is the only place where this document states anything adjacent to G9, and
it states the weakest claim available: that a bound **exists**. `01` → *Fitness functions* item 10 argues why that is implied by all three of G9's positions and
chooses none of them.

**G2, G7 and G8 are open and this document assumes nothing about them**, with one visible dependency: if
G8 settles as anything other than "shell", the REPL's surface changes and §3's table of candidate
public surfaces gains rows. Recorded here so it is not discovered at release time.

**A new gate was proposed here, and this document did not settle that one either: G10.** `05` → G10
is the session; it ran on 2026-08-22 and the decision log records it **Settled**. §1, §2.2 and §3
state its outcome, each marked where it does — written *after* the session, which is the whole point
of the paragraphs that follow. The rule §2.3 applies to G9 holds for G10 as well, and it has
to: a document that guards someone else's gate scrupulously and settles its own by implication has
only moved the defect one gate over. `01` → *Phases* is explicit that *"a gate is not advice"*: a
session whose positions are already marked kept and rejected in the document it is told to **Bring** is
a formality, not a session.

So **§1 and §2.2 were written as the position this document recommends and the argument for it, never
as a verdict.** Every judgement they made was carried into `05` → G10 → *Positions to attack* as the
case to beat. A session that opens from a strong recommendation is still a session; one that opens
from a decision is not. **G10 ran on 2026-08-22 and kept all three recommendations** — with one of
§1's own premises falsified by measurement on the day (§1's opening note), and two questions the
session had to answer that neither this document nor `05` had asked: whether a 1.0 release set may pin
a 0.x distribution, and what the support window actually is. Both are recorded below, in §2.2 and §3.

| # | What G10 decides, and this document does not | Where this document recommends rather than decides |
|---|---|---|
| 1 | **The unit of release** — lockstep, independent semver alone, or independent versions plus a named release set | §1 argues for the third and states the case against the other two. `05` → G10 carries all three |
| 2 | **What 1.0 rests on** — a checklist of demonstrations, or a date | §2.2 recommends demonstrations and enumerates them. `05` → G10 carries both |
| 3 | **What the release checklist is stated against**, and therefore what the Phase 6 exit criterion installs | `01` → Phase 6's **Exit** installs *whichever unit G10 names*; §5.2 says the same for its checklist |

**What G10 returned, on 2026-08-22, for each of the three rows above:** (1) independent semver plus a
named release set, §1; (2) 1.0 rests on evidence, with a date-boxed review that publishes the gap
rather than shipping past it, §2.2; (3) the checklist is stated against the release set, and the
Phase 6 exit installs it, §5.2. Two further answers the session was forced to give, recorded where
they belong rather than here: a 1.0 release set pins **only** distributions at 1.0 or above (§2.2),
and the support window is the current major plus the previous one for a release-set major or six
months, whichever is longer (§3).

Two things G10 does **not** decide, recorded here so they are not read into it. Where a deprecation
notice is emitted follows from the settled rule that cross-cutting concerns live at the registration
seam (§3) — its *clock* is G9's, its *home* is neither gate's. And fitness function 10's two clauses
hold under every position either gate can take, which is why they are stated as weakly as they are.

---

## 1. What a release is when there are several distributions

*(**Settled 2026-08-22 by G10: the recommendation held.** The unit of release is **independent semver
per distribution plus a named release set** — a code-free distribution `weft-rag` pinning one
exactly-tested combination. The case below is the argument that survived the session, and the two
alternatives are kept with their attacks because a settled position whose rejected siblings have been
deleted cannot be re-examined. **One fact moved during the session and is recorded here rather than
left in the brief:** `05` → G10's *Bring* asked for a count of distributions declaring a bound on a
sibling and predicted the answer was zero. Taken on the day, it is **all of them** — G9's enforcement
rule landed in Phase 5, so every distribution under `packages/` now declares `>=X,<MAJOR+1` on each
sibling, `weft-cli` on nine of them. That removes one of the three arguments this section used to make
for the release set — bounds are no longer missing — and strengthens the one that remains: bounds say
what is *compatible*, and only a pinned set says what was *tested together*.)*

> **G10 was reopened and re-settled on 2026-09-05: twenty published names became six, and the
> release set became the thing it used to pin.** The shape G10 chose — a code-free distribution
> pinning an exactly-tested combination — met a real index at `v0.1.0` and the cost showed up
> immediately: nineteen new PyPI projects requested in one matrix, fifteen refused with
> `429 Too many new projects created`, four created (`lessons.md` L7.3). That was the visible
> half. The measurable half, taken from the twenty manifests with a parser: **ten of the twenty
> declared no external dependency at all**, so installing without one of them avoided nothing.
> They were separate distributions for architectural symmetry, and symmetry is not a user-visible
> benefit.
>
> **What ships now:** `weft-rag`, containing the fourteen packs' code and their twelve entry
> points, plus `weft-kernel` (separate because fitness function 1 installs it alone and imports
> it, which is what proves the kernel names no capability) and four add-ons — `weft-openai`,
> `weft-pdf`, `weft-qdrant`, `weft-otel` — each carrying a dependency somebody may decline.
>
> **What G10's argument keeps.** A third-party pack still installs *beside* `weft-rag` on exactly
> the terms `weft-qdrant` does, so requirement 4 holds at the packaging layer, which was the one
> thing this section chose the release set for. Fitness function 10(a) still compares two sources
> that can genuinely disagree: the release job's own matrix against the workspace members that do
> not opt out. And what "tested together" means is now stronger rather than weaker — the members
> cannot disagree about a version, because there is one version.
>
> **What it gives up, on the table rather than in a footnote.** Independent semver for the
> fourteen: they versioned separately and now share one number, so most of the skew G9's machinery
> was built to manage stops existing (contract versions are a separate axis and are untouched).
> Per-pack isolated-install proof: task 6.6's check narrows to the six, and the fourteen get an
> import assertion against the built wheel, which is weaker and is labelled weaker in
> `scripts/check_isolated_installs.py`. And four names — `weft-command`, `weft-embed`,
> `weft-generate`, `weft-llm` — are already on PyPI at `0.1.0` and cannot be deleted; they are
> vestigial, receive no further versions, and are recorded so a future reader does not think they
> were lost.
>
> **What made it affordable, and it was not packaging.** The first attempt at this was rejected on
> 2026-09-05 because bundling collapsed twelve `weft plugins doctor` rows into one name and twelve
> `[packs.*]` settings namespaces into one. The root cause was that `distribution` was doing two
> jobs — the thing PyPI installs, *and* the pack's identity in every operator-facing surface. They
> are separate now: a pack's identity is its `weft.packs` entry-point name (`02` §2 → *Pack
> settings*), which was already unique and already there. Consolidation became ordinary work only
> after that.
>
> **The name is `weft-rag`, not `weft` — corrected 2026-08-25 at ledger task 6.13.** G10 settled
> the *shape* (a code-free distribution pinning one exactly-tested combination) and named it
> `weft`; that name is **taken on PyPI** — "The durable task substrate for agent systems", 99
> releases, and its release list includes the `0.1.0` this set declares, so `uv add weft` gets a
> different project today. Nineteen of the twenty names here are free and this was the twentieth.
> Nothing else about G10's decision moves: the shape, the exact pins, the standing it gives a
> third-party pack, and fitness function 10(a) are all unchanged, and **the command a user types is
> still `weft`**, because that is `weft-cli`'s console script. Found by installing from a real
> index rather than by reading the plan — `docs/lessons.md` **L6.33**, whose rule is that a name is
> a claim on a namespace somebody else owns, checked when it is chosen and not when it is
> published.

`01` → *The architecture stack*, Topology row, already records the cost this section pays: several
distributions to version and release together, and skew between the kernel and a first-party pack. It
lands that obligation on G9. This section makes the argument about the half G9 does not own: what the
unit of *shipping* is.

**The problem in one sentence.** `weft-kernel` and each pack version independently — which is not an
accident but the point, because a third-party pack versions independently too, and requirement 4 says
built-ins get no privileged path. If first-party packs must move together while third-party packs
cannot, then "release" is a privilege built-ins have and outsiders do not, and rule 4 has rotted at the
packaging layer instead of the registration layer. Same failure, one floor down.

| Model | What it means | The argument this document makes about it |
|---|---|---|
| **Lockstep** — one version, all distributions bumped together | Simple, coarse, familiar | **Rejected (G10).** It also now contradicts G9, which makes a distribution's major a function of the contracts *it* publishes — `weft-store` and `weft-command` are already `2.0.0` while the kernel is `0.1.0`, so lockstep would either falsify those numbers or force a major on every distribution for one contract's break. Beyond that, it is exactly the privileged path above, and it forces a kernel release for a pack's typo fix, which makes the kernel's version meaningless as a compatibility signal |
| **Independent semver per distribution, and nothing else** | Honest about what actually changes | **Rejected as insufficient on its own (G10).** The session's counter — publish the tested combination as a table in the release notes — was attacked with this repository's own evidence: `CHANGELOG.md` was written once and went stale by five phases (`lessons.md` L5.8), and a combination nothing installs and nothing checks is that artefact again. A user installing five distributions has to discover a working combination themselves, and *"which versions were tested together"* has no answer |
| **Independent versions plus a named release set** | Each distribution versions on its own; a thin meta-distribution `weft-rag` depends on an exactly-tested combination and is what a newcomer installs | **Settled — this is the unit of release (G10, 2026-08-22).** It is the only one of the three that gives a third-party pack the same standing as a first-party one — `weft-graph` would *not* be in the release set and would install beside it, exactly as `weft-store-qdrant` does. It is also the only one a check can hold to account: the set's pins and the workspace's own distributions are two sources that can genuinely disagree, which is what fitness function 10(a) already compares |

**The release set would not be a new mechanism, and that is the strongest part of the argument.**
Fitness function 8(c) already requires that every persisted run names the active distribution set,
because `weft eval compare` across two runs is meaningless if the pack set differed between them
(`02` §2 → *The trust model*). A release set is that same record with a name and a version attached,
so the recommendation adds a name rather than a mechanism. Anything else would be a second
description of "which packs, at which versions", which is the drift shape this plan refuses everywhere
else.

**What this obliges, now that G10 has adopted it.** These are consequences of the model rather than
four further decisions. They were set out before the session so the recommendation could be argued
with; they are binding now.

- The meta-distribution ships **no code**. If it ships code it is a pack, and it will accumulate the
  convenience shims that a kernel budget exists to prevent.
- **`weft-rag` declares no module and no entry point of its own; the `weft` command a user runs comes from
  `weft-cli`, which the release set depends on** — which is also why the release set would be what a
  newcomer installs, and why the Phase 6 exit criterion can install the whole product with a single
  `uvx` invocation: a consequence of this bullet rather than a contradiction of the one above it.
- A distribution may be released **without** a release set (a pack fixing a bug), but the release set is
  what the documentation, the baseline and the support window are stated against — so "the current
  release" is always a set, never a single wheel.
- `weft plugins doctor` gains one column, not a new command: the version of each active distribution.
  **Whether `doctor` also flags a mismatch, and what a mismatch does, are G9's** (§2.3, dependency 1)
  — the column exists under either answer, because `doctor` has to be able to *say* what is installed
  before any policy can act on it.

---

## 2. The version policy, and its boundary with G9

### 2.1 What each version number means

| Surface | Versioned by | Owned by |
|---|---|---|
| A **contract** — `Extractor`, the store protocol family, `ExtModel` schemas, the filter AST, `Disclosure`, the `Command` permission class | Its own contract version, enforced by fitness function 6 | **G9** |
| A **distribution** — `weft-kernel`, `weft-store`, `weft-graph` | Its own release version, what a user pins | **G10** |
| The **release set** — `weft`, which G10 adopted on 2026-08-22 (§1) | Its own version, naming an exactly-tested combination | **G10** |

They are different numbers because they answer different questions. A contract version answers *"can
this pack still be loaded"*; a distribution version answers *"what do I install"*. The plan will have
both from Phase 5 onward, and conflating them is how a patch release to fix a log message would appear
to break a published contract. **The third row exists, G10
having settled it on 2026-08-22**, and the first two rows were unaffected by how it answered: every
position in §1 kept a distribution version distinct from a contract version.

### 2.2 The 0.x line, and what 1.0 means

**No distribution in this repository has made a 1.0 promise before Phase 6.** That is not a policy
choice so much as an observation: nothing is published to an index before Phase 6, so nothing can have
made that promise to anyone. **What 0.x promises about the published contracts was G9's** (§2.3,
dependency 2), and G9 answered it on 2026-08-21: **inside 0.x a contract may move without a deprecation
period, but never silently** — the registration-seam warning still fires and the changelog entry is
still owed. Phase 5 exists precisely to find the holes in these contracts, so binding 0.x would bind
the project to contracts it already expects to be wrong.

**Task 5.2a gives every distribution a real version number, and two of them already read above `0.x` —
that is a mechanical fact, not an early promise.** G9's binding rule (§2.3) forces a distribution's
version to track the maximum contract it publishes: `weft-store` and `weft-command` are `2.0.0` today
because `STORE_CONTRACT_VERSION` and `COMMAND_CONTRACT_VERSION` already are, and fitness function 6
enforces the binding, not the leading digit. This section's argument survives that unchanged, because
it was never about the digit: nothing is published to an index, so the number a resolver would read is
not a promise to anyone outside this repository yet, and the precondition table below is untouched by
it — `weft-store` reading `2.0.0` says nothing about whether it has satisfied "the store contract is
not over-fitted to one backend" or any other row. **The version number is G9's mechanical fact, settled
2026-08-21; the 1.0 milestone is G10's substantive judgment, settled 2026-08-22 — see the two
paragraphs below** — a distribution can carry a
major digit above `0` before the project has decided it is *1.0-ready* in the sense this section means,
exactly as an actively-iterating library commonly carries a major version with no external users yet.

What can be said without G9, because it is an observation about Phase 5 rather than a policy: Phase 5
exists precisely to discover holes in the contracts, and its finding is not available until it has run.
Whatever G9 decides, it decides it with that evidence in hand, which is why G9 gates Phase 5's successor
and not Phase 0.

**Settled 2026-08-22 by G10: 1.0 rests on evidence, and a date decides what happens when the evidence
is not in.** Each precondition names its demonstration, so *"are we 1.0?"* is answered by running
something rather than by arriving at a date. The attack the session had to answer is that a checklist
whose rows all tick is a date with extra steps, and one whose rows never all tick is a release that
never happens — so **the date is kept, with a different job**: a fixed review date at which the
outstanding rows are *published*, naming what is missing and what it would take. The review either
releases or says publicly why not; what it may never do is ship past a failed row or pass in silence.
The list below is the concrete form, and a row may still be struck or added — by a decision, in this
table, never by a release that quietly stops mentioning it:

| Precondition | Demonstrated by |
|---|---|
| The extension model works for someone who is not us | Phase 5's exit, with the graph pack installed from the index |
| The store contract is not over-fitted to one backend | `01` → *Runtime shape*: pgvector **and** Qdrant, neither stubbed |
| The kernel names no capability and stayed inside its budget | Fitness functions 1 and 3, green on installed wheels |
| Quality is a number someone else can reproduce | §4, the validation prerequisite, and the published baseline run |
| A break is survivable by a pack author | G9's policy exists and is implemented — the policy's *content* is G9's, its *existence* is this precondition |
| Nothing ships that was not meant to ship | Fitness function 10 |

**A 1.0 release set pins only distributions at 1.0 or above — G10, 2026-08-22, and the session had to
decide it because nothing had asked.** G9 settled that inside 0.x a contract may move without a
deprecation period. A release set numbered 1.0 whose pins include a 0.x distribution therefore
promises, at the set level, precisely what its parts reserve the right to break — the product's number
saying more than the product does, which is the one thing a version exists to prevent. So the set
reaching 1.0 forces every distribution it pins to 1.0 first, `weft-kernel` included, and the honest
consequence is stated rather than discovered: six distributions read `0.1.0` today — `weft-kernel`,
`weft-cli`, `weft-pdf`, `weft-openai`, `weft-otel` and `weft-qdrant` — and each either makes the
promise or is left out of the set and installs beside it, exactly as a third-party pack does. A
distribution may of course keep releasing at 0.x forever; what it may not do is be inside a 1.0 set.

**Under either position, 1.0 is the point at which G9's policy stops being advisory.** Before it, a
published surface may move under whatever rule G9 states for 0.x; after it, the rule binds and a breach
is a defect rather than an inconvenience. That much is true whether the number is reached by
demonstration or by date, which is why it is stated here rather than left to G10 — it is not a maturity
feeling and not a marketing event, and it says nothing about *what* the rule is or about *when* the
number is claimed.

### 2.3 What Phase 6 needs from G9, stated as questions

**G9 settled 2026-08-21.** These were the five dependencies from §0, written as the questions the
release checklist could not be run without. Phase 6 needed each to have *an* answer; it needed none of
them to have a *particular* answer, and no section of `09` supplied one. **The answers are recorded
below the table**, and the reasoning that produced them is in `05` → G9 and in the documents each
answer changed.

| # | Phase 6 needs to know | Because |
|---|---|---|
| 1 | **Whether version skew is reported or refused** | §1's last bullet gives `doctor` the column either way; what happens on a mismatch — a report, a refusal, or a `refused`-class status — changes the release notes, the checklist item in §5.2 and `doctor`'s exit code |
| 2 | **What 0.x promises about published contracts** | Whether a contract may move without a deprecation period inside 0.x decides whether the pre-1.0 releases owe pack authors anything at all, and therefore whether §5.2's compatibility block has items before 1.0 |
| 3 | **The deprecation clock and its unit** — releases or months, and how many | §5.2's checklist consumes whichever G9 picks. The two units are not interchangeable: a calendar window requires a release-cadence promise, a release-counted window requires a definition of which distribution's releases count |
| 4 | **Which surfaces carry a promise** — every row of §3's table | G9's *Bring* already enumerates the payload model, the store capability protocols, the filter AST, `Disclosure`, the `Command` permission `ClassVar` and `[packs] allow`. The release cannot state a support surface before that list has a policy |
| 5 | **What a version bound means** — floor, compatible range, or exact pin | Fitness function 10(b) asserts only that a bound exists. Which kind is required is what makes the bound enforceable as a *policy* rather than as a lint |
| — | *Two more that fall out of the above* | What happens when a pack requires a contract version the kernel does not offer — an existing status in `02` §2's vocabulary or a new one; and whether an `ExtModel` schema change is a contract change, which is the only kind of break a user cannot undo by pinning (G9 *Bring* raises both) |

---

**The answers, settled 2026-08-21.**

| # | Answer |
|---|---|
| 1 | **Reported, not refused.** A contract version requirement *is* the distribution dependency specifier, so the resolver refuses an incompatible install before the environment is broken. Runtime skew — an editable install, a forced install, a workspace — is **detected and reported** by `weft plugins doctor`, never used to refuse a load. There is no kernel load-time version check and the kernel gains no lines |
| 2 | **Inside 0.x a contract may move without a deprecation period, but never silently.** §2.2 above |
| 3 | **Releases, not months, and the unit is one major of the distribution that publishes the surface.** A calendar window needs a cadence promise this project does not make; a release-counted window needed *whose* releases count, and binding contract versions to distribution versions answers it. A deprecated surface keeps working, warning at registration, until its publisher's next major |
| 4 | **Every row of §3's table, as amended below.** Two rows changed: the message-catalogue row is **struck** (G11 removed the mechanism, so there is no surface to rule on), and the CLI row is **split** |
| 5 | **A compatible range** — `>=X,<MAJOR+1`. Never an exact pin: a library that pins exactly makes any two packs jointly unresolvable |
| — | A pack requiring a contract version that is not installed is **the resolver's refusal**, not a new status — `02` §2's vocabulary is unamended. An `ExtModel` schema change **is not a contract change**: it is a second axis, versioned in the data, specified in `02` §1 |

**What a contract version means, and what a move obliges.** Semver per contract, **bound to the
distribution version**: a contract major forces a major of the distribution that publishes it, a
contract minor forces at least a minor, and a distribution publishing several contracts takes the
maximum. The contract version is the precise statement; the distribution version is its enforceable
shadow, and the only one a resolver can act on.

**Semver is classified for two audiences and the bump is the maximum.** A change is assessed for the
**caller** and for the **implementer** separately, because the surface is Protocols that others
implement:

| Change | Caller | Implementer | Bump |
|---|---|---|---|
| Add a method to a Protocol | minor | **major** | **major** |
| Add an `Enum` member | minor | **major** | **major** |
| Add a name to `required_declarations` | — | **major** | **major** |
| Widen a parameter type | minor | **major** | **major** |
| Narrow a return type | **major** | minor | **major** |
| Add an optional field to a returned model | minor | minor | minor |

This makes `COMMAND_CONTRACT_VERSION` **1.1.0 a mis-recorded major**: task 3.2 added `help` to
`required_declarations`, which breaks every `Command` that does not declare one. It is corrected to
**2.0.0**, and correcting it is what the two-audience rule is for.

**A version bump does not fix silence, so silence is a separate defect.** Adding an `Enum` member is
textbook-additive and, in this tree, makes a backend answer the wrong query without erroring:
`weft_qdrant.store` reinterprets an unknown `FilterOp` as `eq` in `_condition` and as `gte` in
`_range`, `weft_store.contract`'s own `_shape_matches_op` validates it as `not`, and
`weft_store.fields` *derives* its permitted set from the enum and so silently allows it. A published
`Enum` must therefore be **dispatched exhaustively by construction**, with no fall-through default —
requirement 5 applied to a closed vocabulary instead of an open one.

**Closed by task 5.2b, and this paragraph is the worked example rather than an open item now.**
All four named sites `match`/`case _: raise weft_store.contract.UnhandledFilterOpError(...)`, and
`weft_store.fields`'s permitted set is now the nine operators a person stated by hand rather than
`frozenset(FilterOp) - {AND, OR, NOT}`. The audit that fixed them found four more sites with the
identical shape — `weft_store.pgvector_store`'s SQL translator, the sibling of
`weft_qdrant.store`'s that this paragraph never named — so nine sites in total, not five. `01` →
*Fitness functions* item 13 is the runtime property that keeps all nine (and any future site) this
way: a manufactured `FilterOp` member none of the twelve real ones equal must be refused everywhere,
never answered.

**The entry-point group name is versioned, not immutable.** Renaming `weft.packs` would unregister
every pack in the world at once, which no clock can cover. So discovery reads a *tuple* of groups: if
the name must ever change, the new one is **added**, both are read for one deprecation window, and a
pack found only in the old group is flagged by `doctor` — `09` §3's already-settled flag on an
existing status. That converts the one un-deprecatable surface into an ordinary deprecation.

---

## 3. The support and deprecation surface

**What might be public.** The surfaces below are the candidates. Each is defined by the document that
owns it; this table adds the *consequence* of a change to it — which is the material G9 needs — and
nothing about whether a promise applies, because that is dependency 4.

| Surface | Defined in | G9 decides |
|---|---|---|
| The published capability contracts and the contract mechanism | `02` §1, `02` §1 → *Who publishes a contract* | Whether these are the promise, and what a contract-version move obliges |
| The payload model — `Node`, `Lineage`, `ExtModel` declarations and their persisted shape | `02` §1 → *The payload model* | The only surface where a break also damages **stored data**; G9 *Bring* raises it as its sharpest case |
| The store contract family and its capability protocols | `02` §1 → *The store contract family* | G9 *Bring*: adding a method to `VectorSearch` breaks every backend at once, first- and third-party alike |
| The filter AST as a serialised format | `02` §1 → *The store contract family* | G9 *Bring*: it is versioned data, not only an API, because filters live inside stored pipelines |
| The pipeline format and its four derivation operators | `02` §3 | Whether stored pipelines are a promised format; note `02` §3 closes the operator set until something real needs a fifth |
| The `weft.packs` entry-point group name, and what `register` receives | `02` §2, `02` §2 → *Pack settings* | Renaming the group unregisters every pack in the world — a fact, whatever the policy |
| `Disclosure`, and the mandatory permission `ClassVar` on `Command` | `02` §2 → *The trust model*, `03` | G9 *Bring* names both: adding a required `Disclosure` field breaks every pack that ships one |
| Configuration keys: `packs:`, `[packs] allow`, `${env:}` | `02` §2, `02` §2 → *Pack settings* | G9 *Bring*: `[packs] allow` is operator configuration, the format whose promise is owed to people who never read a changelog |
| CLI command names, flag names and **exit codes** | `03` | **Promised** (G9). A CI job branches on exit 3 versus 4 (`02` §2), so a change is breaking in practice and now in policy |
| CLI **machine-readable output** — `--format json`, and the structured error envelope G9 requires | `03` | **Promised, additively.** New fields may be added; a consumer ignores what it does not recognise. Never frozen — git froze `--porcelain=v1` by explicit guarantee, could not evolve it, and had to ship v2 as a parallel format |
| CLI **error and diagnostic prose** | `03` | **Not promised** (G9). Natural-language output is not a stable interface and may change in any release. The promise is the failure-mode *identity* — the `WeftError` subclass name, which `08`'s troubleshooting ratchet already enumerates — and the structured envelope that carries the prose as a `rendered` field. The exclusion is what lets the message stay rich, which is `08`'s own argument that a remedy is a person's judgement |
| ~~Message-catalogue keys emitted by first-party packs~~ | — | **Struck 2026-08-21.** G11 retired `MessageCatalogue`, `Context.messages` and `ctx.t()`; there are no such keys, so there is no surface to rule on. The row is kept struck rather than deleted because `02` §1 records the removal and a reader arriving here from `§2.3` needs to know the question was retired, not skipped |
| Anything named `_private`, and everything in `weft-canary` | — | Same: not on the *Bring* list. If G9 does not rule, the release has no basis to call them excluded |

**The support window — G10, settled 2026-08-22.** What is owed after a published surface changes, as
distinct from *how* it changes (G9's clock) and *where* the notice appears (the paragraph below):
**the current major of every distribution in the release set is supported, and the previous major
receives fixes for one release-set major or six months, whichever is longer.** Fixes only — a
capability never lands on the old major, because a supported line that grows is a second line to
release, and this project has one maintainer's worth of capacity, which is the honest reason. The two
alternatives are recorded with why they lost: *current major only* leaves an operator on a pinned
major alone the moment the next one ships and gives a pack author no window to follow; *previous major
until the next release-set major*, with no calendar, quietly shortens to nothing if two set majors
land in a month. The `whichever is longer` clause is what makes the pair not merely the sum of both
failures. **Two clocks now exist and they must not drift**: G9's deprecation clock is one major *of
the publishing distribution* and governs when a deprecated surface may be removed; this one is the
release set's and governs how long a released combination still receives fixes. A surface may
therefore be removed from `main` while the previous major that still carries it is supported — that is
the intended shape, not a conflict, and `weft plugins doctor`'s version column is where an operator
sees which side of it they are on.

**Where a deprecation notice is emitted, whatever G9 decides is owed.** The seam is already settled and
is neither gate's to choose — not G9's, and not G10's, whose *Done when* in `05` → G10 says so explicitly: a
deprecated plugin, contract or config key is marked **at registration**, and
the warning is emitted by the registration wrapper — the same wrapper that applies spans, error
attribution and blocking-call detection. This follows the rule in `CLAUDE.md` and the measurement behind
it: every concern the seam's own machinery applied automatically held; every concern an author had to
remember decayed. A deprecation notice an author has to remember to print is a deprecation notice that
will not be printed.

**How `doctor` shows it, if G9's answer requires `doctor` to show anything.** As a **flag on an existing
status**, exactly as `ambient` is a flag on `active` (`02` §2). No new status: `02` §2's vocabulary is
settled, and adding a member would make one word answer two questions.

**Built by task 5.2e, both halves.** `weft_kernel.discovery.PackRegistrar.deprecate` is the
registration-time mark, `weft_kernel.seam.warn_deprecated` is the registration wrapper that emits
the warning from it, and `weft plugins list`/`doctor` read `PackReport.deprecations` as the flag
the paragraph above describes — `02` §2's own trust-model table now carries the row. Answer 1's own
"reported by `doctor`, never refused by the kernel" is built the same task: `weft_cli.skew.
detect_skew()`, comparing a distribution's installed version (`importlib.metadata.version`) against
a different, already-installed distribution's declared requirement on it
(`importlib.metadata.requires`) — two sources neither derived from the other, so a real disagreement
(an editable install, a forced install, a workspace whose lockfile has drifted) is exactly what it
catches. The kernel gained no lines for this half; `03` → *Command surface* has the worked example.

**The clock's unit — releases or months — is G9's** (§2.3, dependency 3). §5.2's checklist consumes
whichever it picks; nothing in `09` states a number, a unit, or a default.

**Built by task 6.5, and it is derived rather than declared.** G9 picked *releases*, the unit being
one major of the publishing distribution, so the removal point is a pure function of that
distribution's own installed version and no pack author states it —
`weft_kernel.seam.removal_for`, called at `PackRegistrar.deprecate`, carried on every `Deprecation`,
and read by both consumers: the registration wrapper's `DeprecationWarning` and `weft plugins
doctor`'s flag line. This is `CLAUDE.md`'s measured rule applied to a number instead of to a
concern — a `removed_in` an author types is stale on that pack's next release with nothing to
notice it. **A 0.x publisher is a third state, not a fourth major.** G9 also settled that "inside
0.x a contract may move without a deprecation period but never silently", so the answer for a 0.x
distribution is *not* "removed in 1.0.0" — that promises a window 0.x reserves the right not to
give. It is that there is no window, printed as such, which is what makes the clock observable
rather than invented; six distributions read `0.1.0` today (§2.2), so it is the common case. The
third state is an unreadable version, reported and never guessed at.

**Removal is a changelog entry with a migration line or it does not happen.** `CHANGELOG.md` already
exists and already states Keep a Changelog and SemVer; from Phase 6 it stops being a courtesy and
becomes the artefact whatever promise G9 states is made in.

> **And that sentence is currently false, measured (G9, 2026-08-21).** `CHANGELOG.md` is 19 lines, has
> been touched in exactly one commit — `9815531`, the repository's initialising commit — and still
> reads *"Nothing released yet. Phase 0 — the walking skeleton — is not built."* Five phases have
> closed since, and `README.md` → *Protocol* does not name the file among what a phase close updates.
> A promise made in an artefact nobody writes to is made nowhere.
>
> So G9 attaches a condition rather than a hope: **the changelog entry becomes checkable.** A
> `tests/docs` check asserts that every surface marked deprecated at registration has a `CHANGELOG.md`
> entry naming it. This is `CLAUDE.md`'s measured rule — every concern the machinery applied held,
> every concern an author had to remember decayed — applied to a document instead of to code, and it
> is the third time in one gate that a mechanism named in a document turned out not to run
> (`lessons.md` L5.1, L5.4, L5.8).

**Built by task 5.2f, and `CHANGELOG.md` itself brought current in the same commit.**
`tests/docs/test_changelog_deprecation_coverage.py` reads two sources that cannot be derived from
each other — `weft_kernel.discovery.discover(Registry())` against the real, installed `weft.packs`
group, exactly as `weft plugins doctor` runs it, folded to every `PackReport.deprecations`'s
`surface`; and `CHANGELOG.md` off disk — and asserts every surface the first names is a literal,
backtick-quoted mention in the second. Zero first-party surfaces are deprecated today, so the real
comparison passes vacuously; the check is proven non-vacuous instead by a real `Deprecation`,
produced through `PackRegistrar.deprecate` → `commit` rather than hand-built, shown reported missing
against the real file and cleared once an entry naming it is added
(`test_the_comparison_can_actually_fail`, `08` §3's own table names it as clause (e)). `CHANGELOG.md`
no longer reads "Phase 0... is not built" — it names what each of Phases 0–4 shipped and what Phase
5 has shipped so far, derived from `docs/build-ledger.md`'s own ticked entries rather than invented.
**Whether `README.md` → *Protocol* should also gain a line requiring this on every phase close is a
question this task leaves open, deliberately** — `docs/lessons.md` L5.8 named that as the other
candidate home, the ledger's own task line chose the check, and a check firing only on a
*deprecation* leaves the rest of the changelog exactly as unmaintained as before. The task's own
`docs/build-ledger.md` entry records this judgement for `implement-ll` to act on or decline.

**One thing the release must not soften.** `02` §2 → *The trust model* states the posture plainly: a
pack runs with your full privileges, and installing is trusting; signature verification, sandboxing and
per-pack privilege separation are out of reach without a process boundary. That paragraph must appear in
the published README of the release, not only in the plan. A design that refused to simulate a control
it cannot enforce would be undone by a package page that lets a reader assume one exists.

---

## 4. The validation prerequisite — the gap, stated honestly

### 4.1 The gap

**Weft has no data, and nothing in the plan currently says when that stops being true.** The falsifiable
form: Weft tracks no corpus, no question set, no ground truth and no provider configuration —
`git ls-files` matches zero `.jsonl`, `.csv`, `.parquet` or `.txt` files anywhere, and the only tracked
`.json` is `.claude/settings.json`, the harness configuration. Phases 2 and 4 build retrieval,
generation and evaluation on top of that.

*(No file census here. A count of the working tree is state, it belongs in `README.md` if anywhere, and
it is stale the moment Phase 0's remaining steps land. If a dated snapshot is wanted for the argument,
it belongs in the G10 session's **Bring** line in `05`, where a session-time measurement belongs.)*

### 4.2 Why "we will evaluate later" is the specific failure to avoid

Skipping evaluation is not the failure worth dwelling on here; the more instructive case is a project
that took evaluation seriously and still produced numbers nobody could trust. A 6,632-line evaluation
package, 21 metrics, two benchmark tracks and a real dataset loader against a public benchmark is a
serious amount of evaluation machinery, and it is possible for every one of the following to be true of
it at once:

- **No run was ever persisted.** Every evaluation path returns a `dict` and prints it.
- **The comparison function is dead and computes no deltas.** All four public functions of the
  comparison module have zero references anywhere in the source tree or in tests.
- **The track documented as benchmarking against gold never reads gold.** A gold-standard id map is
  built, passed, declared in the function's signature and documented — and never referenced in the
  function body that is supposed to consume it.
- **Ground truth is inflated by a paper-level fallback**, so retrieving any chunk of the right paper
  counts as a hit — precision pushed toward 1.0, recall toward 0, and the two tracks' numbers not
  comparable to each other.
- **An "at 10" metric is computed over 4 candidates.** `NDCG(k=10)` evaluated on a list already sliced
  to a top-4 cutoff, reported under a key that names `10`.
- **Failure is indistinguishable from a zero score.** Metrics return `score=0.0` with an `error`
  string; two of the three aggregators never check `error`, so benchmark means silently include
  failures.
- **Missing ground-truth files are tolerated**, producing queries with `None` ground truth that score
  0.0 everywhere; a corrupt corpus file is caught and skipped, silently shrinking the corpus.
- **Only means, no dispersion**, so two runs cannot be compared for significance even in memory.
- **6 of 21 metrics never register in the default import graph, and 2 test dummies ship registered
  into the production registry.**
- **Zero retries in the whole evaluation package**, so a judge that fails scores 0.0 on first failure.

**The generalisation, and it is not "measure things".** An unmeasured engine and a mismeasured one fail
identically from the outside: both produce confident numbers nobody can act on. Building an evaluation
harness and never validating the harness produces exactly this failure. So the prerequisite below is
not *"run an evaluation"* — it is *"produce a measurement whose failure modes are known, whose failures
are distinguishable from bad scores, and which a second person can reproduce."*

### 4.3 Prerequisite V — what "validated" must mean

Six artefacts. Each must **exist as a file or a persisted run**, not as an intention, and each can be
failed.

| # | Artefact | What it must contain | Fails if |
|---|---|---|---|
| **V1** | **A corpus** | Bounded and named; either redistributable or fetched by a pinned, checksummed script; covering every format an installed extractor claims; at least one non-English body, because Polish retrieval technique is shipped product under requirement 6 and untested language handling — a language-conditional branch nothing ever exercises — is functionally the same as a branch that was removed | Any declared format has no document in the corpus, or a fetch is not reproducible byte-for-byte |
| **V2** | **A question set with ground truth** | Questions with relevance judgements for retrieval and reference answers for generation; the provenance of each answer recorded (who wrote it, from which passage); **and unanswerable questions included**, because a RAG engine that cannot say *"not in this corpus"* is untested for its most damaging failure | Ground truth is missing for any question and the harness scores it anyway — precisely the failure named above |
| **V3** | **A baseline, run more than once** | The numbers produced *before* any technique: single-vector top-k, no fusion, no rerank, no enhancement. Every later claim is a delta against this and nothing else. **The baseline is repeated, the repeat count is recorded in the run, and each metric carries the interval its own repetitions produced** — see the tolerance rule below | A shipped technique's improvement is reported against no baseline, or against a baseline from a different corpus, pipeline or model version; **or the baseline was run once**, in which case it records no interval and no later run can be judged against it |
| **V4** | **Metric semantics, fixed at the door** | A failed metric is an **error**, never a zero; aggregates exclude errored metrics and report how many were excluded; every reported number carries the dispersion it was measured with, not only a mean; and the `k` in a metric's name equals the `k` it computed | Any aggregate averages a failure into a score, a metric name misdescribes its computation, or a reported number carries no dispersion |
| **V5** | **Providers, cost and an offline subset** | Which providers and which model versions, pinned; the money and wall-clock cost of one full run; and a deterministic subset that runs in CI with no credentials and no network, so a regression is caught by the gate rather than by a quarterly ritual | A full run cannot be priced, or the whole suite requires credentials, in which case it will be run once |
| **V6** | **A persisted, reproducible run** | The baseline is one of Phase 4's persisted runs, carrying the resolved pipeline, the corpus identity, the model versions and the active distribution set (fitness function 8(c)) | The baseline exists only as terminal output, never persisted |

**The reproduction tolerance is derived, never declared.** No number in this plan says how close a
re-run must be. Instead: V3 requires the baseline to be repeated and to record, per metric, the interval
its own repetitions spanned. **A later run reproduces the baseline when every metric falls inside that
recorded interval, and fails when any metric falls outside it.** The tolerance is therefore a
measurement of the system's own variability at the moment the baseline was taken, carried inside the
baseline run — not a constant chosen by anyone, which is what §4.4 forbids and what fitness function
7's rejected threshold was rejected for.

Three properties follow, and they are why this is a real check rather than a soft one. A system that is
deterministic records a zero-width interval and admits no drift at all, which is correct and strict. A
system that is noisy records a wide interval and honestly says so, rather than being compared against a
number someone liked. And a baseline that skipped the repetition **fails V3** rather than silently
producing an unfalsifiable exit criterion.

**Where these land in the plan.** V1–V3 are needed **before Phase 2 is judged**, because retrieval and
fusion decisions made without them are unmeasured by construction; V4 is a design constraint on Phase 4;
V5 and V6 are Phase 4 deliverables. Phase 6's exit consumes all six. The minimal plan edit this implies
is one line in Phase 2's **Read**, and nothing else, because the artefacts belong to `09` and only their
timing belongs to `01`.

### 4.4 What V is not: it does not set a quality target

**The plan must not invent a threshold** — no *"nDCG@10 ≥ 0.7 before release"*. That number would be
picked before any measurement existed, and the plan already has this argument, in `01` → *Fitness
functions* 7, where a slow-callback duration threshold was rejected because *"a number nobody can defend
gets re-baselined until it means nothing."* A quality threshold invented in advance has the same
property with worse consequences, because re-baselining it looks like progress.

**What V requires instead is that the numbers exist, are reproducible on the rule above, are published
with the release, and that a regression against them is visible.** The first real baseline sets the
value; from then on it is a **ratchet in the same shape as the kernel budget** — the recorded number may
be lowered only by a dated entry in the decision log, never in the pull request that lowered it.

---

## 5. Production ready — a checklist that can be failed

### 5.1 What the six phases already prove — and what that proof is worth

Phases 0–5 and fitness functions 0–9 are specified in `01`; they are not restated here. What matters for
this section is their **shared limitation**: every one of them is demonstrated *in the working tree, by
this repository's own gate, on inputs we chose, by the people who wrote the code*. That is the correct
standard for an architectural property and it establishes nothing about three other axes:

| Axis | Proven by the phases? | Why |
|---|---|---|
| **Architecture** — extensibility, boundaries, colour, trust posture, no privileged built-ins | **Yes**, and this is the strongest part of the project | Fitness functions 0–9, each phase exit |
| **Operational maturity** — failure under load, resource ceilings, restart behaviour, upgrade path, cost | **No** | Nothing in Phases 0–5 runs long, runs concurrently, or runs twice against the same store with different versions |
| **Real-data quality** — does it retrieve and answer well | **No** | §4. Nothing has been measured |
| **A stranger's install path** — installs, resolves, runs, and is understood without reading `docs/` | **No** | Every exit is demonstrated in the checkout; Phase 6's exit is the first that is not |

### 5.2 The checklist

Each item states the condition that **fails** it. An item with no failure condition is not on this list.
Items that restate a fitness function say so and link, rather than describing the check again.

**Where an item says *the release set*, it now means one thing.** G10 settled the unit on 2026-08-22
(§1): a code-free distribution `weft-rag` pinning an exactly-tested combination. The checklist was written
against that noun while it was still a recommendation, and every item survived all three positions
with only the noun changed; nothing needed rewording when the session closed.

**Install path**

- [ ] Fitness function 1 holds for **every** published distribution, not only the kernel — each installs
      alone into a clean environment and imports. *Fails if any distribution needs the workspace, a path
      dependency, or an environment variable to import.*
- [ ] The release set installs by name on a machine that has never seen the repository, on the minimum
      supported Python, and `weft --version` runs — which is fitness function 8(b) observed from an
      index rather than from the tree.
- [ ] A third-party pack installs beside the release set and is discovered — Phase 5's pack, from the
      index, not from a path. *Fails if it needs anything the release set did not publish.*
- [ ] The sdist builds and its tests pass from the sdist. *Fails if a data file, locale catalogue or
      entry-point declaration is present in the checkout and absent from the artefact.*

**Operability**

- [ ] `weft plugins doctor` answers, on a broken installation, *why* — using the status vocabulary in
      `02` §2, with no status reported that is not in it.
- [ ] A cancelled run leaves the store durable to its last finished batch, per `02` §1's `flush`
      guarantee, and a resumable delete finishes on the next command. *Fails if a crash mid-delete leaves
      a store that no later command repairs.*
- [ ] The cost and wall-clock of indexing the validation corpus are recorded, and re-indexing an
      unchanged corpus is measurably cheaper (`SourceRecord` change detection, `02` §1).
- [ ] An upgrade path exists and was executed once: a store written by release *n* is read by release
      *n+1*. *Fails if this has never been run.*

**Quality**

- [ ] V1–V6 exist (§4.3), and the baseline run is published with the release — **attached to it**,
      which is what "with" had to be made to mean. Task 6.13 installed the whole product from an
      index into a clean environment and found `eval/baselines/`, `eval/questions/` and
      `corpus/manifest.toml` reachable only from a git checkout, so the sentence was true of a
      directory and false of anything a stranger holds (`lessons.md` L6.34). The release job
      attaches all three as one archive (task 6.35); the shipped CLI already does the work, with
      `weft eval run` and `weft eval compare` both on the installed binary, so what was missing
      was never capability. *Fails if reproducing the published number requires cloning.*
- [ ] Every shipped technique's claimed improvement is a delta against V3 on the same corpus, pipeline
      and model versions. *Fails if any claim in the documentation has no run behind it.*
- [ ] The offline evaluation subset runs in `ci-checks`. *Fails if quality is checked only manually.*

**Compatibility**

- [ ] G9's policy is implemented, not only written, and `doctor` behaves as G9 specified on skew —
      report or refusal (§2.3, dependency 1). *Fails if the policy exists only as prose.*
- [ ] Whatever deprecation clock G9 states is running and observable: every currently deprecated surface
      names the release or date at which it is removed, in the unit G9 chose (§2.3, dependency 3).
- [ ] Fitness function 10 is green; `weft-canary` is not on the index.
- [ ] `CHANGELOG.md` covers every published distribution, and every removal carries a migration line.
- [ ] The release set pins **no** distribution below 1.0 (§2.2). *Fails if the set is numbered 1.0 or
      above while any pin reads `0.x` — the set would promise what its parts reserve the right to break.*
- [ ] The support window in §3 is published where an operator reads it, not only here, and names the
      current major and the date or set-major at which the previous one stops receiving fixes. *Fails if
      "how long is this supported" has no answer outside `docs/`.*
- [ ] The release set's pins and the workspace's own distributions agree, read from the two files that
      can genuinely disagree — fitness function 10(a). *Fails if the set is assembled from the same
      source it is checked against, which is a check that cannot fail (`lessons.md` L5.6).*

**Security, licensing, documentation**

- [ ] `SECURITY.md` states a reporting path and the trust posture appears in the published README, in
      the words `02` §2 uses. *Fails if the package page implies isolation the design refused to claim.*
- [ ] `LICENSE` and `NOTICE` are in every built artefact, and the originality rule in `CLAUDE.md` is
      re-checked for the release. *Fails if any file in the release cannot be accounted for as
      original work.*
- [ ] A newcomer can install, index and ask from the README alone, without opening `docs/`.

**Explicitly not on this list, and why.** Uptime, SLAs, a support rota, multi-tenant isolation testing
and a service tier. The first three require an operator this project does not have; multi-tenancy is
deferred until the second tenant, and a service tier until someone outside the process needs to call it
— both under `01` → *The least-architecture check*, with their reopen triggers already named. Putting
them on a release checklist would mean either failing every release or ticking them dishonestly.

---

## 6. How the plan is adjusted — and what leaves `README.md` when this lands

**This is a move, not a copy, and the move is explicit.** The reopen procedure currently lives in
`README.md` → *Protocol*. If it also lived here, there would be two descriptions of it that can
disagree — the two-lists bug at the level of the plan, which is exactly what `README.md`'s opening
blockquote forbids. So in the same commit that adds this section:

**Deleted from `README.md` → *Protocol*:** the paragraph **"When a decision reopens."** in full — the
three sentences beginning *"Set the row to Reopened with the reason…"*. It is replaced by one line:
*"How a decision is reopened, how a phase or a fitness function is added, and what a scope change
obliges: `09-release.md` §6."*

**Kept in `README.md` → *Protocol*, unchanged:** *"When a grilling session closes"*, *"When a phase
completes"*, *"When a document is added"*, and *"What never goes in this file"*. Those four are
instructions for maintaining **this file's own state** — which row to update, which box to tick, which
manifest line to add — and state is what `README.md` owns. The reopen paragraph is the odd one out: it
describes a *procedure with consequences across documents*, which is definition.

The machinery already exists and is mostly unstated as a machine: gates in `05`, the Open / Settled /
Reopened statuses in the decision log, and the rule that a reopened decision un-ticks everything
downstream. What follows names the four adjustments people actually make, and what each obliges.

### 6.1 Add a phase

1. Write it in `01` → *Phases* in the four-line format that section defines, with an exit that can be
   **demonstrated rather than argued about**. If the exit cannot be demonstrated, the phase is a wish
   and does not go in.
2. Decide whether it has a gate. A phase whose shape depends on an undecided question needs one; add it
   to `05` and log it **Open**.
3. Add its rows to README's *Execution path*, and its gate row to the decision log.
4. **Re-check:** every fitness function the new phase would activate — clauses are assigned to phases,
   and `01`'s note under item 8 records that sequencing `06` found 8(b) in the wrong one — and whether
   any later phase's exit is now provable earlier or no longer provable at all.

*Phase 6 is the worked example: its block is in `01` → *Phases*, its gate is `05` → G10, and the
re-check is what the commit that landed this document recorded in `01`, `05` and `README.md`.*

### 6.2 Change a settled decision

1. Follow `README.md` → *Protocol* for the mechanics of the log row and the checklist. This section adds
   only what that paragraph does not say, which is what to re-check and in what order.
2. Re-run the session in `05`. It exists; it does not need rewriting to be re-run.
3. Edit the reference document that owns the content, in the same commit as the log row.
4. **Re-check, in this order:** the phases after it, because `05`'s ordering table exists precisely
   because these cascade; then the change against the six requirements in `01` — the `weft-qualities`
   skill is that review, and it exists because these properties are lost one reasonable commit at a
   time.
5. After Phase 6, add one step: **state the compatibility consequence.** A settled decision that has
   been published is also a promise, and reopening it is a changelog entry and possibly a deprecation
   clock, not only a document edit.

**A widening is not a reversal, and the distinction is already in use.** `02` §1 records `Node.synthetic`
being widened during Phase 0 step 1 with the argument for why it strengthens rather than reverses G5.
That is the pattern: a widening is a marked note under the settled content, citing the session; a
reversal is a Reopened row. Getting this wrong in the cheap direction — logging every widening as a
reopen — makes the log unreadable; in the expensive direction it hides a reversal as an edit.

### 6.3 Add a fitness function

1. Write it in `01` → *Fitness functions*, numbered, stated as a **property** rather than as a command
   list or an API shape, in the wording item 8 uses.
2. **Wire it into `ci-checks` in the same commit** — fitness function 0 asserts that membership, and it
   exists for a reason `01` states.
3. Name the phase it activates in, and put the activation in **that phase's exit criterion**, per the
   note under item 8.
4. Prefer a **ratchet** — a named waiver constant pinned empty — over a snapshot, so a waiver is a
   visible act in a diff.
5. **Re-check:** that it carries no tuning constant whose correct value changes with the runner. If it
   needs one, it is a trace or a report, not a gate — `01` → *Fitness functions* item 7 rejected exactly
   that and says why.

### 6.4 Change scope

Cutting and adding scope are the same operation and both are **decisions**, so both get a decision-log
row — the log currently records only gate outcomes, and a scope cut recorded nowhere is how a phase
quietly loses its point.

1. Say which of the six requirements in `01` the change touches. If it touches none, it is a
   phase-content change (cheap, §6.5) and needs no ceremony.
2. If it removes work, name the **forcing function** that reopens it, in the shape of `01` → *The
   least-architecture check*: *"deferred until X happens."* A cut with no reopen trigger is a silent
   scope reduction, and the deferral table's whole discipline is that nothing is deferred on vibes.
3. If it adds work, say which phase owns it and what its exit demonstration is.
4. **Re-check:** every exit criterion that referenced the cut work, and whether any fitness function is
   now unactivated because the phase that switched it on no longer exists.

### 6.5 Which levers are cheap, and which are expensive

The single most useful thing to know about this plan: **cost is a function of what has already been
published or persisted, not of how much code a change touches.**

| Lever | Cost | Why — the settled outcome it follows from |
|---|---|---|
| Phase contents, and ordering within the gate order | **Cheap** | Nothing outside the repository depends on it; `06` re-sequenced Phase 0 without touching a decision |
| Which pack ships which technique | **Cheap** | Requirement 6, `01` → *What "modern and elastic" has to mean concretely* |
| The set of shipped techniques | **Cheap** | Requirement 1. If adding a technique is ever expensive, the extension model has failed, not the plan |
| The kernel budget number | **Cheap, but visible** | `01` → *Fitness functions*, the budget's ratchet rule |
| Documentation structure | **Cheap** | `README.md` → *Protocol*, *When a document is added* |
| CLI command surface | **Cheap before Phase 6, expensive after** | `03`, and §3 above once exit codes are published |
| The derivation operator set | **Medium** | `02` §3 — closed until something real needs a fifth; pipelines are stored data |
| The trust posture and the `allow` pin | **Medium** | G3, `02` §2 → *The trust model* |
| Discovery eagerness | **Medium-high** | G3 — lazy import and bare plugin names are mutually exclusive |
| The store contract family | **High** | G4, and G9 *Bring*: one added method breaks every backend at once |
| **The kernel boundary** (G1) | **Expensive** | `01` → *The kernel boundary*. Every contract, distribution split and fitness functions 1, 2 and 3 are downstream |
| **Async-only** (G6) | **Expensive** | `01` → *Colour*. There is no partial adoption; a sync facade is the bridge the decision refuses |
| **The payload model** (G5) | **Expensive, and uniquely so** | G9 *Bring* — an `ExtModel` is a schema in a database, and pinning an old version does not un-write a node |
| One repository, several distributions | **Expensive after the first publish** | `01` → *The architecture stack*, Topology row; §1 above |

**Read the table twice — before Phase 6 and after.** Almost every "expensive" entry is expensive for the
same reason: something outside this repository has already been compiled or written against it. That is
the real character change Phase 6 makes to the plan. Before the release, the expensive levers are
expensive because of *design coupling*, and the mitigation is argument. After it, they are expensive
because of *promises*, and the mitigation is a deprecation clock. The plan should stay adjustable in
both regimes, and the way it does is by being explicit about which regime it is in — which is exactly
what a version number is for.
