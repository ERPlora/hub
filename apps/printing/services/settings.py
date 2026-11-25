"""How the business prints (PRINTING-F06): the settings row, field by field, and the printer of each function."""


from django.db import IntegrityError
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import InvalidPayload, NotFound
from live.operations import atomic, operation
from live.outbox import record_event

from apps.printing import events
from apps.printing.models import Printer, Settings
from apps.printing.queries.jobs import actor
from apps.printing.queries.printers import find_printer
from apps.printing.queries.settings import DEFAULT_FIELDS, settings_row
from apps.printing.schemas import SettingsOut, SettingsPatchIn

NOT_ITS_FUNCTION = _("That printer does not have this role.")
DEFAULT_INACTIVE = _("That printer is inactive.")


def _locked_settings(ctx: OperationContext) -> Settings:
    """The business's settings row, locked; created with the factory values the first time."""
    settings = Settings.objects.select_for_update().first()
    if settings is not None:
        return settings
    try:
        with atomic():
            return Settings.objects.create(updated_by=actor(ctx))
    except IntegrityError:
        return Settings.objects.select_for_update().get()


def _chosen_printer(field: str, ref: str | None, usage: str) -> Printer | None:
    """The printer chosen for ``usage`` (by id or name): one of its own and active; ``None`` clears it. It is
    held until the settings that name it are saved: a deletion waits for them."""
    if ref is None:
        return None
    try:
        printer = find_printer(None, ref, hold=True)
    except NotFound as missing:  # said at the field the person filled
        raise InvalidPayload(missing.message, fields={field: missing.message}) from None
    if printer.usage != usage:
        raise InvalidPayload(str(NOT_ITS_FUNCTION), fields={field: str(NOT_ITS_FUNCTION)})
    if not printer.is_active:
        raise InvalidPayload(str(DEFAULT_INACTIVE), fields={field: str(DEFAULT_INACTIVE)})
    return printer


@operation(
    "printing.settings.update",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="printing.manage_settings",
    input=SettingsPatchIn,
    output=SettingsOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "print the receipt by itself when I charge",
                "send the kitchen orders to Kitchen 2",
                "print two copies of every receipt",
            ),
            "es": (
                "que el ticket se imprima solo al cobrar",
                "manda los pedidos de cocina a la impresora Cocina 2",
                "imprime dos copias de cada ticket",
                "que se abra el cajón al cobrar",
            ),
        },
        "description": "Change how the business prints, field by field: print the receipt by itself at checkout, open the "
        "drawer with it, receipt copies (1 to 3), and the printer of each function by its name («the kitchen orders go "
        "to Kitchen 2»; null = the first active one of that function). What is not sent is kept.",
        "risk": "normal",
    },
)
def update_settings(ctx: OperationContext, data: SettingsPatchIn) -> dict:
    settings = _locked_settings(ctx)
    sent = data.model_dump(exclude_unset=True)
    values: dict = {}
    for field, value in sent.items():
        usage = next((u for u, f in DEFAULT_FIELDS.items() if f == field), None)
        if usage is not None:
            values[field] = _chosen_printer(field, value, usage)
        elif value is not None:
            values[field] = value
    changes = {field: value for field, value in values.items() if getattr(settings, field) != value}
    if changes:
        for field, value in changes.items():
            setattr(settings, field, value)
        settings.updated_by = actor(ctx)
        settings.save(update_fields=[*changes, "updated_by", "updated_at"])
        record_event(ctx, events.SETTINGS_UPDATED, {"fields": sorted(changes)})
    return settings_row(settings)
