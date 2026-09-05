"""Task **2.26**'s own property, made checkable rather than a one-off reading: every strategy
this phase ships is named for the technique it implements, and no name claims a paper the code
does not implement.

`docs/10-technique-catalogue.md` §1.4 and §2 own the naming rule; this file is the audit that
rule promised, turned into something that stays true rather than something read once and
trusted. Reading every plugin's module docstring against its catalogue row by hand (which task
2.26 did, against `no-retrieval` through `always` — every plugin `weft_retrieve.register` and
`weft_generate.register` ship, tasks 2.13-2.25) found **no open gap**: `.phase2-design.md`'s own
task rows already anticipated this audit (`hyde`'s and `step-back`'s own module docstrings cite
"task 2.26's own naming audit" by name), and every divergence the catalogue records — HyDE fusing
rather than averaging, `step-back` fixed rather than reproduced, `corrective`/`graded-retrieval`
split exactly along `10`'s own condition, `rag_consensus` renamed to `contradiction-check` with
`self-consistency` left free, `adaptive-rag` left unreachable from the router on purpose — is
already stated in the plugin's own docstring, at the name. **What was missing was a test**: a
docstring a future edit strips is a silent regression this file exists to catch, and a hand-read
audit cannot re-run itself next phase.

**Five properties, derived from the catalogue rather than retyped**, the same discipline
`tests/docs/test_manual_config_keys.py` uses for `[services]` keys: a name added to `10` §4,
§1.4, §1.1, §2.2 or §1.5 needs no edit here, and a name removed from any of them fails this
file's own self-test rather than rotting silently.

1. **No registered name claims a reserved technique** (`10` §4) — the literature has already
   fixed `self-rag`, `flare`, `adaptive-rag` and the rest for techniques this build does not
   implement; registering one of those names for something else is exactly the false-provenance
   failure §2.1 rule 4 forbids.
2. **No registered name reuses a reference name `10` §1.4 renamed for cause** — `rag_consensus`,
   `rag_adaptive`, `reverse_hyde` and the rest are not preferences; reusing one would launder the
   defect its row names back into the registry it was corrected out of.
3. **Every technique whose row cites a paper still carries that citation somewhere in the pack
   that registers it** — the anchor is the paper's own arXiv id or DOI, not prose, so a
   docstring can be reworded freely (matching the surrounding module's own voice, per
   `CLAUDE.md`) without this file caring, but cannot be deleted silently while the name that
   earns it stays registered.
4. **Every Weft name §1.1 states resolves to a registered plugin or a shipped pipeline** —
   `.phase2-design.md` → "Task 2.26 — the naming audit as a test", item 1. A catalogue row for
   something that was never built or was renamed since is a citation with nothing behind it.
5. **Every name `weft-retrieve`, `weft-generate`, `weft-llm`, `weft-prompts`, `weft-pdf`,
   `weft-qdrant` or `weft-openai` registers is named somewhere in `10`** — the same design
   item, both directions. §1.1 and §2.2 name the fourteen techniques with an origin; §1.5,
   added by this file's own repair (below), names the rest.

**What this cannot check.** Whether the *code* actually implements what a citation claims is a
judgement call task 2.26 made by reading each plugin against its row — the same limit
`tests/docs/test_phase_document_routing.py`'s own docstring states for its heuristic: a test
can confirm a citation survived, not that it was ever honest. That is what the hand-read audit
recorded in `docs/10-technique-catalogue.md` §1.1/§1.2's own "Reference" column is for, and what a
reviewer re-reads by eye at the next phase's own audit.

**Repaired 2026-08-18, two reviewer findings against the first commit of this file.** (1)
`registered_names()` used to read `weft_retrieve.__all__`/`weft_generate.__all__`, on the
stated claim that `weft_kernel.registry.Registry` "exposes no per-name enumeration" — false:
`Registry.names_for(contract)` is exactly that, added in this same phase's design
(`.phase2-design.md` §11) for exactly this kind of caller, and nothing tied the `__all__`
export to the string a `registrar.add(...)` call actually passes. Properties 1-3 above now run
against the real registry, widened for free to every installed pack. (2) Properties 4 and 5 —
`.phase2-design.md`'s own bidirectional check and the `10` §1.5 table its own item 4 obliges —
were dropped without being recorded as a scope decision. Both are built here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from tests.discovery import discover_for_tests
from weft_cli.pipeline_catalogue import load_contributed, load_pipeline_catalogue
from weft_kernel.discovery import discover
from weft_kernel.registry import Registry

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
CATALOGUE: Final[Path] = REPO_ROOT / "docs" / "10-technique-catalogue.md"
PACKAGES_ROOT: Final[Path] = REPO_ROOT / "packages"

#: `weft-store` requires a `dsn` with no default; a placeholder is enough to let
#: `register()` run without opening a real connection — `test_ff11_pipeline_
#: integrity.py`'s own identical constant, for the identical reason.
_PLACEHOLDER_DSN: Final[str] = "postgresql://technique-naming-placeholder/placeholder"

#: One backtick-quoted token per line-leading `|` cell — `10` §1.4's own table shape (also
#: §1.5's: one name per row, nothing else in the first column).
_TABLE_ROW = re.compile(r"^\| `([^`]+)`", re.MULTILINE)
#: A backtick-quoted token anywhere in §4's prose list — kebab-case, optionally trailing `*`
#: (`ragas-*`, a free *prefix* rather than a single reserved name).
_BACKTICK_TOKEN = re.compile(r"`([a-z][a-z0-9-]*\*?)`")
#: A table row's own leading bold-backtick name cell(s) — one name, or two joined by ` + `
#: (§1.1's `query-scorer` + `routing-policy` row) — captured up to the first thing that is
#: not another bold-backtick name, so a trailing `*(method: ...)*` / `*(name conditional
#: ...)*` annotation (itself sometimes backtick-quoted — `repack`'s three method values)
#: is never mistaken for a second name. Anchored at the line start rather than split on
#: `|`: a cell's own prose can carry an *escaped* `\|` (`repack`'s method list, §2.2's
#: `` `corrective` \| `graded-retrieval` `` row) that a naive `str.split("|")` would
#: mistake for the real column boundary.
_ROW_LEADING_NAMES = re.compile(
    r"^\|\s*((?:\*\*`[a-z][a-z0-9-]*`\*\*(?:\s*\+\s*)?)+)", re.MULTILINE
)


def _catalogue_text() -> str:
    return CATALOGUE.read_text(encoding="utf-8")


def _section(text: str, *, start: str, end: str) -> str:
    return text.split(start, 1)[1].split(end, 1)[0]


def _leading_backticks(segment: str) -> list[str]:
    """Every backtick token in `segment` up to its first `(` — the reserved name(s) an item
    states, never a token inside the citation that follows (an author list can itself contain
    a backtick-quoted term, and the `decomposition` paragraph names `boolean-retrieval` in its
    own explanation without reserving it)."""
    before_paren = segment.split("(", 1)[0]
    return _BACKTICK_TOKEN.findall(before_paren)


def reserved_names() -> tuple[frozenset[str], frozenset[str]]:
    """`10` §4's own reserved vocabulary — `(exact names, prefixes)`.

    §4 is two paragraphs: a `·`-separated list of items (each `` `name` `` or
    `` `name1` / `name2` `` followed by a citation in parentheses), then one more paragraph
    reserving `decomposition` alone with a worked explanation that happens to name
    `boolean-retrieval` in passing. Both paragraphs are parsed the same way — every backtick
    token *before* the first `(` in each `·`-separated (or, for the second paragraph,
    sentence-separated) segment — so a token inside a citation or an explanation is never
    mistaken for a reservation.

    `ragas-*` is the one entry that means "this prefix", not "this literal string" (its own
    row: "free for a pack that genuinely wraps the library") — split out as a prefix rather
    than compared for equality, so a future `ragas-context-relevance` is caught the same way
    a literal `ragas-*` never would be.
    """
    section = _section(_catalogue_text(), start="## 4. Reserved names", end="## 5. What is not")
    list_paragraph, _, decomposition_paragraph = section.partition("`decomposition` is reserved")
    tokens: set[str] = set()
    for item in list_paragraph.split("·"):
        tokens.update(_leading_backticks(item))
    tokens.update(_leading_backticks("`decomposition` is reserved" + decomposition_paragraph))
    exact = frozenset(token for token in tokens if not token.endswith("*"))
    prefixes = frozenset(token[:-1] for token in tokens if token.endswith("*"))
    return exact, prefixes


def renamed_reference_names() -> frozenset[str]:
    """`10` §1.4's own table — the reference names each row states a rename is not a preference for.

    Bounded at `### 1.5`, not `## 2. The naming rule`: §1.5 sits between 1.4 and section 2
    now, and its own table is a plain one-name-per-row shape `_TABLE_ROW` would just as
    happily (and wrongly) parse as reference names if the section ran past it.
    """
    section = _section(
        _catalogue_text(),
        start="### 1.4 The rows where a rename is a correction",
        end="### 1.5 Supporting plugins",
    )
    return frozenset(_TABLE_ROW.findall(section))


def _all_names(registry: Registry) -> frozenset[str]:
    """Every name `registry` holds under any contract — `names_for` walked over
    `contracts()`, both contract-agnostic and read-only (`weft_kernel/registry.py`), so no
    contract has to be imported and listed here for its names to be found."""
    return frozenset(
        name for contract in registry.contracts() for name in registry.names_for(contract)
    )


def registered_names() -> frozenset[str]:
    """Every name any installed pack actually registered, under any contract — plugin and
    prompt alike.

    Built on `weft_cli.contract_reference.discover_for_reference`, the same open-by-default
    `Registry` `manual/contract-reference.md`'s own generator populates — reused rather than
    duplicated a third time, and it already settles `weft-store`'s pack settings with a
    placeholder DSN that is validated and never connected to.

    **This used to read `weft_retrieve.__all__`/`weft_generate.__all__` instead**, on the
    stated claim that `Registry` "exposes no per-name enumeration". That was false the day
    it was written: `Registry.names_for(contract) -> frozenset[str]` was added in this same
    phase's own design (`.phase2-design.md` §11) for exactly this question — its own
    docstring: a caller that needs to know *what a contract's plugins collectively claim*
    "derives it from what actually registered rather than from a list in one pack's
    module", per `docs/02-extension-model.md` §1's "capability is derived, never declared".
    Reading `__all__` also checked a name nothing necessarily registers: no mechanism ties
    an exported `_NAME` constant to the string a `registrar.add(...)` call actually passes,
    so the two drifting apart — one renamed, the other not — would have passed silently.

    Widened for free to every installed pack, not only `weft-retrieve`/`weft-generate`:
    `weft-chunk`, `weft-clean`, `weft-embed`, `weft-enhance` and `weft-extract`/`weft-store`'s
    own built-ins ride along too, which only strengthens the reserved-name and
    reference-rename checks below — nothing in `10` §4 or §1.4 could ever legitimately be one
    of theirs anyway.
    """
    return _all_names(discover_for_tests())


#: `.phase2-design.md` → "Task 2.26 — the naming audit as a test", item 2's own list — the
#: distributions this catalogue is responsible for documenting. Not derived: unlike
#: `registered_names()`, which widens for free the moment a new pack installs, *which*
#: distributions `10` owes a row is a scope decision, not a registry fact — the same reason
#: `_CITED_TECHNIQUES` below is a hand-kept tuple rather than something read off the
#: registry. Extending it to an eighth distribution is a decision this file should make
#: visibly, in the same commit that adds that distribution's own rows to `10`.
_AUDITED_DISTRIBUTIONS: Final[tuple[str, ...]] = (
    "weft-retrieve",
    "weft-generate",
    "weft-llm",
    "weft-prompts",
    "weft-pdf",
    "weft-qdrant",
    "weft-openai",
)


def names_registered_by(distributions: tuple[str, ...]) -> frozenset[str]:
    """Every name registered by exactly `distributions`, and nothing else installed.

    `discover(..., allow=distributions)` is the same open-by-default mechanism `weft.toml`'s
    `[packs] allow` drives: every other installed distribution's entry point is refused
    outright and never imported, so a fresh `Registry` built this way holds only what
    `distributions` themselves contributed. No `Registry` API maps a registered name back
    to its distribution — there isn't one, and inventing it for one test would be exactly
    the kind of surface CLAUDE.md's registration-seam rule reserves for the kernel to own,
    not a docs test to demand.
    """
    registry = Registry()
    discover(registry, allow=distributions)
    return _all_names(registry)


def _reserved_violations(
    names: frozenset[str], *, exact: frozenset[str], prefixes: frozenset[str]
) -> dict[str, str]:
    """`names` that collide with a reserved entry, mapped to which reservation caught them."""
    violations: dict[str, str] = {}
    for name in sorted(names):
        if name in exact:
            violations[name] = f"reserved exactly (`10` §4): `{name}`"
            continue
        hit = next((prefix for prefix in prefixes if name.startswith(prefix)), None)
        if hit is not None:
            violations[name] = f"reserved prefix (`10` §4): `{hit}*`"
    return violations


def test_at_least_one_registered_name_is_found() -> None:
    """The floor: a scan that matched nothing would pass every check below by being blind."""
    # Arrange / Act
    names = registered_names()

    # Assert
    assert names, "no name found under any contract any installed pack registered"


def test_the_catalogue_itself_names_at_least_one_reserved_technique_and_one_rename() -> None:
    """A second floor, over the catalogue's own two sections — a parse that matched nothing
    there would pass the two checks below just as vacuously."""
    # Arrange / Act
    exact, prefixes = reserved_names()

    # Assert
    assert exact or prefixes, "no reserved name parsed from `10` §4"
    assert renamed_reference_names(), "no renamed name parsed from `10` §1.4"


def test_no_registered_name_claims_a_reserved_technique() -> None:
    """`10` §2.1 rule 4: no name may promise more than the code does. A reserved name is the
    sharpest case of that — the literature already named the technique, and Weft does not
    implement it."""
    # Arrange
    exact, prefixes = reserved_names()

    # Act
    violations = _reserved_violations(registered_names(), exact=exact, prefixes=prefixes)

    # Assert
    assert not violations, (
        f"registered name(s) collide with `10` §4's reserved vocabulary: {violations}. "
        f"Rename the plugin, or — if it genuinely implements the reserved technique — move "
        f"the name out of `10` §4 in the same commit that claims it."
    )


def test_no_registered_name_reuses_a_reference_name_the_catalogue_renamed() -> None:
    """`10` §1.4: these renames are not preferences. Reusing one would put the reference's own
    defect back in the registry under the exact name it was corrected out of."""
    # Arrange
    banned = renamed_reference_names()

    # Act
    reused = registered_names() & banned

    # Assert
    assert not reused, (
        f"registered name(s) reuse a reference name `10` §1.4 renamed for cause: {sorted(reused)}. "
        f"See that row for why the rename is not discretionary."
    )


def test_a_reserved_collision_would_be_caught() -> None:
    """The reserved-name check's own teeth: a name that really does collide must be flagged,
    proven against a name `10` §4 actually reserves — not a made-up string this test invents,
    which could pass for reasons that have nothing to do with the check under test."""
    # Arrange
    exact, prefixes = reserved_names()
    assert "self-rag" in exact, (
        "`10` §4 must reserve `self-rag` for this self-test to mean anything"
    )

    # Act
    violations = _reserved_violations(frozenset({"self-rag"}), exact=exact, prefixes=prefixes)

    # Assert
    assert "self-rag" in violations


def test_a_renamed_name_collision_would_be_caught() -> None:
    """The renamed-reference-name check's own teeth, the same self-test discipline one function up."""
    # Arrange
    banned = renamed_reference_names()
    assert "rag_consensus" in banned, (
        "`10` §1.4 must list `rag_consensus` for this test to mean anything"
    )

    # Act
    reused = frozenset({"rag_consensus"}) & banned

    # Assert
    assert reused == {"rag_consensus"}


