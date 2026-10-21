"""Events of the printing app: their names follow ``printing.<entity>.<fact>`` and it reacts to nobody's
(the apps that print call printing.job.create by name, in their own transaction)."""

from live.context import Scope
from live.operations import NAME_RE

from apps.printing import events


def test_every_event_is_named_by_the_convention():
    assert events.ALL == [
        "printing.settings.updated",
        "printing.printer.created",
        "printing.printer.updated",
        "printing.job.queued",
        "printing.job.claimed",
        "printing.job.printed",
        "printing.job.failed",
        "printing.job.retried",
        "printing.job.cancelled",
        "printing.job.pruned",
    ]
    assert all(NAME_RE.match(name) for name in events.ALL)


def test_it_reacts_to_nothing():
    assert events.REACTIONS == {}
    assert events.react(Scope("host", "a"), "sale.sale.completed", {"id": "x"}) is None
