"""How a list that sorts both ways orders its rows (the old product's rule, hub#2355)."""

from collections.abc import Mapping, Sequence

from django.db.models import Expression, F
from django.db.models.expressions import OrderBy


def list_order(*columns: str | Expression, descending: bool, nulls_last: bool | None = None) -> list[OrderBy]:
    """What ``order_by`` needs for ``columns`` and then the id, all in the list's direction.

    A descending list is the ascending one read backwards, ties included. The id settles the last tie, so a
    touched row keeps its place and pages neither repeat nor lose rows. ``nulls_last=True`` keeps the empty values
    at the end both ways; without it they go where the database puts them (last ascending, first descending).
    A column is a name or an expression (``Lower("name")``), and one named twice counts where it first appears.
    """
    keys = [F(column) if isinstance(column, str) else column for column in dict.fromkeys((*columns, "id"))]
    return [key.desc(nulls_last=nulls_last) if descending else key.asc(nulls_last=nulls_last) for key in keys]


def list_order_for(
    sort: str,
    *ties: str | Expression,
    columns: Mapping[str, Sequence[str | Expression]] | None = None,
    nulls_last: bool | None = None,
) -> list[OrderBy]:
    """``list_order`` of a ``sort`` that says its direction itself: a leading «-» is descending.

    ``columns`` says what a sort stands for when it is not simply the column of its name; ``ties`` settle what the
    sort leaves tied, before the id.
    """
    key = sort.removeprefix("-")
    named = (columns or {}).get(key, (key,))
    return list_order(*named, *ties, descending=sort.startswith("-"), nulls_last=nulls_last)