def _weft_names_in_1_1() -> frozenset[str]:
    """§1.1's own "Weft name" column, and nothing else — the source side of property 4's
    forward check: every one of these must resolve to a registered plugin or a shipped
    pipeline."""
    section = _section(
        _catalogue_text(), start="### 1.1 Query-path techniques", end="### 1.2 Index-path"
    )
    names: set[str] = set()
    for match in _ROW_LEADING_NAMES.finditer(section):
        names.update(_BACKTICK_TOKEN.findall(match.group(1)))
    return frozenset(names)


def weft_names_in_catalogue() -> frozenset[str]:
    """Every Weft name `10` states anywhere — the target side of property 5's reverse
    check: §1.1's own names, §2.2's "Applied to all ten" table, and §1.5.

    §2.2 is read whole rather than column-by-column: the reference column and the "Kind of
    change" prose both carry backtick tokens too (some of the reference tokens sit beside a
    literal escaped `\\|`, e.g. `` `corrective` \\| `graded-retrieval` ``, which a
    column split by `str.split("|")` would misread as a column boundary). The extra reference
    tokens this pulls in are harmless here: `test_no_registered_name_reuses_a_reference_name_
    the_catalogue_renamed` above already refuses every one of them as a live registration,
    so none can ever appear in the `names_registered_by(...)` set this function is
    compared against.
    """
    text = _catalogue_text()
    names = set(_weft_names_in_1_1())
    section_2_2 = _section(text, start="### 2.2 Applied to all ten", end="### 2.3 Why the prefix")
    names.update(_BACKTICK_TOKEN.findall(section_2_2))
    section_1_5 = _section(text, start="### 1.5 Supporting plugins", end="## 2. The naming rule")
    names.update(_TABLE_ROW.findall(section_1_5))
    return frozenset(names)


