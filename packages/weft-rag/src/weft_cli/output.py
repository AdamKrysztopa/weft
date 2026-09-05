"""How a command renders its result — the vocabulary the argument grammar needs.

**Here rather than in `weft_cli.ask`, and that placement is fitness function
8(b) rather than taste.** `build_parser` runs for *every* invocation, `weft
--version` included, so anything it names is imported before a command is even
chosen — and `weft_cli.ask` imports `weft_embed` and `weft_store` at its own
module scope. An `--format` choice list read off an enum that lived beside
`render_results_json` would therefore execute pack code for `weft --version`,
which is exactly the clause `tests/architecture/test_ff8_trust_model.py`
asserts by subprocess.
"""

from enum import StrEnum


class AskFormat(StrEnum):
    """How `weft ask` renders what it found — for a person, or for a program.

    Two members and no third, because the two readers want opposite things:
    `docs/03-cli.md` → *Output*, *Score display* withholds the raw similarity
    from a human ("`1. (score=-0.0913) …` looks broken even when it is not")
    and hands it to a script in full, "because a script consuming structured
    output is exactly the reader who can use an unbounded float correctly."

    **`--format json`, not the global `--json` `03` sketches.** That one is a
    Phase 3 flag swapping the *sink* for newline-delimited events over a whole
    run; this is one command choosing the shape of its own result. Both can
    exist: `03`'s sentence is about how tokens reach a reader while a pipeline
    runs, and this is about what a finished retrieval looks like on stdout.
    """

    TEXT = "text"
    JSON = "json"
