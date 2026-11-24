"""The cards of a separate copy of the business and how they meet the business's own: which it lacks, which it holds
deleted and which live card is one of them; and whether a card was made again, an import of a row already imported or
a card brought back already."""

import json
from uuid import UUID

from django.db.models import QuerySet
from psycopg import sql

from apps.customer.models import Customer, CustomField, CustomFieldValue
from apps.customer.schemas.recovery import FieldValueOfCopyIn, GroupOfCopyIn, TagOfCopyIn


def has_live_twin(name: str, phone: str, email: str) -> bool:
    """A live card with the same name, phone and email, the case of the name and the email aside: the same card made
    again (an import of a row already imported; a card brought back from a copy already, hub#1257).

    Only the three together: two people may share a phone or an email (CUSTOMER-F12).
    """
    return _live_twins(name, phone, email).exists()


def _live_twins(name: str, phone: str, email: str) -> QuerySet[Customer]:
    """The live cards ``has_live_twin`` finds, the oldest first."""
    return Customer.objects.live().filter(name__iexact=name, phone=phone, email__iexact=email).order_by("created_at", "id")


def card_in_business(card: dict) -> UUID | None:
    """hub#1284: the business's live card that is ``card`` of a separate copy (its ``id``, ``name``, ``phone`` and
    ``email`` there), what another app's recovery matches a record of the copy that points at it by, by the rule
    ``cards_not_in_business`` tells a card is not lacking by: the same card while live, the one it was merged into since
    (it lives on in that one, CUSTOMER-F13), or one made again (``has_live_twin``: by hand, or brought back already).
    ``None`` when the business has none: deleted and not made again, gone, or erased (never another card, CUSTOMER-F16).
    """
    seen: set[UUID] = set()
    current = card["id"]
    while current is not None and current not in seen:
        seen.add(current)
        row = Customer.objects.filter(pk=current).values("deleted_at", "merged_into", "erased_at").first()
        if row is None:
            break
        if row["erased_at"] is not None:
            return None
        if row["deleted_at"] is None:
            return current
        current = row["merged_into"]
    return _live_twins(card["name"], card["phone"], card["email"]).values_list("pk", flat=True).first()


#: What a card of a separate copy gives its create (``CustomerIn``), as the copy's columns hold it since
#: ``0001_initial`` (``cards_in_copy``).
CARD_FIELDS = (
    "name",
    "email",
    "phone",
    "tax_id",
    "company_name",
    "address",
    "city",
    "postal_code",
    "country",
    "avatar",
    "birthday",
    "anniversary",
    "source",
    "lifecycle_stage",
    "preferred_channel",
    "notes",
)


def cards_in_copy(conn) -> list[dict]:
    """hub#1257: each live card of a separate copy of the business (not deleted, merged nor erased: those three set
    ``deleted_at``), with its ``id`` there and what ``customer.customer.create`` takes, by id; nothing where the app's
    table is not there. ``conn`` is the copy's direct, read-only connection (``recoverable_from_copy`` on this app's
    config: the copy is no business and has no alias), so it is read by its own SQL over the model's names, never the
    ORM."""
    table = Customer._meta.db_table
    if conn.execute("SELECT to_regclass(%s)", [table]).fetchone()[0] is None:
        return []
    read = ("id", *CARD_FIELDS)
    column = {field: sql.Identifier(Customer._meta.get_field(field).column) for field in (*read, "deleted_at")}
    query = sql.SQL("SELECT {} FROM {} WHERE {} IS NULL ORDER BY {}").format(
        sql.SQL(", ").join(column[field] for field in read), sql.Identifier(table), column["deleted_at"], column["id"]
    )
    return [dict(zip(read, row, strict=True)) for row in conn.execute(query)]


def recoverable_cards_in_copy(conn) -> list[dict]:
    """hub#1285: each card of ``cards_in_copy`` with what hung from it in the copy, as ``customer.customer.recover``
    and ``customer.customer.restore`` take it (``HungInCopyIn``): its groups and its tags, active or not (a card keeps
    an inactive one), and its values of the copy's active custom fields (an inactive field shows on no card and takes
    no value, CUSTOMER-F29), each named as the copy named it and with its id there, in the order its card shows them. The same connection and rule as
    ``cards_in_copy``: its own SQL over the models' names, never the ORM."""
    cards = cards_in_copy(conn)
    if not cards:
        return []
    hanging = {card["id"]: {"groups": [], "tags": [], "field_values": []} for card in cards}
    read = (
        ("groups", _members_in_copy(conn, "groups", tuple(GroupOfCopyIn.model_fields))),
        ("tags", _members_in_copy(conn, "tags", tuple(TagOfCopyIn.model_fields))),
        ("field_values", _values_in_copy(conn)),
    )
    for key, rows in read:
        for card_id, item in rows:
            if card_id in hanging:
                hanging[card_id][key].append(item)
    return [card | hanging[card["id"]] for card in cards]