def shipped_pipeline_names() -> frozenset[str]:
    """Every pipeline `name:` field a first-party pack ships, from **both** sources `01`
    item 11(b) now recognises.

    `weft_cli.pipeline_catalogue.load_pipeline_catalogue`, walked over every pack's own
    top-level `pipelines/` directory, is the pre-2.8 reader this function always used —
    a project-local or demonstration pipeline the CLI would read from a checked-out
    tree. **Task 2.8 adds the second source**: `PackRegistrar.add_pipeline_resource`
    contributes a pipeline from *inside* a pack's own installed package, reachable
    through `importlib.resources` from a real wheel — `weft_cli.pipeline_catalogue.
    load_contributed`, fed every real, installed pack's own `PackReport.
    pipeline_resources`, the same discovery pass `weft plugins doctor` runs. Neither
    source alone is now complete — see `tests/architecture/test_ff11_pipeline_
    integrity.py`'s own identical addition to `_shipped_pipeline_files`.
    """
    names: set[str] = set()
    for directory in sorted(PACKAGES_ROOT.glob("*/pipelines")):
        names.update(load_pipeline_catalogue(directory))

    registry = Registry()
    reports = discover(registry, pack_settings={"weft-store": {"dsn": _PLACEHOLDER_DSN}})
    names.update(load_contributed(reports))
    return frozenset(names)


