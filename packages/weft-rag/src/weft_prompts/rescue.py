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

#: The characters that may follow a backslash in JSON, `u` apart (it needs four hex digits).
_VALID_ESCAPES = frozenset('"\\/bfnrt')
_UNICODE_ESCAPE = re.compile(r"u[0-9a-fA-F]{4}")


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


def repair_backslash_escapes(text: str) -> str:
    r"""`text` with every backslash JSON cannot read as an escape doubled. R38.11.

    A backslash beginning one of JSON's own escapes (`\"` `\\` `\/` `\b` `\f` `\n` `\r`
    `\t` `\uXXXX`) is left alone and keeps its meaning, so a LaTeX `\nu` or `\times` reads
    back as a newline or tab followed by letters: a known approximation, accepted because it fixes
    the common case (`\(`, `\cdot`, `\alpha`) without a LaTeX parser.
    """
    out: list[str] = []
    i = 0
    length = len(text)
    while i < length:
        char = text[i]
        if char == "\\" and i + 1 < length:
            nxt = text[i + 1]
            if nxt in _VALID_ESCAPES:
                out.append(text[i : i + 2])
                i += 2
                continue
            if nxt == "u" and _UNICODE_ESCAPE.match(text, i + 1):
                out.append(text[i : i + 6])
                i += 6
                continue
            out.append("\\\\")
            i += 1
            continue
        out.append(char)
        i += 1
    return "".join(out)


def _loads(candidate: str) -> object | None:
    """`json.loads`, catching exactly what it raises for text that is not JSON.

    `JSONDecodeError` and nothing broader: a `RecursionError` from a pathological document is
    not "this is not JSON", and swallowing it here would turn a resource problem into a parse
    failure nobody can act on. A candidate that still fails is retried once with its backslash
    escapes repaired (R38.11), so a document whose only fault is an unescaped LaTeX command is
    read rather than discarded.
    """
    if not candidate:
        return None
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass
    try:
        return json.loads(repair_backslash_escapes(candidate))
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
