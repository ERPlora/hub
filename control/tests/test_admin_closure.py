"""«Move to cluster…» and «Restore from a copy…» say how long each hub chosen can stay closed, by the size of its
database: under each one on their confirmation page, and in what the staff is told once it is asked. The hubs are
copied one after another, so what the staff is told of several is the time of all of them, each moved open until its
own copy starts; a size that cannot be read is counted as the largest. Never «a few minutes» whatever the size: a large database keeps its business closed
up to the copy's time limit. «Restore to a separate copy…» closes nothing, and says nothing of it.
"""

import datetime as dt
import re
import uuid

import pytest
from django.utils import timezone
from live.errors import OperationError

from base.tenancy import move
from control import queries
from control.models import Hub
from control.tests.test_admin import AT_MOMENT, HUBS, MOMENT, PLATFORM, a_cluster, nothing_kept, root  # noqa: F401

pytestmark = pytest.mark.django_db
MB = 1000 * 1000
SMALL = 100 * MB
LARGE = 20 * 1000 * MB
NIGHT_ASKED_AT = dt.datetime(2026, 11, 16, 12, 0, tzinfo=dt.UTC)


@pytest.fixture
def sizes(monkeypatch):
    """The size each hub's database measures, by its name (1 KiB when not said)."""
    measured: dict[str, int] = {}
    monkeypatch.setattr(queries, "measure", lambda cluster, names: {name: measured.get(name, 1024) for name in names})
    return measured


@pytest.fixture
def target():
    return a_cluster(name="cluster-2", host="writer-2.example")


def unreachable(cluster, names):
    raise OperationError("connection refused", code="control.cluster_unreachable", status=503)


def a_hub(sizes: dict, slug: str, size: int, **fields) -> Hub:
    row = {"slug": slug, "status": Hub.Status.READY, "db_name": f"hub_{uuid.uuid7().hex}"}
    hub = Hub.objects.create(**(row | fields))
    sizes[hub.db_name] = size
    return hub


def choose(client, *hubs, language: str = "en", action: str = "move_to_cluster", **more) -> str:
    data = {"action": action, "_selected_action": [str(hub.pk) for hub in hubs]} | more
    response = client.post(HUBS, data, HTTP_HOST=PLATFORM, HTTP_ACCEPT_LANGUAGE=language, follow=True)
    return plain(response.content.decode())


def plain(html: str) -> str:
    """The page with Django's non-breaking spaces (``1\xa0hour``, ``95.4\xa0MB``) as plain ones."""
    return html.replace("\xa0", " ").replace("&nbsp;", " ")


def notes(html: str) -> list[str]:
    """What the confirmation page says under each chosen hub, in order."""
    [rows] = re.findall(r'<fieldset class="module aligned">(.*?)</fieldset>', html, re.S)
    return [note.strip() for note in re.findall(r'<div class="help"><div>(.*?)</div></div>', rows, re.S)]


def told(html: str) -> str:
    [said] = re.findall(r'<li class="success">(.*?)</li>', html, re.S)
    return said


class TestItsPage:
    def test_says_under_each_hub_how_long_it_can_stay_closed_by_its_size(self, client, root, sizes, target):
        small, large = a_hub(sizes, "acme", SMALL), a_hub(sizes, "bistro", LARGE)

        html = choose(client, small, large)

        assert notes(html) == [
            "95.4 MB: closed for up to 1 minute",
            "18.6 GB: closed for up to 1 hour, 7 minutes",
        ]
        assert "a few minutes" not in html

    def test_says_the_copys_time_limit_and_that_the_hubs_move_one_after_another(self, client, root, sizes, target):
        html = choose(client, a_hub(sizes, "acme", SMALL))

        assert "if its copy runs past 2 hours, it is stopped and undone" in html
        assert "copied one after another, and each stays open until its own copy starts" in html
        assert "whose turn has not come by 05:00 waits for its next night" in html

    def test_a_hub_whose_size_cannot_be_read_is_counted_as_the_largest(self, client, root, sizes, target, monkeypatch):
        hub = a_hub(sizes, "acme", SMALL)
        monkeypatch.setattr(queries, "measure", unreachable)

        html = choose(client, hub)

        assert notes(html) == ["Size unknown: closed for up to 2 hours"]
        # The list under the action measured the page already: why is said once, and nothing is measured twice.
        assert html.count("Connection refused") == 1

    def test_follows_the_copys_time_limit(self, client, root, sizes, target, monkeypatch):
        monkeypatch.setattr(move, "COPY_TIMEOUT_SECONDS", 30 * 60)

        html = choose(client, a_hub(sizes, "acme", 500 * 1000 * MB))

        assert notes(html) == ["465.7 GB: closed for up to 1 hour"]
        assert "if its copy runs past 1 hour, it is stopped and undone" in html

    def test_a_separate_copy_closes_nothing_and_says_nothing_under_its_rows(self, client, root, sizes):
        html = choose(client, a_hub(sizes, "acme", LARGE), action="restore_aside")

        assert notes(html) == []


