"""The `[services]` key space, contributed rather than stated — ledger task **9.0**.

Until this task the `[services]` keys were three fixed fields on
`weft_cli.services.ServiceSelection`, so a pack publishing a new run-wide service had no way
to be selected without an edit to `weft-cli` itself — Phase 7's close, finding *(a)*
(`docs/build-ledger.md:4358-4366`). `weft_kernel.discovery.ServiceRoleOffer` already carries a
pack's own declaration on its `PackReport`; this module is where every report's declarations
are gathered into the one table `weft_cli.services` reads instead of stating the set itself.

**Why this filters on `status` when `contributions_from` (`weft_cli.registry_bootstrap:285`)
deliberately does not.** That function's own docstring gives the reason it skips the filter:
`PackRegistrar.commit`'s atomicity already guarantees a non-`ACTIVE` report's own
`contributions` is empty, so a second check here would be redundant with what the kernel
already enforces. The same guarantee holds for `service_roles` — a `FAILED` report's is
`()` too — and this module filters anyway, because `test_a_role_declared_by_a_pack_that_
failed_is_not_selectable` asserts the CLI does not trust the field alone. `phase-step`'s own
rule is "where two layers can both diagnose, the first must make the check the second
makes": the kernel's atomicity is the second layer, and this is the first.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from pydantic import BaseModel, ConfigDict

from weft_kernel.context import ServiceRole
from weft_kernel.discovery import PackReport
from weft_kernel.errors import WeftError


class DuplicateServiceRoleError(WeftError):
    """Two packs declared the same `[services]` role key.

    Deliberately a plain `WeftError`, not a member of fitness function 12's
    `UnresolvedNameError` family: nothing here is being looked up and failing to resolve — two
    claimants are disagreeing about one name, the same distinction `weft_cli.services`'s own
    module docstring draws for its malformed-`[services]`-value check. There is no
    `valid_options` to offer; the fix is renaming one pack's role, not picking from a list.
    """


class RoleTable(BaseModel):
    """Every `ServiceRole` a trusted report declared, keyed by its `[services]` name.

    `roles` defaults empty, so a caller that never ran discovery — a unit test building
    `ServiceSelection` by hand — gets the same `embed`/`store`-only surface it always had.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    roles: Mapping[str, ServiceRole] = {}

    @property
    def declared(self) -> tuple[str, ...]:
        """The sorted set of role keys this run's installed packs made selectable."""
        return tuple(sorted(self.roles))


def role_table_from_reports(reports: Iterable[PackReport]) -> RoleTable:
    """Gather every `ServiceRoleOffer` on every report into one `RoleTable`.

    **Every report, and a `FAILED` one's declarations count.** This function filtered on
    nothing when it was written and still does; it carried a `_TRUSTED_STATUSES` constant
    (`ACTIVE`, `PARTIAL`) that nothing referenced and a summary line saying *"every trusted
    report"*, both removed 2026-09-06 at a review of task 9.0 — a constant no code reads is a
    claim about behaviour, and this one contradicted the paragraph directly beneath it
    (`docs/lessons.md` `L9.51`). Trust is decided upstream, as the paragraph below says.

    `weft_kernel.discovery._read_service_roles`
    reads a pack's `SERVICE_ROLES` at import, before its settings are validated, precisely so
    that a pack which failed to configure still tells an operator its `[services]` key exists.
    `weft-store` is the case that settles it: `[packs.store] dsn` is required, so with no
    `weft.toml` that pack is `FAILED` — and `[services] store = "qdrant"` must still parse.
    Filtering on status here would put that regression straight back.

    Trust is already decided upstream: `discover()` never loads a pack `[packs] allow` refused,
    so a refused pack's module attribute is never read and cannot reach this function at all.

    Two packs claiming the same key raise `DuplicateServiceRoleError` naming the key and both
    distributions, never picking a winner by import order.
    """
    roles: dict[str, ServiceRole] = {}
    claimed_by: dict[str, str] = {}
    for report in reports:
        for offer in report.service_roles:
            key = offer.role.key
            if key in claimed_by and claimed_by[key] != offer.distribution:
                raise DuplicateServiceRoleError(
                    f"role {key!r} was declared by more than one pack for [services]: "
                    f"{claimed_by[key]!r} and {offer.distribution!r}. A role key names exactly "
                    f"one contract, so an operator's [services].{key} must have exactly one "
                    f"pack it could mean."
                )
            claimed_by[key] = offer.distribution
            roles[key] = offer.role
    return RoleTable(roles=roles)