#: A name a genuine, recorded decision has excused from properties 4 and 5 — pinned to
#: exactly what earns the exemption, the same ratchet discipline `test_ff0_gate_in_the_
#: gate.py`'s own waiver constant uses: a name added here is a visible act in a diff,
#: never a silent edit. `routing-policy` is §1.1's own row label for a *family* —
#: `threshold-ladder` / `nearest-description` / `always`, each independently documented in
#: §1.5 — not a plugin promise in its own right, so nothing is ever registered under that
#: exact string and property 4's forward check could never resolve it without this line.
#: `test_the_waiver_is_doing_real_work` below proves this is still true rather than
#: trusting the comment.
NAMES_WAIVED_FROM_THE_CATALOGUE: Final[frozenset[str]] = frozenset({"routing-policy"})


def test_every_weft_name_in_1_1_resolves_to_a_plugin_or_a_pipeline() -> None:
    """Property 4. A name §1.1 states that nothing registers and no pipeline ships is a
    citation with nothing behind it — the forward half of the drift `.phase2-design.md`
    names this audit to close (`retrieve-then-generate` is the pipeline `10` §2.1 rule 5
    and §12 decision 12 both name; the row is the technique it composes)."""
    # Arrange
    claimed = _weft_names_in_1_1() - NAMES_WAIVED_FROM_THE_CATALOGUE
    resolvable = registered_names() | shipped_pipeline_names()

    # Act
    unresolved = claimed - resolvable

    # Assert
    assert not unresolved, (
        f"`10` §1.1 names {sorted(unresolved)}, and nothing registered under that name and no "
        f"shipped pipeline is named that either. Register the plugin, ship the pipeline, "
        f"correct the row, or waive it with a stated reason."
    )


