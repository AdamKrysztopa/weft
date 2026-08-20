"""The V-prerequisite harness is an artefact, not a subsystem — a standing ratchet, not a
one-time prophecy.

`docs/09-release.md` §4.3 asks for six artefacts, each *"a file or a persisted run"*. `eval/`
holds three of them and the code that produces them. Before task **4.8** this file's own docstring
predicted that *"every line of it is meant to be deleted and replaced by Phase 4."* Tasks 4.1 and
4.2 landed first, and what they actually replaced was narrower than that prediction: `weft-eval`
now publishes `GenerationMetric`/`RetrievalMetric` as real, registrable contracts and ships the 21
reference metrics against them — the thing that genuinely risked becoming *"Phase 4's own extensible
system in disguise"* if it had grown inside `eval/` instead. What 4.1/4.2 did **not** touch, and
what task 4.8 confirmed does not need touching, is `eval/metrics.py`'s own `measure`/`judge`
functions and `eval/check_questions.py`'s quote-pinned ground truth: original, Weft-specific
scoring glue for *this one harness's* baseline (span-in-passage containment against a
`(document, quote)` judgement — deliberately not a `weft_eval.contract.RetrievalSample`'s
node-id-based relevance set, for the reason `check_questions.py`'s own docstring gives: a judgement
pinned to a `NodeId` is invalidated by any chunking change). It was never the reference's metric suite
and 4.1/4.2 never claimed to reimplement it — the prediction that *every* line would go was simply
wrong about this part, and 4.8 is where that is said plainly rather than left for a reader to
notice the docstring no longer matches the tree.

**Task 4.8 is what this file's own note O4 (`.phase4-design.md` §5) called for: the published
baseline became one of Phase 4's own persisted runs** (`eval/run_baseline.py`'s `BaselineReport.
record` is a real `weft_eval.run_record.RunRecord`, built through that pack's own
`corpus_identity`/`build_run_record` rather than a second, hand-rolled copy of the same shape) —
which is the one part of the original prediction that *did* come true, just later and by adoption
rather than by deletion. `eval/` is smaller and more honest for it, but it still exists, and it
still runs `weft` as a subprocess to take a real, credentialed measurement no gate can take for it.

**So what this file guards changes from "prove the deletion happens" to "prove `eval/` never
grows the shape that would force one."** Being extensible is precisely what would make it a
second system, which is why this file tests for the absence of things rather than the presence of
them. A registry of metrics, an entry point, a `pyproject.toml` — any one of them and `eval/` has
quietly become a distribution nothing in this plan budgeted for, and the phase boundary `01` draws
would have been crossed by a convenience nobody argued for. Retiring this file at 4.8 was
considered and rejected: `eval/` is permanent now (a hand-run harness taking a credentialed
measurement, not a phase's scaffolding), so the property it guards is permanent too — an
architecture check earns retirement when the thing it watches is gone, not when the prediction
that used to justify it turns out to have been too strong.

The third check is the one that would otherwise rot silently: a pack importing the harness would
make the *measurement* part of the engine, so a change to how a baseline is scored would change
what the engine does. The dependency is one-way by design — `eval/` drives `weft` as a
subprocess and imports the CLI's own result models (`weft_cli.ask.AskResult`) and, since 4.8,
`weft_eval.run_record`/`weft_kernel.resolution`/`weft_cli.compile`/`weft_cli.registry_bootstrap`
to build a real `RunRecord` in-process — reading what those modules publish, never the reverse,
and this is the direction that must never appear.
"""

import ast
from pathlib import Path
from typing import Final

from .conftest import REPO_ROOT

EVAL_ROOT: Final[Path] = REPO_ROOT / "eval"
PACKAGES_ROOT: Final[Path] = REPO_ROOT / "packages"

#: Every top-level module name `eval/` publishes on the import path. Derived from what is there
#: rather than listed, so a fourth harness module is covered the day it is written.
EVAL_MODULES: Final[frozenset[str]] = frozenset(
    path.stem for path in EVAL_ROOT.glob("*.py") if not path.stem.startswith("_")
)

#: What a distribution is made of. Any of these under `eval/` means it became one.
_DISTRIBUTION_FILES: Final[tuple[str, ...]] = ("pyproject.toml", "setup.py", "setup.cfg")


def test_the_walk_found_the_harness_and_the_packages() -> None:
    # Task 1.18's floor: every check below is "no violations", which is true of an empty walk.
    # A renamed directory would otherwise turn this whole file green by finding nothing.
    # Assert
    assert {"metrics", "run_baseline", "check_baseline", "check_questions"} <= EVAL_MODULES, (
        f"the harness modules this file exists to fence are not under {EVAL_ROOT}: found "
        f"{sorted(EVAL_MODULES)}"
    )
    assert list(PACKAGES_ROOT.glob("*/src")), f"no distribution sources under {PACKAGES_ROOT}"


def test_the_harness_is_not_a_distribution() -> None:
    # A `pyproject.toml` here is the whole difference between "a script that produced a file"
    # and "a package Phase 4 has to keep working". `09` §4.3's artefacts are files.
    # Act
    found = sorted(
        str(path.relative_to(REPO_ROOT))
        for name in _DISTRIBUTION_FILES
        for path in EVAL_ROOT.rglob(name)
    )

    # Assert
    assert not found, (
        f"{found} make eval/ a distribution. It is a set of hand-run tools producing the "
        f"artefacts `docs/09-release.md` §4.3 requires — the extensible, registrable half of "
        f"what a metric suite needs already lives in the real `weft-eval` pack (tasks 4.1/4.2), "
        f"so nothing here should ever need the shape of one."
    )


def test_the_harness_registers_nothing() -> None:
    # The other half of the same rule, and the one a helpful refactor would reach for first: a
    # metric that could be registered would need a registry, a name space and a config model,
    # and `eval/` would be the extension system Phase 4 is supposed to design.
    # Act
    declaring = sorted(
        str(path.relative_to(REPO_ROOT))
        for path in EVAL_ROOT.rglob("*.py")
        if "weft.packs" in path.read_text(encoding="utf-8")
    )

    # Assert
    assert not declaring, (
        f"{declaring} name the `weft.packs` entry point group. Nothing under eval/ is a plugin, "
        f"a contract or a registry — see this file's docstring."
    )


def test_no_distribution_imports_the_harness() -> None:
    # The direction that must never appear. `eval/` imports `weft_cli.ask`'s result model to
    # read what the command printed, which is one-way and fine; a pack importing `metrics` would
    # make how a baseline is scored part of what the engine does.
    # Act
    violations = [
        f"{path.relative_to(REPO_ROOT)} imports {imported}"
        for path in sorted(PACKAGES_ROOT.rglob("*.py"))
        for imported in _top_level_imports(path)
        if imported in EVAL_MODULES
    ]

    # Assert
    assert not violations, (
        "a distribution imports the evaluation harness:\n  "
        + "\n  ".join(violations)
        + "\nThe harness measures the engine; the engine may not depend on the harness, or the "
        "measurement is part of what is being measured."
    )


def _top_level_imports(path: Path) -> set[str]:
    """Every root module name `path` imports, however the import was spelled."""
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".", 1)[0])
    return names
