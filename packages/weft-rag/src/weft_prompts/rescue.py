"""The single JSON-rescue extractor — one implementation, in the order that works.

`.phase2-design.md` §7, tier 3: the single JSON-rescue extractor runs in one fixed order — direct
`json.loads` → fenced code block → bare object — because a bare-object regex tried first makes
the fenced-block branch nearly unreachable for the common ```` ```json ```` reply. Order is the
whole asset here, and it is not obvious: both orders look correct until you notice that a bare
`{`…`}` scan run first will clip a fenced block at its first brace and swallow the fence.

**Returns a value or `None`, never an `{"error": …}` dict.** A caller string-matching on an
error key is a caller that cannot tell a refusal from an answer containing the word "error";
`docs/02-extension-model.md` §5's silent-fallback row is the same defect in a different costume.

**One implementation.** `docs/10-technique-catalogue.md`:68 records the cost of duplicating this
technique: of two copies, only one ever grew the behaviour anyone wanted. Nothing else in Weft
may parse a completion into an object.
"""

import json
import re

#: A fenced block, with an optional language tag. Non-greedy so the *first* complete fence
#: wins, which is the one a model opens right after its prose preamble.
_FENCE = re.compile(r"```[a-zA-Z0-9_-]*\s*\n(?P<body>.*?)\n?```", re.DOTALL)


def rescue_json(text: str) -> object | None:
    """The first JSON value `text` can be read as, or `None`. Three steps, in this order."""
    stripped = text.strip()
    direct = _loads(stripped)
    if direct is not None:
        return direct
    for match in _FENCE.finditer(text):
        fenced = _loads(match.group("body").strip())
        if fenced is not None:
            return fenced
    return _loads(_widest_object(text))


def _loads(candidate: str) -> object | None:
    """`json.loads`, catching exactly what it raises for text that is not JSON.

    `JSONDecodeError` and nothing broader: a `RecursionError` from a pathological document is
    not "this is not JSON", and swallowing it here would turn a resource problem into a parse
    failure nobody can act on.
    """
    if not candidate:
        return None
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return None


def _widest_object(text: str) -> str:
    """The span from the first `{` to the last `}`, or `""`. The last resort, and it looks it.

    Widest rather than balanced-scan: a model's prose around an object is what this step exists
    for, and a brace inside a string value would defeat a naive balance count while `json.loads`
    on the widest span simply succeeds or does not.
    """
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        return ""
    return text[start : end + 1]
