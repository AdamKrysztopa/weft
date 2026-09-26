"""Repair **R43.57** — every generation judge can be named in an experiment's `metrics`.

Task 43.50 let an experiment name a judge by the name it records, found through the class's
declared `reported_name`. Only `answer-correctness` declared one, so four of the five registered
generation judges could not be named at all. The population is read from the registry, so a judge
added later without the declaration fails here rather than being refused in an operator's run.
"""

from typing import cast

from weft_eval import Settings, register
from weft_eval.contract import GenerationMetric
from weft_eval.harness import judge_plugin_names
from weft_kernel.discovery import PackRegistrar
from weft_kernel.registry import Registry, unwrap_factory


def _registry() -> Registry:
    registry = Registry()
    registrar = PackRegistrar(registry, distribution="weft-rag")
    register(registrar, Settings())
    registrar.commit()
    return registry


def _judges(registry: Registry) -> dict[str, object]:
    found: dict[str, object] = {}
    for name in registry.names_for(GenerationMetric):
        target = unwrap_factory(registry.lookup(GenerationMetric, name))
        if getattr(target, "runs_in_gate", True) is False:
            found[name] = target
    return found


def test_every_registered_generation_judge_declares_the_name_it_records() -> None:
    # Arrange
    registry = _registry()
    judges = _judges(registry)

    # Act
    undeclared = sorted(
        name for name, target in judges.items() if getattr(target, "reported_name", None) is None
    )

    # Assert
    assert len(judges) >= 2
    assert undeclared == []


def test_an_experiment_can_name_every_generation_judge_by_what_it_records() -> None:
    # Arrange
    registry = _registry()
    judges = _judges(registry)
    recorded = {
        cast("str", getattr(target, "reported_name", "")): name for name, target in judges.items()
    }

    # Act
    found = judge_plugin_names(recorded, registry=registry)

    # Assert
    assert len(judges) >= 2
    assert dict(found) == recorded
