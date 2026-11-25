"""Read operations of the printing app: what the lists of every module share."""

import pytest

from base.tests.ordering import assert_reads_backwards, listed_with

from apps.printing.tests.conftest import HUB_DB, enqueue, printer, run

pytestmark = HUB_DB


@pytest.mark.parametrize(
    ("operation", "column", "tied"),
    [
        ("printing.printer.list", "kind", lambda: [printer(f"Till {n}").id for n in range(4)]),
        ("printing.job.list", "attempts", lambda: [enqueue().job.id for _ in range(4)]),
    ],
)
def test_ties_go_by_id_in_the_lists_own_direction(operation, column, tied):
    """hub#768: a descending list is the ascending one read backwards, ties included, and its
    pages neither repeat nor lose rows."""
    assert_reads_backwards(listed_with(run, operation, column, by_dir=True), sorted(tied()))
