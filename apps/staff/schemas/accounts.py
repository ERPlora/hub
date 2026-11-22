"""Schemas of the accounts: the «Hub user» a staff record can hang from."""

from uuid import UUID

from ninja import Field, Schema

from apps.staff.schemas.fields import Page, PageIn, Search


class AccountListIn(PageIn):
    search: Search | None = Field(None, description="Text to look for in the account's name or email.")
    user_id: UUID | None = Field(
        None, description="Only this business user (to name the one a record hangs from)."
    )


class AccountOut(Schema):
    user_id: UUID = Field(description="The business user's id, for user_id of a record.")
    name: str = Field(description="Its name, or its email when it has none.")


AccountPage = Page[AccountOut]
