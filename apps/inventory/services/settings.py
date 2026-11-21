"""The business's inventory settings (INVENTORY-F19)."""

from django.db import IntegrityError
from live.context import OperationContext
from live.operations import atomic, operation
from live.outbox import record_event

from apps.inventory import events
from apps.inventory.models import Settings
from apps.inventory.queries.settings import config_row
from apps.inventory.schemas import ConfigOut, ConfigPatchIn
from apps.inventory.services.writes import _actor


@operation(
    "inventory.config.update",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="inventory.manage_settings",
    input=ConfigPatchIn,
    output=ConfigOut,
    expose_api=True,
    ai={
        "description": "Change the inventory settings: allow selling without stock, the default low-stock "
        "threshold and whether stock is tracked (an article's own decision wins).",
        "risk": "normal",
        "asks": {
            "en": (
                "let me sell products even with no stock",
                "change the default low stock threshold to 5",
                "stop tracking stock",
            ),
            "es": (
                "deja vender productos aunque no haya stock",
                "pon el aviso de stock bajo en 5 por defecto",
                "no quiero controlar el stock",
            ),
        },
    },
)
def update_config(ctx: OperationContext, data: ConfigPatchIn) -> dict:
    """One row per business; changing the threshold does not touch the products that exist."""
    settings = _locked_settings(ctx)
    sent = data.model_dump(exclude_unset=True, exclude_none=True)
    changes = {field: value for field, value in sent.items() if getattr(settings, field) != value}
    if changes:
        for field, value in changes.items():
            setattr(settings, field, value)
        settings.updated_by = _actor(ctx)
        settings.save(update_fields=[*changes, "updated_by", "updated_at"])
        record_event(ctx, events.CONFIG_UPDATED, {})
    return config_row(settings)


def _locked_settings(ctx: OperationContext) -> Settings:
    """The business's settings row, locked; created with the factory values the first time.

    Two first saves at once: the second waits on the single-row constraint and then locks the first's.
    """
    settings = Settings.objects.select_for_update().first()
    if settings is not None:
        return settings
    try:
        with atomic():
            return Settings.objects.create(updated_by=_actor(ctx))
    except IntegrityError:
        return Settings.objects.select_for_update().get()
