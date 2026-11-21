"""The business's inventory settings (``inventory.config.get``), the factory ones until they are saved."""

from live.context import OperationContext
from live.operations import operation

from apps.inventory.models import Settings
from apps.inventory.schemas import ConfigGetIn, ConfigOut


def current_settings() -> Settings:
    """The business's settings; the factory ones (unsaved) if they were never saved."""
    return Settings.objects.first() or Settings()


@operation(
    "inventory.config.get",
    kind="query",
    permission="inventory.manage_settings",
    input=ConfigGetIn,
    output=ConfigOut,
    expose_api=True,
    ai={
        "description": "Get the inventory settings: selling without stock, the default low-stock threshold and stock tracking.",
        "asks": {
            "en": (
                "how is my inventory set up?",
                "can I sell without stock right now?",
                "what is the low stock threshold?",
            ),
            "es": (
                "¿cómo tengo configurado el inventario?",
                "¿ahora puedo vender sin stock?",
                "¿cuál es el aviso de stock bajo?",
            ),
        },
    },
)
def get_config(ctx: OperationContext, data: ConfigGetIn) -> dict:
    return config_row(current_settings())


def config_row(settings: Settings) -> dict:
    return {
        "allow_sell_without_stock": settings.allow_sell_without_stock,
        "low_stock_threshold": settings.low_stock_threshold,
        "track_stock": settings.track_stock,
    }
