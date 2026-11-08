"""A business's Hub while the database is cut for a moment (BASE-F111; PLAN-DB round 2026-11-04e, point 5).

The whole chain of the Hub, against the real Postgres, as production runs it (``no_test_fallback``): ``pg_terminate_backend``
is the server cutting a connection right before a statement of the request, ``default_transaction_read_only`` the old
writer refusing writes during a switchover. The piece itself, and what it never repeats, is tested in ``live``
(``tests/test_database_cut.py``); here, that the Hub is wired to it, on control and on a business's own database: control's
pool hands out no dead connection; a read waits and answers, also when the cut comes while the business's database is
being opened; a save of a command that touches nothing but its database (the reference app's) goes in once, in its own
business only; one that numbers is never repeated; a wait holds no place of the business's plan; past the limit a person
reads «come back in a moment» with 503 and ``Retry-After``, never a 500; and the SaaS's ``/internal`` calls get theirs at
once.
"""

import asyncio
import json
import time
from types import SimpleNamespace

import live.database_cut as live_database_cut
import psycopg
import pytest
from django.contrib.auth import get_user_model
from django.db import DatabaseError, connections
from django.test import Client
from django.utils import translation
from live.database_cut import DatabaseCut
from live.models import OutboxEvent
from psycopg import sql

from apps.demo.models import Item
from apps.task.models import Task
from base.models import Membership
from base.tenancy import context, identity, limits
from base.tenancy.tests import hubs
from base.tests.test_internal import signed

pytestmark = [
    pytest.mark.usefixtures("no_test_fallback"),
    pytest.mark.django_db(databases=hubs.HUB_DATABASES, transaction=True),
]

ITEMS = "/api/demo/items"
TASKS = "/api/task/tasks"
UNAVAILABLE = "database_unavailable"
UNKNOWN = "database_outcome_unknown"
HUB_UNAVAILABLE = "base.hub_unavailable"
ITEM_CREATED = "demo.item.created"
LIMIT_SECONDS = 1


def _admin() -> psycopg.Connection:
    """The connection that cuts the others, on ``postgres``: never read only itself, or it could not undo ``_read_only``."""
    params = connections["default"].settings_dict
    return psycopg.connect(
        dbname="postgres",
        user=params["USER"],
        password=params["PASSWORD"],
        host=params["HOST"],
        port=params["PORT"],
        autocommit=True,
    )


def _terminate(pid: int) -> None:
    with _admin() as admin:
        admin.execute("SELECT pg_terminate_backend(%s)", (pid,))
        deadline = time.monotonic() + 5
        while admin.execute("SELECT 1 FROM pg_stat_activity WHERE pid = %s", (pid,)).fetchone():
            assert time.monotonic() < deadline, "the backend outlived pg_terminate_backend"
            time.sleep(0.01)


def _read_only(database: str, on: bool) -> None:
    """New sessions of ``database`` are read only, as the old writer's are during a switchover."""
    statement = "ALTER DATABASE {} SET default_transaction_read_only = on" if on else "ALTER DATABASE {} RESET default_transaction_read_only"
    with _admin() as admin:
        admin.execute(sql.SQL(statement).format(sql.Identifier(database)))


def _old_writer(hub) -> None:
    """``hub``'s database answers as the old writer does during a switchover: every new session is read only. The
    connection this thread already holds (the suite's client keeps it across requests) is closed, so the request opens
    one of those."""
    _read_only(hub.db_name, True)
    connections[hubs.HUB_A_ALIAS if hub.id == hubs.HUB_A_ID else hubs.HUB_B_ALIAS].close()


class CutOn:
    """Cuts the connection right before the statements that name ``table``: the next ``times`` (``None``: all of them)."""

    def __init__(self, table: str, times: int | None = 1) -> None:
        self.table = table
        self.times = times
        self.done = 0

    def __call__(self, execute, query, params, many, context):
        if self.table in str(query) and (self.times is None or self.done < self.times):
            self.done += 1
            _terminate(context["connection"].connection.info.backend_pid)
        return execute(query, params, many, context)


class Refused:
    """The first statement that writes opens the new sessions of ``database`` again, and is itself refused: this session
    stays read only, as a connection to the old writer does. Keeps the statements Postgres refused."""

    def __init__(self, database: str) -> None:
        self.database = database
        self.statements: list[str] = []

    def __call__(self, execute, query, params, many, context):
        statement = str(query).lstrip().upper()
        if statement.startswith(("INSERT", "UPDATE", "DELETE")) or "FOR UPDATE" in statement:
            _read_only(self.database, False)
        try:
            return execute(query, params, many, context)
        except DatabaseError:
            self.statements.append(str(query))
            raise


@pytest.fixture(autouse=True)
def quick_limit(settings, hub_a, hub_b):
    """The project's own setting with a short limit; never one the project does not ask for."""
    if (cut := settings.LIVE.get("database_cut")) is not None:
        settings.LIVE = {**settings.LIVE, "database_cut": {**cut, "wait_seconds": LIMIT_SECONDS}}
    yield
    # Before the tables are emptied: no business's database left read only, no connection this test cut.
    for hub in (hub_a, hub_b):
        _read_only(hub.db_name, False)
    connections.close_all()
    connections["default"].close_pool()