def test_every_name_the_audited_distributions_register_is_documented_in_10() -> None:
    """Property 5, the reverse direction: a name one of `_AUDITED_DISTRIBUTIONS` actually
    registers and `10` never mentions — in §1.1, §2.2 or §1.5 — is exactly the gap that let
    a future plugin claim a reserved technique's near neighbour unnoticed, which is what
    the base commit shipped fourteen documented names and left roughly two dozen others
    silent about."""
    # Arrange
    audited = names_registered_by(_AUDITED_DISTRIBUTIONS) - NAMES_WAIVED_FROM_THE_CATALOGUE
    documented = weft_names_in_catalogue()

    # Act
    undocumented = audited - documented

    # Assert
    assert not undocumented, (
        f"{sorted(undocumented)} registered by one of {_AUDITED_DISTRIBUTIONS} and named "
        f"nowhere in `10` §1.1, §2.2 or §1.5. Add a row — §1.5, if it earns no citation of "
        f"its own — or waive it with a stated reason."
    )


def test_an_unresolvable_catalogue_name_would_be_caught() -> None:
    """Property 4's own teeth: a name §1.1 could state that resolves to neither a plugin
    nor a pipeline must be flagged, proven against a fabricated name no real plugin and no
    real pipeline could ever coincidentally hold."""
    # Arrange
    claimed = frozenset({"not-a-real-technique-2026"})
    resolvable = registered_names() | shipped_pipeline_names()

    # Act
    unresolved = claimed - resolvable

    # Assert
    assert unresolved == {"not-a-real-technique-2026"}


