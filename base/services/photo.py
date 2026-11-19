"""The SaaS's photo of a business applied in its own database: its people and the blocks of the apps it has on."""

import logging
from collections.abc import Iterable

import pydantic
from live.context import Scope, system_context
from live.errors import InvalidPayload
from live.operations import get as get_operation

from base.apps_on import active_apps
from base.models import Hub
from base.schemas.hub_registry import HubStateIn
from base.schemas.sessions import HubUserSyncIn
from base.services.sessions import hub_user_sync

logger = logging.getLogger(__name__)


#: The app whose block (and the business's status) travels in the photo (``verifactu``).
VERIFACTU_APP = "verifactu"


def _sync_verifactu(hub: Hub, data: HubStateIn) -> None:
    from base.tenancy.context import use_hub

    sync = get_operation("verifactu.config.sync")
    try:
        payload = sync.input.model_validate(
            {**(data.verifactu or {}), "version": data.version, "hub_status": data.status, "hub_id": hub.id}
        )
    except pydantic.ValidationError as invalid:
        raise InvalidPayload(
            f"The verifactu block is out of contract: {invalid}", code="internal.payload_invalid"
        ) from None
    # The hub's own operation, in its database.
    # Off in the business (base.activation), its block waits: turning VeriFactu on applies the photo kept then.
    scope = Scope("host", hub.slug)
    with use_hub(hub):
        if VERIFACTU_APP in active_apps(scope):
            sync(system_context(scope), payload)


#: The app whose number's state travels in the photo (``whatsapp``) and whose doors erplora.com calls.
WHATSAPP_APP = "whatsapp_inbox"


def _sync_whatsapp(hub: Hub, data: HubStateIn) -> None:
    from base.tenancy.context import use_hub

    scope = Scope("host", hub.slug)
    # Which apps are on is the business's (its database): asked inside it. Off, the block is not read: it waits for
    # the app (turning it on applies the photo kept then).
    with use_hub(hub):
        if WHATSAPP_APP not in active_apps(scope):
            return
        sync = get_operation("whatsapp_inbox.channel.sync")
        try:
            payload = sync.input.model_validate({**data.whatsapp, "version": data.version})
        except pydantic.ValidationError as invalid:
            raise InvalidPayload(
                f"The whatsapp block is out of contract: {invalid}", code="internal.payload_invalid"
            ) from None
        sync(system_context(scope), payload)


def _sync_photo_blocks(hub: Hub, labels: Iterable[str]) -> None:
    """Apply the blocks of the SaaS's last photo kept (``Hub.state``) that belong to ``labels``, just turned on: what
    came while they were off waited for them. Each sync ignores a version it already has."""
    photo = hub.state if isinstance(hub.state, dict) else {}
    if not photo or not hub.state_version:
        return
    labels = set(labels)
    data = HubStateIn.model_validate(
        {
            "id": hub.id,
            "version": hub.state_version,
            "status": photo.get("status"),
            "verifactu": photo.get("verifactu"),
            "whatsapp": photo.get("whatsapp"),
            "photo": photo,
        }
    )
    syncs = [
        (VERIFACTU_APP, _sync_verifactu, data.verifactu is not None or data.status is not None),
        (WHATSAPP_APP, _sync_whatsapp, data.whatsapp is not None),
    ]
    for label, sync, carried in syncs:
        if label not in labels or not carried:
            continue
        try:
            # Refused before it writes anything (its block is read first); a sync that writes is an operation, whose
            # own transaction is undone if it fails.
            sync(hub, data)
        except InvalidPayload as refused:
            # The block the photo kept is one the app refuses: it waits for the next photo; the app is on all the same.
            logger.warning("base.app.photo_block_refused %s of hub %s: %s", label, hub.slug, refused.message)


def apply_kept_photo(hub: Hub) -> None:
    """Inside ``use_hub(hub)``: apply the SaaS's photo kept on its row (its seeding: the photo came while its database
    was being made): its people (``base.hub_user.sync``, which leaves out whoever it no longer lists) and the blocks
    that belong to the apps it has on."""
    photo = hub.state if isinstance(hub.state, dict) else {}
    if hub.state_version and photo.get("members") is not None:
        hub_user_sync(
            system_context(Scope("host", hub.slug)), HubUserSyncIn(members=photo["members"], left=[])
        )
    _sync_photo_blocks(hub, active_apps(Scope("host", hub.slug)))
