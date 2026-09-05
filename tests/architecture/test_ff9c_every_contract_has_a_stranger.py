"""Fitness function 9, clause (c) — every published contract has a stranger.

Specified in `docs/07-extension-cost.md` §2 clause (c), and this file is what turns it on —
`docs/build-ledger.md` 2.11: "turns on FF9(c)". Clauses (a) and (b) are
`test_ff9_extension_from_outside.py`'s, whose own docstring says clause (c) is not that
file's — this is the file it is.

**The left side and the right side are computed from different places and never from each
other.** The left is `weft_cli.contract_reference.published_contracts(discover_for_reference())`
— this repository's own registrations, `registry.contracts()` plus derived capability
siblings, exactly what `manual/contract-reference.md` is generated from. The right is four
independent throwaway-environment probes, one per out-of-tree example pack
(`examples/weft-example-chunker`, `-ingest`, `-llm`, `-query`), each installed alone-plus-the-
first-party-wheels into a venv that has never heard of this repository, reporting which
contracts it registered a name under and which capability siblings its own registered class
satisfies — read the same way `weft_cli.contract_reference.capability_siblings` and
`_distributions_satisfying` already ask that question, imported directly rather than
reimplemented, so a probe's "yes, this class is a `VectorSearch`" cannot come to disagree
with what the generated manual says. This is what stops the comparison being the reference's
`test_keys_parity` shape (`reference/study/08-salvage.md:777-782`) — a check computed once and
compared against itself, which cannot fail.

**Every venv installs every first-party wheel, not just the one example pack's own
dependencies.** `.phase2-design.md` §9 says "the first-party wheels" once, built in a shared
step; naming each example's own transitive closure by hand would be a second dependency
graph, hand-maintained, drifting from each `pyproject.toml`'s own `dependencies` list the
first time one of them changes. Installing everything and then attributing a registration to
a contract only when `RegistryEntry.distribution` names the example under test is what makes
that safe: eager discovery runs every installed pack's `register()` (G3), but a first-party
plugin's own registration is simply not counted as this probe's answer, so the extra installs
cost venv space and `weft-store`'s mandatory `dsn` setting — the same placeholder
`discover_for_reference()` uses, needed because `pgvector`'s `register()` now always runs
too — and nothing else.

**Two ratchets**, `07` §2's own shape (`CONTRACTS_WITHOUT_AN_EXAMPLE_PACK`, that clause's
exact name) plus a grafted loophole-closer (`SERVICE_PROTOCOLS_WITHOUT_AN_EXAMPLE_PACK`): a
`Prompts`, an `LLM`, a `TokenSink`, a `StageLookup`, a `RouteCatalogue`, an `EntryPointLike`
and a `Stage` are each a real, exported, `Protocol`-shaped thing with no registration path —
services or kernel-level infrastructure, never a capability a pack chooses among — and
`test_every_named_service_protocol_genuinely_has_no_registrations` is what stops "list it as
a service" from becoming a way to dodge clause (c): each name in that ratchet is checked
against a real registry for exactly zero registrations. Both ratchets are pinned empty/exact
and changeable only by a dated decision-log entry, in item 0's own style.
"""

from __future__ import annotations

import os
import subprocess
import tomllib
import typing
from collections.abc import Iterable
from importlib import import_module
from pathlib import Path
from typing import Final

import pytest

from weft_cli.contract_reference import discover_for_reference, published_contracts

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
PACKAGES_ROOT: Final[Path] = REPO_ROOT / "packages"
EXAMPLES_ROOT: Final[Path] = REPO_ROOT / "examples"

#: The same placeholder DSN `weft_cli.contract_reference.discover_for_reference` uses — never
#: dialled, only structurally valid enough for `PgVectorSettings` to validate at `register()`.
_PLACEHOLDER_DSN: Final[str] = "postgresql://ff9c-generation/placeholder"

#: `07` §2's own name for clause (c)'s ratchet. Pinned empty — see `test_waiver_list_is_empty`.
CONTRACTS_WITHOUT_AN_EXAMPLE_PACK: Final[frozenset[str]] = frozenset()

