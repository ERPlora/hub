"""What the cash register's schemas share: the limits of money and pieces, the messages of a refused input, the
assistant's marks, the field types, the closed input and the page."""

from typing import Annotated, Generic, Literal, TypeVar

from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext_noop
from ninja import Field, Schema
from pydantic import ConfigDict, StringConstraints

from base.schemas.assistant import names

T = TypeVar("T")

#: Just under ten trillion minor units of the business's currency (ninety-nine billion with two decimals): far above
#: any drawer, inside a bigint.
MAX_CENTS = 9_999_999_999_999
#: Pieces of one note or coin in a count: more than any drawer holds.
MAX_PIECES = 100_000

SAY_WHICH_SESSION = _("Say which session: its id or its number.")
SAY_WHICH_DRAWER = _("Say which drawer: its id or its name.")
NOTHING_TO_CHANGE = _(
    "Say what changes: the drawer's new name, or whether it is active."
)
ONE_LIST = _(
    "Ask for the lines of one session (its id or number) or for the unassigned ones, one of the two."
)
#: How «Open session» and the drawers of the settings name a drawer (the assistant's card names the datum by it).
DRAWER = gettext_noop("Drawer")

# The assistant's card names the record a write acts on by these reads (base/assistant/cards.py ``REFERS``), run as whoever
# asks, never by its id: a session by its number, as the sessions' list and every window of a shift («Cash count ·
# S-…»); a drawer by its name, as «Open session» and the drawers of the settings. Every till role reads both.
A_SESSION = names("cash_register.session.get", by="session_id", name=("number",))
A_DRAWER = names("cash_register.register.get", by="register_id", name=("name",))


def _text(max_length: int, min_length: int = 0) -> type[str]:
    return Annotated[
        str,
        StringConstraints(
            strip_whitespace=True, min_length=min_length, max_length=max_length
        ),
    ]


Name = _text(100, 1)
SessionNumber = _text(24, 1)
Notes = _text(1000)
Cents = Annotated[int, Field(ge=0, le=MAX_CENTS, json_schema_extra={"money": True})]
PositiveCents = Annotated[int, Field(ge=1, le=MAX_CENTS, json_schema_extra={"money": True})]
SignedCents = Annotated[int, Field(ge=-MAX_CENTS, le=MAX_CENTS, json_schema_extra={"money": True})]
#: A note or coin by its face value in major units («50», «0.50», «0.005»).
FaceValue = Annotated[str, StringConstraints(pattern=r"^\d{1,6}(\.\d{1,3})?$")]
Pieces = Annotated[int, Field(ge=0, le=MAX_PIECES)]
#: A whole hour of the day, «00:00» to «23:00».
WholeHour = Annotated[str, StringConstraints(pattern=r"^([01]\d|2[0-3]):00$")]
MethodType = Literal["cash", "card", "transfer", "other"]
SessionStatus = Literal["open", "closed"]
MovementType = Literal["in", "out", "sale", "refund", "void"]
ManualType = Literal["in", "out"]
CountType = Literal["opening", "closing"]
SortDir = Literal["asc", "desc"]


class Closed(Schema):
    """An input that refuses fields it does not know (a typo is a 422, never silently ignored)."""

    model_config = ConfigDict(extra="forbid")


class EmptyIn(Closed):
    pass


class PageIn(Closed):
    limit: int = Field(50, ge=1, le=100, description="Rows per page, 1 to 100.")
    offset: int = Field(0, ge=0, description="Rows to skip.")


class Page(Schema, Generic[T]):
    rows: list[T] = Field(description="The rows of this page.")
    total: int = Field(description="Rows that match, in every page.")
    limit: int = Field(description="Rows per page asked.")
    offset: int = Field(description="Rows skipped.")
