"""The booking page's logo: a JPG, PNG or WebP the owner uploads in Settings (``online_booking.settings.upload_logo``)
and saves with the page's other settings. It is kept as every image a business shows to anyone
(``base.public_images``), in this app's public folder :data:`FOLDER`, which ``base.media`` serves from the business's
own address: the only origin the page's Content Security Policy loads images from. The settings keep the file's name;
an address of somewhere else is no logo."""

import re
from typing import Annotated

from django.utils.translation import gettext_lazy as _
from live.context import Scope
from ninja import Field, Schema
from pydantic import AfterValidator, StringConstraints

from base.operations import hub_id
from base.storage import media_url

#: Under the business's prefix of the hub file store; ``public_media`` of the app's config.
FOLDER = "online_booking/logo/"
#: The name ``base.public_images`` gives a file: the first 16 hex of its sha256 and its type's extension.
_NAME = re.compile(r"^[0-9a-f]{16}\.(jpg|png|webp)$")

NOT_AN_UPLOAD = _("That logo was not uploaded to this business: upload it again.")


def _a_name(value: str) -> str:
    if value and not _NAME.match(value):
        raise ValueError(str(NOT_AN_UPLOAD))
    return value


#: What the settings take as their logo: the name an upload answered, or empty for none.
LogoName = Annotated[str, StringConstraints(strip_whitespace=True, max_length=32), AfterValidator(_a_name)]


def logo_url(scope: Scope, name: str) -> str:
    """Where ``scope``'s business serves its logo ``name``, from its own address; empty without one."""
    return media_url(hub_id(scope), f"{FOLDER}{name}") if name else ""


class LogoOut(Schema):
    id: str = Field(description="The uploaded logo, to save as the settings' logo.")
    url: str = Field(description="Where the business's own address serves it.")


class LogoFieldsOut(Schema):
    logo: str = Field(description="The uploaded logo the page shows; empty = none.")
    logo_url: str = Field(description="Where the business's own address serves the logo; empty = none.")

    @classmethod
    def logo_of(cls, scope: Scope, name: str) -> dict:
        return {"logo": name, "logo_url": logo_url(scope, name)}
