"""A table's code: one per table, unique across the business, with a UUIDv7 key."""

import uuid

import pytest
from django.db import IntegrityError, transaction

from apps.online_order.models import TableCode

from .conftest import HUB_DB

pytestmark = HUB_DB


def test_the_key_is_a_uuid7():
    code = TableCode.objects.create(table_id=uuid.uuid7(), code="abc")
    assert code.id.version == 7


def test_a_table_has_one_code():
    table_id = uuid.uuid7()
    TableCode.objects.create(table_id=table_id, code="first")
    with pytest.raises(IntegrityError), transaction.atomic():
        TableCode.objects.create(table_id=table_id, code="second")


def test_two_tables_never_share_a_code():
    TableCode.objects.create(table_id=uuid.uuid7(), code="same")
    with pytest.raises(IntegrityError), transaction.atomic():
        TableCode.objects.create(table_id=uuid.uuid7(), code="same")
