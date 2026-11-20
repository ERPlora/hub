"""The last connection test (``verifactu.diagnostic.last``)."""

from live.context import OperationContext
from live.operations import operation

from apps.verifactu.models import Event
from apps.verifactu.schemas.diagnostics import DiagnosticLastOut
from apps.verifactu.schemas.fields import NoInput

from .reads import VIEW
from .route import wait


@operation(
    "verifactu.diagnostic.last",
    kind="query",
    permission=VIEW,
    input=NoInput,
    output=DiagnosticLastOut,
    ai={
        "description": "The result of the last VeriFactu connection test, or none.",
        "asks": {
            "en": (
                "what did the last connection diagnostic say?",
                "did the last VeriFactu diagnostic pass?",
            ),
            "es": (
                "¿qué dio el último diagnóstico de conexión con Hacienda?",
                "¿pasó VeriFactu el último diagnóstico?",
            ),
        },
    },
)
def last_diagnostic(ctx: OperationContext, data: NoInput) -> DiagnosticLastOut:
    event = (
        Event.objects.filter(kind=Event.Kind.CONNECTION_TEST)
        .order_by("-created_at", "-id")
        .first()
    )
    if event is None or "result" not in event.params:
        return DiagnosticLastOut(result=None)
    result = dict(event.params["result"])
    # The reasons in the reader's language, from their codes.
    result["reasons"] = [
        wait(item["code"], item.get("detail", "")) for item in result.get("reasons", [])
    ]
    return DiagnosticLastOut(result=result)
