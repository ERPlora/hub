"""``manage.py create_platform_hub [--execute]``: bring up ERPlora's own hub, repeatably (PLAN-SAAS §4).

ERPlora's platform hub issues ERPlora's invoices to its customers, posted by the SaaS to
``/internal/platform/invoices`` (``base.internal``). Ported from the old SaaS's ``ensure_platform_hub``: idempotent and a
dry run unless ``--execute``; it names what it finds, and it refuses rather than guesses, because one hub is one
issuer is one VeriFactu chain: it never writes over another identity.

The platform hub is its reserved slug, ``PLATFORM_HUB_SLUG`` (``erplora``, in ``live.slugs``' reserved list, so no
business can ever take it and the SaaS's normal sign-up never creates it), and since S5 a row of the registry
(``is_platform``) with a database of its own, as every business: with ``--execute``, a missing one is made as a sign-up
is (``base.services.platform_hub_register``, then ``base.tenancy.provision``), never as a business of the SaaS's.
Then, inside that database, it gives the hub its issuer, ERPlora's tax identity from ``PLATFORM_ISSUER_*``
(``invoice.issuer.update``), and pins VeriFactu to the deployment's environment (``verifactu.config.follow_deployment``;
prod: production, pre: testing), always through their operations, as the system on that slug. Invoicing and
VeriFactu are always active on it.

In AWS it runs once per environment as a one-off ECS task of the ``hub-migrate`` task definition, which has the
migrator's credentials to make the database (WORKBOOK of invoice; runbook ``docs/runbooks/cut-shared-hubs.md``).
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from live.context import Scope, system_context
from live.errors import OperationError
from live.operations import get as get_operation

from base import services
from base.tenancy import provision
from base.tenancy.context import use_control, use_hub

ISSUER_SETTINGS = {
    "legal_name": "PLATFORM_ISSUER_LEGAL_NAME",
    "tax_id": "PLATFORM_ISSUER_TAX_ID",
    "address": "PLATFORM_ISSUER_ADDRESS",
    "postal_code": "PLATFORM_ISSUER_POSTAL_CODE",
    "city": "PLATFORM_ISSUER_CITY",
    "province": "PLATFORM_ISSUER_PROVINCE",
    "country": "PLATFORM_ISSUER_COUNTRY",
}
REQUIRED = ("legal_name", "tax_id", "address")


class Command(BaseCommand):
    help = (
        "Bring up ERPlora's own hub (its issuer and VeriFactu's environment). Idempotent; a dry run unless "
        "--execute is given."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--execute",
            action="store_true",
            help="Write. Without it the command only says what it would do.",
        )

    def handle(self, *args, execute: bool = False, **options):
        slug = settings.PLATFORM_HUB_SLUG
        with use_control():
            hub = services.registry_row_by_slug(slug)
        if hub is not None and not hub.is_platform:
            raise CommandError(f"The row {slug} of the registry is no platform hub's: nothing was written.")
        if hub is None or hub.status != hub.Status.READY:
            if not execute:
                self.stdout.write(f"ERPlora's own hub: {slug} ({settings.ERPLORA_ENVIRONMENT})")
                self.stdout.write("Dry run: nothing is written without --execute.")
                self.stdout.write("- would make its registry row and its own database, then set its issuer")
                return None
            hub = self._made(slug)
        self.stdout.write(f"- the platform hub works on its own database {hub.db_name}")
        with use_hub(hub):
            return self._handle(*args, execute=execute, **options)

    def _made(self, slug: str):
        """Its row (``is_platform``) and its own database, made now as a sign-up's (the SaaS is not told)."""
        with use_control():
            hub = services.platform_hub_register(slug)
        if hub.status != hub.Status.READY and not provision.provision(hub, tell_saas=False):
            with use_control():
                found = services.registry_row(hub.id)
            raise CommandError(
                f"The platform hub's database could not be made ({found.status}: {found.last_error or '-'}); run it "
                "again. Nothing else was written."
            )
        with use_control():
            return services.registry_row(hub.id)

    def _handle(self, *args, execute: bool = False, **options):
        ctx = system_context(Scope("host", settings.PLATFORM_HUB_SLUG))
        wanted = {
            field: str(getattr(settings, name, "")).strip()
            for field, name in ISSUER_SETTINGS.items()
        }
        missing = [ISSUER_SETTINGS[field] for field in REQUIRED if not wanted[field]]
        if missing:
            raise CommandError(
                f"Set {', '.join(missing)}: the platform hub's issuer. Nothing was written."
            )
        # What ``verifactu.config.follow_deployment`` pins on a new hub (``queries.production_open``): production only
        # on the prod deployment once ERPlora opens real filing there (working-rules §15).
        environment = (
            "production"
            if settings.ERPLORA_ENVIRONMENT == "prod"
            and settings.VERIFACTU_PRODUCTION_ENABLED
            else "testing"
        )
        self.stdout.write(
            f"ERPlora's own hub: {settings.PLATFORM_HUB_SLUG} ({settings.ERPLORA_ENVIRONMENT})"
        )
        if not execute:
            self.stdout.write("Dry run: nothing is written without --execute.")
        current = self._call(ctx, "invoice.issuer.get", {})
        if current.configured and current.tax_id != wanted["tax_id"]:
            raise CommandError(
                f"The database already has another issuer, {current.legal_name} ({current.tax_id}): one issuer is "
                "one VeriFactu chain, so it is never overwritten. Nothing was written."
            )
        if current.configured:
            self.stdout.write(
                f"- issuer found: {current.legal_name} ({current.tax_id})"
            )
        elif execute:
            self._call(ctx, "invoice.issuer.update", wanted)
            self.stdout.write(
                f"- issuer set: {wanted['legal_name']} ({wanted['tax_id']})"
            )
        else:
            self.stdout.write(
                f"- would set the issuer {wanted['legal_name']} ({wanted['tax_id']})"
            )
        if execute:
            config = self._call(ctx, "verifactu.config.follow_deployment", {})
            self.stdout.write(
                f"- VeriFactu files in {config.environment}, route {config.route}"
            )
            health = self._call(ctx, "invoice.invoice.platform_health", {})
            if health.ready:
                self.stdout.write(
                    self.style.SUCCESS("- ready to issue ERPlora's invoices")
                )
            else:
                self.stdout.write(self.style.WARNING(f"- not ready: {health.detail}"))
        else:
            self.stdout.write(f"- would pin VeriFactu to {environment}")
        self.stdout.write("- Invoicing and VeriFactu: always active on it")
        if settings.ERPLORA_ENVIRONMENT == "prod":
            self.stdout.write(self.style.MIGRATE_HEADING("Before a single real record"))
            self.stdout.write(
                "  - VeriFactu files in production only with VERIFACTU_PRODUCTION_ENABLED=true, under Ioan's "
                "supervision;"
            )
            self.stdout.write(
                "  - the SaaS posts invoices only with PLATFORM_INVOICING_ENABLED=true;"
            )
            self.stdout.write(
                "  - its gateway presents with ERPlora's seal (FISCAL_SEAL_CURRENT_*), under Ioan's supervision."
            )

    def _call(self, ctx, name: str, payload: dict):
        op = get_operation(name)
        try:
            return op(ctx, op.input.model_validate(payload))
        except OperationError as refused:
            raise CommandError(
                f"{name}: {refused.message} ({refused.code}). Nothing more was written."
            ) from None
