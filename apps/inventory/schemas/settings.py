"""Schemas of the inventory settings."""

from ninja import Field, Schema


class ConfigGetIn(Schema):
    pass


class ConfigPatchIn(Schema):
    allow_sell_without_stock: bool | None = Field(
        None,
        description="True: a sale lowers the stock even below zero. False: an article that does not reach is not lowered.",
    )
    low_stock_threshold: int | None = Field(
        None,
        ge=0,
        le=1_000_000,
        description="Whole units: the threshold of a product created without its own.",
    )
    track_stock: bool | None = Field(
        None, description="Whether articles that did not decide track their stock."
    )


class ConfigOut(Schema):
    allow_sell_without_stock: bool = Field(
        description="Whether a sale lowers the stock below zero."
    )
    low_stock_threshold: int = Field(
        description="Default threshold of a new product, in whole units."
    )
    track_stock: bool = Field(
        description="Whether articles that did not decide track their stock."
    )
