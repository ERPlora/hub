"""A card's groups and tags, set by id or by name (CUSTOMER-F06)."""

from uuid import UUID

from live.context import OperationContext
from live.errors import InvalidPayload
from live.operations import AI, operation
from live.outbox import record_event

from apps.customer import events
from apps.customer.models import Customer, CustomerGroup, CustomerTag
from apps.customer.queries.cards import load_detail
from apps.customer.queries.reads import GROUP_UNAVAILABLE, TAG_UNAVAILABLE, find_customer, named
from apps.customer.schemas.cards import CustomerDetailOut
from apps.customer.schemas.memberships import SetGroupsIn, SetTagsIn
from apps.customer.services.writes import lock_rows


class MembersUnavailable(InvalidPayload):
    """A group or tag sent by id no longer exists: the usual refusal (code, message, field), plus
    ``unavailable_ids``, which of the ids sent are gone, so a client takes exactly those off its
    selection (the card's editor, CUSTOMER-F06) without guessing from a list it may only see part of."""

    def __init__(self, message, *, code: str, fields: dict, unavailable: set[UUID]):
        super().__init__(message, code=code, fields=fields)
        self.unavailable_ids = sorted(str(pk) for pk in unavailable)

    def envelope(self) -> dict:
        envelope = super().envelope()
        envelope["error"]["unavailable_ids"] = self.unavailable_ids
        return envelope


def _named_ids(  # noqa: PLR0913, PLR0917
    model, ids: list[UUID], names: list[str], missing, code: str, field: str
) -> set[UUID]:
    """The ids of the groups or tags sent by id or by name, held until the COMMIT; one that does not exist
    (or that was deleted meanwhile) saves nothing, and the refusal names the ids that are gone."""
    wanted = set(ids)
    for name in names:
        match = named(model, name)
        if match is None:
            raise InvalidPayload(missing, code=code, fields={field: missing})
        wanted.add(match.id)
    gone = wanted - set(lock_rows(model, wanted))
    if gone:
        raise MembersUnavailable(
            missing, code=code, fields={field: missing}, unavailable=gone
        )
    return wanted


def _set_members(
    ctx: OperationContext, customer: Customer, relation: str, ids: set[UUID], event: str
) -> dict:
    members = getattr(customer, relation)
    if set(members.values_list("id", flat=True)) != ids:
        members.set(ids)
        customer.save(update_fields=["updated_at"])
        record_event(ctx, event, {"id": str(customer.id)})
    return load_detail(customer)


@operation(
    "customer.customer.set_groups",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="customer.manage",
    input=SetGroupsIn,
    output=CustomerDetailOut,
    ai=AI(
        "Sets a customer's groups, by id or by name, replacing the previous selection; an empty selection takes them "
        "all off.",
        asks={
            "en": ("put Ana in the VIP group", "take Luis out of all groups"),
            "es": ("mete a Ana en el grupo VIP", "saca a Luis de los grupos", "pon a Marta en Empresas"),
        },
    ),
)
def set_groups(ctx: OperationContext, data: SetGroupsIn) -> dict:
    customer = find_customer(ctx, data.id, data.customer, lock=True)
    ids = _named_ids(
        CustomerGroup,
        data.group_ids,
        data.groups,
        GROUP_UNAVAILABLE,
        "customer.group_unavailable",
        "groups",
    )
    return _set_members(ctx, customer, "groups", ids, events.CUSTOMER_GROUPS_CHANGED)


@operation(
    "customer.customer.set_tags",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="customer.manage",
    input=SetTagsIn,
    output=CustomerDetailOut,
    ai=AI(
        "Sets a customer's tags, by id or by name, replacing the previous selection; an empty selection takes them "
        "all off.",
        asks={
            "en": ("tag Javier as a regular", "remove all tags from Sara"),
            "es": ("ponle la etiqueta habitual a Javier", "quítale las etiquetas a Sara"),
        },
    ),
)
def set_tags(ctx: OperationContext, data: SetTagsIn) -> dict:
    customer = find_customer(ctx, data.id, data.customer, lock=True)
    ids = _named_ids(
        CustomerTag,
        data.tag_ids,
        data.tags,
        TAG_UNAVAILABLE,
        "customer.tag_unavailable",
        "tags",
    )
    return _set_members(ctx, customer, "tags", ids, events.CUSTOMER_TAGS_CHANGED)
