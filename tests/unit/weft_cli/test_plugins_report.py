"""Unit tests for `weft_cli.plugins_report`.

Mirrors `packages/weft-cli/src/weft_cli/plugins_report.py`. Covers the
`list` summary line, `doctor`'s fuller block (reason and disclosure
included), and the empty-report edge case both renderers share.

**Task 1.12** adds `render_doctor`'s `displaced` parameter — `docs/03-cli.md`:
"a displaced registration: the pack lost a `(contract, name)` collision to an
operator's pin, so it is installed, active, and one of its plugins is
unreachable." Covers a displaced entry appearing under its losing
distribution's own block, and the default empty tuple changing nothing about
the existing renderers.

**Task 5.2e** adds two more: a pack's `PackReport.deprecations` rendered as a flag beside
its status (`", deprecated"`, exactly the shape `", ambient"` already takes) plus a detail
line per surface, and `render_doctor`'s own `skew` parameter — every `weft_cli.skew.
SkewReport` printed as its own trailing block, the same shape `unconsulted_pins`/`tracing`
already take.
"""

from weft_cli.plugins_report import render_doctor, render_list
from weft_cli.skew import SkewReport
from weft_kernel.discovery import Disclosure, PackReport, PackStatus
from weft_kernel.pipeline import StageDeclaration
from weft_kernel.registry import DisplacedRegistration
from weft_kernel.resolution import Contribution
from weft_kernel.seam import Deprecation, Removal, RemovalClock


class _Chunker:
    """A stand-in contract — only its `__name__` is ever read here."""


def test_render_list_summarises_status_ambient_and_contribution_count() -> None:
    # Arrange
    reports = (
        PackReport(
            distribution="weft-store", status=PackStatus.ACTIVE, ambient=True, contributed=2
        ),
    )

    # Act
    output = render_list(reports)

    # Assert
    assert output == "weft-store: active, ambient (2 contributed)"


def test_render_list_reports_no_packs_discovered_when_empty() -> None:
    # Arrange / Act
    output = render_list(())

    # Assert
    assert output == "no packs discovered."


def test_render_doctor_includes_reason_and_disclosure() -> None:
    # Arrange
    reports = (
        PackReport(
            distribution="weft-graph",
            status=PackStatus.REFUSED,
            reason="'weft-graph' is not listed in [packs] allow.",
            disclosure=Disclosure(network=("bolt://localhost:7687",), note="reads a graph db"),
        ),
    )

    # Act
    output = render_doctor(reports)

    # Assert
    assert "never imported — 'weft-graph' is not listed in [packs] allow." in output
    assert "network=['bolt://localhost:7687']" in output
    assert "note='reads a graph db'" in output


def test_render_doctor_reports_not_disclosed_when_disclosure_is_absent() -> None:
    # Arrange
    reports = (PackReport(distribution="weft-store", status=PackStatus.ACTIVE, contributed=1),)

    # Act
    output = render_doctor(reports)

    # Assert
    assert "disclosure: not disclosed" in output


def test_render_doctor_lists_a_displaced_registration_under_its_losing_distribution() -> None:
    # Arrange
    reports = (
        PackReport(distribution="weft-loser", status=PackStatus.ACTIVE, contributed=1),
        PackReport(distribution="weft-winner", status=PackStatus.ACTIVE, contributed=1),
    )
    displaced = (
        DisplacedRegistration(
            contract=_Chunker,
            name="shared",
            distribution="weft-loser",
            winner="weft-winner",
            pin="_Chunker:shared",
        ),
    )

    # Act
    output = render_doctor(reports, displaced)
    blocks = output.split("\n\n")
    loser_block = next(block for block in blocks if block.startswith("weft-loser"))
    winner_block = next(block for block in blocks if block.startswith("weft-winner"))

    # Assert — the loser's block names what it lost and to whom; the winner's does not.
    assert "displaced" in loser_block
    assert "_Chunker:shared" in loser_block
    assert "weft-winner" in loser_block
    assert "displaced" not in winner_block


def test_render_doctor_with_no_displaced_registrations_is_unchanged() -> None:
    # Arrange — edge case: the default `displaced=()` must not alter existing output.
    reports = (PackReport(distribution="weft-store", status=PackStatus.ACTIVE, contributed=1),)

    # Act / Assert
    assert render_doctor(reports) == render_doctor(reports, ())


