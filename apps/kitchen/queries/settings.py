"""The kitchen's settings as the display reads them (KITCHEN-F26)."""

from live.context import OperationContext
from live.operations import operation

from apps.kitchen.queries.reads import current_settings, settings_out
from apps.kitchen.schemas.fields import NoIn
from apps.kitchen.schemas.settings import SettingsOut


@operation(
    "kitchen.settings.get",
    kind="query",
    permission="kitchen.view_ticket",
    input=NoIn,
    output=SettingsOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "after how many minutes does the display go amber?",
                "is the display's sound on?",
            ),
            "es": (
                "¿a los cuántos minutos se pone en rojo la pantalla?",
                "¿suena la pantalla cuando entra algo?",
            ),
        },
        "description": "The kitchen display settings: the clock, the amber and red minutes, the sound, the pass on "
        "paper, whether the kitchen works from the screen and the default ticket type."
    },
)
def get_settings(ctx: OperationContext, params: NoIn) -> dict:
    return settings_out(current_settings())
