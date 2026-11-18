"""Schemas of the person's profile, preferences and avatar (``base.profile.*``)."""

from typing import Literal

from ninja import Schema
from pydantic import Field


class ProfileIn(Schema):
    """No input: the profile is always the person's who asks."""


class ProfileOut(Schema):
    first_name: str
    last_name: str
    contact_email: str
    avatar_url: str = Field(description="Where this hub serves the photo; empty without one.")
    language: Literal["", "es", "en"] = Field(description="Empty: the business's.")
    theme_mode: Literal["", "system", "light", "dark"] = Field(description="Empty: the business's.")
    palette: str = Field(description="Empty: the business's.")
    ui_scale: int
    role: str
    has_pin: bool
    pin_length: int


class ProfileUpdateIn(Schema):
    first_name: str = Field(max_length=150)
    last_name: str = Field(default="", max_length=150)
    contact_email: str = Field(default="", max_length=254)


class PreferencesIn(Schema):
    language: Literal["", "es", "en"]
    theme_mode: Literal["", "system", "light", "dark"]
    palette: Literal["", "erplora", "terracotta", "corporate", "minimal", "forest", "ocean", "violet"]
    ui_scale: Literal[80, 90, 100, 110, 120]


class PreferencesOut(Schema):
    language: str = Field(description="The language now in use: the person's, else the business's.")
    theme_mode: str
    palette: str
    ui_scale: int


class AvatarIn(Schema):
    content_type: Literal["image/jpeg", "image/png", "image/webp"]
    # 2 MB of bytes is 2 796 204 characters of base64.
    data_base64: str = Field(max_length=2_800_000, description="The photo, in base64 (2 MB at most).")


class AvatarOut(Schema):
    avatar_url: str


class AvatarRemoveIn(Schema):
    """No input: one's own photo."""

