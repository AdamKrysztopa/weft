"""Unit tests for `weft_cli.plugins_report`.

Mirrors `packages/weft-cli/src/weft_cli/plugins_report.py`. Covers the
`list` summary line, `doctor`'s fuller block (reason and disclosure
included), and the empty-report edge case both renderers share.
"""

from weft_cli.plugins_report import render_doctor, render_list
from weft_kernel.discovery import Disclosure, PackReport, PackStatus


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
