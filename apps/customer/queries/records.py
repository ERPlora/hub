"""What the card of a write says of a group, a tag or a custom field: its own row, by its id or by the name its write
finds it by, also one no longer active."""

from live.context import OperationContext
from live.operations import INTERNAL, operation

from apps.customer.models import CustomerGroup, CustomerTag, CustomField
from apps.customer.queries.groups import _groups
from apps.customer.queries.reads import GROUP_UNAVAILABLE, TAG_UNAVAILABLE, _by_id, find_field, find_group, find_tag
from apps.customer.queries.tags import _tags
from apps.customer.schemas.custom_fields import FieldRow
from apps.customer.schemas.fields import FieldRefIn, GroupRefIn, TagRefIn
from apps.customer.schemas.groups import GroupRow
from apps.customer.schemas.tags import TagRow


# Not assistant tools: what names a group, a tag or a custom field on the card of a write (``schemas.A_GROUP``,
# ``A_TAG``, ``A_FIELD``), also one no longer active, which a change brings back; the model finds them in their lists.
# Said by its name (``schemas.A_GROUP_SAID``…), the one its write finds by it (``find_group``…, hub#1280).
@operation(
    "customer.group.detail",
    kind="query",
    permission="customer.view",
    input=GroupRefIn,
    output=GroupRow,
    ai=INTERNAL,
)
def group_detail(ctx: OperationContext, data: GroupRefIn) -> CustomerGroup:
    group_id = data.id if data.id is not None else find_group(None, data.group).id
    return _by_id(_groups(), group_id, missing=GROUP_UNAVAILABLE, code="customer.group_unavailable")


@operation(
    "customer.tag.detail",
    kind="query",
    permission="customer.view",
    input=TagRefIn,
    output=TagRow,
    ai=INTERNAL,
)
def tag_detail(ctx: OperationContext, data: TagRefIn) -> CustomerTag:
    tag_id = data.id if data.id is not None else find_tag(None, data.tag).id
    return _by_id(_tags(), tag_id, missing=TAG_UNAVAILABLE, code="customer.tag_unavailable")


@operation(
    "customer.field.detail",
    kind="query",
    permission="customer.view",
    input=FieldRefIn,
    output=FieldRow,
    ai=INTERNAL,
)
def field_detail(ctx: OperationContext, data: FieldRefIn) -> CustomField:
    return find_field(data.id, data.field)
