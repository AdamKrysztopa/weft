"""Unit tests for `weft_cli.service_roles` and the `[services]` role set it decides.

Mirrors `packages/weft-rag/src/weft_cli/service_roles.py`. **Ledger task 9.0, property (i) —
role selection**, tested alone: the other two properties (exact-key aliasing by demand, and
`needs_store` validation over the selected set) have their own files, because the task line
requires each to be tested without the others standing in for it.

What this file is about is a **key space that no longer lives in `weft-cli`**. Until 9.0 the
`[services]` keys were three fixed fields on `ServiceSelection`
(`packages/weft-rag/src/weft_cli/services.py:141 'class Serv'`), so a pack publishing a new run-wide
service had no way to be selected without an edit to this distribution — requirement 1
failing for the next pack, which is what Phase 7's close filed rather than fixed
(`docs/build-ledger.md:4358-4366 'emits prose'`, finding *(a)*). Here the set is contributed: a pack
declares a `ServiceRole` beside the contract it publishes, discovery carries it on the pack's
own report, and `weft-cli` reads the set rather than stating it.

**`route` is deliberately not a role.** It names a *pipeline document* resolved in the
contributed catalogue, not a plugin resolved in the registry
(`docs/03-cli.md:925-930 'weft_cli.commands.CommandRefusalError'`), so it
stays a field of its own. `embed` and `store` are roles whose names predate the mechanism, and
the tests below assert they came through it rather than being special-cased.
"""

from pathlib import Path

import pytest

from weft_cli.config_surface import config_keys_for
from weft_cli.service_roles import (
    DuplicateServiceRoleError,
    RoleTable,
    role_table_from_reports,
)
from weft_cli.services import UnknownServiceKeyError, service_selection_from_config
from weft_kernel.context import ServiceRole
from weft_kernel.discovery import PackReport, PackStatus, ServiceRoleOffer


class _BlobStore:
    """A stand-in contract published by a pack `weft-cli` has never heard of."""


class _GraphTraversal:
    """A second, unrelated stranger contract — Phase 11's, named here only as a type."""


def _report(
    *, distribution: str, roles: tuple[ServiceRole, ...], status: PackStatus = PackStatus.ACTIVE
) -> PackReport:
    return PackReport(
        pack=distribution.removeprefix("weft-"),
        distribution=distribution,
        status=status,
        service_roles=tuple(
            ServiceRoleOffer(distribution=distribution, role=role) for role in roles
        ),
    )


# --- the declared set ---------------------------------------------------------------------


def test_a_role_a_stranger_pack_declared_joins_the_selectable_set() -> None:
    """Requirement 1, for the next pack: a run-wide service becomes selectable on install.

    `docs/build-ledger.md:5024-5027 'is the d'` — "`[services].<role>` names one plugin for a role
    the
    contract-publishing pack declares selectable". Nothing in this distribution names
    `"blobs"`; it is reachable because a pack said so.
    """
    # Arrange
    reports = (
        _report(distribution="weft-blob", roles=(ServiceRole(key="blobs", contract=_BlobStore),)),
    )

    # Act
    table = role_table_from_reports(reports)

    # Assert
    assert "blobs" in table.declared
    assert table.roles["blobs"].contract is _BlobStore


def test_a_role_stays_selectable_when_the_pack_declaring_it_failed_to_load() -> None:
    """A pack that could not configure itself still tells an operator its key exists.

    This is the case that decided where the declaration is read from.
    `packages/weft-rag/src/weft_store/__init__.py` requires `[packs.store] dsn`, so on a
    machine with no `weft.toml` — this repository included, which ships none — the `store`
    pack reports `FAILED` and registers nothing. Had the declaration been buffered through
    `register()`, `[services] store = "qdrant"` would then be refused as an **unknown key**,
    naming the wrong problem entirely, on exactly the machine where an operator is trying to
    configure their way out of it. Reading `SERVICE_ROLES` at import — where `DISCLOSURE` is
    already read, before settings are validated — is what keeps the pre-9.0 behaviour: the key
    parses, and the plugin name fails later through `require_plugin`, which names the pack and
    its reason.
    """
    # Arrange
    reports = (
        _report(
            distribution="weft-blob",
            roles=(ServiceRole(key="blobs", contract=_BlobStore),),
            status=PackStatus.FAILED,
        ),
    )

    # Act
    table = role_table_from_reports(reports)

    # Assert
    assert "blobs" in table.declared


def test_two_packs_declaring_one_role_key_are_refused_naming_both() -> None:
    """One key, two claimants, and no way to tell which an operator meant.

    The same stance `weft_kernel.registry` takes for two packs claiming one plugin name, and
    for the same reason: a silent overwrite is a bug someone eventually has to find, and here
    it would silently repoint every `ctx.require` for that role at whichever pack was
    imported last.
    """
    # Arrange
    reports = (
        _report(distribution="weft-blob", roles=(ServiceRole(key="blobs", contract=_BlobStore),)),
        _report(
            distribution="weft-other", roles=(ServiceRole(key="blobs", contract=_GraphTraversal),)
        ),
    )

    # Act / Assert
    with pytest.raises(DuplicateServiceRoleError) as caught:
        role_table_from_reports(reports)

    message = str(caught.value)
    assert "blobs" in message
    assert "weft-blob" in message, "the refusal names both claimants, not just the loser"
    assert "weft-other" in message


