"""A note on a card, and the entries other apps record in its activity (CUSTOMER-F05)."""

from live.context import OperationContext
from live.operations import AI, operation
from live.outbox import record_event

from apps.customer import events
from apps.customer.models import Activity
from apps.customer.queries import find_customer
from apps.customer.schemas import ActivityIn, ActivityRow, NoteIn
from apps.customer.services.writes import _actor


@operation(
    "customer.note.add",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="customer.manage",
    input=NoteIn,
    output=ActivityRow,
    ai=AI(
        "Adds a note to a customer's card, by its id or exact name, phone or email; the note shows at the top of its "
        "activity with who wrote it and when.",
        asks={
            "en": (
                "add a note to Luis",
                "note that Marta likes her coffee black",
                "jot down that Carmen prefers mornings",
            ),
            "es": (
                "añade una nota a Marta: prefiere venir por la tarde",
                "apunta que Carmen prefiere las mañanas",
                "apunta que Luis viene siempre con su perro",
            ),
        },
    ),
)
def add_note(ctx: OperationContext, data: NoteIn) -> Activity:
    customer = find_customer(ctx, data.customer_id, data.customer, lock=True)
    entry = Activity.objects.create(
        customer=customer,
        kind=Activity.Kind.NOTE_ADDED,
        title=data.title,
        text=data.content,
        data={"author_name": data.author_name} if data.author_name else {},
        related_type="note",
        actor=_actor(ctx),
    )
    record_event(
        ctx, events.NOTE_ADDED, {"id": str(entry.id), "customer_id": str(customer.id)}
    )
    return entry


@operation(
    "customer.activity.add",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="customer.record_activity",
    input=ActivityIn,
    output=ActivityRow,
    ai=AI(
        "Records an entry of another app in a customer's activity history (a visit, a booking), with that app's own "
        "key, title and data.",
        asks={
            "en": (
                "log Ana's visit to the tasting in her history",
                "put on Luis's timeline that he came to the workshop",
            ),
            "es": (
                "deja constancia en la ficha de Luis de la visita de hoy",
                "apunta en el historial de Ana que vino a la cata",
            ),
        },
    ),
)
def add_activity(ctx: OperationContext, data: ActivityIn) -> Activity:
    customer = find_customer(ctx, data.customer_id, data.customer, lock=True)
    entry = Activity.objects.create(
        customer=customer,
        kind=data.kind,
        title=data.title,
        text=data.text,
        data=data.data,
        related_id=data.related_id,
        related_type=data.related_type,
        actor=_actor(ctx),
    )
    record_event(
        ctx,
        events.ACTIVITY_RECORDED,
        {"id": str(entry.id), "customer_id": str(customer.id)},
    )
    return entry
