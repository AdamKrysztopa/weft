"""`release_preflight`'s provenance scan — carried repair `R22.15`.

`09` §5.2 asks that the originality rule be re-checked for a release, and until this repair nothing
did: task 6.11's audit ran once, and only its licence half became a check. The owner chose a scan
in preflight. It cannot prove a line is original, and says so; what it can do is fail on the marks
another codebase leaves behind — a copyright line naming someone other than this project's holder,
and a file saying it was adapted or copied from a URL — every release, with the passages judged
acceptable named in a waiver.
"""

from __future__ import annotations

from pathlib import Path

import release_preflight


def test_a_foreign_copyright_line_is_flagged_and_the_holders_own_is_not() -> None:
    # Arrange
    text = "Copyright (c) 2026 Adam Krysztopa\n# Copyright (c) 2019 Some Other Project\n"

    # Act
    found = release_preflight.provenance_markers(Path("x.py"), text, holder="Adam Krysztopa")

    # Assert
    assert found == ["x.py: Copyright (c) 2019 Some Other Project"]


def test_a_file_sourced_from_a_url_is_flagged_and_an_internal_copy_is_not() -> None:
    # Arrange
    text = (
        "# adapted from https://github.com/example/project/blob/main/x.py\n"
        "# copied from tests/unit/weft_cli/test_commands.py's double of the same seam\n"
    )

    # Act
    found = release_preflight.provenance_markers(Path("y.py"), text, holder="Adam Krysztopa")

    # Assert
    assert len(found) == 1
    assert found[0].startswith("y.py: adapted from https://github.com/example")


def test_the_tree_carries_no_unwaived_provenance_marker() -> None:
    # Arrange / Act
    failures = release_preflight.provenance_failures()

    # Assert
    assert failures == [], failures


def test_every_waiver_still_matches_a_marker_in_the_tree() -> None:
    # Arrange
    found = {release_preflight.waiver_key(hit) for hit in release_preflight.provenance_hits()}

    # Act
    stale = sorted(set(release_preflight.PROVENANCE_WAIVED) - found)

    # Assert
    assert stale == [], f"waived provenance markers no longer in the tree: {stale}"
