"""What ingest accepts, derived from what actually registered — never from a constant.

**The defect this exists to remove, stated because it shipped.** Ingest used to
filter discovered files against `weft_extract.text.EXTENSIONS`, one pack's
module constant, and select the `"text"` extractor by name. That was correct
while `weft-extract` was the only extractor pack and became silently wrong the
moment `weft-pdf` shipped: `weft index corpus/mrmr` walked nine PDFs, matched
none of them, handed an empty batch to a text extractor and exited 0 reporting
success. `docs/11-multimodal.md:205` predicted it by line number before the pack
existed. Fail-closed, so better than the reference's fail-open — and still a run
whose failure path and success path are indistinguishable, which is the one
thing this project refuses.

`docs/02-extension-model.md` §1 already had the rule: **capability is derived,
never declared.** A file suffix is claimed by an extractor declaring it, and
what ingest accepts is the union of those claims over the plugins that actually
resolved. Nothing in this module knows the name of a single extractor, so a
third party's `weft-extract-epub` becomes reachable by installing it, which is
requirement 1's zero-edits test answered literally.

**What this module deliberately does not do: choose.** A suffix two extractors
claim maps to both names here, and deciding between them is the caller's,
loudly. Composing two backends for one media type into a chain that tries each
is ledger task **2.28**, and inventing a private ordering here would be that
task decided by accident.
"""

from pathlib import Path

from weft_extract.contract import Extractor
from weft_kernel.registry import Registry, unwrap_factory


def claimed_extensions(registry: Registry) -> dict[str, tuple[str, ...]]:
    """Every file suffix a registered `Extractor` claims, mapped to the names claiming it.

    Read through `unwrap_factory`, per `weft_kernel.registry`'s own rule: a
    plugin registered as a `functools.partial` carrying its settings would
    otherwise answer for the partial, which declares nothing.

    `extensions` is read defensively rather than required, because a plugin
    that reads from an object store, a database or a message queue satisfies
    the same contract and has no file suffix to declare — `Extractor` says
    nothing about filesystems, and this is the one place that could quietly
    start requiring it to.

    Both the mapping and each name tuple come out sorted, so a caller printing
    an ambiguity prints the same list twice running.
    """
    claims: dict[str, list[str]] = {}
    for name in sorted(registry.names_for(Extractor)):
        plugin = unwrap_factory(registry.lookup(Extractor, name))
        for suffix in getattr(plugin, "extensions", ()):
            claims.setdefault(suffix, []).append(name)
    return {suffix: tuple(names) for suffix, names in sorted(claims.items())}


def present_suffixes(directory: Path) -> frozenset[str]:
    """Every file suffix that actually occurs under `directory`, claimed or not.

    The other half of honesty about an accept set: knowing what ingest *can*
    read is only useful if a caller can also say what it found and could not.
    A directory of `.docx` reporting "produced 0" is the same silent no-op in
    a different costume, and the difference between "nothing here" and
    "nothing here I can read" is one set subtraction against this.

    Files with no suffix at all are not reported: there is nothing to name in
    a refusal, and a `README` with no extension is not a format anyone failed
    to install.
    """
    return frozenset(path.suffix for path in directory.rglob("*") if path.is_file() and path.suffix)
