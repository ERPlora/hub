"""Schemas of a card's groups and tags, the whole set at once."""

from typing import Annotated

from ninja import Field

from apps.customer.schemas.fields import GROUPS, TAGS, CustomerRefIn, GroupId, Reference, TagId
from base.schemas.assistant import IN_OWN_WORDS

#: A group or a tag by the name the person says.
SaidName = Annotated[Reference, Field(json_schema_extra=IN_OWN_WORDS)]


class SetGroupsIn(CustomerRefIn):
    group_ids: list[GroupId] = Field(
        [], max_length=200, title=GROUPS, description="The ids of the groups the customer is in."
    )
    groups: list[SaidName] = Field(
        [], max_length=200, description="The names of the groups the customer is in."
    )


class SetTagsIn(CustomerRefIn):
    tag_ids: list[TagId] = Field(
        [], max_length=200, title=TAGS, description="The ids of the tags the customer has."
    )
    tags: list[SaidName] = Field(
        [], max_length=200, description="The names of the tags the customer has."
    )