class TestWhatTheStaffIsTold:
    def test_one_hub_asked_now_is_closed_for_as_long_as_its_size_takes(self, client, root, sizes, target):
        html = choose(client, a_hub(sizes, "bistro", LARGE), apply="yes", cluster=str(target.pk), when="now")

        assert told(html) == "1 hub will move to cluster-2: closed while it moves, for up to 1 hour, 7 minutes."

    def test_several_asked_now_add_up_as_they_move_one_after_another_each_open_until_its_turn(
        self, client, root, sizes, target
    ):
        small, large = a_hub(sizes, "acme", SMALL), a_hub(sizes, "bistro", LARGE)

        html = choose(client, small, large, apply="yes", cluster=str(target.pk), when="now")

        assert told(html) == (
            "2 hubs will move to cluster-2, one after another: each open until its own move starts and closed only "
            "while it moves; all of them take up to 1 hour, 8 minutes."
        )

    def test_asked_for_the_night_they_add_up_too(self, client, root, sizes, target, monkeypatch):
        monkeypatch.setattr(timezone, "now", lambda: NIGHT_ASKED_AT)
        small, large = a_hub(sizes, "acme", SMALL), a_hub(sizes, "bistro", LARGE)

        html = choose(client, small, large, apply="yes", cluster=str(target.pk), when="at_night")

        assert told(html).endswith(
            "in its next night or, if its turn has not come by then, in the one after: each open until its own move "
            "starts and closed only while it moves; all of them take up to 1 hour, 8 minutes."
        )

    def test_a_hub_the_operation_refuses_does_not_count(self, client, root, sizes, target):
        ready = a_hub(sizes, "bistro", LARGE)
        preparing = a_hub(sizes, "acme", SMALL, status=Hub.Status.REQUESTED)

        html = choose(client, ready, preparing, apply="yes", cluster=str(target.pk), when="now")

        assert "1 hub will move to cluster-2: closed while it moves, for up to 1 hour, 7 minutes." in html


class TestInSpanish:
    def test_its_page_says_the_size_and_the_closure_of_each_hub(self, client, root, sizes, target):
        html = choose(client, a_hub(sizes, "acme", SMALL), a_hub(sizes, "bistro", LARGE), language="es")

        assert notes(html) == ["95,4 MB: cerrado hasta 1 minuto", "18,6 GB: cerrado hasta 1 hora, 7 minutos"]
        assert "si su copia pasa de 2 horas, se para y se deshace" in html
        assert "se copian uno tras otro, y cada uno sigue abierto hasta que empieza su copia" in html
        assert "unos minutos" not in html

    def test_a_size_that_cannot_be_read_says_so(self, client, root, sizes, target, monkeypatch):
        hub = a_hub(sizes, "acme", SMALL)
        monkeypatch.setattr(queries, "measure", unreachable)

        assert notes(choose(client, hub, language="es")) == ["Tamaño desconocido: cerrado hasta 2 horas"]

    def test_what_the_staff_is_told(self, client, root, sizes, target):
        now = {"apply": "yes", "cluster": str(target.pk), "when": "now", "language": "es"}

        one = choose(client, a_hub(sizes, "bistro", LARGE), **now)
        two = choose(client, a_hub(sizes, "acme", SMALL), a_hub(sizes, "corner", LARGE), **now)

        assert told(one) == "1 hub se moverá a cluster-2: cerrado mientras se mueve, hasta 1 hora, 7 minutos."
        assert told(two) == (
            "2 hubs se moverán a cluster-2, uno tras otro: cada uno abierto hasta que empieza su traslado y cerrado "
            "solo mientras se mueve; todos juntos tardan hasta 1 hora, 8 minutos."
        )

    def test_what_the_staff_is_told_of_the_night(self, client, root, sizes, target, monkeypatch):
        monkeypatch.setattr(timezone, "now", lambda: NIGHT_ASKED_AT)
        night = {"apply": "yes", "cluster": str(target.pk), "when": "at_night", "language": "es"}

        two = choose(client, a_hub(sizes, "acme", SMALL), a_hub(sizes, "bistro", LARGE), **night)
        one = choose(client, a_hub(sizes, "corner", LARGE), **night)

        assert told(two).endswith(
            "o, si no le llega el turno, en la siguiente: cada uno abierto hasta que empieza su traslado y cerrado solo "
            "mientras se mueve; todos juntos tardan hasta 1 hora, 8 minutos."
        )
        assert told(one).endswith("abierto hasta entonces y cerrado mientras se mueve, hasta 1 hora, 7 minutos.")


