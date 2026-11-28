"""The lines of a session as its movements, and whether this database holds any."""

from django.utils import timezone, translation
from live.context import OperationContext
from live.operations import operation

from apps.cash_register.models import Movement
from apps.cash_register.queries.figures import visible_lines
from apps.cash_register.queries.lines import Line
from apps.cash_register.queries.sessions import find_session, hides_expected, lines_of
from apps.cash_register.queries.settings import current_settings
from apps.cash_register.queries.unassigned import unassigned_lines
from apps.cash_register.schemas.movements import MovementListIn, MovementPage
from base.system import app_name


def line_row(line: Line) -> dict:
    return {
        "key": line.key,
        "session_id": line.session_id,
        "type": line.type,
        "amount": line.amount,
        "signed_amount": line.signed_amount,
        "method_type": line.method_type,
        "method_name": line.method_name,
        "description": line.description,
        "app": line.app,
        "app_name": app_name(line.app),
        "sale_id": line.sale_id,
        "sale_number": line.sale_number,
        "document_type": line.document_type,
        "gift_total": line.gift_total,
        "created_at": line.created_at,
        "created_by": line.created_by,
    }


@operation(
    "cash_register.movement.list",
    kind="query",
    permission="cash_register.view_movement",
    input=MovementListIn,
    output=MovementPage,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "which cash went in or out of the till today?",
                "show me the movements of the cash session",
            ),
            "es": (
                "¿cuánto dinero ha salido hoy de la caja?",
                "enséñame los movimientos de la sesión de caja",
            ),
        },
        "description": "The lines of a cash session (by its id or number), newest first: cash in and out written by hand, "
        "and the sales, voids and refunds of Sales with their payment method (a blind count shows whoever may not see "
        "the expected only the lines written by hand of an open session); or, with unassigned=true, the sale lines that "
        "fell in no shift. Search by concept or sale number; filter by type, payment method type and amount in cents."
    },
)
def list_movements(ctx: OperationContext, params: MovementListIn) -> dict:
    settings, now = current_settings(), timezone.now()
    if params.unassigned:
        lines = unassigned_lines(ctx, settings, now)
    else:
        session = find_session(ctx, params.session_id, params.session)
        lines = visible_lines(
            hides_expected(ctx, session, settings), lines_of(session, settings, now)
        )
    if params.search:
        text = params.search.strip().lower()
        lines = [
            line
            for line in lines
            if text in line.description.lower() or text in line.sale_number.lower()
        ]
    if params.type:
        lines = [line for line in lines if line.type == params.type]
    if params.method_type:
        lines = [line for line in lines if line.method_type == params.method_type]
    if params.amount_min is not None:
        lines = [line for line in lines if line.amount >= params.amount_min]
    if params.amount_max is not None:
        lines = [line for line in lines if line.amount <= params.amount_max]
    lines.sort(
        key=lambda line: (getattr(line, params.sort), line.key),
        reverse=params.dir == "desc",
    )
    page = lines[params.offset : params.offset + params.limit]
    with translation.override(ctx.language):  # Each line names its app in the reader's language.
        rows = [line_row(line) for line in page]
    return {
        "rows": rows,
        "total": len(lines),
        "limit": params.limit,
        "offset": params.offset,
    }


def keeps_fiscal_documents() -> bool:
    """Whether this database holds its cash movements (``fiscal_documents_kept`` on this app's config), of any status: a draft counts
    too, for what it asks is whether a database can go, and that cannot be undone."""
    return Movement.objects.exists()