#: Every real, exported `Protocol` with no registration path — a service or kernel-level
#: infrastructure type, never a capability a pipeline chooses among. See the module
#: docstring's "Two ratchets" paragraph and
#: `test_every_named_service_protocol_genuinely_has_no_registrations`, which is what stops
#: this list from being a way to hide a real contract.
SERVICE_PROTOCOLS_WITHOUT_AN_EXAMPLE_PACK: Final[frozenset[str]] = frozenset(
    {
        "weft_kernel.discovery.EntryPointLike",
        "weft_kernel.runner.Stage",
        "weft_llm.contract.LLM",
        "weft_llm.contract.TokenSink",
        "weft_prompts.contract.Prompts",
        "weft_retrieve.contract.RouteCatalogue",
        "weft_retrieve.contract.StageLookup",
    }
)

#: Every first-party distribution — read from `packages/`'s own directory listing, never a
#: hand-typed count, so a sixteenth (or a twentieth) pack changes this without an edit here.
FIRST_PARTY_DISTRIBUTIONS: Final[tuple[str, ...]] = tuple(
    sorted(p.name for p in PACKAGES_ROOT.iterdir() if (p / "pyproject.toml").is_file())
)

#: Every out-of-tree example pack — read from `examples/`'s own directory listing, the
#: identical pattern applied one level up.
_EXAMPLE_DIRS: Final[tuple[Path, ...]] = tuple(
    sorted(p for p in EXAMPLES_ROOT.iterdir() if (p / "pyproject.toml").is_file())
)

#: The probe every throwaway environment runs, once per example pack. `capability_siblings`
#: is imported from the installed `weft-cli` wheel rather than reimplemented — see the module
#: docstring's opening paragraph for why a second implementation would be the risk this
#: function exists to avoid.
_PROBE_SCRIPT = """
import sys

repo_root = {repo_root!r}
leaked = [p for p in sys.path if p and (p == repo_root or p.startswith(repo_root + "/"))]
if leaked:
    print("LEAKED")
    print(",".join(leaked))
    raise SystemExit(0)

from weft_cli.contract_reference import capability_siblings
from weft_kernel.discovery import discover
from weft_kernel.registry import Registry, unwrap_factory

registry = Registry()
discover(registry, pack_settings={{"store": {{"dsn": {dsn!r}}}}})

found: set[str] = set()
for contract in registry.contracts():
    for name in registry.names_for(contract):
        entry = registry.entry(contract, name)
        if entry.distribution != {distribution!r}:
            continue
        found.add(f"{{contract.__module__}}.{{contract.__qualname__}}")
        target = unwrap_factory(entry.factory)
        if not isinstance(target, type):
            continue
        for sibling in capability_siblings(contract):
            try:
                satisfies = issubclass(target, sibling)
            except TypeError:
                continue
            if satisfies:
                found.add(f"{{sibling.__module__}}.{{sibling.__qualname__}}")

print("OK")
for qualname in sorted(found):
    print(qualname)
"""


def _qualname(contract: type[object]) -> str:
    return f"{contract.__module__}.{contract.__qualname__}"


def _example_identity(example_dir: Path) -> str:
    """This example's own distribution name, read from its own `pyproject.toml`."""
    with (example_dir / "pyproject.toml").open("rb") as handle:
        return typing.cast("str", tomllib.load(handle)["project"]["name"])


