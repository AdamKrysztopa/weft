"""The plugin-to-pack table an install hint reads is what each extra-backed pack registers.

Task 45.4. A pack behind an extra fails to import when the extra is missing, so it never registers
and nothing at run time can say which plugin names it would have provided. A plugin's name is not
its pack's name (`pdf` registers `pdf-text`; `docling` registers `pdf-layout-model`), so
`weft_engine.pack_attribution.PLUGINS_BEHIND_EXTRAS` writes the mapping down, and this check holds
it to what each of those packs registers when its extra is installed, as it is in this workspace.
"""

from __future__ import annotations

import importlib.metadata
from collections.abc import Mapping
from typing import cast

from weft_engine.pack_attribution import PLUGINS_BEHIND_EXTRAS
from weft_kernel.discovery import EntryPointLike, PackStatus, discover
from weft_kernel.registry import Registry


def registered_behind_extras() -> dict[str, str]:
    """Every plugin name a `weft-rag` pack named after one of its extras registers, to that pack."""
    extras = set(
        importlib.metadata.distribution("weft-rag").metadata.get_all("Provides-Extra") or ()
    )
    registered: dict[str, str] = {}
    for entry_point in importlib.metadata.entry_points(group="weft.packs"):
        if entry_point.name not in extras or entry_point.dist is None:
            continue
        if entry_point.dist.name != "weft-rag":
            continue
        registry = Registry()
        (report,) = discover(registry, entry_points=[cast("EntryPointLike", entry_point)])
        # PARTIAL is a pack that registered and declared a surface unavailable, as `docling` does
        # where its model weights are absent (CI); its names are still in the registry.
        assert report.status in {PackStatus.ACTIVE, PackStatus.PARTIAL}, (
            f"'{entry_point.name}' did not register here ({report.status.value}: {report.reason}); "
            "this check needs every extra installed, as `uv sync` installs them"
        )
        for contract in registry.contracts():
            for name in registry.names_for(contract):
                registered[name] = entry_point.name
    return registered


def disagreements(table: Mapping[str, str], registered: Mapping[str, str]) -> set[str]:
    """Each plugin name the table and the registrations do not map to the same pack."""
    return {
        name for name in table.keys() | registered.keys() if table.get(name) != registered.get(name)
    }


def test_the_table_is_what_the_extra_backed_packs_register() -> None:
    # Act
    registered = registered_behind_extras()

    # Assert
    assert registered["pdf-text"] == "pdf"
    assert disagreements(PLUGINS_BEHIND_EXTRAS, registered) == set()


def test_the_check_can_actually_fail() -> None:
    # Arrange
    planted = dict(PLUGINS_BEHIND_EXTRAS)
    del planted["pdf-layout-model"]
    planted["pdf-text"] = "docling"

    # Act
    found = disagreements(planted, registered_behind_extras())

    # Assert
    assert found == {"pdf-layout-model", "pdf-text"}
