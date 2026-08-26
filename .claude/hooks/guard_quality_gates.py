"""PreToolUse guard: an agent that cannot make a check pass must not make the check pass instead.

Weft's quality gates — `docs/01-high-level-plan.md`'s fitness functions and the lint/type
configuration in `pyproject.toml` — are the specification. `CLAUDE.md`'s *Quality gates* section
names the failure mode this file exists to catch: raising a budget, adding a waiver entry,
sprinkling `# type: ignore`, deleting an assertion, or dropping a step out of `ci-checks` — every
one of these makes the gate agree with the code instead of moving the code to agree with the
gate. Several fitness functions are pinned-empty named waivers for exactly this reason (the
reference's `test_allowlist_empty.py` technique, credited in `test_ff0_gate_in_the_gate.py`): a
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
deny > defer > ask > allow, so a reference-path write this hook would otherwise `ask` about stays
blocked if `guard_readonly.py` also denies it. `_ASK_IS_SUPPORTED` below is the one flag to flip
back to `False` — falling back to `deny` with the same human-directed reason — should a future
harness revision drop `ask` for this event.

**Known blind spot, stated rather than hidden:** this is a `PreToolUse` hook on
`Edit|Write|NotebookEdit`. It cannot see `rm` deleting a whole `tests/architecture/` file — no
tool call passes through this matcher for that. A `Write` that overwrites an existing file with
materially fewer assertions or `def test_` blocks is still caught by signature 4.

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

import json
import os
import re
import sys
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
            if current.strip():
                items.append(current.strip())
            current = ""
        else:
            current += char
    if current.strip():
        items.append(current.strip())
    return items


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
    finding** (`docs/lessons.md` L6.23). `old_text` is empty by construction for a `Write` to a
    path that did not exist, so *every* marker in the initial content looks added — the
    false-positive rate on that input is 100%, which makes it a guaranteed prompt rather than a
    heuristic. The check still fires, because a new file is a perfectly good place to hide a
    suppression; what changes is that the human being asked is told which of the two situations
    they are in. Two dispatched implementers and one session paid for the old message before this
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
    problems: list[str] = []

    old_select = _named_literal(old_text, "select")
    new_select = _named_literal(new_text, "select")
    if old_select is not None and new_select is not None:
        old_items = _string_items(old_select)
        missing = [item for item in old_items if item not in _string_items(new_select)]
        if missing:
            problems.append(f"ruff select lost {missing}")

    mode_match_old = re.search(r'typeCheckingMode\s*=\s*"([^"]*)"', old_text)
    mode_match_new = re.search(r'typeCheckingMode\s*=\s*"([^"]*)"', new_text)
    if mode_match_old and mode_match_new:
        old_mode, new_mode = mode_match_old.group(1), mode_match_new.group(1)
        old_rank, new_rank = _TYPE_CHECKING_RANK.get(old_mode), _TYPE_CHECKING_RANK.get(new_mode)
        if old_rank is not None and new_rank is not None and new_rank < old_rank:
            problems.append(f"typeCheckingMode weakened {old_mode!r} -> {new_mode!r}")

    old_rules, new_rules = _report_rule_values(old_text), _report_rule_values(new_text)
    for rule, old_value in old_rules.items():
        new_value = new_rules.get(rule)
        if new_value is None:
            continue
        if old_value.lower() not in {"none", "false"} and new_value.lower() in {"none", "false"}:
            problems.append(f"{rule} loosened {old_value!r} -> {new_value!r}")

    if not problems:
        return None
    return "lint_types", "; ".join(problems)


_SIGNATURES: Final[tuple[_Detector, ...]] = (
    _waiver_gained_entries,
    _budget_grew,
    _suppression_appeared,
    _assertions_or_tests_disappeared,
    _composite_lost_a_step,
    _lint_or_types_loosened,
)


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
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(state), encoding="utf-8")
    except OSError:
        pass  # persistence failing degrades to "always first attempt" — never a crash


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
        f"(docs/05-grilling-sessions.md), not an in-place fix."
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


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0
    if not isinstance(payload, dict):
        return 0

    tool_name = payload.get("tool_name")
    tool_input = payload.get("tool_input")
    if tool_name not in {"Edit", "Write", "NotebookEdit"} or not isinstance(tool_input, dict):
        return 0

    extracted = _extract_edit(tool_name, tool_input)
    if extracted is None:
        return 0
    target, old_text, new_text = extracted

    findings = [
        finding
        for detector in _SIGNATURES
        if (finding := detector(target, old_text, new_text)) is not None
    ]
    if not findings:
        return 0

    session_id = payload.get("session_id")
    session_id = session_id if isinstance(session_id, str) and session_id else "unknown-session"
    count, limit = _record_attempt(session_id, target)

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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