def test_render_doctor_reports_an_unconsulted_pin_as_its_own_trailing_block() -> None:
    # Arrange — repair for a reviewer finding: `weft plugins doctor` must still say an
    # inert pin exists once `discover(strict_pins=False)` stops that from being fatal.
    reports = (PackReport(distribution="weft-only", status=PackStatus.ACTIVE, contributed=1),)

    # Act
    output = render_doctor(reports, (), ("_Chunker:shared",))
    blocks = output.split("\n\n")

    # Assert — a distinct block, not folded into 'weft-only's own — no single distribution
    # is at fault for a pin that never saw a collision.
    assert len(blocks) == 2
    assert "_Chunker:shared" in blocks[1]
    assert "_Chunker:shared" not in blocks[0]


def test_render_doctor_with_no_unconsulted_pins_is_unchanged() -> None:
    # Arrange — edge case: the default `unconsulted_pins=()` must not alter existing output.
    reports = (PackReport(distribution="weft-store", status=PackStatus.ACTIVE, contributed=1),)

    # Act / Assert
    assert render_doctor(reports) == render_doctor(reports, (), ())


def test_render_doctor_reports_tracing_as_its_own_trailing_block() -> None:
    # Arrange — task 5.1d: the fact answers "are my spans going anywhere?", independent of
    # any one distribution's own block.
    reports = (PackReport(distribution="weft-otel", status=PackStatus.ACTIVE, contributed=0),)

    # Act
    output = render_doctor(reports, (), (), "configured — spans export through weft_otel.")
    blocks = output.split("\n\n")

    # Assert
    assert len(blocks) == 2
    assert blocks[1] == "tracing: configured — spans export through weft_otel."


def test_render_doctor_with_no_tracing_is_unchanged() -> None:
    # Arrange — edge case: the default `tracing=None` must not alter existing output.
    reports = (PackReport(distribution="weft-store", status=PackStatus.ACTIVE, contributed=1),)

    # Act / Assert
    assert render_doctor(reports) == render_doctor(reports, (), (), None)


def test_render_list_and_doctor_flag_a_deprecated_pack_beside_its_status() -> None:
    # Arrange — task 5.2e: a flag on an existing status, exactly as `ambient` already is
    # one, never a new `PackStatus` member.
    reports = (
        PackReport(
            distribution="weft-old",
            status=PackStatus.ACTIVE,
            contributed=1,
            deprecations=(
                Deprecation(
                    distribution="weft-old",
                    surface="legacy",
                    reason="use 'fast'",
                    removal=Removal(
                        clock=RemovalClock.NEXT_MAJOR,
                        distribution="weft-old",
                        installed_version="2.3.1",
                        release="weft-old 3.0.0",
                    ),
                ),
            ),
        ),
    )

    # Act
    list_output = render_list(reports)
    doctor_output = render_doctor(reports)

    # Assert
    assert list_output == "weft-old: active, deprecated (1 contributed)"
    assert "weft-old: active, deprecated (1 contributed)" in doctor_output
    assert "deprecated: 'legacy' — use 'fast'" in doctor_output


def test_render_list_and_doctor_do_not_flag_a_pack_with_no_deprecations() -> None:
    # Arrange — edge case: the default `deprecations=()` must not alter existing output.
    reports = (PackReport(distribution="weft-store", status=PackStatus.ACTIVE, contributed=1),)

    # Act / Assert
    assert "deprecated" not in render_list(reports)
    assert "deprecated" not in render_doctor(reports)


def test_render_doctor_reports_skew_as_its_own_trailing_block() -> None:
    # Arrange — task 5.2e: a fact about the environment, not about any one distribution.
    reports = (PackReport(distribution="weft-cli", status=PackStatus.ACTIVE, contributed=1),)
    skew = (
        SkewReport(
            requiring_distribution="weft-cli",
            required_distribution="weft-kernel",
            specifier=">=0.1.0,<1.0.0",
            installed_version="9.9.9",
        ),
    )

    # Act
    output = render_doctor(reports, (), (), None, skew)
    blocks = output.split("\n\n")

    # Assert
    assert len(blocks) == 2
    assert blocks[1] == (
        "version skew — installed does not satisfy a declared specifier:\n"
        "  'weft-cli' requires 'weft-kernel' >=0.1.0,<1.0.0, but 9.9.9 is installed."
    )


def test_render_doctor_with_no_skew_is_unchanged() -> None:
    # Arrange — edge case: the default `skew=()` must not alter existing output.
    reports = (PackReport(distribution="weft-store", status=PackStatus.ACTIVE, contributed=1),)

    # Act / Assert
    assert render_doctor(reports) == render_doctor(reports, (), (), None, ())


