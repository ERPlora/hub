"""What the test of an app's lists checks (``base/ordering.py``, the rule of hub#2355)."""


def assert_reads_backwards(listed, expected):
    """``listed(descending, **page)`` gives a list's ids: ``expected`` ascending, the same read backwards descending,
    ties included, and the pages of the descending one neither repeat nor lose rows."""
    assert listed(False) == expected
    assert listed(True) == expected[::-1]
    half = len(expected) // 2
    pages = listed(True, limit=half, offset=0) + listed(True, limit=len(expected) - half, offset=half)
    assert pages == expected[::-1]


def listed_with(run, operation, column, *, schema=dict, by_dir=False, **filters):
    """The ``listed`` of ``assert_reads_backwards``: the ids ``run`` gets from ``operation`` sorted by ``column``, with
    the direction in a leading «-» or, ``by_dir``, in ``dir``. ``schema`` builds the input when ``run`` wants it built."""

    def listed(descending, **page):
        if by_dir:
            order = {"sort": column, "dir": "desc" if descending else "asc"}
        else:
            order = {"sort": f"-{column}" if descending else column}
        return [row.id for row in run(operation, schema(**order, **filters, **page)).rows]

    return listed
