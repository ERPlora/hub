"""The way a record goes to the AEAT: the configuration, Invoicing's issuer, the environment, the own
certificate and the route, and what keeps a record from leaving. What keeps it is computed when it is read,
from the configuration, the gateway and the chain's AEAT wait, plus the last attempt's failure kept on the
record."""

import datetime as dt

from django.conf import settings
from django.utils import timezone
from live.context import OperationContext, Scope

from apps.invoice.models import Issuer
from base import operations as platform
from apps.verifactu import certificates, erplora_route, gateway, producer
from apps.verifactu.models import Config, Environment, OwnCertificate, Record, SendControl, wait_reason_text

from .country import OUTSIDE_SPAIN, outside_spain

#: The waits that are a past attempt's failure, kept on the record (the rest are computed when read).
ATTEMPT_FAILURES = ("unreachable", "refused", "unknown", "aeat_fault", "xml_invalid")


def config_row() -> Config:
    """The configuration; an unsaved default while nothing was ever saved."""
    return Config.objects.filter(singleton=True).first() or Config()


def issuer_identity() -> tuple[str, str]:
    """Invoicing's issuer: (tax ID, legal name), empty without one."""
    row = Issuer.objects.first()
    return (row.tax_id, row.legal_name) if row else ("", "")


def issuer_model_details() -> dict[str, str]:
    """Invoicing's issuer as the model of the authorisation names the taxpayer (``representation.MODEL_FIELDS``): its
    tax ID, legal name and fiscal address, the number within the street as the issuer keeps it; empty without one."""
    row = Issuer.objects.first()
    if row is None:
        return {}
    return {
        "taxpayer_tax_id": row.tax_id,
        "taxpayer_name": row.legal_name,
        "municipality": row.city,
        "street": row.address,
    }


def issuer_configured() -> bool:
    row = Issuer.objects.first()
    return bool(row and row.configured)


def production_open() -> bool:
    """Whether this server lets a business go live (VERIFACTU-F08): only the ``prod`` deployment, and only once ERPlora
    opens it there (``VERIFACTU_PRODUCTION_ENABLED``, a supervised step); ``pre`` always files in testing."""
    return settings.ERPLORA_ENVIRONMENT == "prod" and bool(
        settings.VERIFACTU_PRODUCTION_ENABLED
    )


def effective_environment(ctx: OperationContext, config: Config) -> str:
    """The AEAT environment a new record of this business files in: ERPlora's own hub, its deployment's (``prod``:
    production; ``pre``: testing), whatever its switch says, but production only once ERPlora opens it on the server
    (``production_open``: its own invoices skip no lock); once live there, it stays in production while the server is
    closed, its records waiting (``production_closed``), so its real invoices never move to the test chain. A demo,
    always testing, whatever its configuration says: it never goes live (``go_live_forbidden``). Any other
    business, its configuration's."""
    if platform.is_demo_hub(ctx.scope):
        return Environment.TESTING
    if platform.is_platform_hub(ctx.scope):
        if production_open() or (
            settings.ERPLORA_ENVIRONMENT == "prod"
            and config.environment == Environment.PRODUCTION
        ):
            return Environment.PRODUCTION
        return Environment.TESTING
    return config.environment


def _counted_certificate():
    """The own certificate as it counts: never one the trusted list's check found no recognised authority issued
    (until checked, it counts as it did when it was uploaded)."""
    return OwnCertificate.objects.filter(singleton=True).exclude(issuer_recognised=False)


def own_certificate() -> OwnCertificate | None:
    """The business's own certificate, its sealed material left unread; ``None`` while none counts."""
    return _counted_certificate().defer("sealed_blob").first()


def own_certificate_blob() -> bytes | None:
    """The sealed material of the own certificate (``certificates.material`` opens it); ``None`` without one."""
    blob = _counted_certificate().values_list("sealed_blob", flat=True).first()
    return bytes(blob) if blob is not None else None


def own_certificate_material(route: str) -> gateway.Certificate | None:
    """What the gateway presents with on the «own» ``route`` (``None`` on ERPlora's, or without a certificate);
    ``certificates.CertificateUnreadable`` when this server's key cannot open it."""
    if route != Config.Route.OWN:
        return None
    blob = own_certificate_blob()
    return certificates.material(blob) if blob is not None else None


def own_certificate_readable(route: str) -> bool:
    try:
        own_certificate_material(route)
    except certificates.CertificateUnreadable:
        return False
    return True


def certificate_valid(now: dt.datetime | None = None) -> bool:
    """Whether an own certificate counts and has not expired."""
    now = now or timezone.now()
    return _counted_certificate().filter(expires_at__gt=now).exists()


def sending_route(config: Config, environment: str, scope: Scope | None) -> str:
    """The route the records of ``environment`` go by (``erplora_route.route_for``)."""
    return erplora_route.route_for(config, environment, scope, certificate_valid())


def _route_sending_problem(config: Config, environment: str, scope: Scope | None) -> str:
    """What the route of ``environment`` lacks to carry a record to its AEAT: on the own route, a valid certificate
    and, in production, one this server can open; on ERPlora's in production, being open to a business not live
    through it yet and the approved signed authorisation, but for ERPlora's own records on ERPlora's own hub
    (``scope``; ``None``, no hub's, never is: a business typing ERPlora's tax ID is no exemption)."""
    production = environment == Environment.PRODUCTION
    route = sending_route(config, environment, scope)
    if route == Config.Route.OWN:
        if not certificate_valid():
            return "own_certificate_missing"
        return "own_certificate_unreadable" if production and not own_certificate_readable(route) else ""
    if not production or (
        scope is not None
        and platform.is_platform_hub(scope)
        and issuer_identity()[0] == settings.PLATFORM_ISSUER_TAX_ID
    ):
        # ERPlora's seal presents ERPlora's own records on its own hub: it represents nobody.
        return ""
    if erplora_route.closed(config, route, scope):
        return erplora_route.CLOSED
    return "" if config.representation_status == Config.Representation.APPROVED else "representation_not_approved"


