"""VeriFactu's configuration as its screen shows it (``verifactu.config.get``)."""

from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.operations import operation

from apps.verifactu import erplora_route, gateway, producer
from apps.verifactu.models import Config, Environment, OwnCertificate, Record
from apps.verifactu.schemas.config import ConfigOut
from apps.verifactu.schemas.fields import NoInput
from apps.verifactu.schemas.own_certificate import CertificateOut

from .authorisation import representation_out
from .reads import VIEW
from .route import (
    _route_sending_problem,
    blockers,
    config_row,
    issue_problem,
    issuer_identity,
    live_problems,
    own_certificate,
    production_open,
    route_problem,
    sending_route,
    wait,
)

#: Days before its expiry from which the own certificate is announced as expiring soon (VERIFACTU-F34).
EXPIRY_WARNING_DAYS = 30
REFUSED_BY_THE_AEAT = _("The AEAT's test environment refused this certificate (%(detail)s): upload another one.")
#: The AEAT's door answers a certificate it cannot verify with a redirect to its «401» page, which says these causes.
NOT_VERIFIED_BY_THE_AEAT = _(
    "The AEAT's test environment refused this certificate: it could not verify it (no authority it recognises issued "
    "it, it is not valid for this service or it has expired). Upload another one."
)


def _proof_detail(certificate: OwnCertificate | None) -> str:
    if certificate is None or certificate.aeat_proof != OwnCertificate.Proof.REJECTED:
        return ""
    if not certificate.aeat_proof_detail:
        return str(NOT_VERIFIED_BY_THE_AEAT)
    return str(REFUSED_BY_THE_AEAT) % {"detail": certificate.aeat_proof_detail}


def certificate_out() -> CertificateOut:
    certificate = own_certificate()
    expires = certificate.expires_at if certificate else None
    days = (expires - timezone.now()).days if expires else None
    return CertificateOut(
        loaded=certificate is not None,
        holder=certificate.holder if certificate else "",
        holder_tax_id=certificate.holder_tax_id if certificate else "",
        kind=certificate.kind if certificate else "",
        uploaded_at=certificate.uploaded_at if certificate else None,
        expires_at=expires,
        expires_in_days=days,
        expires_soon=days is not None and 0 <= days <= EXPIRY_WARNING_DAYS,
        aeat_proof=certificate.aeat_proof if certificate else OwnCertificate.Proof.UNTESTED,
        aeat_proof_detail=_proof_detail(certificate),
    )


def config_out(config: Config, ctx: OperationContext) -> ConfigOut:
    nif, name = issuer_identity()
    refused = issue_problem(config, ctx.scope)
    return ConfigOut(
        environment=config.environment,
        route=sending_route(config, config.environment, ctx.scope),
        erplora_route_available=erplora_route.available(ctx.scope),
        production_since=config.production_since,
        production_open=production_open(),
        can_go_back=not Record.objects.filter(
            environment=Environment.PRODUCTION
        ).exists(),
        gateway_configured=gateway.configured(),
        issuer_nif=nif,
        issuer_name=name,
        producer={
            "name": producer.MANUFACTURER["NombreRazon"],
            "nif": producer.MANUFACTURER["NIF"],
            "system_name": producer.MANUFACTURER["NombreSistemaInformatico"],
            "system_id": producer.MANUFACTURER["IdSistemaInformatico"],
            "version": producer.running_version(),
            "installation": ctx.scope.key,
            "only_verifactu": producer.MANUFACTURER["TipoUsoPosibleSoloVerifactu"],
            "multi_ot": producer.MANUFACTURER["TipoUsoPosibleMultiOT"],
            "multiple_ot": producer.MULTIPLE_OT,
        },
        declaration_version=producer.DECLARATION_VERSION,
        declaration_url=producer.declaration_url(),
        account_url=settings.SAAS_URL.rstrip("/"),
        own_certificate=certificate_out(),
        representation=representation_out(config, nif),
        synced_at=config.synced_at,
        route_ready=not route_problem(config, config.environment, ctx.scope),
        route_ready_for_production=not _route_sending_problem(config, Environment.PRODUCTION, ctx.scope),
        reasons=[wait(code) for code in blockers(config, config.environment, ctx.scope)],
        issue_blocker=wait(refused) if refused else None,
        live_blockers=[wait(code) for code in live_problems(config, ctx.scope)],
    )


@operation(
    "verifactu.config.get",
    kind="query",
    permission=VIEW,
    input=NoInput,
    output=ConfigOut,
    ai={
        "description": "VeriFactu's configuration: the environment (testing or production), the sending route (ERPlora "
        "files for the business, or its own certificate), the own certificate uploaded here (holder and expiry, never "
        "its material), the signed authorisation's state as the ERPlora account says, the software producer's details, the responsible declaration, and what keeps "
        "records from leaving now.",
        "asks": {
            "en": (
                "which route files our invoices with the AEAT, and are we still in testing?",
                "what keeps VeriFactu from filing with the AEAT?",
            ),
            "es": (
                "¿con qué vía remitimos a Hacienda y en qué entorno estamos?",
                "¿por qué no se pueden mandar los registros a la AEAT?",
            ),
        },
    },
)
def get_config(ctx: OperationContext, data: NoInput) -> ConfigOut:
    return config_out(config_row(), ctx)
