"""ERPlora's own hub in the registry: its row, its name, and what nobody does to it (``manage.py create_platform_hub``)."""

from django.conf import settings
from django.utils.translation import gettext
from live.context import OperationContext
from live.errors import Conflict, NotFound
from live.operations import INTERNAL, operation
from live.outbox import record_event

from base import events
from base.models import Hub
from base.registry import hub_answer, internal_only
from base.schemas.hub_registry import HubGetIn, HubOut, HubStateIn
from base.services.address_change import address_changed


def platform_rows() -> list[Hub]:
    """The registry's rows that are ERPlora's own hub, their cluster with them, whatever their name: one, or none."""
    return list(Hub.objects.select_related("cluster").filter(is_platform=True).order_by("created_at"))


# Not an assistant tool: manage.py create_platform_hub's step, no person.
@operation(
    "base.hub.platform_rename", kind="command", permission=None, input=HubGetIn, output=HubOut, ai=INTERNAL
)
def platform_hub_rename(ctx: OperationContext, data: HubGetIn) -> dict:
    """ERPlora's own hub ``data.id`` under the name it goes by, ``PLATFORM_HUB_SLUG``, as a business's address changes:
    its id and its database stay, and what is kept under the name it leaves goes with it."""
    internal_only(ctx)
    hub = Hub.objects.select_for_update().filter(pk=data.id, is_platform=True).first()
    if hub is None:
        raise NotFound(gettext("No hub has this id."))
    former, hub.slug = hub.slug, settings.PLATFORM_HUB_SLUG
    hub.save(update_fields=["slug", "updated_at"])
    address_changed(hub, former)
    record_event(ctx, events.HUB_REGISTERED, {"id": str(hub.id), "slug": hub.slug, "created": False})
    return hub_answer(hub)


def people_only(data: HubStateIn) -> HubStateIn:
    """erplora.com's photo of ERPlora's own hub with nothing but its people and its version: that hub has no plan nor
    anything to pay there, so nothing else of a photo is kept or applied, whatever it says."""
    kept = {"members": data.photo["members"]} if "members" in data.photo else {}
    return HubStateIn(id=data.id, version=data.version, members=data.members, photo=kept)


def refuse_platform_hub(hub: Hub) -> None:
    """``Conflict`` for ERPlora's own hub: erplora.com never registers, closes nor restores it, and nobody empties it."""
    if hub.is_platform:
        raise Conflict(
            gettext("ERPlora's own business is never changed, closed or emptied here."), code="base.platform_hub_kept"
        )