def _server_problem(environment: str) -> str:
    """What this server lacks to carry anything to the AEAT of production: ERPlora's gateway, and the opening of real
    filing (``production_open``). Testing lacks nothing here (its waits are ``blockers``')."""
    if environment != Environment.PRODUCTION:
        return ""
    if not gateway.configured():
        return "gateway_unavailable"
    if not production_open():
        return "production_closed"
    return ""


def presenter(scope: Scope) -> str:
    """Who ERPlora's gateway is told presents the records of ``scope`` (its ``hub``): ``scope``'s business by its
    slug, whatever tax ID a record bears. Every business runs its pass in its own database, and ERPlora's own hub's
    (``PLATFORM_HUB_SLUG``) holds ERPlora's records alone, so it presents ERPlora's own and nobody else's."""
    return scope.key


def going_live_problem(config: Config, scope: Scope) -> str:
    """What the route of this moment lacks to take the business live (VERIFACTU-F08): to carry a record to production
    and, by the own certificate, the AEAT's test environment having accepted it. Not a route's problem: a business
    already live keeps filing with a certificate uploaded after (production never proves one)."""
    problem = _route_sending_problem(config, Environment.PRODUCTION, scope)
    if problem or config.environment == Environment.PRODUCTION:
        return problem
    if sending_route(config, Environment.PRODUCTION, scope) != Config.Route.OWN:
        return ""
    proof = own_certificate().aeat_proof
    if proof == OwnCertificate.Proof.ACCEPTED:
        return ""
    return "own_certificate_rejected" if proof == OwnCertificate.Proof.REJECTED else "own_certificate_untested"


def route_problem(config: Config, environment: str, scope: Scope | None) -> str:
    """Why nothing can be carried to the AEAT of ``environment`` now (a wait code), or ``""`` (VERIFACTU-F04, F08):
    the route's own lack first, then the server's in production (no gateway, closed). It keeps the queue waiting
    before the gateway is ever called and, in production, refuses every new sale (``verifactu.record.create``) and
    going live. No subscription plan gates it: ERPlora's route needs its approved authorisation alone."""
    return _route_sending_problem(config, environment, scope) or _server_problem(environment)


def issue_problem(config: Config, scope: Scope | None) -> str:
    """Why no new sale or invoice can be sealed now (production without a way to the AEAT), or ``""``."""
    if config.environment != Environment.PRODUCTION:
        return ""
    return route_problem(config, config.environment, scope)


def live_problems(config: Config, scope: Scope) -> list[str]:
    """Everything that keeps this business from going live now (VERIFACTU-F08), as codes; empty when it can, in
    ``go_live``'s order: the server (closed, no gateway), a demo, the route, the account. Invoicing's issuer is told
    apart. A demo never goes live; whether it is one, the platform says
    (``base.operations.is_demo_hub``). Outside Spain, that alone: nothing else would ever let it."""
    if outside_spain(scope):
        return [OUTSIDE_SPAIN]
    found = [] if production_open() else ["production_closed"]
    if not gateway.configured():
        found.append("gateway_unavailable")
    if platform.is_demo_hub(scope):
        found.append("go_live_forbidden")
    if problem := going_live_problem(config, scope):
        found.append(problem)
    if config.hub_status != Config.HubStatus.ACTIVE:
        found.append("hub_not_active")
    return found


def system_for(ctx: OperationContext) -> producer.SystemInfo:
    """``SistemaInformatico`` of this installation."""
    return producer.system_info(
        version=producer.running_version(), installation=ctx.scope.key
    )


def blockers(config: Config, environment: str, scope: Scope | None) -> list[str]:
    """What keeps every record of ``environment`` from leaving now, as wait codes; outside Spain, that alone: nothing
    else would ever let them leave."""
    if outside_spain(scope):
        return [OUTSIDE_SPAIN]
    found = []
    if not gateway.configured():
        found.append("gateway_unavailable")
    problem = route_problem(config, environment, scope)
    if not problem and not own_certificate_readable(sending_route(config, environment, scope)):
        problem = "own_certificate_unreadable"
    if problem and problem not in found:
        found.append(problem)
    if (
        environment == Environment.PRODUCTION
        and not production_open()
        and "production_closed" not in found
    ):
        found.append("production_closed")
    return found


def wait(code: str, detail: str = "", at: str = "") -> dict:
    return {"code": code, "message": wait_reason_text(code, detail, at)}


def _local_time(moment: dt.datetime) -> str:
    return timezone.localtime(moment).strftime("%H:%M:%S")


def waiting_of(record: Record, config: Config, scope: Scope | None) -> list[dict]:
    """Why ``record`` is not in the AEAT yet; empty when it is, or when the AEAT rejected it."""
    if record.status not in Record.UNSENT:
        return []
    reasons = [wait(code) for code in blockers(config, record.environment, scope)]
    control = SendControl.objects.filter(
        issuer_nif=record.issuer_nif, environment=record.environment
    ).first()
    if control and control.next_send_at and control.next_send_at > timezone.now():
        reasons.append(wait("aeat_wait", at=_local_time(control.next_send_at)))
    if record.wait_reason in ATTEMPT_FAILURES:
        reasons.append(wait(record.wait_reason, record.wait_detail))
    return reasons