@pytest.fixture
def waits(monkeypatch):
    """Each wait of a request for the database, with the places of each business's plan in use at that moment: the
    waits of ``live.database_cut`` alone, from a sync route (``time.sleep``) or an async one (``asyncio.sleep``)."""
    seen: list[dict[str, int]] = []

    def places() -> None:
        seen.append({hub: limits.limiter_for(alias).in_use for hub, alias in (("a", hubs.HUB_A_ALIAS), ("b", hubs.HUB_B_ALIAS))})

    def sleep(seconds):
        places()
        time.sleep(seconds)

    async def asynchronous_sleep(seconds):
        places()
        await asyncio.sleep(seconds)

    monkeypatch.setattr(live_database_cut, "time", SimpleNamespace(monotonic=time.monotonic, sleep=sleep))
    monkeypatch.setattr(live_database_cut, "asyncio", SimpleNamespace(sleep=asynchronous_sleep))
    return seen


def _member(hub, username: str = "boss") -> Client:
    user = get_user_model().objects.create_user(username=username, password="pw")
    with context.use_hub(hub):
        Membership.objects.create(user=user, host=hub.slug, role="hub_admin")
    client = Client(raise_request_exception=False)
    client.force_login(user)
    return client


@pytest.fixture
def boss(hub_a):
    return _member(hub_a)


def _host(hub) -> str:
    return f"{hub.slug}.localhost"


def _create(client, hub, path: str, data: dict):
    return client.post(path, json.dumps(data), content_type="application/json", HTTP_HOST=_host(hub))


def _items(hub) -> list[str]:
    with context.use_hub(hub):
        return sorted(Item.objects.values_list("name", flat=True))


def _created_events(hub) -> int:
    with context.use_hub(hub):
        return OutboxEvent.objects.filter(name=ITEM_CREATED).count()


def _in(hub, alias: str, wrapper):
    """``wrapper`` around every statement of ``hub``'s alias in this thread, for the request the test makes next."""
    return connections[alias].execute_wrapper(wrapper)


def _assert_come_back(response, code: str) -> None:
    assert response.status_code == 503, response.content
    assert response.json()["error"]["code"] == code
    assert int(response["Retry-After"]) > 0
    assert "no-store" in response["Cache-Control"]


# --- Control's pool ---------------------------------------------------------------------------------------------------


def test_controls_pool_hands_out_no_connection_the_server_cut_while_it_was_idle(boss, hub_a, caplog):
    """Nothing waits, nothing fails: the business's read does not even notice that control's connection died."""
    assert boss.get(ITEMS, HTTP_HOST=_host(hub_a)).status_code == 200
    connections["default"].close()
    name = connections["default"].settings_dict["NAME"]
    with _admin() as admin:
        pids = admin.execute(
            "SELECT pid FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid()", (name,)
        ).fetchall()
    assert pids, "the pool keeps its connection: there has to be one to cut"
    for (pid,) in pids:
        _terminate(pid)
    caplog.clear()

    response = boss.get(ITEMS, HTTP_HOST=_host(hub_a))

    assert response.status_code == 200, response.content
    assert [record.getMessage() for record in caplog.records if record.name == "django.request"] == []


# --- Reads ------------------------------------------------------------------------------------------------------------


def test_a_read_cut_in_the_business_database_waits_and_answers(boss, hub_a):
    with context.use_hub(hub_a):
        Item.objects.create(name="Kept")
    cut = CutOn("demo_item")

    with _in(hub_a, hubs.HUB_A_ALIAS, cut):
        response = boss.get(ITEMS, HTTP_HOST=_host(hub_a))

    assert response.status_code == 200, response.content
    assert cut.done == 1
    assert [row["name"] for row in response.json()["rows"]] == ["Kept"]


@pytest.fixture
def unverified(monkeypatch):
    """The business's database is not yet known to be its own in this process: the request checks it first."""
    monkeypatch.setattr(identity, "_verified", set())


def test_a_cut_while_the_business_database_is_opened_waits_and_answers(boss, hub_a, unverified):
    """The first statement of a request on its database is the check that it is its own (``base.tenancy.identity``)."""
    cut = CutOn("base_hub_identity")

    with _in(hub_a, hubs.HUB_A_ALIAS, cut):
        response = boss.get(ITEMS, HTTP_HOST=_host(hub_a))

    assert response.status_code == 200, response.content
    assert cut.done == 1


def test_a_read_that_stays_cut_says_come_back_as_its_envelope(boss, hub_a):
    with _in(hub_a, hubs.HUB_A_ALIAS, CutOn("demo_item", times=None)):
        response = boss.get(ITEMS, HTTP_HOST=_host(hub_a))

    _assert_come_back(response, UNAVAILABLE)


