"""Schemas of a card's groups and tags, the whole set at once."""

from ninja import Field

from apps.customer.schemas.fields import GROUPS, TAGS, CustomerRefIn, GroupId, Reference, TagId


class SetGroupsIn(CustomerRefIn):
    group_ids: list[GroupId] = Field(
        [], max_length=200, title=GROUPS, description="The ids of the groups the customer is in."
    )
    groups: list[Reference] = Field(
        [], max_length=200, description="The names of the groups the customer is in."
    )


class SetTagsIn(CustomerRefIn):
    tag_ids: list[TagId] = Field(
        [], max_length=200, title=TAGS, description="The ids of the tags the customer has."
    )
    tags: list[Reference] = Field(
        [], max_length=200, description="The names of the tags the customer has."
    )
