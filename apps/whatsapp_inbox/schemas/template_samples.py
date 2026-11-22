"""Schemas of the file of a template's photo, video or document header."""

from typing import Literal
from uuid import UUID

from django.utils.translation import gettext_noop
from ninja import Field, Schema

from apps.whatsapp_inbox.schemas.fields import _text

#: The headers with a file.
FileHeaderFormat = Literal["IMAGE", "VIDEO", "DOCUMENT"]

#: A 25 MB document in base64 is 34 952 536 characters; a little more still reads «too heavy» under its field.
MAX_SAMPLE_BASE64 = 36_000_000


class TemplateSampleUploadIn(Schema):
    header_format: FileHeaderFormat = Field(
        description="The header it is for: IMAGE (a JPEG or PNG photo, 5 MB at most), VIDEO (an MP4, 16 MB) or "
        "DOCUMENT (a PDF, 25 MB)."
    )
    name: _text(255, 1) = Field(description="The file's name, as Meta shows it in its review (carta.pdf).")
    content_base64: str = Field(
        max_length=MAX_SAMPLE_BASE64, title=gettext_noop("File"), description="The file, in base64."
    )


class TemplateSampleRefIn(Schema):
    id: UUID = Field(description="The file's id, as whatsapp_inbox.template_sample.upload answered it.")


class TemplateSampleOut(Schema):
    id: UUID = Field(description="The file's id: give it as header_sample when creating or changing the template.")
    header_format: FileHeaderFormat = Field(description="IMAGE, VIDEO or DOCUMENT, as its bytes say.")
    content_type: str = Field(description="image/jpeg, image/png, video/mp4 or application/pdf.")
    size: int = Field(description="Its size in bytes.")
    name: str = Field(description="The name it was chosen with.")
    url: str = Field(
        description="Where the Hub shows it to the hub's people (/p/media/…, opened only with a session of this hub); "
        "empty when it cannot."
    )
