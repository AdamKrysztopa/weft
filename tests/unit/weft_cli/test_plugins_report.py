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
"""

from weft_cli.plugins_report import render_doctor, render_list
from weft_kernel.discovery import Disclosure, PackReport, PackStatus
from weft_kernel.registry import DisplacedRegistration


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
