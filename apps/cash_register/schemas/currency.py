"""The business's currency, as a count of the drawer reads it: its decimals, its notes and its coins."""

from ninja import Field, Schema

class CurrencyOut(Schema):
    currency: str = Field(description="The business's currency, ISO 4217.")
    decimals: int = Field(description="Its decimals: 2 in EUR, 0 in JPY, 3 in KWD.")
    bills: list[str] = Field(
        description="Its notes, largest first (face value in major units); empty = no table."
    )
    coins: list[str] = Field(description="Its coins, largest first; empty = no table.")
