"""The business's own certificate (``verifactu.certificate.*``): uploaded, removed, and checked again against the
trusted list of recognised authorities once it is kept."""

import base64
import binascii

from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict
from live.operations import operation
from live.outbox import record_event

from apps.verifactu import certificates, events, trust
from apps.verifactu.models import Environment, Event, OwnCertificate
from apps.verifactu.queries.config import config_out
from apps.verifactu.queries.route import config_row, issuer_configured, issuer_identity, own_certificate
from apps.verifactu.schemas import CertificateUploadIn, ConfigOut, NoInput

from .sending import _back_in_the_queue, _unsent
from .writes import CONFIGURE, ISSUER_MISSING, _actor, _event

CERTIFICATE_STORAGE_UNAVAILABLE = _(
    "This server cannot keep certificates yet: ERPlora has to set its storage key."
)
CERTIFICATE_HOLDER_MISMATCH = _(
    "The certificate belongs to %(holder)s, not to this business's issuer %(issuer)s."
)
CERTIFICATE_EXPIRED = _("The certificate expired on %(date)s: upload a valid one.")
#: Only the platform runs the check of the kept certificate (the scheduled task): no role is given this permission.
SYSTEM = "verifactu.system"


def _certificate_event(ctx, key: str, row: OwnCertificate, severity: str = "info") -> None:
    _event(
        ctx,
        Event.Kind.CONFIG_CHANGED,
        key,
        {
            "holder": row.holder,
            "holder_tax_id": row.holder_tax_id,
            "expires_on": timezone.localtime(row.expires_at).date().isoformat(),
        },
        severity=severity,
        environment=config_row().environment,
    )
    record_event(ctx, events.CONFIG_CHANGED, {"fields": ["own_certificate"]})


@operation(
    "verifactu.certificate.upload",
    kind="command",
    permission=CONFIGURE,
    input=CertificateUploadIn,
    output=ConfigOut,
    ai={
        "description": "Not an assistant tool (a certificate and its password are secrets, given on the screen and "
        "never in a chat): upload the business's own certificate (.p12/.pfx in base64, with its password) to file its "
        "VeriFactu records with it (the «own» route). It must belong to Invoicing's issuer, allow client "
        "authentication and be in force; it replaces the one uploaded before and is kept encrypted, never shown again.",
        "risk": "high",
    },
)
def upload_certificate(ctx: OperationContext, data: CertificateUploadIn) -> ConfigOut:
    if not certificates.storage_available():
        raise Conflict(
            str(CERTIFICATE_STORAGE_UNAVAILABLE),
            code="verifactu.certificate_storage_unavailable",
        )
    if not issuer_configured():
        raise Conflict(str(ISSUER_MISSING), code="verifactu.issuer_missing")
    try:
        p12 = base64.b64decode(
            "".join(data.p12_base64.get_secret_value().split()), validate=True
        )
    except (binascii.Error, ValueError):
        p12 = b""
    password = data.password.get_secret_value()
    try:
        facts = certificates.inspect(p12, password)
    except certificates.CertificateInvalid as invalid:
        raise Conflict(str(invalid), code="verifactu.certificate_invalid") from None
    if facts.expires_at <= timezone.now():
        raise Conflict(
            str(CERTIFICATE_EXPIRED)
            % {"date": timezone.localtime(facts.expires_at).date().isoformat()},
            code="verifactu.certificate_invalid",
        )
    issuer = issuer_identity()[0].strip().upper()
    if facts.holder_tax_id != issuer:
        raise Conflict(
            str(CERTIFICATE_HOLDER_MISMATCH)
            % {"holder": facts.holder_tax_id or facts.holder, "issuer": issuer},
            code="verifactu.certificate_holder_mismatch",
        )
    row, _created = OwnCertificate.objects.update_or_create(
        singleton=True,
        defaults={
            "holder": facts.holder[:200],
            "holder_tax_id": facts.holder_tax_id,
            "kind": facts.kind,
            "expires_at": facts.expires_at,
            "uploaded_at": timezone.now(),
            "uploaded_by": _actor(ctx),
            "sealed_blob": certificates.seal(p12, password),
            "issuer_recognised": True,
            "checked_list": trust.sequence(),
        },
    )
    _back_in_the_queue()
    _certificate_event(ctx, "certificate_uploaded", row)
    return config_out(config_row(), ctx)


@operation(
    "verifactu.certificate.remove",
    kind="command",
    permission=CONFIGURE,
    input=NoInput,
    output=ConfigOut,
    ai={
        "description": "Remove the business's own certificate from this Hub. In testing, records then go out with "
        "ERPlora's seal; live on the «own» route, they wait in the queue until another certificate is uploaded.",
        "risk": "high",
        "asks": {
            "en": (
                "remove our own certificate from the Hub",
                "delete the digital certificate we uploaded",
            ),
            "es": (
                "quita nuestro certificado digital del Hub",
                "borra la firma electrónica que subimos",
            ),
        },
    },
)
def remove_certificate(ctx: OperationContext, data: NoInput) -> ConfigOut:
    row = own_certificate()
    if row is not None:
        OwnCertificate.objects.filter(pk=row.pk).delete()
        # Only testing changes route without it: production keeps the route fixed on going live.
        _back_in_the_queue(_unsent().filter(environment=Environment.TESTING))
        _certificate_event(ctx, "certificate_removed", row)
    return config_out(config_row(), ctx)


@operation(
    "verifactu.certificate.recheck",
    kind="command",
    permission=SYSTEM,
    input=NoInput,
    output=ConfigOut,
    ai={
        "description": "Platform only: check the kept own certificate again against the trusted list of recognised "
        "authorities, when it was never checked or was checked against an older list; one no recognised authority "
        "issued stops counting.",
        "risk": "normal",
    },
)
def recheck_certificate(ctx: OperationContext, data: NoInput) -> ConfigOut:
    # Locked: an upload meanwhile waits, so its certificate never takes this one's verdict.
    row = OwnCertificate.objects.select_for_update().filter(singleton=True).exclude(checked_list=trust.sequence()).first()
    if row is not None:
        _check(ctx, row)
    return config_out(config_row(), ctx)


def _check(ctx: OperationContext, row: OwnCertificate) -> None:
    """Records whether ``row`` still presents: one this server cannot open is left unchecked, as it was (production
    already waits on it with ``own_certificate_unreadable``)."""
    try:
        p12, password = certificates.open(row.sealed_blob)
    except certificates.CertificateUnreadable:
        return
    try:
        certificates.inspect(p12, password)
    except certificates.CertificateInvalid:
        recognised = False
    else:
        recognised = True
    counted = row.issuer_recognised is not False
    row.issuer_recognised, row.checked_list = recognised, trust.sequence()
    row.save(update_fields=["issuer_recognised", "checked_list"])
    if counted and not recognised:
        # Like a removal: in testing, what the gateway refused goes out again by ERPlora's seal.
        _back_in_the_queue(_unsent().filter(environment=Environment.TESTING))
        _certificate_event(ctx, "certificate_refused", row, severity=Event.Severity.WARNING)
