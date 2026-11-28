"""The cash register's settings: what they say and what a change of them sends."""

from datetime import datetime

from ninja import Field, Schema

from apps.cash_register.schemas.fields import Closed, WholeHour

class SettingsFields(Schema):
    enable_cash_register: bool = Field(
        description="The cash register is on: Sales asks for an open session before charging in cash."
    )
    require_opening_balance: bool = Field(
        description="A session cannot open without an opening float above zero."
    )
    require_closing_balance: bool = Field(
        description="A session cannot close without the counted cash."
    )
    allow_negative_balance: bool = Field(
        description="A cash-out may leave the expected cash below zero."
    )
    require_blind_count: bool = Field(
        description="Blind count: whoever counts does not see the expected cash of an open session, unless allowed."
    )
    auto_close_enabled: bool = Field(
        description="A session still open at the cut-off hour closes by itself."
    )
    auto_close_time: WholeHour = Field(
        description="The cut-off hour of the daily auto-close, business time, «04:00»."
    )


class SettingsOut(SettingsFields):
    updated_at: datetime | None = Field(
        description="When they were last saved; empty = the factory values."
    )


class SettingsPatchIn(Closed):
    enable_cash_register: bool | None = Field(
        None, description="The cash register is on."
    )
    require_opening_balance: bool | None = Field(
        None, description="Require an opening float."
    )
    require_closing_balance: bool | None = Field(
        None, description="Require the counted cash to close."
    )
    allow_negative_balance: bool | None = Field(
        None, description="Allow a cash-out to leave the drawer below zero."
    )
    require_blind_count: bool | None = Field(None, description="Blind count.")
    auto_close_enabled: bool | None = Field(None, description="Daily auto-close.")
    auto_close_time: WholeHour | None = Field(
        None, description="The cut-off hour, «00:00» to «23:00»."
    )