class TestRestoreFromACopy:
    """Restoring a hub closes it while its database is replaced, as a move does: its page and its notice say for how
    long by its size. The sizes stay within what a restore copies today (``RESTORE_MAX_BYTES``)."""

    MEDIUM = 500 * MB

    @pytest.fixture
    def temporary(self):
        return a_cluster(name="restore-1", host="restore-1.example", is_open=False)

    def test_its_page_says_under_each_hub_how_long_it_can_stay_closed(self, client, root, sizes, temporary):
        small, medium = a_hub(sizes, "acme", SMALL), a_hub(sizes, "bistro", self.MEDIUM)

        html = choose(client, small, medium, action="restore_from_a_copy")

        assert notes(html) == ["95.4 MB: closed for up to 1 minute", "476.8 MB: closed for up to 2 minutes"]
        assert "restored one after another" in html and "a few minutes" not in html

    def test_what_the_staff_is_told_adds_them_up(self, client, root, sizes, temporary):
        small, medium = a_hub(sizes, "acme", SMALL), a_hub(sizes, "bistro", self.MEDIUM)
        asked = {"action": "restore_from_a_copy", "apply": "yes", "cluster": str(temporary.pk), "at": MOMENT}

        html = choose(client, small, medium, **asked)

        assert told(html) == (
            "2 hubs will be restored from restore-1 as they were at 2026-11-09 14:30 UTC, one after another: each "
            "closed until its own restore ends, for up to 3 minutes in all. If one is refused, its page says why "
            "under «last error»."
        )
        assert Hub.objects.get(pk=small.pk).restore_point == AT_MOMENT

    def test_a_hub_the_operation_refuses_does_not_count(self, client, root, sizes, temporary):
        ready = a_hub(sizes, "bistro", self.MEDIUM)
        preparing = a_hub(sizes, "acme", SMALL, status=Hub.Status.REQUESTED)
        asked = {"action": "restore_from_a_copy", "apply": "yes", "cluster": str(temporary.pk), "at": MOMENT}

        html = choose(client, ready, preparing, **asked)

        assert told(html) == (
            "1 hub will be restored from restore-1 as it was at 2026-11-09 14:30 UTC: closed while it is restored, "
            "for up to 2 minutes. If it is refused, its page says why under «last error»."
        )

    def test_several_hubs_in_spanish(self, client, root, sizes, temporary):
        small, medium = a_hub(sizes, "acme", SMALL), a_hub(sizes, "bistro", self.MEDIUM)
        asked = {"action": "restore_from_a_copy", "apply": "yes", "cluster": str(temporary.pk), "at": MOMENT}

        html = choose(client, small, medium, language="es", **asked)

        assert told(html) == (
            "2 hubs se restaurarán desde restore-1 tal como estaban el 2026-11-09 14:30 UTC, uno tras otro: cada uno "
            "cerrado hasta que acaba su restauración, hasta 3 minutos en total. Si se rechaza alguno, su ficha dice "
            "por qué en «último error»."
        )

    def test_one_hub_in_spanish(self, client, root, sizes, temporary):
        asked = {"action": "restore_from_a_copy", "apply": "yes", "cluster": str(temporary.pk), "at": MOMENT}

        page = choose(client, a_hub(sizes, "corner", self.MEDIUM), action="restore_from_a_copy", language="es")
        html = choose(client, a_hub(sizes, "acme", self.MEDIUM), language="es", **asked)

        assert notes(page) == ["476,8 MB: cerrado hasta 2 minutos"]
        assert "se restauran uno tras otro" in page and "unos minutos" not in page
        assert told(html) == (
            "1 hub se restaurará desde restore-1 tal como estaba el 2026-11-09 14:30 UTC: cerrado mientras se "
            "restaura, hasta 2 minutos. Si se rechaza, su ficha dice por qué en «último error»."
        )