def run_subprocess(command: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
    return subprocess.run(  # noqa: S603 — fixed argv, no shell, nothing user-controlled
        command, cwd=cwd, env=env, capture_output=True, text=True, timeout=180, check=False
    )


def build_wheel(source_dir: Path, *, out_dir: Path) -> Path:
    result = run_subprocess(
        ["uv", "build", "--wheel", "--out-dir", str(out_dir), str(source_dir)], cwd=out_dir
    )
    assert result.returncode == 0, (
        f"building a wheel for {source_dir} failed:\nstdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
    wheels = sorted(out_dir.glob(f"{source_dir.name.replace('-', '_')}-*.whl"))
    assert wheels, f"uv build reported success but no wheel matching {source_dir.name} appeared"
    return wheels[-1]


def missing_strangers(
    *, published: frozenset[str], implemented: frozenset[str], waived: frozenset[str]
) -> frozenset[str]:
    """Every published contract `implemented` lacks, unless `waived` names it.

    A pure function, kept separate from the two sides' own computation — `weft_cli.
    contract_reference.missing_from_walked_set`'s own precedent for the identical reason:
    "the check has something to call that is not the same code path it is checking."
    """
    return frozenset(published - implemented - waived)


def test_missing_strangers_can_actually_fail() -> None:
    # Arrange — the self-test `07` §2 requires: a fabricated contract on the left with no
    # counterpart on the right, so this function is proven able to report a real gap rather
    # than having stopped being able to fail.
    published = frozenset({"weft_store.contract.NodeStore", "some_pack.contract.NeverImplemented"})
    implemented = frozenset({"weft_store.contract.NodeStore"})

    # Act
    missing = missing_strangers(published=published, implemented=implemented, waived=frozenset())

    # Assert
    assert missing == frozenset({"some_pack.contract.NeverImplemented"})


def test_missing_strangers_honours_the_waiver() -> None:
    # Arrange
    published = frozenset({"some_pack.contract.Waived"})

    # Act
    missing = missing_strangers(
        published=published,
        implemented=frozenset(),
        waived=frozenset({"some_pack.contract.Waived"}),
    )

    # Assert
    assert missing == frozenset()


def test_waiver_list_is_empty() -> None:
    # Assert — `07` §2's ratchet: an exemption is a visible entry in a diff, changeable only
    # by a dated decision-log entry, never a silent edit.
    assert frozenset() == CONTRACTS_WITHOUT_AN_EXAMPLE_PACK


def test_at_least_one_contract_is_published() -> None:
    # Assert — the floor: a check comparing two empty sets would pass by being blind.
    left = {
        _qualname(published.contract) for published in published_contracts(discover_for_reference())
    }
    assert left


def test_at_least_one_example_pack_is_found() -> None:
    # Assert — the other floor: nothing to install would make the right side vacuous too.
    assert _EXAMPLE_DIRS


def _exported_protocol_classes() -> dict[str, type[object]]:
    """Every `Protocol` subclass exported from a first-party pack's own top-level `__all__`."""
    found: dict[str, type[object]] = {}
    for dist_dir in PACKAGES_ROOT.iterdir():
        src = dist_dir / "src"
        if not src.is_dir():
            continue
        for package_dir in src.iterdir():
            if not (package_dir / "__init__.py").is_file():
                continue
            module = import_module(package_dir.name)
            for name in getattr(module, "__all__", ()):
                obj = getattr(module, name, None)
                if (
                    isinstance(obj, type)
                    and issubclass(obj, typing.Protocol)
                    and obj is not typing.Protocol
                ):
                    protocol_class = typing.cast("type[object]", obj)
                    found[_qualname(protocol_class)] = protocol_class
    return found


def test_every_exported_protocol_without_a_version_is_a_named_service() -> None:
    # Arrange — the classification rule that makes the split mechanical rather than
    # editorial: every exported `Protocol` either carries `.version` (and is therefore a
    # published contract, on the left side already) or is named in the service ratchet.
    exported = _exported_protocol_classes()

    # Act
    unclassified = sorted(
        qualname
        for qualname, obj in exported.items()
        if not hasattr(obj, "version") and qualname not in SERVICE_PROTOCOLS_WITHOUT_AN_EXAMPLE_PACK
    )

    # Assert
    assert not unclassified, (
        f"exported `Protocol`(s) with no `.version` and not named in "
        f"SERVICE_PROTOCOLS_WITHOUT_AN_EXAMPLE_PACK: {unclassified} — either give it a "
        f"version (it is a real contract and clause (c) now requires a stranger for it) or "
        f"name it in the ratchet (it is genuinely a service)"
    )


def test_every_named_service_protocol_genuinely_has_no_registrations() -> None:
    # Arrange — the check that stops "list it as a service" from being a way to dodge
    # clause (c): every ratchet entry is asked, against a real registry, whether anything
    # actually registered a name under it.
    exported = _exported_protocol_classes()
    registry = discover_for_reference()

    for qualname in sorted(SERVICE_PROTOCOLS_WITHOUT_AN_EXAMPLE_PACK):
        obj = exported.get(qualname)
        assert obj is not None, (
            f"{qualname} is pinned in the service ratchet but no longer exported"
        )
        assert registry.distributions_for(obj) == frozenset(), (
            f"{qualname} is named as a service with no registration path, but something "
            f"registered a name under it — this ratchet entry is dodging a real contract"
        )


@pytest.mark.timeout(900)
def test_every_published_contract_has_a_stranger(tmp_path: Path) -> None:
    # Arrange — the left side, from this repository's own registrations, never from a wheel.
    left = frozenset(
        _qualname(published.contract) for published in published_contracts(discover_for_reference())
    )

    # Arrange — every first-party wheel, built once and shared across all four probes below.
    wheel_dir = tmp_path / "wheels"
    wheel_dir.mkdir()
    first_party_wheels = [
        build_wheel(PACKAGES_ROOT / distribution, out_dir=wheel_dir)
        for distribution in FIRST_PARTY_DISTRIBUTIONS
    ]

    right: set[str] = set()
    for example_dir in _EXAMPLE_DIRS:
        distribution = _example_identity(example_dir)
        example_wheel = build_wheel(example_dir, out_dir=wheel_dir)

        project_dir = tmp_path / f"throwaway-{distribution}"
        project_dir.mkdir()
        venv_dir = project_dir / ".venv"
        created = run_subprocess(["uv", "venv", str(venv_dir), "--python", "3.12"], cwd=project_dir)
        assert created.returncode == 0, f"uv venv failed for {distribution}:\n{created.stderr}"
        python = venv_dir / "bin" / "python"

        installed = run_subprocess(
            [
                "uv",
                "pip",
                "install",
                "--python",
                str(python),
                *(str(wheel) for wheel in first_party_wheels),
                str(example_wheel),
            ],
            cwd=project_dir,
        )
        assert installed.returncode == 0, (
            f"uv pip install failed for {distribution}:\n{installed.stderr}"
        )

        probe = project_dir / "probe.py"
        probe.write_text(
            _PROBE_SCRIPT.format(
                repo_root=str(REPO_ROOT), dsn=_PLACEHOLDER_DSN, distribution=distribution
            ),
            encoding="utf-8",
        )

        # Act
        ran = run_subprocess([str(python), str(probe)], cwd=project_dir)

        # Assert — this one pack's own contribution to the right side.
        assert ran.returncode == 0, f"{distribution}'s probe crashed:\n{ran.stdout}\n{ran.stderr}"
        lines = ran.stdout.strip().splitlines()
        assert lines and lines[0] != "LEAKED", (
            f"a path back into this repository is on sys.path inside {distribution}'s throwaway "
            f"environment: {lines[1] if len(lines) > 1 else '?'}"
        )
        assert lines[:1] == ["OK"], f"{distribution}'s probe did not discover cleanly: {lines}"
        registered = lines[1:]
        assert registered, (
            f"{distribution} registered nothing under its own name — a stranger implementing no "
            f"contract proves nothing about clause (c)"
        )
        right.update(registered)

    # Assert — the property clause (c) states, computed with neither side derived from the
    # other: every contract the first-party packs publish has an out-of-tree counterpart.
    missing = missing_strangers(
        published=left, implemented=frozenset(right), waived=CONTRACTS_WITHOUT_AN_EXAMPLE_PACK
    )
    assert not missing, (
        f"published with no out-of-tree stranger: {sorted(missing)} — task 2.11's own "
        f"obligation is that every contract this phase (or an earlier one) publishes has an "
        f"implementation living outside the workspace"
    )


def test_the_grep_can_actually_be_wrong_about_leakage(tmp_path: Path) -> None:
    """The self-test for the probe's own leak-detection line — `06` step 10's precedent.

    Plants a path this repository's own root would produce and confirms the identical
    substring check the probe script runs would have caught it, so that check is not one
    that stopped being able to fail.
    """
    del tmp_path
    fake_sys_path: Iterable[str] = (str(REPO_ROOT), "/some/other/venv/site-packages")
    leaked = [
        p
        for p in fake_sys_path
        if p and (p == str(REPO_ROOT) or p.startswith(str(REPO_ROOT) + "/"))
    ]
    assert leaked == [str(REPO_ROOT)]
