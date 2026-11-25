"""The printing settings: what is printed by itself at checkout and the printer chosen for each function."""

from live.context import OperationContext
from live.operations import operation

from apps.printing.models import Settings, Usage
from apps.printing.schemas import EmptyIn, SettingsOut

#: The functions, in the order the screens and the summary show them.
USAGES = [usage.value for usage in Usage]
#: The settings' field of each function's printer.
DEFAULT_FIELDS = {usage: f"{usage}_printer" for usage in USAGES}


def current_settings() -> Settings:
    """The business's settings, or the factory ones (unsaved) when it never saved them. The printer chosen
    for each function comes in the same read: one deleted meanwhile is either still there or already
    cleared, never one left to load that is gone."""
    return Settings.objects.select_related(*DEFAULT_FIELDS.values()).first() or Settings()


def settings_row(settings: Settings) -> dict:
    return {
        "print_receipt_on_sale": settings.print_receipt_on_sale,
        "open_drawer_on_sale": settings.open_drawer_on_sale,
        "receipt_copies": settings.receipt_copies,
        **{f"{field}_id": getattr(settings, f"{field}_id") for field in DEFAULT_FIELDS.values()},
        # The factory values are an unsaved row: they were never saved.
        "updated_at": None if settings._state.adding else settings.updated_at,
    }


@operation(
    "printing.settings.get",
    kind="query",
    permission="printing.view_settings",
    input=EmptyIn,
    output=SettingsOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "is the receipt printed automatically at checkout?",
                "which printer prints the kitchen orders?",
                "how is printing set up?",
            ),
            "es": (
                "¿está activada la impresión automática del ticket?",
                "¿qué impresora tengo elegida para la cocina?",
                "¿cómo tengo configurada la impresión?",
            ),
        },
        "description": "Get the printing settings: whether the receipt prints and the drawer opens by itself at checkout, "
        "the receipt copies and the printer chosen for each function (receipts, kitchen, bar, labels). The receipt's "
        "header and footer are not here: they are Sales' settings."
    },
)
def get_settings(ctx: OperationContext, data: EmptyIn) -> dict:
    return settings_row(current_settings())
