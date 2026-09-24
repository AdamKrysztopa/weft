"""PreToolUse guard: an agent that cannot make a check pass must not make the check pass instead.

Weft's quality gates — `docs/01-high-level-plan.md`'s fitness functions and the lint/type
configuration in `pyproject.toml` — are the specification. `CLAUDE.md`'s *Quality gates* section
names the failure mode this file exists to catch: raising a budget, adding a waiver entry,
sprinkling `# type: ignore`, deleting an assertion, or dropping a step out of `ci-checks` — every
one of these makes the gate agree with the code instead of moving the code to agree with the
gate. Several fitness functions are pinned-empty named waivers for exactly this reason (the
pinned-empty-allowlist technique `test_ff0_gate_in_the_gate.py` describes): a
weakening is supposed to be a *visible act in a diff*. This hook is what makes it a deliberate one
too, by refusing the edit the first few times and coaching the agent back toward the code, then
handing the decision to a human once the same file has been fought over repeatedly.

**What is guarded is weakening, not editing.** Adding a new fitness function, wiring one into
`ci-checks`, or writing a brand-new `tests/architecture/test_*.py` file is required work — fitness
function 0 exists to force exactly that, and build-ledger task 2.36 is doing it as this file is
written. So detection is six specific signatures, each read off a diff (`old_string`/`new_string`
for `Edit`, current-disk-content vs new `content` for `Write`), never a bare "this file changed":

  1. A waiver/allowlist-shaped collection (name containing WAIVER, WAIVED, WITHOUT_, ALLOWLIST,
     ALLOW_LIST, EXEMPT, IGNORE or SKIP_ — case-insensitively, so ruff's `ignore` list qualifies
     too) goes from fewer elements to more, anywhere in the tree.
  2. An ALL_CAPS numeric constant in a `tests/architecture/` file grows (the kernel budget in
     `test_ff3_kernel_budget.py` is the constant this exists for; shrinking is never flagged).
  3. A suppression marker (`# noqa`, `# type: ignore`, `# pyright: ignore`, `@pytest.mark.skip`,
     `@pytest.mark.xfail`, `pytest.skip(`, `ruff: noqa`) appears in the new text and was not in
     the old, under `packages/`, `tests/`, `examples/`, `testing/`, `scripts/` or `eval/`.
  4. A `tests/architecture/` edit's `assert` count or `def test_` count goes down.
  5. `pyproject.toml`'s `sequence = [...]` under a `[tool.poe.tasks.*]` loses an entry it had, or
     one of the `fmt`/`lint`/`types`/`arch`/`test` tasks disappears. Additions are never flagged.
  6. `pyproject.toml` (or a `ruff.toml`/`pyrightconfig.json`) loses a `ruff.lint.select` entry,
     moves `typeCheckingMode` toward a weaker setting, or moves a `report*` rule to `"none"`/
     `false`.
  7. `.pre-commit-config.yaml` loses a hook `id:` it had.

Each detector is a textual heuristic, not a TOML or Python parser — deliberately, because this
hook coaches an agent's behaviour, it does not replace `ci-checks` as the actual enforcement.
A heuristic that misses an unusual edit shape is a missed nudge; the gate itself still has to be
weakened *and pass review* for the weakening to stick. A heuristic that over-fires costs one
`deny` and a specific, actionable reason — never a crash, and never a silent block with no
explanation.

**Escalation.** Attempts are counted per `(session_id, file)`, read from the hook's stdin payload
and persisted in `.claude/.gate-attempts.json` (gitignored — session-local scratch, not a record
anyone should read later). Attempts 1 through `WEFT_GATE_GUARD_LIMIT - 1` (default limit 3) deny
with a reason addressed to the agent: which signature fired, what it saw, and the concrete
alternative — fix the code, or, if the check is genuinely wrong, raise it with the human rather
than editing it in place. Attempt `WEFT_GATE_GUARD_LIMIT` and beyond asks instead of denying: the
edit still does not go through unreviewed, but the reason is addressed to the human, kindly and
specifically — N attempts have now been made against this file, here is what is being asked for
and what it would cost to grant, please decide. They may well be right.

**On the hook contract:** verified against code.claude.com/docs/en/hooks.md and permissions.md
(Decision control, and the exit-code table) — a PreToolUse hook returns its decision as
`hookSpecificOutput` (`hookEventName`, `permissionDecision`, `permissionDecisionReason`) printed
to stdout, honoured on any exit code except 2 (2 always blocks, regardless of JSON). Current
`permissionDecision` values are `"allow"`, `"deny"`, `"ask"` and headless-only `"defer"` — so the
"hand it to the human" step below really does emit `"ask"`, which the harness surfaces as a
prompt to the user rather than a silent block, with `permissionDecisionReason` written for that
human reader. Multiple `PreToolUse` hooks can fire on the same matcher (`guard_readonly.py` does,
on the identical `Edit|Write|NotebookEdit` matcher) and precedence across them is
deny > defer > ask > allow, so a read-only-path write this hook would otherwise `ask` about stays
blocked if `guard_readonly.py` also denies it. `_ASK_IS_SUPPORTED` below is the one flag to flip
back to `False` — falling back to `deny` with the same human-directed reason — should a future
harness revision drop `ask` for this event.

**A gate file written through `Bash` is read after the fact** (`docs/internal/lessons.md`
`L28.49`). A per-file-ignore reached `pyproject.toml` through a Python script run by `Bash`, where
the editing-tool matcher never saw it. So this file is also hooked on `Bash`, from both sides:
`PreToolUse` snapshots every file `_bash_guarded_files` names, and `PostToolUse` runs the same
signatures over each one the command changed — a deleted architecture test included, which
signature 4 reads as every assertion gone. A command cannot be judged before it writes, so a
finding there always blocks with a reason telling the agent to put the file back; it never
escalates to `ask` and never restores the file itself. A gate change that is genuinely wanted goes
through `Edit`, which is where the owner is asked. **A command that exits non-zero reaches
`PostToolUseFailure`, not `PostToolUse`** (measured 2026-09-24: its snapshot was never consumed).
`main` handles that event too, but it reaches this file only if `.claude/settings.json` registers
it for `Bash`. Where it does not, a gate written by a failing command goes unread, and its
snapshot is pruned after `_SNAPSHOT_MAX_AGE_SECONDS`.

A corrupt or unreadable `.gate-attempts.json`, or a malformed stdin payload, must never crash this
hook — a hook that raises blocks every edit in the session, which is a far worse failure than one
missed detection. Both degrade to "first attempt" / "allow" respectively.

**On the Python this runs under:** hooks are launched as bare `python3` by the harness, not
through this workspace's `uv`-managed 3.12 environment — this machine's `python3` is 3.9. So,
unlike every package under `packages/`, this file carries `from __future__ import annotations`
(deferring every annotation's evaluation to a string, PEP 563) and avoids the `X | Y` union
operator (PEP 604, 3.10+) in the one place it would be evaluated eagerly rather than deferred as
an annotation. This is a constraint of where the file runs, not a stylistic departure from
`CLAUDE.md`'s "native 3.12 type hints" — the rest of this repository is under no such constraint.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    # Only for static type checkers (`pyright`, run under this workspace's own 3.12). This
    # module also runs under a bare `python3` that may be older — see "On the Python this runs
    # under" above — so nothing here may be evaluated at import time; it never is, because
    # `from __future__ import annotations` defers every annotation to a string.
    from collections.abc import Callable

REPO: Final[Path] = Path(__file__).resolve().parents[2]
STATE_FILE: Final[Path] = REPO / ".claude" / ".gate-attempts.json"
DEFAULT_ATTEMPT_LIMIT: Final[int] = 3
LIMIT_ENV_VAR: Final[str] = "WEFT_GATE_GUARD_LIMIT"

#: See the module docstring's "On the hook contract" paragraph. Flip this to `False` — no other
#: code change needed — if a future harness revision drops `ask` as a `PreToolUse` value.
_ASK_IS_SUPPORTED: Final[bool] = True

_SUPPRESSION_SCOPE: Final[tuple[str, ...]] = (
    "packages",
    "tests",
    "examples",
    "testing",
    "scripts",
    "eval",
)
_ARCHITECTURE_TESTS: Final[str] = "tests/architecture"
_POE_COMPOSITE_TASKS: Final[frozenset[str]] = frozenset({"fmt", "lint", "types", "arch", "test"})
_TYPE_CHECKING_RANK: Final[dict[str, int]] = {"off": 0, "basic": 1, "standard": 2, "strict": 3}
_LINT_TYPE_CONFIG_NAMES: Final[frozenset[str]] = frozenset(
    {"pyproject.toml", "ruff.toml", ".ruff.toml", "pyrightconfig.json"}
)

_PRE_COMMIT_CONFIG: Final[str] = ".pre-commit-config.yaml"
_BASH_GUARDED_ROOT_FILES: Final[frozenset[str]] = _LINT_TYPE_CONFIG_NAMES | {_PRE_COMMIT_CONFIG}
_SNAPSHOT_DIR: Final[Path] = Path(tempfile.gettempdir()) / "weft-gate-snapshots"
_SNAPSHOT_MAX_AGE_SECONDS: Final[int] = 3600
_AFTER_EVENTS: Final[frozenset[str]] = frozenset({"PostToolUse", "PostToolUseFailure"})
_HOOK_ID_RE: Final[re.Pattern[str]] = re.compile(r"(?m)^[ \t-]*id:\s*([^\s#]+)")

_WAIVER_KEYWORDS: Final[tuple[str, ...]] = (
    "waiver",
    "waived",
    "without_",
    "allowlist",
    "allow_list",
    "exempt",
    "ignore",
    "skip_",
)
_SUPPRESSION_MARKERS: Final[tuple[str, ...]] = (
    "# noqa",
    "# type: ignore",
    "# pyright: ignore",
    "@pytest.mark.skip",
    "@pytest.mark.xfail",
    "pytest.skip(",
    "ruff: noqa",
)

_ASSIGN_NAME_RE: Final[re.Pattern[str]] = re.compile(
    r"(?m)^[ \t]*([A-Za-z_][A-Za-z0-9_-]*)\s*(?::[^=\n]*)?=\s*"
)
_INT_ASSIGN_RE: Final[re.Pattern[str]] = re.compile(
    r"(?m)^[ \t]*([A-Z][A-Z0-9_]*)\s*(?::[^=\n]*)?=\s*([0-9][0-9_]*)\s*(?:#.*)?$"
)
_ASSERT_RE: Final[re.Pattern[str]] = re.compile(r"(?<![\w.])assert(?![\w])")
_TEST_DEF_RE: Final[re.Pattern[str]] = re.compile(r"(?m)^[ \t]*(?:async\s+)?def\s+test_\w*")
_REPORT_RULE_RE: Final[re.Pattern[str]] = re.compile(
    r'(?m)^[ \t]*(report[A-Za-z]+)\s*=\s*"?([A-Za-z]+)"?'
)

if TYPE_CHECKING:
    # A finding is (signature key, human-readable detail). Also guarded by `TYPE_CHECKING`:
    # `_Finding | None` is a plain expression here, not an annotation, so on real Python 3.9
    # (see the module docstring) it would be evaluated eagerly and fail — PEP 604 union syntax
    # needs 3.10+. Under `TYPE_CHECKING` it is never executed on any interpreter, only read by
    # `pyright`, which checks this workspace at its own `py312` target regardless.
    _Finding = tuple[str, str]
    _Detector = Callable[[Path, str, str], _Finding | None]


def _relative(path: Path) -> str:
    try:
        return str(path.relative_to(REPO))
    except ValueError:
        return str(path)


def _under(path: Path, *prefixes: str) -> bool:
    rel = _relative(path)
    return any(rel == prefix or rel.startswith(prefix + "/") for prefix in prefixes)


# --- balanced-literal extraction --------------------------------------------------------------
# These three helpers read a Python or TOML collection literal (possibly spanning several lines,
# such as the multi-line `frozenset({...})` ratchets in `tests/architecture/`) without a real
# parser. Any bracket character counts toward one shared depth; well-formed source is always
# balanced, so this cannot mismatch a `(` against a `]` in a way that matters here.


def _extract_literal(text: str, start: int) -> str | None:
    index = start
    length = len(text)
    while index < length and text[index] in " \t":
        index += 1
    name_match = re.match(r"[A-Za-z_][A-Za-z0-9_]*", text[index:])
    if name_match:
        index += name_match.end()
        while index < length and text[index] in " \t":
            index += 1
    if index >= length or text[index] not in "([{":
        return None
    depth = 0
    cursor = index
    while cursor < length:
        char = text[cursor]
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
            if depth == 0:
                return text[start:cursor].strip() + text[cursor]
        cursor += 1
    return None


def _inner_content(literal: str) -> str:
    first = next((i for i, ch in enumerate(literal) if ch in "([{"), None)
    last = next((i for i in range(len(literal) - 1, -1, -1) if literal[i] in ")]}"), None)
    if first is None or last is None or last <= first:
        return ""
    inner = literal[first + 1 : last]
    stripped = inner.strip()
    if stripped[:1] in "([{" and stripped[-1:] in ")]}":
        return _inner_content(stripped)
    return inner


def _top_level_items(inner: str) -> list[str]:
    items: list[str] = []
    current = ""
    depth = 0
    quote = ""
    for char in inner:
        if quote:
            current += char
            if char == quote:
                quote = ""
            continue
        if char in "'\"":
            quote = char
            current += char
        elif char in "([{":
            depth += 1
            current += char
        elif char in ")]}":
            depth -= 1
            current += char
        elif char == "," and depth == 0:
            _append_stripped(items, current)
            current = ""
        else:
            current += char
    _append_stripped(items, current)
    return items


def _append_stripped(items: list[str], item: str) -> None:
    if item.strip():
        items.append(item.strip())


def _count_elements(literal: str) -> int:
    return len(_top_level_items(_inner_content(literal)))


def _string_items(literal: str) -> list[str]:
    return [item.strip("'\"") for item in _top_level_items(_inner_content(literal))]


def _named_literal(text: str, key: str) -> str | None:
    match = re.search(rf"(?m)^[ \t]*{re.escape(key)}\s*=\s*", text)
    if match is None:
        return None
    return _extract_literal(text, match.end())


# --- signature 1: a waiver/allowlist-shaped collection gains entries -----------------------


def _looks_like_waiver_name(name: str) -> bool:
    lowered = name.lower()
    return any(keyword in lowered for keyword in _WAIVER_KEYWORDS)


def _named_collections(text: str) -> dict[str, str]:
    found: dict[str, str] = {}
    for match in _ASSIGN_NAME_RE.finditer(text):
        name = match.group(1)
        if not _looks_like_waiver_name(name):
            continue
        literal = _extract_literal(text, match.end())
        if literal is not None:
            found[name] = literal
    return found


def _waiver_gained_entries(path: Path, old_text: str, new_text: str) -> _Finding | None:
    del path  # unscoped by design — see signature 1 in the module docstring
    old_literals = _named_collections(old_text)
    new_literals = _named_collections(new_text)
    grown = sorted(
        name
        for name, new_literal in new_literals.items()
        if name in old_literals
        and _count_elements(new_literal) > _count_elements(old_literals[name])
    )
    if not grown:
        return None
    detail = "; ".join(
        f"{name} {_count_elements(old_literals[name])} -> {_count_elements(new_literals[name])} "
        f"entries"
        for name in grown
    )
    return "waiver", f"a waiver/allowlist-shaped collection gained entries ({detail})"


# --- signature 2: a numeric budget or threshold grows, in tests/architecture/ ------------------


def _int_assignments(text: str) -> dict[str, int]:
    found: dict[str, int] = {}
    for name, raw_value in _INT_ASSIGN_RE.findall(text):
        try:
            found[name] = int(raw_value.replace("_", ""))
        except ValueError:
            continue
    return found


def _budget_grew(path: Path, old_text: str, new_text: str) -> _Finding | None:
    if not _under(path, _ARCHITECTURE_TESTS):
        return None
    old_values = _int_assignments(old_text)
    new_values = _int_assignments(new_text)
    grown = sorted(
        name
        for name, new_value in new_values.items()
        if name in old_values and new_value > old_values[name]
    )
    if not grown:
        return None
    detail = "; ".join(f"{name} {old_values[name]} -> {new_values[name]}" for name in grown)
    return "budget", f"a numeric budget/threshold grew in a fitness function ({detail})"


# --- signature 3: a suppression marker appears -------------------------------------------------


def _suppression_appeared(path: Path, old_text: str, new_text: str) -> _Finding | None:
    """A marker in `new_text` that was not in `old_text`.

    **A new file has no "before", and this says so rather than reporting its blind spot as a
    finding** (`docs/internal/lessons.md` L6.23). `old_text` is empty by construction for a `Write`
    to a path that did not exist, so *every* marker in the initial content looks added — the
    false-positive rate on that input is 100%, which makes it a guaranteed prompt rather than a
    heuristic. The check still fires, because a new file is a perfectly good place to hide a
    suppression; what changes is that the human being asked is told which of the two situations they
    are in. Two dispatched implementers and one session paid for the old message before this
    distinction existed.
    """
    if not _under(path, *_SUPPRESSION_SCOPE):
        return None
    appeared = [
        marker for marker in _SUPPRESSION_MARKERS if marker in new_text and marker not in old_text
    ]
    if not appeared:
        return None
    if not old_text.strip():
        return (
            "suppression",
            "this file is NEW, so there is no previous content to compare against and every "
            "marker in it necessarily reads as added. The markers are: "
            "{markers}. Judge them on whether they belong in new code, not on the fact that "
            "they are new -- the check cannot tell those apart here.".format(markers=appeared),
        )
    return "suppression", f"a suppression marker appeared that was not there before: {appeared}"


# --- signature 4: fewer assertions or tests, in tests/architecture/ ----------------------------


def _assertions_or_tests_disappeared(path: Path, old_text: str, new_text: str) -> _Finding | None:
    if not _under(path, _ARCHITECTURE_TESTS):
        return None
    problems: list[str] = []
    old_asserts, new_asserts = len(_ASSERT_RE.findall(old_text)), len(_ASSERT_RE.findall(new_text))
    if new_asserts < old_asserts:
        problems.append(f"assert count {old_asserts} -> {new_asserts}")
    old_tests, new_tests = len(_TEST_DEF_RE.findall(old_text)), len(_TEST_DEF_RE.findall(new_text))
    if new_tests < old_tests:
        problems.append(f"def test_ count {old_tests} -> {new_tests}")
    if not problems:
        return None
    return (
        "coverage",
        f"a fitness function edit has fewer checks than before ({'; '.join(problems)})",
    )


# --- signature 5: pyproject.toml's composite loses a step --------------------------------------


def _poe_task_present(text: str, name: str) -> bool:
    key = re.search(rf"(?m)^[ \t]*{re.escape(name)}\s*=", text)
    header = re.search(rf"(?m)^\[tool\.poe\.tasks\.{re.escape(name)}\]", text)
    return bool(key or header)


def _composite_lost_a_step(path: Path, old_text: str, new_text: str) -> _Finding | None:
    if path.name != "pyproject.toml":
        return None
    problems: list[str] = []

    old_sequence = _named_literal(old_text, "sequence")
    new_sequence = _named_literal(new_text, "sequence")
    if old_sequence is not None and new_sequence is not None:
        old_items = _string_items(old_sequence)
        missing = [item for item in old_items if item not in _string_items(new_sequence)]
        if missing:
            problems.append(f"sequence lost {missing}")

    for task_name in sorted(_POE_COMPOSITE_TASKS):
        if _poe_task_present(old_text, task_name) and not _poe_task_present(new_text, task_name):
            problems.append(f"task {task_name!r} appears removed or renamed")

    if not problems:
        return None
    return "composite", "; ".join(problems)


# --- signature 6: lint or type checking loosened ------------------------------------------------


def _report_rule_values(text: str) -> dict[str, str]:
    return dict(_REPORT_RULE_RE.findall(text))


def _lint_or_types_loosened(path: Path, old_text: str, new_text: str) -> _Finding | None:
    if path.name not in _LINT_TYPE_CONFIG_NAMES:
        return None
    problems = [
        *_select_lost(old_text, new_text),
        *_type_checking_weakened(old_text, new_text),
        *_report_rules_loosened(old_text, new_text),
    ]
    if not problems:
        return None
    return "lint_types", "; ".join(problems)


def _select_lost(old_text: str, new_text: str) -> list[str]:
    old_select = _named_literal(old_text, "select")
    new_select = _named_literal(new_text, "select")
    if old_select is None or new_select is None:
        return []
    old_items = _string_items(old_select)
    missing = [item for item in old_items if item not in _string_items(new_select)]
    return [f"ruff select lost {missing}"] if missing else []


def _type_checking_weakened(old_text: str, new_text: str) -> list[str]:
    mode_match_old = re.search(r'typeCheckingMode\s*=\s*"([^"]*)"', old_text)
    mode_match_new = re.search(r'typeCheckingMode\s*=\s*"([^"]*)"', new_text)
    if not (mode_match_old and mode_match_new):
        return []
    old_mode, new_mode = mode_match_old.group(1), mode_match_new.group(1)
    old_rank, new_rank = _TYPE_CHECKING_RANK.get(old_mode), _TYPE_CHECKING_RANK.get(new_mode)
    if old_rank is not None and new_rank is not None and new_rank < old_rank:
        return [f"typeCheckingMode weakened {old_mode!r} -> {new_mode!r}"]
    return []


def _report_rules_loosened(old_text: str, new_text: str) -> list[str]:
    problems: list[str] = []
    old_rules, new_rules = _report_rule_values(old_text), _report_rule_values(new_text)
    for rule, old_value in old_rules.items():
        new_value = new_rules.get(rule)
        if new_value is None:
            continue
        if old_value.lower() not in {"none", "false"} and new_value.lower() in {"none", "false"}:
            problems.append(f"{rule} loosened {old_value!r} -> {new_value!r}")
    return problems


# --- signature 7: .pre-commit-config.yaml loses a hook -----------------------------------------


def _pre_commit_lost_a_hook(path: Path, old_text: str, new_text: str) -> _Finding | None:
    if path.name != _PRE_COMMIT_CONFIG:
        return None
    remaining = set(_HOOK_ID_RE.findall(new_text))
    lost = sorted({hook for hook in _HOOK_ID_RE.findall(old_text) if hook not in remaining})
    if not lost:
        return None
    return "pre_commit", f"pre-commit lost hook(s) {lost}"


_SIGNATURES: Final[tuple[_Detector, ...]] = (
    _waiver_gained_entries,
    _budget_grew,
    _suppression_appeared,
    _assertions_or_tests_disappeared,
    _composite_lost_a_step,
    _lint_or_types_loosened,
    _pre_commit_lost_a_hook,
)


def _findings(target: Path, old_text: str, new_text: str) -> list[_Finding]:
    return [
        finding
        for detector in _SIGNATURES
        if (finding := detector(target, old_text, new_text)) is not None
    ]


# --- payload extraction --------------------------------------------------------------------


def _read_existing(path: Path) -> str:
    try:
        if path.is_file():
            return path.read_text(encoding="utf-8")
    except OSError:
        pass
    return ""


def _extract_edit(tool_name: str, tool_input: dict[str, object]) -> tuple[Path, str, str] | None:
    if tool_name == "Edit":
        raw_path, old_text, new_text = (
            tool_input.get("file_path"),
            tool_input.get("old_string"),
            tool_input.get("new_string"),
        )
        if not (
            isinstance(raw_path, str) and isinstance(old_text, str) and isinstance(new_text, str)
        ):
            return None
        return Path(raw_path).expanduser().resolve(), old_text, new_text

    if tool_name == "Write":
        raw_path, new_text = tool_input.get("file_path"), tool_input.get("content")
        if not (isinstance(raw_path, str) and isinstance(new_text, str)):
            return None
        target = Path(raw_path).expanduser().resolve()
        return target, _read_existing(target), new_text

    if tool_name == "NotebookEdit":
        # No prior cell source travels in this payload — see the module docstring's "Known
        # blind spot" paragraph. Treated as an insertion into an unknown prior state.
        raw_path, new_text = tool_input.get("notebook_path"), tool_input.get("new_source")
        if not (isinstance(raw_path, str) and isinstance(new_text, str)):
            return None
        return Path(raw_path).expanduser().resolve(), "", new_text

    return None


# --- attempt counting -----------------------------------------------------------------------


def _attempt_limit() -> int:
    raw = os.environ.get(LIMIT_ENV_VAR)
    if raw:
        try:
            parsed = int(raw)
        except ValueError:
            parsed = 0
        if parsed > 0:
            return parsed
    return DEFAULT_ATTEMPT_LIMIT


def _load_state() -> dict[str, object]:
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_state(state: dict[str, object]) -> None:
    # persistence failing degrades to "always first attempt" — never a crash
    with contextlib.suppress(OSError):
        _write_state(state)


def _write_state(state: dict[str, object]) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state), encoding="utf-8")


def _record_attempt(session_id: str, target: Path) -> tuple[int, int]:
    limit = _attempt_limit()
    key = _relative(target)
    state = _load_state()
    bucket = state.get(session_id)
    bucket = bucket if isinstance(bucket, dict) else {}
    raw_count = bucket.get(key)
    count = raw_count + 1 if isinstance(raw_count, int) else 1
    bucket[key] = count
    state[session_id] = bucket
    _save_state(state)
    return count, limit


# --- reasons ----------------------------------------------------------------------------------


def _coach_reason(findings: list[_Finding], count: int, limit: int) -> str:
    detail = " | ".join(text for _, text in findings)
    return (
        f"Quality-gate guard (attempt {count} of {limit} on this file this session): {detail}. "
        f"The gate is the specification and the code is what should move — fix what the check "
        f"is failing on rather than loosening the check. If the check itself is genuinely "
        f"wrong, that is a finding to raise with the human, never a silent edit; for a fitness "
        f"function specifically it is a docs/ conversation "
        f"(docs/internal/05-grilling-sessions.md), not an in-place fix."
    )


def _human_reason(findings: list[_Finding], count: int, target: Path) -> str:
    detail = " | ".join(text for _, text in findings)
    return (
        f"{count} attempts have now been made this session against {_relative(target)} to "
        f"change a quality gate rather than fix what it is failing on ({detail}). Changing it "
        f"would give up the coverage or boundary that finding describes — worth knowing before "
        f"deciding. Should this gate move, or is there another way to satisfy it?"
    )


def _fallback_reason(findings: list[_Finding], count: int, target: Path) -> str:
    """Used only if `_ASK_IS_SUPPORTED` is flipped off — see the module docstring."""
    return (
        "Stop here and put the following to the user directly, in your very next message, "
        f"before making this edit: {_human_reason(findings, count, target)}"
    )


def _session_id(payload: dict[str, object]) -> str:
    session_id = payload.get("session_id")
    return session_id if isinstance(session_id, str) and session_id else "unknown-session"


def _guard_edit(payload: dict[str, object], tool_name: str, tool_input: dict[str, object]) -> None:
    extracted = _extract_edit(tool_name, tool_input)
    if extracted is None:
        return
    target, old_text, new_text = extracted
    findings = _findings(target, old_text, new_text)
    if not findings:
        return

    count, limit = _record_attempt(_session_id(payload), target)
    if count < limit:
        decision, reason = "deny", _coach_reason(findings, count, limit)
    elif _ASK_IS_SUPPORTED:
        decision, reason = "ask", _human_reason(findings, count, target)
    else:
        decision, reason = "deny", _fallback_reason(findings, count, target)

    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": decision,
                    "permissionDecisionReason": reason,
                }
            }
        )
    )


# --- Bash: snapshot before, compare after -----------------------------------------------------


def _bash_guarded_files() -> dict[str, str]:
    paths = [REPO / name for name in sorted(_BASH_GUARDED_ROOT_FILES)]
    paths.extend(sorted((REPO / _ARCHITECTURE_TESTS).rglob("*.py")))
    return {_relative(path): _read_existing(path) for path in paths if path.is_file()}


def _snapshot_path(payload: dict[str, object]) -> Path:
    key = payload.get("tool_use_id")
    if not (isinstance(key, str) and key):
        tool_input = payload.get("tool_input")
        command = tool_input.get("command") if isinstance(tool_input, dict) else None
        digest = hashlib.sha256(str(command).encode("utf-8")).hexdigest()[:16]
        key = f"{_session_id(payload)}-{digest}"
    return _SNAPSHOT_DIR / f"{re.sub(r'[^A-Za-z0-9_-]', '_', key)}.json"


def _take_snapshot(payload: dict[str, object]) -> None:
    # a snapshot that cannot be written costs one missed comparison — never a blocked command
    with contextlib.suppress(OSError):
        _write_snapshot(_snapshot_path(payload), _bash_guarded_files())


def _write_snapshot(target: Path, files: dict[str, str]) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    # a command another PreToolUse hook refuses never reaches PostToolUse, stranding ~800 KB
    stale_before = time.time() - _SNAPSHOT_MAX_AGE_SECONDS
    for stale in target.parent.glob("*.json"):
        with contextlib.suppress(OSError):
            _unlink_if_older(stale, stale_before)
    target.write_text(json.dumps(files), encoding="utf-8")


def _unlink_if_older(path: Path, cutoff: float) -> None:
    if path.stat().st_mtime < cutoff:
        path.unlink()


def _pop_snapshot(payload: dict[str, object]) -> dict[str, str] | None:
    target = _snapshot_path(payload)
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    with contextlib.suppress(OSError):
        target.unlink()
    if not isinstance(data, dict):
        return None
    return {str(rel): text for rel, text in data.items() if isinstance(text, str)}


def _bash_findings(before: dict[str, str]) -> dict[str, list[_Finding]]:
    after = _bash_guarded_files()
    found: dict[str, list[_Finding]] = {}
    for rel in sorted(set(before) | set(after)):
        old_text, new_text = before.get(rel, ""), after.get(rel, "")
        if old_text == new_text:
            continue
        findings = _findings(REPO / rel, old_text, new_text)
        if findings:
            found[rel] = findings
    return found


def _bash_reason(found: dict[str, list[_Finding]], session_id: str) -> str:
    parts: list[str] = []
    for rel, findings in found.items():
        count, _ = _record_attempt(session_id, REPO / rel)
        detail = " | ".join(text for _, text in findings)
        parts.append(f"{rel} (attempt {count} this session): {detail}")
    return (
        "Quality-gate guard, after a Bash command: it weakened a quality gate — "
        + "; ".join(parts)
        + ". The change is already on disk. Put each file back to what it was before this "
        "command (`git diff` shows it) and fix the code the gate is failing on instead. If the "
        "gate is genuinely wrong, make the change with the Edit tool, where it reaches the "
        "owner — never through a shell command (docs/internal/lessons.md L28.49)."
    )


def _guard_bash_after(payload: dict[str, object]) -> None:
    before = _pop_snapshot(payload)
    if before is None:
        return
    found = _bash_findings(before)
    if not found:
        return
    reason = _bash_reason(found, _session_id(payload))
    event = payload.get("hook_event_name")
    # a command that exits non-zero reaches PostToolUseFailure, which takes context, not a block
    if event == "PostToolUseFailure":
        output = {"hookSpecificOutput": {"hookEventName": event, "additionalContext": reason}}
    else:
        output = {"decision": "block", "reason": reason}
    print(json.dumps(output))


def main() -> int:
    """Deny, then escalate to the human, an edit that weakens a quality gate.

    `Edit`, `Write` and `NotebookEdit` are judged before they land. `Bash` is snapshotted on
    `PreToolUse` and judged on `PostToolUse`, because what a command writes is known only once
    it has run.

    Returns:
        Always 0: the decision travels as JSON on stdout.
    """
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0
    if not isinstance(payload, dict):
        return 0

    tool_name = payload.get("tool_name")
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return 0
    if tool_name == "Bash" and payload.get("hook_event_name") in _AFTER_EVENTS:
        _guard_bash_after(payload)
    elif tool_name == "Bash":
        _take_snapshot(payload)
    elif tool_name in {"Edit", "Write", "NotebookEdit"}:
        _guard_edit(payload, tool_name, tool_input)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
