"""One page of a list of the room: its rows, how many there are in all, and the page asked for (``limit`` ≤ 100)."""


def _page(queryset, params, row) -> dict:
    items = list(queryset[params.offset : params.offset + params.limit])
    return {
        "rows": row(items),
        "total": queryset.count(),
        "limit": params.limit,
        "offset": params.offset,
    }
