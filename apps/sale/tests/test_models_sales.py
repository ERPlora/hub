"""The sales: what the database itself refuses of the fiscal record, and the indexes others read it by."""

from django.db import connections

from apps.sale.models.refunds import Refund
from apps.sale.models.sales import Sale
from apps.sale.tests.conftest import HUB_DB, a_sale, refused
from base.tenancy.context import current_alias

pytestmark = HUB_DB


def test_a_sale_number_and_an_attempt_key_are_unique():
    a_sale()
    refused(lambda: a_sale(idempotency_key="other"))
    refused(lambda: a_sale(number="20261014-0002", sequence=2))


def test_amounts_are_never_negative():
    refused(lambda: a_sale(total=-1))
    refused(lambda: a_sale(subtotal=-1, number="x-2", idempotency_key="k2"))


def _business_database():
    return connections[current_alias()]


def _indexes(table: str) -> dict:
    connection = _business_database()
    with connection.cursor() as cursor:
        found = connection.introspection.get_constraints(cursor, table)
    return {name: info for name, info in found.items() if info["index"]}


def test_the_cash_register_reads_voids_and_refunds_by_time_through_an_index():
    # Cash register (CASH_REGISTER-F11, F17) reads the voids and the refunds of a shift by their time:
    # a partial index on the voided sales only, and one on when each refund was made.
    connection = _business_database()
    sale_indexes = _indexes(Sale._meta.db_table)
    assert sale_indexes["sale_sale_voided_idx"]["columns"] == ["voided_at"]
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT pg_get_indexdef(indexrelid) FROM pg_index WHERE indexrelid = %s::regclass",
            ["sale_sale_voided_idx"],
        )
        (definition,) = cursor.fetchone()
    assert "WHERE (voided_at IS NOT NULL)" in definition
    assert _indexes(Refund._meta.db_table)["sale_refund_created_idx"]["columns"] == [
        "created_at"
    ]