def test_the_two_roles_whose_names_predate_the_mechanism_arrive_through_it() -> None:
    """`embed` and `store` are declared, not special-cased.

    `docs/build-ledger.md:5028-5030 's ticked'`: "`embed` and `store` stay as the two roles whose
    names
    predate the mechanism". *Stay as* is the whole point — if `weft-cli` kept naming them
    itself, the mechanism would have one exception and requirement 1 would still fail for the
    pack that needed the exception. Read off real discovery rather than a double, per
    `docs/lessons.md` L6.4: a marker means what its live instances say.
    """
    # Arrange
    from weft_cli import registry_bootstrap

    deps = registry_bootstrap.build_dependencies(Path("/nonexistent/weft.toml"))

    # Act
    declared = deps.roles.declared

    # Assert
    assert "embed" in declared
    assert "store" in declared
    assert "route" not in declared, (
        "route names a pipeline document, not a plugin, so it is not a role — "
        "docs/03-cli.md:925 'weft_cli.commands.CommandRefusalError'"
    )


# --- what the set is used for -------------------------------------------------------------


def test_a_declared_role_is_selected_from_weft_toml_with_no_edit_to_this_distribution() -> None:
    """The whole operation, one line in a file.

    This is the property the task exists for. `weft-cli` is not edited, not reinstalled, and
    has never heard of `blobs`.
    """
    # Arrange
    table = RoleTable(roles={"blobs": ServiceRole(key="blobs", contract=_BlobStore)})
    document: dict[str, object] = {"services": {"blobs": "fs-blobs"}}

    # Act
    selection = service_selection_from_config(document, table=table)

    # Assert
    assert selection.plugin_for("blobs") == "fs-blobs"


def test_a_declared_role_nothing_selected_is_absent_rather_than_guessed() -> None:
    """An unselected role is unselected. `weft-cli` does not invent one.

    A role carries no default of its own — `01`'s least-architecture check, and `L6.14`: a
    field no shipped pack writes answers emptily rather than usefully. `embed` and `store`
    keep defaults because their names predate the mechanism
    (`docs/build-ledger.md:5028 's ticked'`),
    and those two defaults live in `weft_cli.services` where they always have.

    `CLAUDE.md`: a silent fallback is worse than a failure — it produces a plausible answer
    against the wrong thing. A stage reaching for the contract gets
    `weft_kernel.context.UnresolvedServiceError` naming what this run *does* offer, which is
    requirement 5 doing its job on a role nobody configured.
    """
    # Arrange
    table = RoleTable(roles={"blobs": ServiceRole(key="blobs", contract=_BlobStore)})

    # Act
    selection = service_selection_from_config(None, table=table)

    # Assert
    assert "blobs" not in selection.roles


def test_an_undeclared_role_key_is_refused_naming_the_declared_set() -> None:
    """Requirement 5: an unknown name says what was wanted and what the valid options are.

    The set named is *derived from what is installed*, so an operator who mistypes a role a
    pack really does declare is told the real alternatives rather than a list this
    distribution wrote down once.
    """
    # Arrange
    table = RoleTable(roles={"blobs": ServiceRole(key="blobs", contract=_BlobStore)})
    document: dict[str, object] = {"services": {"blobz": "fs-blobs"}}

    # Act / Assert
    with pytest.raises(UnknownServiceKeyError) as caught:
        service_selection_from_config(document, table=table)

    assert "blobz" in str(caught.value)
    assert set(caught.value.valid_options) == {"blobs", "route"}, (
        "every declared role, plus route — which is a key without being a role"
    )


def test_route_is_accepted_as_a_key_while_never_being_a_role() -> None:
    """The one `[services]` key that names a pipeline rather than a plugin.

    `docs/03-cli.md:925-930 'weft_cli.commands.Comman'`. It shares the block because the question it
    answers is the same
    one — which of the installed things fills this role for this project — and splitting the
    block by how the lookup happens would put an implementation detail in a user's file.
    """
    # Arrange
    table = RoleTable(roles={"blobs": ServiceRole(key="blobs", contract=_BlobStore)})
    document: dict[str, object] = {"services": {"route": "route-by-score"}}

    # Act
    selection = service_selection_from_config(document, table=table)

    # Assert
    assert selection.route == "route-by-score"
    assert "route" not in selection.roles


def test_weft_config_offers_a_dotted_key_for_a_role_no_one_here_named() -> None:
    """`weft config get|set`'s vocabulary is the same set, not a second copy of it.

    `weft_cli.config_surface._KEY_FIELDS` was a hand-written closed vocabulary over the same
    `[services]` block, and it had already drifted: it listed `services.embed` and
    `services.store` and never `services.route`, which task 8.3 added to `ServiceSelection`
    and wired into `route_ask`. Two key spaces over one block, derived from different
    sources, is the failure `docs/README.md`'s own opening rule names — and the test that
    should have caught it asserted the five keys as a *literal*, so both sides of the
    comparison came from the same hand and it could not fail (`docs/lessons.md` L9.28).

    The stranger role here is the second source that makes this check non-vacuous: nothing in
    this distribution writes `"blobs"` anywhere.
    """
    # Arrange
    table = RoleTable(roles={"blobs": ServiceRole(key="blobs", contract=_BlobStore)})

    # Act
    keys = config_keys_for(table)

    # Assert
    assert "services.blobs" in keys
    assert "services.route" in keys, "the key 8.3 added and the hand-written vocabulary missed"
