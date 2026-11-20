"""The signed authorisation (VERIFACTU-F05, F06): its new state left in the audit trail, and the
authorisation sent to ERPlora (``verifactu.representation.submit``)."""


from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, InvalidPayload
from live.operations import operation

from apps.verifactu import erplora_route, representation
from apps.verifactu.models import Config, Event
from apps.verifactu.queries.authorisation import saas_unreachable
from apps.verifactu.queries.config import config_out
from apps.verifactu.queries.country import refuse_outside_spain
from apps.verifactu.queries.route import config_row, issuer_configured, issuer_identity
from apps.verifactu.schemas.authorisation import RepresentationSubmitIn
from apps.verifactu.schemas.config import ConfigOut

from .writes import CONFIGURE, ISSUER_MISSING, _changed, _config, _event

SIGNER_REQUIRED = _("Fill in the name and ID number of the person signing.")
SIGNED_MODEL_REQUIRED = _("Attach the signed form.")
SIGNED_MODEL_NOT_PDF = _("The signed form has to be a PDF: scan it or sign it with AutoFirma.")
ID_COPY_REQUIRED = _("Attach a copy of the identity document.")
SIGNATURE_SAMPLE_REQUIRED = _("With a NIE we also need a sample of the handwritten signature.")
REPRESENTATION_PROOF_REQUIRED = _(
    "Attach the document that proves you may sign for the company."
)
DOCUMENT_TOO_LARGE = _("Each file has to be 5 MB at most.")
DOCUMENT_NOT_PDF = _("Each file has to be a PDF.")
REPRESENTATION_INCOMPLETE = _("The authorisation cannot be sent as it is.")
REPRESENTATION_REFUSED = _("ERPlora did not take the authorisation as it is.")
HUB_UNREGISTERED = _(
    "ERPlora has not linked this business yet. Try again in a few minutes."
)
#: The documents in the order the SaaS checks them: (this input's field, the contract's name).
REPRESENTATION_DOCUMENTS = (
    ("signed_model_base64", "signed_model"),
    ("id_copy_base64", "id_copy"),
    ("signature_sample_base64", "signature_sample"),
    ("representation_proof_base64", "representation_proof"),
)


def _representation_step(ctx: OperationContext, config: Config, data) -> None:
    """Leave in the audit trail the authorisation's new state, as the photo says it."""
    at = data.updated_at or timezone.now()
    key = (
        "representation_under_review"
        if data.status == Config.Representation.SUBMITTED
        else f"representation_{data.status}"
    )
    _event(
        ctx,
        Event.Kind.CONFIG_CHANGED,
        key,
        {"at": at, "note": data.reason},
        environment=config.environment,
    )


