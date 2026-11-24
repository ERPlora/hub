"""ERPlora's own hub in the registry: its row, its name, and what nobody does to it (``manage.py create_platform_hub``)."""

from uuid import UUID

from django.utils.translation import gettext
from live.errors import Conflict

from base.models import Hub
from base.services.provisioning import _control_transaction


def platform_rows() -> list[Hub]:
    """The registry's rows that are ERPlora's own hub, their cluster with them, whatever their name: one, or none."""
    return list(Hub.objects.select_related("cluster").filter(is_platform=True).order_by("created_at"))


def platform_hub_renamed(hub_id: UUID, slug: str) -> Hub:
    """ERPlora's own hub under the name ``slug``: its row's name alone, so its id, its database and what it keeps stay
    as they are. Any other row is never found; a name another row bears is refused by the registry."""
    with _control_transaction():
        hub = Hub.objects.select_for_update(of=("self",)).select_related("cluster").get(pk=hub_id, is_platform=True)
        hub.slug = slug
        hub.save(update_fields=["slug", "updated_at"])
    return hub


def refuse_platform_hub(hub: Hub) -> None:
    """``Conflict`` for ERPlora's own hub: erplora.com never registers nor closes it, and nobody empties it."""
    if hub.is_platform:
        raise Conflict(
            gettext("ERPlora's own business is never changed, closed or emptied here."), code="base.platform_hub_kept"
        )
