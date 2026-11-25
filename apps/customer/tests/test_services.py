"""What the write operations of the customer app declare, and who hears of one.

The writes of each entity are tested by ``test_services_<module>.py``.
"""

import json

import psycopg
import pytest
from live.errors import InvalidPayload
from live.operations import get
from live.outbox import channel_for

from apps.customer import events
from apps.customer.schemas.activity import ActivityIn, ActivityRow, NoteIn
from apps.customer.schemas.cards import CustomerDetailOut, CustomerIn, CustomerPatchIn
from apps.customer.schemas.consent import ConsentGrantIn, ConsentRow, ConsentWithdrawIn
from apps.customer.schemas.custom_fields import FieldIn, FieldPatchIn, FieldRow
from apps.customer.schemas.erasing import EraseIn, ErasedOut
from apps.customer.schemas.fields import (
    CustomerRefIn as RefIn,
    DeletedOut,
    FieldRefIn as FieldRef,
    GroupRefIn,
    TagRefIn,
)
from apps.customer.schemas.groups import GroupIn, GroupPatchIn, GroupRow
from apps.customer.schemas.importing import ImportIn, ImportOut
from apps.customer.schemas.memberships import SetGroupsIn, SetTagsIn
from apps.customer.schemas.merging import MergeIn
from apps.customer.schemas.orders import OrderCustomerOut, OrderLinkIn
from apps.customer.schemas.purchases import PurchaseRecordIn, PurchaseRecordOut, PurchaseVoidIn, PurchaseVoidOut
from apps.customer.schemas.recovery import CustomerRecoverIn, CustomerRecoveredOut, CustomerRestoreIn
from apps.customer.schemas.tags import TagIn, TagPatchIn, TagRow

from base.tenancy.context import use_hub

from .conftest import HUB_DB, HUB_DB_COMMITTED, A, B, run

pytestmark = HUB_DB


WAIT = 1.0


QUIET = 0.3


# Declarations


@pytest.mark.parametrize(
    ("name", "permission", "input", "output"),
    [
        ("customer.customer.create", "customer.manage", CustomerIn, CustomerDetailOut),
        (
            "customer.customer.update",
            "customer.manage",
            CustomerPatchIn,
            CustomerDetailOut,
        ),
        ("customer.customer.import", "customer.manage", ImportIn, ImportOut),
        (
            "customer.customer.set_groups",
            "customer.manage",
            SetGroupsIn,
            CustomerDetailOut,
        ),
        ("customer.customer.set_tags", "customer.manage", SetTagsIn, CustomerDetailOut),
        ("customer.customer.delete", "customer.delete", RefIn, DeletedOut),
        ("customer.customer.merge", "customer.merge", MergeIn, CustomerDetailOut),
        ("customer.customer.erase", "customer.erase", EraseIn, ErasedOut),
        ("customer.customer.restore", "customer.restore", CustomerRestoreIn, CustomerRecoveredOut),
        ("customer.customer.recover", "customer.restore", CustomerRecoverIn, CustomerRecoveredOut),
        ("customer.note.add", "customer.manage", NoteIn, ActivityRow),
        ("customer.activity.add", "customer.record_activity", ActivityIn, ActivityRow),
        ("customer.consent.grant", "customer.manage", ConsentGrantIn, ConsentRow),
        ("customer.consent.withdraw", "customer.manage", ConsentWithdrawIn, ConsentRow),
        ("customer.order.link", "customer.manage", OrderLinkIn, OrderCustomerOut),
        ("customer.group.create", "customer.configure", GroupIn, GroupRow),
        ("customer.group.update", "customer.configure", GroupPatchIn, GroupRow),
        ("customer.group.delete", "customer.delete", GroupRefIn, DeletedOut),
        ("customer.tag.create", "customer.configure", TagIn, TagRow),
        ("customer.tag.update", "customer.configure", TagPatchIn, TagRow),
        ("customer.tag.delete", "customer.delete", TagRefIn, DeletedOut),
        ("customer.field.create", "customer.configure", FieldIn, FieldRow),
        ("customer.field.update", "customer.configure", FieldPatchIn, FieldRow),
        ("customer.field.delete", "customer.configure", FieldRef, DeletedOut),
        (
            "customer.purchase.record",
            "customer.record_purchase",
            PurchaseRecordIn,
            PurchaseRecordOut,
        ),
        (
            "customer.purchase.void",
            "customer.record_purchase",
            PurchaseVoidIn,
            PurchaseVoidOut,
        ),
    ],
)
def test_declarations(name, permission, input, output):
    op = get(name)
    assert (op.kind, op.permission, op.input, op.output) == (
        "command",
        permission,
        input,
        output,
    )


# Notifications: after the COMMIT, on the channel of the command's scope only


@pytest.fixture
def listen(db_dsn):
    sessions = []

    def open_session(scope):
        session = psycopg.connect(db_dsn, autocommit=True)
        sessions.append(session)
        session.execute(f"LISTEN {channel_for(scope)}")
        return session

    yield open_session
    for session in sessions:
        session.close()


def received(session, timeout=WAIT, stop_after=None):
    return [
        (note.channel, json.loads(note.payload))
        for note in session.notifies(timeout=timeout, stop_after=stop_after)
    ]


@HUB_DB_COMMITTED
def test_a_command_in_scope_b_notifies_the_channel_of_b_only(listen, hub_b):
    on_a, on_b = listen(A), listen(B)
    with use_hub(hub_b):
        run("customer.customer.create", CustomerIn(name="Ana"), scope=B)
    assert received(on_b, stop_after=1) == [
        (channel_for(B), {"events": [events.CUSTOMER_CREATED]})
    ]
    assert received(on_a, timeout=QUIET) == []


@HUB_DB_COMMITTED
def test_a_rejected_command_notifies_nobody(listen):
    on_a = listen(A)
    with pytest.raises(InvalidPayload):
        run("customer.customer.create", CustomerIn(name="Ana", phone="600111"))
    assert received(on_a, timeout=QUIET) == []
