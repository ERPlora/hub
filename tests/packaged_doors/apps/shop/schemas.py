"""What the operations of the made-up shop take and give."""

from ninja import Schema


class ItemIn(Schema):
    name: str


class ItemOut(Schema):
    name: str


class ItemsOut(Schema):
    names: list[str]
