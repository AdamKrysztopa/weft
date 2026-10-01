"""Fitness function 39 — a router's fallback is a rung that can always answer.

`fix-plans/23` MUST-3. When no rule of an `evidence-policy` router holds, or the rung a rule chose
refuses at run time, the ask is answered by the policy's `fallback`. A fallback that needs a layer
the corpus may not have, or that no router can offer, turns the safety net into a second failure.
For every tracked first-party pipeline document with an `evidence-policy` stage, the fallback must:

- be a tracked first-party pipeline document, so it exists wherever the router does;
- carry a `route.summary`, directly or through `extends`, so the catalogue offers it;
- name no `route.requires`, `route.requires-nodes` or `route.requires-role`, directly or through
  `extends`, so it is offerable on a base-only corpus.

**Not checked**, and said so: that the fallback needs no model role beyond `generate`. A pipeline
document does not declare the roles its stages use, so that half would be a guess; it is carried
until roles are declared per rung.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

import yaml

from .conftest import REPO_ROOT, tracked_files

_REQUIRES = ("route.requires", "route.requires-nodes", "route.requires-role")
_SUMMARY = "route.summary"


def _shipped_documents() -> dict[str, dict[str, Any]]:
    documents: dict[str, dict[str, Any]] = {}
    for tracked in sorted(tracked_files()):
        path = Path(tracked)
        if (
            path.suffix == ".yaml"
            and path.parent.name == "pipelines"
            and path.parts[:2]
            == (
                "packages",
                "weft-rag",
            )
        ):
            documents[path.stem] = yaml.safe_load((REPO_ROOT / tracked).read_text(encoding="utf-8"))
    return documents


def _stages(document: Mapping[str, Any]) -> list[dict[str, Any]]:
    return cast("list[dict[str, Any]]", document.get("stages") or [])


def _vars_through_extends(name: str, documents: Mapping[str, dict[str, Any]]) -> dict[str, Any]:
    document = documents.get(name)
    if document is None:
        return {}
    inherited = (
        _vars_through_extends(str(document["extends"]), documents) if "extends" in document else {}
    )
    return {**inherited, **(document.get("vars") or {})}


def _fallback_problems(
    router: str, fallback: object, documents: Mapping[str, dict[str, Any]]
) -> list[str]:
    if fallback not in documents:
        return [f"{router}: fallback '{fallback}' is not a shipped pipeline document"]
    declared = _vars_through_extends(str(fallback), documents)
    found = [
        f"{router}: fallback '{fallback}' declares {key}; a base-only corpus cannot offer it"
        for key in _REQUIRES
        if key in declared
    ]
    if _SUMMARY not in declared:
        found.append(
            f"{router}: fallback '{fallback}' carries no {_SUMMARY}, so no router offers it"
        )
    return found


def fallback_violations(documents: Mapping[str, dict[str, Any]]) -> list[str]:
    """Every way a shipped evidence-policy router's fallback is not a safe one."""
    found: list[str] = []
    for name, document in sorted(documents.items()):
        for stage in _stages(document):
            if stage.get("use") == "evidence-policy":
                fallback = cast("dict[str, Any]", stage.get("with") or {}).get("fallback")
                found.extend(_fallback_problems(name, fallback, documents))
    return found


def test_at_least_one_shipped_evidence_router_exists() -> None:
    # Floor — with none, the check below asks nothing.
    documents = _shipped_documents()
    assert any(
        stage.get("use") == "evidence-policy"
        for document in documents.values()
        for stage in _stages(document)
    )


def test_every_shipped_evidence_router_has_a_safe_fallback() -> None:
    # Act
    found = fallback_violations(_shipped_documents())

    # Assert
    assert not found, "\n".join(found)


def _router(fallback: str) -> dict[str, dict[str, Any]]:
    return {
        "r": {"stages": [{"id": "d", "use": "evidence-policy", "with": {"fallback": fallback}}]},
        "dense": {"vars": {"route.summary": "one search"}},
        "layered": {"extends": "dense", "vars": {"route.requires": "enrich-with-questions"}},
        "noted": {"vars": {}},
        "nodes": {"vars": {"route.summary": "s", "route.requires-nodes": "ext.x=y"}},
        "roled": {"vars": {"route.summary": "s", "route.requires-role": "graph"}},
    }


def test_the_check_can_actually_fail() -> None:
    # Act / Assert — a clean fallback passes, and each way of not being safe is named.
    assert fallback_violations(_router("dense")) == []
    assert "not a shipped pipeline document" in "".join(fallback_violations(_router("absent")))
    assert "route.requires" in "".join(fallback_violations(_router("layered")))
    assert "no route.summary" in "".join(fallback_violations(_router("noted")))
    assert "route.requires-nodes" in "".join(fallback_violations(_router("nodes")))
    assert "route.requires-role" in "".join(fallback_violations(_router("roled")))