def test_an_undocumented_registered_name_would_be_caught() -> None:
    """Property 5's own teeth, the same self-test discipline one function up."""
    # Arrange
    audited = frozenset({"not-a-real-technique-2026"})
    documented = weft_names_in_catalogue()

    # Act
    undocumented = audited - documented

    # Assert
    assert undocumented == {"not-a-real-technique-2026"}


def test_the_waiver_is_doing_real_work() -> None:
    """`NAMES_WAIVED_FROM_THE_CATALOGUE` is not a silent escape hatch: every name in it must
    actually need the exemption — provably unresolvable without it — or the entry is dead
    weight nobody would notice going stale. Proven against `routing-policy`, the one member
    today: neither a registered plugin nor a shipped pipeline names it, so the forward
    check in `test_every_weft_name_in_1_1_resolves_to_a_plugin_or_a_pipeline` really would
    fail on it without this waiver."""
    # Arrange
    resolvable = registered_names() | shipped_pipeline_names()

    # Act
    still_unresolved = NAMES_WAIVED_FROM_THE_CATALOGUE - resolvable

    # Assert
    assert still_unresolved == NAMES_WAIVED_FROM_THE_CATALOGUE, (
        f"a waived name resolved on its own: {NAMES_WAIVED_FROM_THE_CATALOGUE & resolvable}. "
        f"Remove it from the waiver — the exemption is no longer earning its place."
    )


@dataclass(frozen=True)
class _CitedTechnique:
    """One `10` §1.1/§1.2 row whose Origin column names a paper, and the anchor that paper's
    own citation is found by — an arXiv id or a DOI, never prose, so a citation can be reworded
    to match its module's own voice without this check caring."""

    name: str
    distribution: str
    anchors: tuple[str, ...]