def test_a_business_database_that_stays_cut_while_opened_says_come_back(boss, hub_a, unverified):
    """The same 503 as a business whose database cannot be reached (``base.hub_unavailable``), only after waiting."""
    started = time.monotonic()

    with _in(hub_a, hubs.HUB_A_ALIAS, CutOn("base_hub_identity", times=None)):
        response = boss.get(ITEMS, HTTP_HOST=_host(hub_a))

    _assert_come_back(response, HUB_UNAVAILABLE)
    assert time.monotonic() - started >= LIMIT_SECONDS


@pytest.mark.parametrize("language", ["en", "es"])
def test_a_page_that_stays_cut_says_come_back_in_the_language_of_the_visitor(hub_a, language):
    """With no control at all: the host's business is read before any page, so a page that needed it was a 500."""
    visitor = Client(raise_request_exception=False)

    with connections["default"].execute_wrapper(CutOn("", times=None)):
        response = visitor.get("/", HTTP_HOST=_host(hub_a), HTTP_ACCEPT="text/html", HTTP_ACCEPT_LANGUAGE=language)

    with translation.override(language):
        message = DatabaseCut(repeatable=True).message
    assert response.status_code == 503, response.content
    assert int(response["Retry-After"]) > 0
    assert "base/hub_maintenance.html" in [template.name for template in response.templates]
    assert message in response.content.decode()


# --- Writes -----------------------------------------------------------------------------------------------------------


def test_a_save_cut_while_reading_who_asks_goes_in_once(boss, hub_a):
    """Who asks (the session, the person, their role in the business, on control) is read inside the route, before its
    command: nothing of the save has started."""
    cut = CutOn("base_membership")

    with connections["default"].execute_wrapper(cut):
        response = _create(boss, hub_a, ITEMS, {"name": "Once"})

    assert response.status_code == 201, response.content
    assert cut.done == 1
    assert _items(hub_a) == ["Once"]
    assert _created_events(hub_a) == 1


def test_a_save_refused_as_read_only_goes_in_once(boss, hub_a):
    """The reference app's command touches nothing but its database (``repeatable=True``): the try the old writer
    refused is rolled back, and the next one, on a new session, goes in."""
    _old_writer(hub_a)
    refused = Refused(hub_a.db_name)

    with _in(hub_a, hubs.HUB_A_ALIAS, refused):
        response = _create(boss, hub_a, ITEMS, {"name": "Once"})

    assert response.status_code == 201, response.content
    assert refused.statements
    assert _items(hub_a) == ["Once"]
    assert _created_events(hub_a) == 1


def test_a_save_that_numbers_is_never_repeated_blindly(boss, hub_a):
    """A task is numbered (TSK-…): its command does not say it may run again, so a cut after it began asks to check."""
    _old_writer(hub_a)
    refused = Refused(hub_a.db_name)

    with _in(hub_a, hubs.HUB_A_ALIAS, refused):
        response = _create(boss, hub_a, TASKS, {"title": "Never twice"})

    _assert_come_back(response, UNKNOWN)
    assert len(refused.statements) == 1
    with context.use_hub(hub_a):
        assert not Task.objects.exists()


def test_a_wait_holds_no_place_of_the_business_plan(boss, hub_a, waits):
    """Free gives one transaction at once: a request holding it while it waits would refuse every other one."""
    _old_writer(hub_a)

    with _in(hub_a, hubs.HUB_A_ALIAS, Refused(hub_a.db_name)):
        response = _create(boss, hub_a, ITEMS, {"name": "Once"})

    assert waits, "the save waited for the database"
    assert all(places == {"a": 0, "b": 0} for places in waits), waits
    assert response.status_code == 201, response.content


def test_a_cut_in_one_business_repeats_in_its_own_database_only(boss, hub_a, hub_b, waits):
    """Its old writer refuses ``a``'s writes: ``a``'s save waits and goes in ``a``; ``b``'s, a moment later, at once."""
    other = _member(hub_b, username="other")
    _old_writer(hub_a)

    with _in(hub_a, hubs.HUB_A_ALIAS, Refused(hub_a.db_name)):
        in_a = _create(boss, hub_a, ITEMS, {"name": "In a"})
    waited_for_a = len(waits)
    in_b = _create(other, hub_b, ITEMS, {"name": "In b"})

    assert (in_a.status_code, in_b.status_code) == (201, 201), (in_a.content, in_b.content)
    assert waited_for_a > 0
    assert len(waits) == waited_for_a
    assert (_items(hub_a), _items(hub_b)) == (["In a"], ["In b"])
    assert (_created_events(hub_a), _created_events(hub_b)) == (1, 1)


# --- What tries again on its own --------------------------------------------------------------------------------------


def test_a_call_of_the_saas_gets_its_503_at_once(hub_a, settings):
    """``/internal`` is the SaaS's, which tries again on its own: it waits for nobody, with ``Retry-After`` all the same."""
    if (cut := settings.LIVE.get("database_cut")) is not None:
        settings.LIVE = {**settings.LIVE, "database_cut": {**cut, "wait_seconds": 5}}
    started = time.monotonic()

    with connections["default"].execute_wrapper(CutOn("base_hub", times=None)):
        response = signed(Client(raise_request_exception=False), "get", f"/internal/hubs/{hub_a.id}", b"")

    _assert_come_back(response, UNAVAILABLE)
    assert time.monotonic() - started < 2