def test_render_doctor_flags_a_contribution_that_lands_in_no_pipeline_at_all() -> None:
    # Arrange — task 5.3a (S8), `02` §3 → *Slots*: "`weft plugins doctor` flags a pack whose
    # contributions land in *no* pipeline at all."
    reports = (
        PackReport(distribution="weft-graph", status=PackStatus.ACTIVE, contributed=1),
        PackReport(distribution="weft-store", status=PackStatus.ACTIVE, contributed=1),
    )
    unreachable = (
        Contribution(
            slot="never-declared",
            distribution="weft-graph",
            stage=StageDeclaration(id="entities", use="entity-extractor"),
        ),
    )

    # Act
    output = render_doctor(reports, (), (), None, (), unreachable)
    blocks = output.split("\n\n")
    graph_block = next(block for block in blocks if block.startswith("weft-graph"))
    store_block = next(block for block in blocks if block.startswith("weft-store"))

    # Assert — the offering distribution's own block names it; an unrelated one does not.
    assert "unreachable" in graph_block
    assert "never-declared" in graph_block
    assert "entities" in graph_block
    assert "unreachable" not in store_block


def test_render_doctor_with_no_unreachable_contributions_is_unchanged() -> None:
    # Arrange — edge case: the default `unreachable_contributions=()` must not alter output.
    reports = (PackReport(distribution="weft-store", status=PackStatus.ACTIVE, contributed=1),)

    # Act / Assert
    assert render_doctor(reports) == render_doctor(reports, (), (), None, (), ())


# ---------------------------------------------------------------------------
# Task 6.4 — `weft plugins doctor` says what is installed. `09` section 1:
# "gains one column, not a new command: the version of each active distribution."
# ---------------------------------------------------------------------------


def test_render_doctor_names_the_installed_version_of_each_distribution() -> None:
    """`09` section 1's one column. The version sits on the status line, beside the name."""
    # Arrange
    reports = (PackReport(distribution="weft-store", status=PackStatus.ACTIVE, contributed=2),)

    # Act
    output = render_doctor(reports, versions={"weft-store": "2.0.0"})

    # Assert
    assert output.startswith("weft-store 2.0.0: active (2 contributed)")


def test_render_doctor_says_when_a_version_is_not_recorded() -> None:
    """`docs/lessons.md` L5.9 — an absent measurement is reported, never rendered as a blank."""
    # Arrange
    reports = (PackReport(distribution="weft-mystery", status=PackStatus.ACTIVE),)

    # Act
    output = render_doctor(reports, versions={})

    # Assert
    assert output.startswith("weft-mystery (version not recorded): active (0 contributed)")


def test_render_list_is_not_given_the_version_column() -> None:
    """`09` section 1 gives the column to `doctor`, and `weft plugins list` is a summary."""
    # Arrange
    reports = (PackReport(distribution="weft-store", status=PackStatus.ACTIVE, contributed=2),)

    # Act
    output = render_list(reports)

    # Assert
    assert output == "weft-store: active (2 contributed)"


def test_render_doctor_without_versions_is_unchanged() -> None:
    """The default leaves every existing caller's output exactly as it was."""
    # Arrange
    reports = (PackReport(distribution="weft-store", status=PackStatus.ACTIVE, contributed=2),)

    # Act
    output = render_doctor(reports)

    # Assert
    assert output.startswith("weft-store: active (2 contributed)")


def test_render_doctor_names_when_a_deprecated_surface_goes() -> None:
    """Task 6.5 — `09` section 3's clock, where an operator actually reads it.

    G9 settled the unit as one major of the publishing distribution. The line already named the
    surface and the reason; what it could not say was *until when*, which is the whole content of
    a deprecation policy.
    """
    # Arrange
    reports = (
        PackReport(
            distribution="weft-old",
            status=PackStatus.ACTIVE,
            deprecations=(
                Deprecation(
                    distribution="weft-old",
                    surface="legacy",
                    reason="use 'fast'",
                    removal=Removal(
                        clock=RemovalClock.NEXT_MAJOR,
                        distribution="weft-old",
                        installed_version="2.3.1",
                        release="weft-old 3.0.0",
                    ),
                ),
            ),
        ),
    )

    # Act
    output = render_doctor(reports)

    # Assert
    assert "  deprecated: 'legacy' — use 'fast' (removed in weft-old 3.0.0)" in output


def test_render_doctor_says_a_0x_publisher_promises_no_window() -> None:
    """The state that must not be rendered as a release number — see `seam.RemovalClock`."""
    # Arrange
    reports = (
        PackReport(
            distribution="weft-young",
            status=PackStatus.ACTIVE,
            deprecations=(
                Deprecation(
                    distribution="weft-young",
                    surface="legacy",
                    reason="use 'fast'",
                    removal=Removal(
                        clock=RemovalClock.UNPROMISED_BEFORE_1_0,
                        distribution="weft-young",
                        installed_version="0.4.0",
                        release=None,
                    ),
                ),
            ),
        ),
    )

    # Act
    output = render_doctor(reports)

    # Assert
    assert "0.x" in output
    assert "1.0.0" not in output
