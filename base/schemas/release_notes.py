"""What is new in ERPlora (``base.release_note.list``): a page of the notes the version running ships."""

import datetime as dt
from typing import Literal

from ninja import Schema
from pydantic import Field


class ReleaseNoteListIn(Schema):
    """A page of the release notes, newest first."""

    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class ReleaseNoteOut(Schema):
    """One change the business notices, in the person's language."""

    #: Stable while the note exists: «2026-11-19-allergens-on-products».
    id: str
    #: The day the change reached the businesses.
    date: dt.date
    #: Something new, an improvement or a fix.
    kind: Literal["new", "improved", "fixed"]
    title: str
    #: What the person can do now, in a sentence or two of plain text.
    body: str


class ReleaseNoteListOut(Schema):
    items: list[ReleaseNoteOut]
    total: int