#: Every technique this phase ships (tasks 2.13-2.25) whose catalogue row cites a paper the
#: plugin's name is earned against — read straight off task 2.26's own audit of each plugin
#: against `docs/10-technique-catalogue.md` §1.1. Sufficiency's two implementations
#: (`llm-sufficiency`, `hedge-phrases`) and `contextual-query-rewrite` are absent on purpose:
#: `10` §1.1 states neither traces to a paper (`llm-sufficiency`/`hedge-phrases` are this
#: build's own mechanism; `contextual-query-rewrite`'s own row: "no single origin traced …
#: unconfirmed"), so there is no citation for a future edit to silently drop. `vector-top-k`
#: is likewise absent: it is `10` §2.1 rule 5's *composition*, not a cited technique in its own
#: right — see that plugin's own module docstring.
_CITED_TECHNIQUES: Final[tuple[_CitedTechnique, ...]] = (
    _CitedTechnique("no-retrieval", "weft-retrieve", ("2002.08910", "2403.14403")),
    _CitedTechnique("hyde", "weft-retrieve", ("2212.10496",)),
    _CitedTechnique("step-back", "weft-retrieve", ("2310.06117",)),
    _CitedTechnique("multi-query", "weft-retrieve", ("2305.03653",)),
    _CitedTechnique("reciprocal-rank-fusion", "weft-retrieve", ("1571941.1572114",)),
    _CitedTechnique("boolean-retrieval", "weft-retrieve", ("2305.11694",)),
    _CitedTechnique("repack", "weft-retrieve", ("2407.01219", "2307.03172")),
    _CitedTechnique("iterative-retrieval", "weft-retrieve", ("1910.07000",)),
    _CitedTechnique("graded-retrieval", "weft-retrieve", ("2401.15884",)),
    _CitedTechnique("corrective", "weft-retrieve", ("2401.15884",)),
    _CitedTechnique("query-scorer", "weft-retrieve", ("2403.14403",)),
    _CitedTechnique("contradiction-check", "weft-generate", ("2403.08319",)),
    _CitedTechnique("refine-on-uncertainty", "weft-generate", ("2305.06983",)),
)


def _distribution_source(distribution: str) -> str:
    """Every `.py` file `packages/<distribution>/src` holds, concatenated — the whole pack's
    own text, not one hand-picked module, because a citation may legitimately live beside the
    prompt that asks the paper's own question (`weft_retrieve.prompts`) rather than beside the
    plugin's `run` method."""
    src = PACKAGES_ROOT / distribution / "src"
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(src.rglob("*.py"))
        if "__pycache__" not in path.parts
    )


def test_every_cited_technique_names_a_plugin_actually_registered() -> None:
    """The table above is a claim about the registry, not just about `10` — a name it lists
    that nothing registers would make every check below pass vacuously for that row."""
    # Arrange
    registered = registered_names()

    # Act
    missing = [t.name for t in _CITED_TECHNIQUES if t.name not in registered]

    # Assert
    assert not missing, (
        f"_CITED_TECHNIQUES names plugin(s) nothing registers: {missing}. Either the plugin "
        f"was renamed (update this table to match) or removed (drop the row)."
    )


def test_every_cited_technique_still_carries_its_paper_citation() -> None:
    """A name earned against a paper keeps that paper's own id somewhere in the pack that
    registers it — the mechanical half of `10` §2.1 rule 4, which a docstring rewrite cannot
    silently break the way prose alone could."""
    # Arrange
    sources = {t.distribution: _distribution_source(t.distribution) for t in _CITED_TECHNIQUES}

    # Act
    missing = {
        technique.name: [
            anchor for anchor in technique.anchors if anchor not in sources[technique.distribution]
        ]
        for technique in _CITED_TECHNIQUES
    }
    missing = {name: anchors for name, anchors in missing.items() if anchors}

    # Assert
    assert not missing, (
        f"technique(s) registered under a name earned against a paper no longer carry that "
        f"paper's own citation anywhere in the pack that registers them: {missing}. Either the "
        f"citation was dropped from a docstring (restore it) or the name has drifted from "
        f"`10` §1.1/§1.2 (update the catalogue row and this table together)."
    )


def test_a_missing_citation_would_be_caught() -> None:
    """This check's own teeth: a technique whose anchor is not actually in its pack's source
    must be flagged, proven against a fabricated arXiv id no real paper carries."""
    # Arrange
    fabricated = _CitedTechnique("hyde", "weft-retrieve", ("9999.99999",))
    source = _distribution_source(fabricated.distribution)

    # Act
    missing = [anchor for anchor in fabricated.anchors if anchor not in source]

    # Assert
    assert missing == ["9999.99999"]