def _representation_payload(  # noqa: C901, PLR0912
    data: RepresentationSubmitIn, taxpayer_tax_id: str, taxpayer_name: str
) -> dict:
    """The contract's body, or ``InvalidPayload`` naming every broken rule with the first one's code: the SaaS's
    own rules and codes (the old Hub's ``validate``), checked before anything crosses the network."""
    problems: list[tuple[str, str, str]] = []
    company = representation.is_legal_person_nif(taxpayer_tax_id)
    signer_tax_id = representation.normalise_nif(data.signer_tax_id)
    signer_name = data.signer_name
    if not company and not signer_tax_id and not signer_name:
        # A self-employed business signs itself: its signer is the taxpayer, not a second person.
        signer_tax_id = representation.normalise_nif(taxpayer_tax_id)
        signer_name = taxpayer_name
    if not signer_tax_id:
        problems.append(("signer_tax_id", "fiscal.signer_required", SIGNER_REQUIRED))
    if not signer_name:
        problems.append(("signer_name", "fiscal.signer_required", SIGNER_REQUIRED))
    required = {
        "signed_model": ("fiscal.signed_model_required", SIGNED_MODEL_REQUIRED),
        "id_copy": ("fiscal.id_copy_required", ID_COPY_REQUIRED),
    }
    if data.signer_document_type == "nie":
        # Many foreign identity documents carry no printed signature to compare against.
        required["signature_sample"] = (
            "fiscal.signature_sample_required",
            SIGNATURE_SAMPLE_REQUIRED,
        )
    if company:
        # A company signs through whoever its deeds name: the model's note (2).
        required["representation_proof"] = (
            "fiscal.representation_proof_required",
            REPRESENTATION_PROOF_REQUIRED,
        )
    documents: dict[str, str | None] = {}
    for field, name in REPRESENTATION_DOCUMENTS:
        value = getattr(data, field).get_secret_value().strip()
        documents[name] = None
        if not value:
            if name in required:
                problems.append((field, *required[name]))
            continue
        problem = representation.document_problem(value)
        if problem == "too_large":
            problems.append((field, "fiscal.document_too_large", DOCUMENT_TOO_LARGE))
        elif problem == "not_pdf" and name == "signed_model":
            problems.append((field, "fiscal.signed_model_not_pdf", SIGNED_MODEL_NOT_PDF))
        elif problem == "not_pdf":
            problems.append((field, "fiscal.document_not_pdf", DOCUMENT_NOT_PDF))
        else:
            documents[name] = value
    if problems:
        raise InvalidPayload(
            str(REPRESENTATION_INCOMPLETE),
            code=problems[0][1],
            fields={field: str(message) for field, _code, message in problems},
        )
    return {
        "taxpayer_tax_id": taxpayer_tax_id,
        "taxpayer_name": taxpayer_name,
        "signer_tax_id": signer_tax_id,
        "signer_name": signer_name,
        "signer_document_type": data.signer_document_type,
        "documents": documents,
    }


@operation(
    "verifactu.representation.submit",
    kind="command",
    permission=CONFIGURE,
    input=RepresentationSubmitIn,
    output=ConfigOut,
    ai={
        "description": "Not an assistant tool (it takes signed PDFs and a copy of an identity document, picked on the "
        "screen and never sent through a chat): send the signed representation authorisation (Anexo I of the AEAT's "
        "Convenio 17) for ERPlora to file on the business's behalf: the signed model and a copy of the signer's "
        "identity document, plus a signature sample with a NIE and the proof of representation for a company, each a "
        "PDF of 5 MB at most. "
        "A person at ERPlora reviews it; until then it is under review. This Hub keeps none of the documents.",
        "risk": "high",
    },
)
def submit_representation(
    ctx: OperationContext, data: RepresentationSubmitIn
) -> ConfigOut:
    refuse_outside_spain(ctx)
    erplora_route.refuse_unavailable(ctx.scope)
    hub_id = config_row().hub_id
    if hub_id is None:
        raise Conflict(str(HUB_UNREGISTERED), code="verifactu.hub_unregistered")
    if not issuer_configured():
        raise Conflict(str(ISSUER_MISSING), code="verifactu.issuer_missing")
    payload = _representation_payload(data, *issuer_identity())
    try:
        result = representation.submit(
            hub_id, payload, language=ctx.language or "en"
        )
    except representation.RepresentationRefused as refused:
        raise InvalidPayload(
            refused.message or str(REPRESENTATION_REFUSED),
            code=refused.code,
            fields=refused.fields or None,
        ) from None
    except representation.HubUnknown:
        raise Conflict(
            str(HUB_UNREGISTERED), code="verifactu.hub_unregistered"
        ) from None
    except representation.SaasUnreachable:
        raise saas_unreachable() from None
    # Locked only now: nothing is held while the documents travel.
    config = _config()
    submitted_at = result.submitted_at or timezone.now()
    if config.representation_status != Config.Representation.APPROVED:
        # The account's photo says it too; until then the Hub knows it is under review. An approved one stays in
        # force (and keeps filing) until a person approves the new one.
        config.representation_status = Config.Representation.SUBMITTED
        config.representation_updated_at = submitted_at
        config.representation_reason = ""
    _changed(
        ctx,
        config,
        "representation_submitted",
        {
            "version": result.version,
            "submitted_at": submitted_at,
            "document_type": data.signer_document_type,
            "documents": [name for name, value in payload["documents"].items() if value],
        },
        fields=["representation"],
    )
    return config_out(config, ctx)
