"""Fitness function 25 — a handler that swallows an error into an `Outcome` lets ours past first.

**This check exists because its absence cost a whole phase, silently.** `docs/internal/lessons.md`
`L9.87`: `openai-vision` built its SDK client on the event loop thread, so the registration seam's
blocking-call detector raised `BlockingCallError` — a `WeftError`, this project telling itself its
own code is wrong. The plugin's broad `except Exception` caught it and returned
`Failed(reason=...)`, and `describe-figure` then discarded that `Failed` as an ordinary absence. Net
result: `weft index` through a shipped document stored a figure with no description, exit code `0`,
nothing printed, `weft plugins doctor` reporting the pack `active`, and 2,395 tests green. It was
found by running the binary at Phase 9's exit demonstration, not by any test.

**The rule this asserts, and the two it deliberately does not.** A broad handler is legitimate —
`weft_kernel.seam`, `weft_kernel.discovery`, `weft_kernel.runner` and `weft_cli.cli` all catch
`Exception` at a boundary in order to *raise* a `WeftError` with attribution, which is exactly the
right shape and is what `CLAUDE.md` means by attaching cross-cutting concerns at the seam. What is
never right is a handler that **swallows** — returns `Failed` or `NothingToProduce` — without first
letting a narrower error class through, because an `Outcome` is a statement about the *data*, and a
`WeftError` is a statement about the *code*. Reporting the second as the first is a silent fallback
wearing a result, which `CLAUDE.md` ranks as worse than a crash for exactly the reason this cost:
it does not stop, it produces a plausible answer, and its success and failure paths become
indistinguishable to the caller.

**Population, measured before this check was written** (`docs/internal/lessons.md` `L9.89`): of 15
`try` blocks under `packages/` carrying a broad handler, **13 raise** and are none of this check's
business; **2 swallow into an `Outcome`** — `weft_openai.vision` and `weft_docling.pdf_layout_model`
— and both guard correctly today. A first draft of this check asked the wider question ("is any
narrower handler present?") and would have arrived red on six kernel boundary sites that are all
correct; sizing it against the population is what turned it into a ratchet with an empty waiver
rather than a waiver with six entries for the real violations to hide behind.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Final

from .conftest import REPO_ROOT

PACKAGES: Final[Path] = REPO_ROOT / "packages"

#: What a swallowing handler returns. `NothingToProduce` is here beside `Failed` on purpose: it is
#: the *more* dangerous of the two to reach by accident, because it reads downstream as "there was
#: legitimately nothing here" rather than as trouble at all.
_SWALLOWED: Final[frozenset[str]] = frozenset({"Failed", "NothingToProduce"})

#: Handlers permitted to swallow with nothing narrower ahead of them. **Pinned empty.** An entry
#: here is a claim that some error of ours is genuinely a fact about the data, which is a claim
#: worth making in a diff and not in an edit.
HANDLERS_SWALLOWING_OUR_OWN_ERRORS: Final[frozenset[str]] = frozenset()


def _is_broad(handler: ast.ExceptHandler) -> bool:
    """`except:` or `except Exception:` — the two spellings that catch our own error types."""
    return handler.type is None or (
        isinstance(handler.type, ast.Name) and handler.type.id == "Exception"
    )


def _swallows(handler: ast.ExceptHandler) -> bool:
    """Whether this handler returns an `Outcome` rather than raising.

    A `raise` — bare, or of a `WeftError` built from the caught exception — is the boundary shape
    this check exists to leave alone, so the test is what the handler *returns*, never what it
    catches.
    """
    return any(
        isinstance(node, ast.Return)
        and isinstance(node.value, ast.Call)
        and _called_name(node.value.func) in _SWALLOWED
        for node in ast.walk(handler)
    )


def _called_name(func: ast.expr) -> str | None:
    if isinstance(func, ast.Name):
        return func.id
    return func.attr if isinstance(func, ast.Attribute) else None


def _guarded_before(handlers: list[ast.ExceptHandler], index: int) -> bool:
    """Whether an earlier handler in the same `try` lets **`WeftError`** past.

    **Not "any narrower error class", and the first draft of this function was exactly that.**
    Planted against the real defect, that version passed: `weft_openai.vision` already carried
    `except asyncio.CancelledError: raise` ahead of its broad handler *before* the repair, and
    `CancelledError` ends in `Error`, so a check asking "is anything narrower present?" was
    satisfied by a guard that has nothing to do with this. It would have shipped green through
    the very phase it was written to prevent. `phase-step` → *Finish* item 3 — plant the *right*
    disagreement — caught it, and the sentence in `implement-ll` that this drain adds is the
    generalisation.

    `WeftError` by name, because it is this project's own base and every error the seam raises
    derives from it (`weft_kernel.errors`); a pack that guards only its own subclass still turns
    every *other* `WeftError` into a `Failed`, which is the defect, so a subclass name is not
    enough and the strictness is deliberate.
    """
    return any(
        isinstance(name, str) and name == "WeftError"
        for earlier in handlers[:index]
        if earlier.type is not None
        for node in ast.walk(earlier.type)
        for name in [node.id if isinstance(node, ast.Name) else getattr(node, "attr", None)]
    )


def _swallowing_handlers() -> list[tuple[str, ast.ExceptHandler, list[ast.ExceptHandler]]]:
    """Every broad handler under `packages/` that returns an `Outcome`, with its siblings."""
    found: list[tuple[str, ast.ExceptHandler, list[ast.ExceptHandler]]] = []
    for path in sorted(PACKAGES.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        relative = str(path.relative_to(REPO_ROOT))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Try):
                continue
            for handler in node.handlers:
                if _is_broad(handler) and _swallows(handler):
                    found.append((f"{relative}:{handler.lineno}", handler, node.handlers))
    return found


def test_the_waiver_is_empty() -> None:
    assert frozenset() == HANDLERS_SWALLOWING_OUR_OWN_ERRORS, (
        "HANDLERS_SWALLOWING_OUR_OWN_ERRORS is no longer empty. A broad handler that turns one "
        "of this project's own errors into a Failed is reporting a defect in the code as a fact "
        "about the data — add the narrower handler rather than recording the exception here."
    )


def test_the_population_is_not_empty() -> None:
    """Floor — a walk that matched nothing would pass by asking nothing.

    Two swallowing handlers existed when this was written (`weft_openai.vision`,
    `weft_docling.pdf_layout_model`). If this ever reads zero, the pattern stopped matching, which
    is the vacuous shape `phase-step` → *Finish* item 3 refuses — not evidence that the shape went
    away.
    """
    assert len(_swallowing_handlers()) >= 2


def test_a_handler_that_swallows_lets_our_own_errors_past_first() -> None:
    """Fitness function 25 itself."""
    offenders = [
        location
        for location, handler, siblings in _swallowing_handlers()
        if location not in HANDLERS_SWALLOWING_OUR_OWN_ERRORS
        and not _guarded_before(siblings, siblings.index(handler))
    ]
    assert not offenders, (
        "these handlers turn every exception — including this project's own — into an Outcome, "
        "with nothing narrower ahead of them:\n  "
        + "\n  ".join(offenders)
        + "\n\nA WeftError is a statement about the code and an Outcome is a statement about the "
        "data; reporting the first as the second is how `describe-figure` shipped dead and "
        "silent for a phase (docs/internal/lessons.md L9.87). Add `except CancelledError: raise` "
        "and"
        "`except WeftError: raise` ahead of the broad handler."
    )


def test_the_check_can_actually_fail() -> None:
    """Non-vacuity, driven through the same predicates the check uses.

    Synthetic source rather than a real file: the tree's two live instances are both correct, so
    a check exercised only against them would pass whether or not it works.
    """
    # Arrange
    unguarded = ast.parse(
        "try:\n    x()\nexcept Exception as exc:\n    return Failed(reason=str(exc))\n"
    )
    guarded = ast.parse(
        "try:\n    x()\nexcept WeftError:\n    raise\n"
        "except Exception as exc:\n    return Failed(reason=str(exc))\n"
    )
    # The shape that fooled the first draft: a narrower handler that is not one of ours.
    cancelled_only = ast.parse(
        "try:\n    x()\nexcept asyncio.CancelledError:\n    raise\n"
        "except Exception as exc:\n    return Failed(reason=str(exc))\n"
    )

    # Act
    def verdict(tree: ast.AST) -> bool:
        node = next(n for n in ast.walk(tree) if isinstance(n, ast.Try))
        handler = node.handlers[-1]
        return (
            _is_broad(handler)
            and _swallows(handler)
            and not _guarded_before(node.handlers, node.handlers.index(handler))
        )

    # Assert
    assert verdict(unguarded), "the check cannot see an unguarded swallowing handler"
    assert not verdict(guarded), "the check fires on a handler that is correctly guarded"
    assert verdict(cancelled_only), (
        "a CancelledError guard is not a WeftError guard — this is the exact shape "
        "weft_openai.vision carried while describe-figure was dead (L9.87), and the first "
        "draft of this check passed it"
    )
