"""Who may write and who hears of a write. The writes of each entity (MODIFIER-F02 to F05) are tested by
``test_services_<module>.py``, with Inventory and Taxes as the real apps (no doubles)."""

import pytest
from live.errors import PermissionDenied
from live.models import OutboxEvent

from base.tenancy.context import use_hub

from .conftest import HUB_DB, HUB_DB_COMMITTED, A, B, ctx_for, group, received, run

pytestmark = HUB_DB


def test_an_employee_reads_but_never_writes():
    with pytest.raises(PermissionDenied):
        run("modifier.group.create", {"name": "Sauces"}, role="hub_employee")
    group("Sauces")
    with pytest.raises(PermissionDenied):
        run(
            "modifier.option.create",
            {"group": "Sauces", "name": "Mayo", "price_delta": 0},
            role="hub_employee",
        )


@HUB_DB_COMMITTED
def test_a_write_in_scope_b_notifies_b_only(listen, hub_b):
    on_a, on_b = listen(A), listen(B)

    with use_hub(hub_b):
        run("modifier.group.create", {"name": "Sauces"}, ctx=ctx_for("hub_admin", B))
        # The notice goes out on the operation's scope: the event itself is B's, in B's database.
        assert list(OutboxEvent.objects.values_list("name", "scope_kind", "scope_key")) == [
            ("modifier.group.created", B.kind, B.key)
        ]

    assert received(on_b, stop_after=1) == [{"events": ["modifier.group.created"]}]
    assert received(on_a, timeout=0.3) == []
    assert not OutboxEvent.objects.exists()
