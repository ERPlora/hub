"""The counts of a session: their rows and their read."""

from live.context import OperationContext
from live.operations import operation

from apps.cash_register.models import Count
from apps.cash_register.queries.sessions import find_session
from apps.cash_register.schemas.counts import CountListIn, CountPage
from base.ordering import list_order


def count_row(count: Count) -> dict:
    return {
        "id": count.id,
        "session_id": count.session_id,
        "type": count.type,
        "total": count.total,
        "denominations": count.denominations,
        "notes": count.notes,
        "counted_at": count.counted_at,
        "counted_by": count.counted_by,
    }


@operation(
    "cash_register.count.list",
    kind="query",
    permission="cash_register.view_count",
    input=CountListIn,
    output=CountPage,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "show me the counts of session S-261014-0001",
                "list this morning's drawer counts",
            ),
            "es": (
                "enséñame los arqueos de la sesión S-261014-0001",
                "lista los arqueos del cajón de esta mañana",
            ),
        },
        "description": "The counts of a cash session (by its id or number), newest first: opening or closing, the total "
        "counted in cents and its notes and coins."
    },
)
def list_counts(ctx: OperationContext, params: CountListIn) -> dict:
    session = find_session(ctx, params.session_id, params.session)
    counts = Count.objects.filter(session=session).order_by(
        *list_order(params.sort, descending=params.dir == "desc")
    )
    page = counts[params.offset : params.offset + params.limit]
    return {
        "rows": [count_row(count) for count in page],
        "total": counts.count(),
        "limit": params.limit,
        "offset": params.offset,
    }
