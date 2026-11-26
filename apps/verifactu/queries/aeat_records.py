"""What the AEAT holds (``verifactu.aeat_record.list``), as the last «Query AEAT» left it."""

from live.context import OperationContext
from live.operations import operation

from apps.verifactu.models import AeatRecord
from apps.verifactu.schemas.aeat_records import AeatRecordListIn, AeatRecordOut
from apps.verifactu.schemas.fields import Page
from base.text_search import contains_text

from .reads import VIEW, page


def aeat_row(row: AeatRecord) -> dict:
    return {
        "id": row.id,
        "issuer_nif": row.issuer_nif,
        "environment": row.environment,
        "invoice_number": row.invoice_number,
        "issue_date": row.issue_date,
        "fingerprint": row.fingerprint,
        "state": row.state,
        "csv": row.csv,
        "generated_on": row.generated_on,
        "queried_at": row.queried_at,
    }


@operation(
    "verifactu.aeat_record.list",
    kind="query",
    permission=VIEW,
    input=AeatRecordListIn,
    output=Page[AeatRecordOut],
    ai={
        "description": "The last photo of what the AEAT holds (from the last «Query AEAT»), the newest first: "
        "search by invoice number, fingerprint or CSV; filter by its state at the AEAT (Correcto, "
        "AceptadoConErrores, Anulado) and issue date.",
        "asks": {
            "en": (
                "what does the AEAT hold of ours, per the last query?",
                "show what the AEAT has on file for us",
            ),
            "es": (
                "¿qué registros nuestros constan en la AEAT según la última consulta?",
                "enséñame lo que dice Hacienda que tiene nuestro",
            ),
        },
    },
)
def list_aeat_records(ctx: OperationContext, data: AeatRecordListIn) -> dict:
    queryset = AeatRecord.objects.all()
    text = (data.search or "").strip()
    if text:
        queryset = queryset.filter(contains_text(text, "invoice_number", "fingerprint", "csv"))
    if data.state:
        queryset = queryset.filter(state=data.state)
    if data.issue_date_from:
        queryset = queryset.filter(issue_date__gte=data.issue_date_from)
    if data.issue_date_to:
        queryset = queryset.filter(issue_date__lte=data.issue_date_to)
    prefix = "-" if data.dir == "desc" else ""
    column = data.sort or "generated_on"
    queryset = queryset.order_by(f"{prefix}{column}", f"{prefix}id")
    return page(queryset, data.limit, data.offset, aeat_row)
