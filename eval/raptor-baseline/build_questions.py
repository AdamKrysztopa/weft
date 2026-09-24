"""Generate the RAPTOR measurement's question set — ledger task `16.6`'s payoff.

**This exists because the question set the Phase 10 exit was measured on lives nowhere.** Its
fifteen records report `n=66`, and nothing in this tree produces 66 of anything: the file was
built by hand in a scratch directory, its labels rewritten from manifest ids to whatever the rig's
staging produced, and thrown away. So the exit's own subject cannot be reconstructed — which is
the defect `16.5` and `16.6` were built to end, and the reason the re-measurement taken after them
is a *new* measurement rather than a replay.

What this writes is derivable, and therefore re-derivable by anyone:

- **Which questions.** `weft_eval.question_set`'s own `reproducible_questions` over the tiers a
  stranger can obtain — `fetch` — so no question resting on a paper under publisher copyright is
  in it. That function is the published baseline's own selector and is reused rather than a second
  rule invented here.
- **Narrowed to PDF-labelled questions**, because the arms replace `extract` with `pdf-text` and a
  question naming a `.txt` document would name something the run never indexed. `16.5` would
  refuse the whole run for it, loudly and correctly, which is how this narrowing was found.
- **Labels as corpus-relative paths** — `arxiv/1304.7717v2.pdf`, the manifest's own `path` — which
  is what `16.5` made resolvable on any machine. Before it, a label was a manifest id and matched
  nothing, and an early run of this very rig read `0.000` at every cutoff without anyone noticing
  (`docs/internal/build-ledger.md:5528 "an early run read"`).
- **`language` and `id` carried through**, because `16.8` made a language a scored fact and `16.4`
  keys per-question scores on an id. Both now enter the question-set digest `16.6` records, so two
  runs scored on this file are provably scored on the same questions.

Run it as `uv run python eval/raptor-baseline/build_questions.py`. It writes
`eval/raptor-baseline/questions.json` and prints what it wrote.
"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

from weft_eval.question_set import load_questions, reproducible_questions

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parents[1]

#: The tiers a stranger can obtain. `operator` holds papers under publisher copyright, so a
#: question resting on one is excluded — `reproducible_questions`' own argument, not a new rule.
REPRODUCIBLE = frozenset({"fetch"})

OUTPUT = _HERE / "questions.json"


def main() -> int:
    """Write the reproducible, PDF-labelled question subset to `questions.json`.

    Returns:
        The process exit code, always 0.
    """
    manifest = tomllib.loads((_REPO_ROOT / "corpus" / "manifest.toml").read_text(encoding="utf-8"))
    documents = manifest["document"]
    tiers = {entry["id"]: entry["tier"] for entry in documents}
    paths = {entry["id"]: entry["path"] for entry in documents}

    subset = reproducible_questions(
        load_questions(_REPO_ROOT / "eval" / "questions"), tiers=tiers, reproducible=REPRODUCIBLE
    )
    written: list[dict[str, object]] = []
    for question in subset:
        labels = [paths[name] for name in question.relevant_documents if name in paths]
        if len(labels) != len(question.relevant_documents):
            continue
        if not all(label.endswith(".pdf") for label in labels):
            continue
        kind = question.kind
        written.append(
            {
                "id": question.id,
                "query": question.text,
                "relevant_documents": sorted(labels),
                "kind": getattr(kind, "value", kind),
                "language": question.language,
            }
        )

    OUTPUT.write_text(json.dumps(written, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(written)} questions -> {OUTPUT.relative_to(_REPO_ROOT)}")
    print("kinds: " + ", ".join(sorted({str(entry["kind"]) for entry in written})))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
