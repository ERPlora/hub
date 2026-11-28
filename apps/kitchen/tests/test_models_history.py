"""The kitchen's History and the rule the database itself keeps for it."""

from .conftest import HUB_DB, make_ticket, refused

pytestmark = HUB_DB


def test_a_log_entry_belongs_to_its_ticket():
    from apps.kitchen.models.history import LogEntry

    ticket = make_ticket()
    entry = LogEntry.objects.create(
        ticket=ticket, action="received", actor="ana", notes=""
    )
    assert entry.created_at is not None and str(entry) == "received 20261014-0001"
    assert refused(lambda: LogEntry.objects.create(ticket=ticket, action="sang"))
