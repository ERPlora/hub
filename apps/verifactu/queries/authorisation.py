"""The signed authorisation (VERIFACTU-F05, F06): as the account tells it, and its model to sign
(``verifactu.representation.model``)."""

import base64
import datetime as dt

from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import OperationError
from live.operations import operation

from apps.verifactu import erplora_route, representation
from apps.verifactu.models import Config, Event
from apps.verifactu.schemas.authorisation import RepresentationModelOut
from apps.verifactu.schemas.fields import NoInput

from .route import issuer_model_details

CONFIGURE = "verifactu.configure"
SAAS_UNREACHABLE = _(
    "ERPlora could not handle this right now. Try again in a few minutes."
)
MODEL_FILENAME = "anexo-i-otorgamiento-representacion-erplora.pdf"
#: The audit trail's lines about the authorisation (``Event.message_key``) and the state each one tells.
REPRESENTATION_STEPS = {
    "representation_submitted": Config.Representation.SUBMITTED,
    "representation_under_review": Config.Representation.SUBMITTED,
    "representation_approved": Config.Representation.APPROVED,
    "representation_returned": Config.Representation.RETURNED,
    "representation_revoked": Config.Representation.REVOKED,
    "representation_none": Config.Representation.NONE,
}
REPRESENTATION_HISTORY_SHOWN = 20


def _instant(value, default: dt.datetime) -> dt.datetime:
    try:
        return dt.datetime.fromisoformat(value) if isinstance(value, str) else default
    except ValueError:
        return default


def representation_out(config: Config, issuer_nif: str) -> dict:
    """The authorisation as the account says it, plus what this Hub sent and the steps it has been told."""
    steps = Event.objects.filter(message_key__in=REPRESENTATION_STEPS).order_by(
        "-created_at", "-id"
    )
    last = steps.filter(message_key="representation_submitted").first()
    submission = None
    if last is not None:
        submission = {
            "version": last.params.get("version"),
            "submitted_at": _instant(last.params.get("submitted_at"), last.created_at),
            "document_type": last.params.get("document_type"),
            "documents": last.params.get("documents", []),
        }
    return {
        "status": config.representation_status,
        "updated_at": config.representation_updated_at,
        "reason": config.representation_reason,
        "linked": config.hub_id is not None,
        "company": representation.is_legal_person_nif(issuer_nif),
        "submission": submission,
        "history": [
            {
                "status": REPRESENTATION_STEPS[step.message_key],
                "at": _instant(step.params.get("at"), step.created_at),
                "version": step.params.get("version"),
                "reason": step.params.get("note", ""),
            }
            for step in steps[:REPRESENTATION_HISTORY_SHOWN]
        ],
    }


def saas_unreachable() -> OperationError:
    return OperationError(str(SAAS_UNREACHABLE), code="verifactu.saas_unreachable", status=503)


@operation(
    "verifactu.representation.model",
    kind="query",
    permission=CONFIGURE,
    input=NoInput,
    output=RepresentationModelOut,
    ai={
        "description": "The official model of the representation authorisation (Anexo I of the AEAT's Convenio "
        "17) with the business's legal name, tax ID and address from Invoicing already written in, a PDF the "
        "business prints and signs by hand, or signs with AutoFirma, before sending it for ERPlora to file on its "
        "behalf.",
        "asks": {
            "en": (
                "download the representation form filled in with our details",
                "give me the Anexo I to sign for ERPlora",
            ),
            "es": (
                "descarga el modelo de apoderamiento para ERPlora relleno",
                "dame el Anexo I con nuestros datos para firmarlo",
            ),
        },
    },
)
def representation_model(ctx: OperationContext, data: NoInput) -> RepresentationModelOut:
    erplora_route.refuse_unavailable(ctx.scope)
    try:
        content = representation.model_pdf(issuer_model_details())
    except representation.SaasUnreachable:
        raise saas_unreachable() from None
    return RepresentationModelOut(
        filename=MODEL_FILENAME,
        content_type="application/pdf",
        content_base64=base64.b64encode(content).decode("ascii"),
    )
