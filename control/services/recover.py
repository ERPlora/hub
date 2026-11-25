"""Bringing back into a business what one of its separate copies holds and the business lacks."""

from django.utils.translation import gettext
from live.context import OperationContext
from live.errors import Conflict, InvalidPayload, NotFound
from live.operations import INTERNAL, operation
from live.outbox import record_event

from control import events
from control.models.copies import CopyRecovery, RestoredCopy
from control.schemas import CopyRecoverIn, CopyRecoveryOut
from control.services.actor import _who, platform_admin_only


# Not an assistant tool: the platform's admins, in the Hub admin.
@operation(
    "control.copy.recover",
    kind="command",
    permission=None,
    input=CopyRecoverIn,
    output=CopyRecoveryOut,
    ai=INTERNAL,
)
def copy_recover(ctx: OperationContext, data: CopyRecoverIn) -> dict:
    """Ask the worker to bring back into its business what the separate copy ``data.copy_id`` holds and the business
    lacks, of the apps ``data.apps`` (``base.tenancy.recovery``): each record created by its app's own
    operation, in the staff member's language. Only from a made copy, of apps that say what they give back from one,
    and one recovery of a copy at a time; the business is not touched by the ask."""
    # Imported here: base.tenancy.recovery runs on control.services (its worker's side, ``worker_recovery``).
    from base.tenancy.recovery import recoverable_apps

    platform_admin_only(ctx)
    copy = RestoredCopy.objects.select_related("hub").filter(pk=data.copy_id).first()
    if copy is None:
        raise NotFound(gettext("This separate copy does not exist."))
    if copy.status != RestoredCopy.Status.MADE:
        raise Conflict(gettext("Only a separate copy that is made gives anything back."), code="control.copy_not_made")
    recoverable, apps = recoverable_apps(), list(dict.fromkeys(data.apps))
    unknown = [label for label in apps if label not in recoverable]
    if unknown:
        message = gettext("These apps give nothing back from a separate copy: %(apps)s.") % {"apps": ", ".join(unknown)}
        raise InvalidPayload(message, code="control.copy_app_not_recoverable", fields={"apps": message})
    if CopyRecovery.objects.filter(copy=copy, status=CopyRecovery.Status.ASKED).exists():
        raise Conflict(
            gettext("This separate copy is already giving something back: wait until it is done."),
            code="control.copy_recovery_pending",
        )
    recovery = CopyRecovery.objects.create(copy=copy, apps=apps, language=ctx.language or "en", asked_by=_who(ctx))
    record_event(
        ctx,
        events.COPY_RECOVERY_REQUESTED,
        {"id": str(recovery.pk), "copy": str(copy.pk), "hub": str(copy.hub_id), "slug": copy.hub.slug, "apps": apps},
    )
    return {
        "id": recovery.pk,
        "copy_id": copy.pk,
        "hub": copy.hub_id,
        "slug": copy.hub.slug,
        "apps": apps,
        "status": recovery.status,
    }
