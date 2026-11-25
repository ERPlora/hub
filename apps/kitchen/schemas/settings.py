"""The kitchen's settings: the card's clock and colours, the sound, the paper, whether the kitchen works
from the screen, and the type a ticket made by hand starts with."""

from ninja import Field, Schema

from apps.kitchen.schemas.fields import In, Minutes, OrderType, SoundTone, Volume


class SettingsOut(Schema):
    show_timer: bool = Field(description="The card shows its clock.")
    warning_minutes: int = Field(
        description="The card turns amber after these minutes."
    )
    critical_minutes: int = Field(description="The card turns red after these minutes.")
    color_coding: bool = Field(
        description="The card's border follows the clock (green, amber, red)."
    )
    sound_enabled: bool = Field(
        description="The display rings when a ticket arrives or is rushed."
    )
    sound_volume: int = Field(description="Volume, 0 to 100.")
    sound_tone: SoundTone = Field(description="chime, bell or buzzer.")
    print_pass: bool = Field(description="Prints the pass when a ticket is ready.")
    works_from_screen: bool = Field(
        description="False: the kitchen cooks from paper and charging serves the rounds."
    )
    default_order_type: OrderType = Field(
        description="The type a ticket made by hand starts with."
    )
    timezone: str = Field(
        description="The business's time zone (dates of the History, the ticket's day)."
    )


class SettingsPatchIn(In):
    show_timer: bool | None = Field(None, description="The card shows its clock.")
    warning_minutes: Minutes | None = Field(
        None, description="Amber after these minutes (1 to 120)."
    )
    critical_minutes: Minutes | None = Field(
        None, description="Red after these minutes (1 to 120), after the amber."
    )
    color_coding: bool | None = Field(
        None, description="The card's border follows the clock."
    )
    sound_enabled: bool | None = Field(
        None, description="Ring when a ticket arrives or is rushed."
    )
    sound_volume: Volume | None = Field(None, description="Volume, 0 to 100.")
    sound_tone: SoundTone | None = Field(None, description="chime, bell or buzzer.")
    print_pass: bool | None = Field(
        None, description="Print the pass when a ticket is ready."
    )
    works_from_screen: bool | None = Field(
        None, description="False if nobody marks anything on the screen."
    )
    default_order_type: OrderType | None = Field(
        None, description="The type a ticket made by hand starts with."
    )
