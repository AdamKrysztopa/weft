"""Unit tests for `needs_store` over the **selected set** — ledger task 9.0, property (iii), alone.

Property (i) is `test_service_roles.py`; property (ii) is `test_service_role_aliasing.py`. Each
fails independently, which is why the task line requires three files rather than one: a role can
be selected and aliased correctly and a stage's demand can still be validated against the wrong
instance, refused before aliasing could ever have helped.

**The second enforcement point.** `check_store_capabilities`
(`packages/weft-rag/src/weft_cli/run_services.py:129 'class MalformedNeed'`) validates every stage's
`needs_store`
against **the one configured store**, and its remedy names only `[services] store`. So a stage
needing a capability that some *other* selected role provides is refused before assembly, with a
remedy that points at the wrong key. Aliasing (property ii) cannot help: this check runs first and
speaks only to refuse. Fixing one of the two points is not fixing the seam.

**And the refusal has to name something an operator can type.** The one production call site passes
`store_name=type(store).__name__` (`packages/weft-rag/src/weft_cli/route_ask.py:550 'to turn '`), so
a live
refusal reads *the configured store 'PgVectorStore'* while `[services] store` accepts `pgvector`.
Every one of the six other call sites is a test passing a plausible plugin-shaped name by hand, so
nothing exercised it — `docs/internal/lessons.md` `L9.26`.
"""

import pytest

from weft_cli.service_roles import RoleTable
from weft_kernel.context import ServiceRole
from weft_store.contract import NodeStore, TextSearch, VectorSearch


#: The **real** store family, deliberately, rather than stand-ins. `_roles_publishing` asks
#: `weft_cli.contract_reference.capability_siblings` which capabilities a role's contract
#: family publishes, and that walks the publishing pack's own public module — so a stand-in
#: contract declared inside a test module has no siblings by construction and could not
#: exercise the mechanism at all. `docs/internal/lessons.md` L6.4: read the live population, not the
#: declaration. The role key stays `blobs` — a stranger's name — so nothing here depends on the
#: role happening to be called `store`.
class _ReadOnlyBlobs:
    """Satisfies `NodeStore`'s role and `VectorSearch`, and never `TextSearch` — the asymmetry
    `weft-qdrant` really has (`02` § *The store contract family*), used here so the refusal
    case is one a shipped backend actually produces.
    """

    async def search_vector(
        self, vector: object, top_k: int, filter: object = None
    ) -> list[object]:
        return []


BLOBS = ServiceRole(key="blobs", contract=NodeStore)


def _table(*roles: ServiceRole) -> RoleTable:
    return RoleTable(roles={role.key: role for role in roles})


def test_a_demand_is_checked_against_the_instance_its_own_role_resolves() -> None:
    """A capability the selected instance provides passes, and passes *because that role's
    instance* provides it — not because the configured node store happens to.
    """
    # Arrange
    from weft_cli.run_services import check_selected_capabilities

    selected = {"blobs": _ReadOnlyBlobs()}

    # Act
    check_selected_capabilities(
        demanded={VectorSearch: "fetch"}, selected=selected, table=_table(BLOBS), names={}
    )

    # Assert — this check speaks only to refuse; reaching here is the assertion.


def test_a_demand_nothing_selected_provides_is_refused_naming_the_role_key_to_set() -> None:
    """The refusal names **the role key**, which is the thing an operator edits.

    Before 9.0 this remedy said `[services] store` whatever the capability was, because the
    check knew about exactly one configured service. A stage needing a blob capability was told
    to change its node store.
    """
    # Arrange
    from weft_cli.run_services import SelectedCapabilityMissingError, check_selected_capabilities

    selected = {"blobs": _ReadOnlyBlobs()}

    # Act / Assert
    with pytest.raises(SelectedCapabilityMissingError) as caught:
        check_selected_capabilities(
            demanded={TextSearch: "archive"}, selected=selected, table=_table(BLOBS), names={}
        )

    message = str(caught.value)
    assert "TextSearch" in message, "the capability that is missing, by its published name"
    assert "archive" in message, "the stage that needs it is named"
    assert "[services] blobs" in message, (
        "the remedy names the role key whose contract publishes the capability, "
        "never a fixed `[services] store`"
    )


def test_the_refusal_names_the_plugin_name_an_operator_configured_not_a_python_class() -> None:
    """`L9.26`: the remedy has to be a step someone can carry out.

    The production call site derived this from `type(store).__name__`, so a live refusal named
    `PgVectorStore` where `[services] store` accepts `pgvector` — a remedy that cannot be
    followed. Every existing test supplied the parameter by hand, which is exactly why none of
    them could catch it.
    """
    # Arrange
    from weft_cli.run_services import SelectedCapabilityMissingError, check_selected_capabilities

    selected = {"blobs": _ReadOnlyBlobs()}

    # Act / Assert
    with pytest.raises(SelectedCapabilityMissingError) as caught:
        check_selected_capabilities(
            demanded={TextSearch: "archive"},
            selected=selected,
            table=_table(BLOBS),
            names={"blobs": "fs-blobs"},
        )

    message = str(caught.value)
    assert "fs-blobs" in message, "the configured plugin name, as written in weft.toml"
    assert "_ReadOnlyBlobs" not in message, (
        "never the Python class name — it is not what [services] accepts"
    )


def test_a_demand_for_a_role_nobody_selected_is_refused_naming_that_role() -> None:
    """An unselected role is a configuration gap, and the refusal says which key fills it.

    Distinct from the case above: there the role was selected and its instance lacked the
    capability; here nothing was selected at all. Collapsing the two would tell an operator to
    swap a plugin they never chose.
    """
    # Arrange
    from weft_cli.run_services import SelectedCapabilityMissingError, check_selected_capabilities

    # Act / Assert
    with pytest.raises(SelectedCapabilityMissingError) as caught:
        check_selected_capabilities(
            demanded={VectorSearch: "fetch"}, selected={}, table=_table(BLOBS), names={}
        )

    assert "[services] blobs" in str(caught.value)
