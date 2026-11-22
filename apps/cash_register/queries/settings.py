"""The drawer's settings: the business's row, the factory values until it is saved."""

from live.context import OperationContext
from live.operations import operation

from apps.cash_register.models import Settings
from apps.cash_register.schemas import EmptyIn, SettingsOut

SETTINGS_FIELDS = [
    "enable_cash_register",
    "require_opening_balance",
    "require_closing_balance",
    "allow_negative_balance",
    "require_blind_count",
    "auto_close_enabled",
]


def current_settings() -> Settings:
    """The business's row, or an unsaved one with the factory values."""
    return Settings.objects.first() or Settings()


def settings_row(settings: Settings) -> dict:
    row = {field: getattr(settings, field) for field in SETTINGS_FIELDS}
    row["auto_close_time"] = f"{settings.auto_close_time:%H:%M}"
    row["updated_at"] = None if settings._state.adding else settings.updated_at
    return row


@operation(
    "cash_register.settings.get",
    kind="query",
    permission="cash_register.view_session",
    input=EmptyIn,
    output=SettingsOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "is the blind count on in the till?",
                "what time does the till close by itself?",
                "show me the till settings",
            ),
            "es": (
                "¿tenemos puesto el arqueo ciego en los ajustes?",
                "¿a qué hora se cierra sola la caja?",
                "enséñame los ajustes de caja",
            ),
        },
        "description": "Read how the drawer works: cash register on, opening float required, count required to close, "
        "negative balance allowed, blind count, and the daily auto-close with its hour (the factory values until saved)."
    },
)
def get_settings(ctx: OperationContext, params: EmptyIn) -> dict:
    return settings_row(current_settings())
