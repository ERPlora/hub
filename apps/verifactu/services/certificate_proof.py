"""The own certificate as the AEAT's test environment proves it (VERIFACTU-F02, F08): each answer to a submission
presented with it in testing may accept it or reject it (``aeat.certificate_verdict``); going live needs it accepted.
Only testing proves it: an answer of production never changes it, nor one presented with ERPlora's seal (no
certificate of the business travelled with it)."""

from django.utils import timezone
from live.context import OperationContext
from live.outbox import record_event

from apps.verifactu import aeat, certificates, events, gateway
from apps.verifactu.models import Environment, Event, OwnCertificate

from .writes import _event


def note_answer(
    ctx: OperationContext, environment: str, reply: gateway.Reply, presented: gateway.Certificate | None
) -> None:
    """Keeps what ``reply`` says of the certificate ``presented`` in ``environment``, while it is still the one kept: an
    answer for a certificate replaced on its way says nothing of the new one."""
    if environment != Environment.TESTING or presented is None:
        return
    verdict = aeat.certificate_verdict(reply.aeat_status, reply.aeat_body)
    if verdict is None:
        return
    row = OwnCertificate.objects.select_for_update().filter(singleton=True).first()
    if row is None or not _still_kept(row, presented):
        return
    proof = OwnCertificate.Proof.ACCEPTED if verdict.accepted else OwnCertificate.Proof.REJECTED
    detail = verdict.detail[:500]
    if (row.aeat_proof, row.aeat_proof_detail) == (proof, detail):
        return
    row.aeat_proof, row.aeat_proof_detail = proof, detail
    row.save(update_fields=["aeat_proof", "aeat_proof_detail"])
    _told(ctx, row)


def _still_kept(row: OwnCertificate, presented: gateway.Certificate) -> bool:
    try:
        return certificates.material(row.sealed_blob) == presented
    except certificates.CertificateUnreadable:
        return False


def _told(ctx: OperationContext, row: OwnCertificate) -> None:
    params = {
        "holder": row.holder,
        "holder_tax_id": row.holder_tax_id,
        "expires_on": timezone.localtime(row.expires_at).date().isoformat(),
        # The door that cannot verify a certificate answers nothing but its status.
        "detail": row.aeat_proof_detail or f"HTTP {aeat.CERTIFICATE_REDIRECT}",
    }
    if row.aeat_proof == OwnCertificate.Proof.ACCEPTED:
        key, severity = "certificate_accepted_by_aeat", Event.Severity.INFO
    else:
        key, severity = "certificate_rejected_by_aeat", Event.Severity.WARNING
    _event(ctx, Event.Kind.CONFIG_CHANGED, key, params, severity=severity, environment=Environment.TESTING)
    record_event(ctx, events.CONFIG_CHANGED, {"fields": ["own_certificate"]})