def _members_in_copy(conn, relation: str, read: tuple[str, ...]) -> list[tuple[UUID, dict]]:
    """Each group or tag (``relation`` of a card) of each card of the copy: the card's id and its ``read`` columns, by
    name."""
    field = Customer._meta.get_field(relation)
    through, model = field.remote_field.through._meta, field.related_model._meta
    columns = [sql.Identifier("m", field.m2m_column_name())]
    columns += [sql.Identifier("x", model.get_field(name).column) for name in read]
    query = sql.SQL("SELECT {} FROM {} m JOIN {} x ON x.{} = m.{} ORDER BY x.{}, x.{}").format(
        sql.SQL(", ").join(columns),
        sql.Identifier(through.db_table),
        sql.Identifier(model.db_table),
        sql.Identifier(model.pk.column),
        sql.Identifier(field.m2m_reverse_name()),
        sql.Identifier(model.get_field("name").column),
        sql.Identifier(model.pk.column),
    )
    return [(row[0], dict(zip(read, row[1:], strict=True))) for row in conn.execute(query)]


def _values_in_copy(conn) -> list[tuple[UUID, dict]]:
    """Each value of an active custom field of each card of the copy: the card's id and the field as its create takes
    it, with the value, in the order the card shows them. A select's options are read as their JSON text, whatever
    the connection makes of a ``jsonb``."""
    value, field = CustomFieldValue._meta, CustomField._meta
    read = tuple(name for name in FieldValueOfCopyIn.model_fields if name != "value")
    columns = [sql.Identifier("v", value.get_field("customer").column)]
    columns += [
        sql.SQL("{}::text").format(sql.Identifier("f", field.get_field(name).column))
        if name == "options"
        else sql.Identifier("f", field.get_field(name).column)
        for name in read
    ]
    columns += [sql.Identifier("v", value.get_field("value").column)]
    query = sql.SQL("SELECT {} FROM {} v JOIN {} f ON f.{} = v.{} WHERE f.{} ORDER BY f.{}, f.{}, f.{}").format(
        sql.SQL(", ").join(columns),
        sql.Identifier(value.db_table),
        sql.Identifier(field.db_table),
        sql.Identifier(field.pk.column),
        sql.Identifier(value.get_field("field").column),
        sql.Identifier(field.get_field("is_active").column),
        sql.Identifier(field.get_field("sort_order").column),
        sql.Identifier(field.get_field("name").column),
        sql.Identifier(field.pk.column),
    )
    found = []
    for row in conn.execute(query):
        item = dict(zip((*read, "value"), row[1:], strict=True))
        found.append((row[0], item | {"options": json.loads(item["options"])}))
    return found


def cards_not_in_business(cards: list[dict]) -> list[dict]:
    """hub#1257: the cards of a separate copy (``cards_in_copy``) the business no longer has, in their order, for
    ``customer.customer.create``. Not lacking: any card it still holds, live, deleted (it comes back the same,
    ``cards_deleted_in_business``), merged into another (it lives on in that one, CUSTOMER-F13) or erased (never
    brought back, CUSTOMER-F16), and one made again (``has_live_twin``: by hand, or brought back already)."""
    held = set(Customer.objects.filter(pk__in=[card["id"] for card in cards]).values_list("pk", flat=True))
    return [
        card
        for card in cards
        if card["id"] not in held and not has_live_twin(card["name"], card["phone"], card["email"])
    ]


def cards_deleted_in_business(cards: list[dict]) -> list[dict]:
    """hub#1306: the cards of a separate copy (``cards_in_copy``) the business still holds deleted (CUSTOMER-F07), in
    their order, for ``customer.customer.restore``: the same card back with all that hangs from it. Never one merged
    into another or erased, and never one made again since (``has_live_twin``)."""
    deleted = set(
        Customer.objects.filter(
            pk__in=[card["id"] for card in cards],
            deleted_at__isnull=False,
            merged_into__isnull=True,
            erased_at__isnull=True,
        ).values_list("pk", flat=True)
    )
    return [
        card
        for card in cards
        if card["id"] in deleted and not has_live_twin(card["name"], card["phone"], card["email"])
    ]
