"""How a list that sorts both ways orders its rows (the old product's rule, hub#2355)."""

from django.db.models import F
from django.db.models.expressions import OrderBy


def list_order(*columns: str, descending: bool, nulls_last: bool | None = None) -> list[OrderBy]:
    """What ``order_by`` needs for ``columns`` and then the id, all in the list's direction.

    A descending list is the ascending one read backwards, ties included. The id settles the last tie, so a
    touched row keeps its place and pages neither repeat nor lose rows. ``nulls_last=True`` keeps the empty values
    at the end both ways; without it they go where the database puts them (last ascending, first descending).
    """
    return [
        F(column).desc(nulls_last=nulls_last) if descending else F(column).asc(nulls_last=nulls_last)
        for column in (*columns, "id")
    ]
