"""A hub's database as it was at a moment, made aside on its own cluster while the business goes on (hub#1213, layer 1;
BASE-F114).

``control.hub.restore_aside`` asks (a ``RestoredCopy`` row, ``<control>_copy_<its hex>``); the worker makes it
(``base.tenancy.restore.run_aside_due``, in the moves' thread), one a pass, under the row's own lease, never the hub's:

1. the hub's copy is dumped from the temporary cluster (a point-in-time restore of its cluster, closed to new hubs);
2. on the hub's cluster a new database of the row's name is cloned from its vertical's template, granted to nobody,
   emptied, filled with the dump's ``pg_restore`` and its identity checked (it says it is this hub);
3. control notes it made, and lets the temporary cluster go.

The business is never closed nor changed: it is not restored, so its fiscal records are never compared and a
production VeriFactu record made after the moment stops nothing. In the copy, nothing reaches the tax authority, by
construction: it is no business (no row of ``base_hub`` names it, the worker never serves it), it is closed to the
app's roles, and its name is one of a copy left behind, which no process registers an alias for. Any failure drops what
it made and notes why on the row. The copies go after ``move.MOVED_COPY_DAYS``, with their rows, in the moves' pass.

Real databases on the session's server, as ``test_restore.py``: the temporary cluster's row points at it, so the hub's
copy there has a name of its own (``run_aside_due(source=…)``).
"""

import copy as copying
import datetime as dt
import ipaddress
import socket
import uuid

import pytest
from django.utils import timezone

from base import registry, services
from base.tenancy import connections as tenancy_connections
from base.tenancy import identity, move, names, restore
from base.tenancy.context import use_control
from base.tenancy.tests import hubs
from base.tenancy.tests.test_restore import AFTER, AS_THEN, SINCE, THEN, Restores, a_record
from control.models import Cluster, Hub, MovedCopy, RestoredCopy

pytestmark = pytest.mark.usefixtures("no_test_fallback")

AT = dt.datetime(2026, 11, 12, 9, 0, tzinfo=dt.UTC)

databases, marker, says_it_is = hubs.control_databases, hubs.marker, hubs.says_it_is


@pytest.fixture(autouse=True)
def nothing_checked_yet(monkeypatch):
    monkeypatch.setattr(identity, "_verified", set())


@pytest.fixture(autouse=True)
def off_the_machine(monkeypatch):
    """Every connection this process opens to anything but this machine, recorded and refused: the AEAT (of testing or
    of production) and ERPlora's gateway among them. A copy aside never opens one."""
    opened: list[tuple] = []
    connect = socket.socket.connect

    def here(host: str) -> bool:
        try:
            return ipaddress.ip_address(host).is_loopback
        except ValueError:  # a name: only this machine's
            return host == "localhost"

    def only_here(sock, address):
        if sock.family in (socket.AF_INET, socket.AF_INET6) and not here(address[0]):
            opened.append(address)
            raise ConnectionRefusedError(f"a copy aside opened a connection to {address}")
        return connect(sock, address)

    monkeypatch.setattr(socket.socket, "connect", only_here)
    return opened


class Asides(Restores):
    """The rows and databases of one test (``test_restore.Restores``'): each hub's own database says ``AS_THEN`` and
    ``SINCE``, its copy on the temporary cluster only ``AS_THEN``."""

    def aside(self, hub: Hub, source: Cluster | None, **fields) -> RestoredCopy:
        """A copy aside of ``hub`` asked from ``source``, as ``control.hub.restore_aside`` writes it."""
        copy_id = uuid.uuid7()
        values = {
            "id": copy_id,
            "hub": hub,
            "cluster": hub.cluster,
            "source": source,
            "restore_point": THEN,
            "db_name": names.copy_db_name(tenancy_connections.control_name(), copy_id),
            "asked_by": "root",
        }
        return RestoredCopy.objects.create(**(values | fields))


@pytest.fixture
def asides(django_db_blocker, hub_databases):
    with django_db_blocker.unblock():
        made = Asides(hub_databases.template)
        yield made
        made.clean()


@pytest.fixture
def app_role(asides):
    with hubs.an_app_role() as role:
        yield role


def fresh(row: RestoredCopy) -> RestoredCopy:
    return RestoredCopy.objects.get(pk=row.pk)


def run(asides: Asides, now: dt.datetime = AT, **kwargs) -> int:
    with use_control():
        return restore.run_aside_due(now, source=asides.source, **kwargs)


def a_hub_with_its_copy(asides: Asides, **fields) -> tuple[Hub, RestoredCopy]:
    hub = asides.hub(source=None, **fields)
    return hub, asides.aside(hub, asides.cluster())


class TestACopyAside:
    def test_the_copy_has_the_moments_data_and_the_business_is_never_closed_nor_changed(
        self, asides, app_role, monkeypatch
    ):
        hub, aside = a_hub_with_its_copy(asides)
        hubs.grant_connect(app_role, hub.db_name)
        meanwhile: list[tuple[bool, bool]] = []
        real = move._restore

        def restoring(path, name, cluster, heartbeat, cancelled=None):
            # While the copy is filled, the business is open: its host answers and the app reaches its database.
            meanwhile.append((registry.is_copying(Hub.objects.get(pk=hub.pk)), hubs.reaches(app_role, hub.db_name)))
            return real(path, name, cluster, heartbeat, cancelled)

        monkeypatch.setattr(move, "_restore", restoring)

        assert run(asides, roles=hubs.app_roles(app_role)) == 1

        assert meanwhile == [(False, True)]
        made = fresh(aside)
        assert (made.status, made.made_at, made.source_id, made.last_error) == ("made", AT, None, "")
        assert (made.lease_owner, made.lease_until) == ("", None)
        assert marker(made.db_name) == [AS_THEN] and says_it_is(made.db_name) == [hub.id]
        # The business as it was, on its own database; the temporary cluster's copy only read.
        row = Hub.objects.get(pk=hub.pk)
        assert (row.status, row.db_name, row.cluster_id, row.restoring_from_id, row.last_error) == (
            "ready",
            hub.db_name,
            None,
            None,
            "",
        )
        assert marker(hub.db_name) == [AS_THEN, SINCE]
        assert marker(asides.copies[hub.id]) == [AS_THEN]
        assert not MovedCopy.objects.filter(hub=hub).exists()

    def test_a_hub_on_a_cluster_gets_its_copy_on_it(self, asides):
        own = asides.cluster("own", is_open=True)
        hub = asides.hub(source=None, cluster=own)
        aside = asides.aside(hub, asides.cluster())
        assert aside.cluster_id == own.pk

        run(asides)

        assert fresh(aside).status == "made" and marker(aside.db_name) == [AS_THEN]

    def test_one_copy_a_pass_the_longest_asked_first(self, asides):
        first = a_hub_with_its_copy(asides)[1]
        second = a_hub_with_its_copy(asides)[1]

        assert run(asides) == 1

        assert (fresh(first).status, fresh(second).status) == ("made", "copying")
        assert aside_absent(second)

    def test_nothing_asked_nothing_done(self, asides):
        hub = asides.hub(source=None)

        assert run(asides) == 0

        assert marker(hub.db_name) == [AS_THEN, SINCE]

    def test_a_copy_whose_lease_another_worker_holds_is_left_to_it(self, asides):
        aside = a_hub_with_its_copy(asides)[1]
        RestoredCopy.objects.filter(pk=aside.pk).update(
            lease_owner="other:1", lease_until=timezone.now() + dt.timedelta(minutes=1)
        )

        assert run(asides) == 0

        assert fresh(aside).status == "copying" and aside_absent(aside)

    def test_its_lease_is_its_own_never_the_hubs(self, asides, monkeypatch):
        # The business goes on meanwhile: its apps' setup and data work, under the hub's lease, never wait for its copy.
        hub, aside = a_hub_with_its_copy(asides)
        held: list[tuple[bool, str]] = []
        real = move._restore

        def restoring(path, name, cluster, heartbeat, cancelled=None):
            held.append((services.claim_hub(hub.id, timezone.now(), restore.LEASE, owner="other:1") is not None,
                         fresh(aside).lease_owner))
            services.release_hub(hub.id, timezone.now(), owner="other:1")
            return real(path, name, cluster, heartbeat, cancelled)

        monkeypatch.setattr(move, "_restore", restoring)

        run(asides)

        assert held == [(True, services.LEASE_OWNER)]


def aside_absent(aside: RestoredCopy) -> bool:
    return aside.db_name not in databases()


class TestSendingToTheTaxAuthorityIsOffInTheCopy:
    """BLOCKING (fiscal): a copy aside of a business that files with VeriFactu in production holds its production
    records and settings as they were, so a copy any process could serve would file them again with the AEAT. It never
    can: none of these may ever fail."""

    def test_the_guard_refuses_a_connection_off_this_machine(self, off_the_machine):
        """Positive control of ``off_the_machine``: a connection to an address off this machine is caught."""
        with pytest.raises(ConnectionRefusedError):
            socket.create_connection(("192.0.2.1", 443), timeout=1)
        assert off_the_machine == [("192.0.2.1", 443)]

    def test_production_records_after_the_moment_stop_nothing_and_stay_as_they_are(self, asides, off_the_machine):
        hub = asides.hub(source=None)
        # The business filed after the moment (what makes a restore in place refuse it); its copy holds one to send.
        made_after = a_record(hub.db_name, created_at=AFTER, updated_at=AFTER)
        to_send = a_record(asides.copies[hub.id], status="pending")
        aside = asides.aside(hub, asides.cluster())

        assert run(asides) == 1

        assert fresh(aside).status == "made"
        assert record_states(hub.db_name) == {made_after: "accepted"}
        assert record_states(aside.db_name) == {to_send: "pending"}
        assert off_the_machine == []

    def test_the_copy_is_no_business_any_process_serves_reaches_or_registers(self, asides, app_role):
        hub, aside = a_hub_with_its_copy(asides)
        a_record(asides.copies[hub.id], status="pending")
        hubs.grant_connect(app_role, hub.db_name)

        run(asides, roles=hubs.app_roles(app_role))

        name = fresh(aside).db_name
        # No row of the registry names it, so the worker never serves it (VeriFactu's queue runs on the hubs served).
        assert not Hub.objects.filter(db_name=name).exists()
        with use_control():
            assert name not in {served.db_name for served in services.hubs_to_serve(timezone.now())}
        # The app's roles do not reach it (they still reach the business's own database).
        assert (hubs.reaches(app_role, name), hubs.reaches(app_role, hub.db_name)) == (False, True)
        # Nor does any process of the app: even a row that named it would get no alias of it.
        named_it = copying.copy(Hub.objects.get(pk=hub.pk))
        named_it.db_name = name
        with pytest.raises(names.InvalidDatabaseName):
            tenancy_connections.register_hub_alias(named_it)

    def test_the_copy_is_granted_to_no_role_even_on_a_template_granted_to_the_app(self, asides, app_role):
        # The clone of a template keeps none of its grants, and the copy is granted to nobody (PUBLIC included).
        hubs.grant_connect(app_role, asides.template)
        try:
            aside = a_hub_with_its_copy(asides)[1]
            run(asides, roles=hubs.app_roles(app_role))
            assert not hubs.reaches(app_role, fresh(aside).db_name)
        finally:
            with hubs._maintenance() as conn:
                from psycopg import sql

                conn.execute(
                    sql.SQL("REVOKE ALL ON DATABASE {} FROM {}").format(
                        sql.Identifier(asides.template), sql.Identifier(app_role)
                    )
                )


    def test_the_clone_is_granted_to_no_role_even_when_the_apps_are_given(self, asides, app_role):
        # The first barrier on its own: ``ops.clone_database(aside=True)`` leaves the copy to its owner alone.
        from base.tenancy import ops

        name = names.copy_db_name(tenancy_connections.control_name(), uuid.uuid7())
        ops.clone_database(name, template=asides.template, roles=hubs.app_roles(app_role), aside=True)

        assert not hubs.reaches(app_role, name)
        with pytest.raises(names.InvalidDatabaseName):
            ops.clone_database(f"{tenancy_connections.control_name()}_old_{uuid.uuid7().hex}", template=asides.template,
                               aside=True)

    def test_a_copy_its_clone_left_open_is_closed_before_it_is_noted_made(self, asides, app_role, monkeypatch):
        # The second barrier on its own: a server whose new databases came open to the app still ends with it closed.
        from base.tenancy import ops

        real = ops.clone_database

        def left_open(name, **kwargs):
            made = real(name, **kwargs)
            hubs.grant_connect(app_role, name)
            return made

        monkeypatch.setattr(ops, "clone_database", left_open)
        aside = a_hub_with_its_copy(asides)[1]

        run(asides, roles=hubs.app_roles(app_role))

        assert fresh(aside).status == "made" and not hubs.reaches(app_role, aside.db_name)


def record_states(name: str) -> dict[uuid.UUID, str]:
    with hubs._maintenance(name) as conn:
        return {row[0]: row[1] for row in conn.execute("SELECT id, status FROM verifactu_record")}


class TestAFailureDropsWhatItMade:
    @pytest.mark.parametrize(
        "step, code",
        [("_dump", "restore_aside_dump_failed"), ("_restore", "restore_aside_restore_failed")],
    )
    def test_the_row_says_why_and_nothing_of_the_copy_is_left(self, asides, monkeypatch, step, code):
        hub, aside = a_hub_with_its_copy(asides)

        def broken(*args, **kwargs):
            raise move.MoveFailed(f"move_{code.removeprefix('restore_aside_')}", "it broke on purpose")

        monkeypatch.setattr(move, step, broken)

        assert run(asides) == 1

        failed = fresh(aside)
        assert (failed.status, failed.last_error, failed.source_id, failed.made_at) == (
            "failed",
            f"{code}: it broke on purpose",
            None,
            None,
        )
        assert (failed.lease_owner, failed.lease_until) == ("", None)
        assert aside_absent(aside)
        assert marker(hub.db_name) == [AS_THEN, SINCE] and Hub.objects.get(pk=hub.pk).last_error == ""

    def test_a_copy_that_says_it_is_another_hub_is_refused(self, asides):
        hub, aside = a_hub_with_its_copy(asides)
        with hubs._maintenance(asides.copies[hub.id]) as conn:
            conn.execute("UPDATE base_hub_identity SET hub_id = %s", [uuid.uuid7()])

        run(asides)

        assert fresh(aside).last_error.startswith("restore_aside_identity_mismatch: it says it is")
        assert aside_absent(aside)

    def test_a_copy_missing_on_the_temporary_cluster_fails_it_with_why(self, asides):
        hub, aside = a_hub_with_its_copy(asides)
        hubs.drop_database(asides.copies[hub.id])

        run(asides)

        assert fresh(aside).status == "failed"
        assert fresh(aside).last_error.startswith("restore_aside_dump_failed:")
        assert marker(hub.db_name) == [AS_THEN, SINCE]

    def test_one_left_without_its_temporary_cluster_fails_with_why(self, asides):
        aside = asides.aside(asides.hub(source=None), None)

        run(asides)

        assert fresh(aside).last_error == "restore_aside_source_missing: its temporary cluster is gone"
        assert aside_absent(aside)


class TestTwoWorkers:
    def test_a_lease_lost_meanwhile_leaves_the_copy_to_its_new_holder(self, asides, monkeypatch):
        aside = a_hub_with_its_copy(asides)[1]
        real = move._restore

        def taken(path, name, cluster, heartbeat, cancelled=None):
            real(path, name, cluster, heartbeat, cancelled)
            RestoredCopy.objects.filter(pk=aside.pk).update(lease_owner="other:1")

        monkeypatch.setattr(move, "_restore", taken)

        run(asides)

        left = fresh(aside)
        assert (left.status, left.lease_owner, left.made_at) == ("copying", "other:1", None)
        # Its new holder's: never dropped here.
        assert marker(aside.db_name) == [AS_THEN]

    def test_a_copy_cut_short_is_made_anew_on_the_next_pass(self, asides):
        hub, aside = a_hub_with_its_copy(asides)
        # A worker died after its clone: a database of the copy's name with something else in it, its lease run out.
        with hubs._maintenance() as conn:
            from psycopg import sql

            control = tenancy_connections.control_name()
            conn.execute(
                sql.SQL("CREATE DATABASE {} TEMPLATE {}").format(
                    names.identifier(aside.db_name, control=control), names.identifier(hub.db_name, control=control)
                )
            )
        with hubs._maintenance(aside.db_name) as conn:
            conn.execute("CREATE SCHEMA left_over")
        RestoredCopy.objects.filter(pk=aside.pk).update(
            lease_owner="gone:1", lease_until=timezone.now() - dt.timedelta(seconds=1)
        )

        run(asides)

        assert fresh(aside).status == "made" and marker(aside.db_name) == [AS_THEN]
        # Made anew from the template: nothing of what was there is left, not only its tables.
        with hubs._maintenance(aside.db_name) as conn:
            assert not conn.execute("SELECT 1 FROM pg_namespace WHERE nspname = 'left_over'").fetchone()


class TestTheCopiesGoAfterTheirDays:
    def test_a_copy_past_its_days_is_dropped_with_its_row_by_the_moves_pass(self, asides):
        hub, aside = a_hub_with_its_copy(asides)
        run(asides)

        with use_control():
            restore.drop_old_aside_copies(AT + dt.timedelta(days=move.MOVED_COPY_DAYS) - dt.timedelta(minutes=1))
        assert aside.db_name in databases()

        with use_control():
            assert restore.drop_old_aside_copies(AT + dt.timedelta(days=move.MOVED_COPY_DAYS)) == 1
        assert aside_absent(aside) and not RestoredCopy.objects.filter(pk=aside.pk).exists()
        assert marker(hub.db_name) == [AS_THEN, SINCE]

    def test_a_failed_one_is_forgotten_after_its_days_and_one_still_to_make_never(self, asides, monkeypatch):
        failed = a_hub_with_its_copy(asides)[1]
        RestoredCopy.objects.filter(pk=failed.pk).update(
            status=RestoredCopy.Status.FAILED, source=None, last_error="restore_aside_dump_failed: x"
        )
        waiting = a_hub_with_its_copy(asides)[1]

        with use_control():
            restore.drop_old_aside_copies(timezone.now() + dt.timedelta(days=move.MOVED_COPY_DAYS))

        assert not RestoredCopy.objects.filter(pk=failed.pk).exists()
        assert fresh(waiting).status == "copying"

    def test_the_worker_makes_and_drops_them_in_its_moves_pass(self, asides, monkeypatch):
        from base import worker

        made = a_hub_with_its_copy(asides)[1]
        old = a_hub_with_its_copy(asides)[1]
        monkeypatch.setattr(restore, "source_name", asides.source)

        worker._moves(AT)
        RestoredCopy.objects.filter(pk=made.pk).update(made_at=AT - dt.timedelta(days=move.MOVED_COPY_DAYS))
        worker._moves(AT)

        assert not RestoredCopy.objects.filter(pk=made.pk).exists() and aside_absent(made)
        assert fresh(old).status == "made" and marker(old.db_name) == [AS_THEN]


# ── Asked in the Hub admin (BASE-F114) ────────────────────────────────────────────────────────────────────────────────

PLATFORM = "hubs.localhost:8000"
HUBS = "/admin/control/hub/"
COPIES = "/admin/control/restoredcopy/"


def staff(client, *, superuser: bool):
    from django.contrib.auth import get_user_model

    with use_control():
        model = get_user_model()
        name = f"staff-{uuid.uuid4().hex[:8]}"
        if superuser:
            user = model.objects.create_superuser(username=name, password="pw")
        else:
            # Support, as its sign-in makes it: staff in the group with every ``view_*`` permission.
            user = model.objects.create_user(username=name, password="pw", is_staff=True)
            user.groups.add(services._support_group())
        client.force_login(user)
    return user


@pytest.fixture
def signed_in(client, asides):
    """The test client on the Hub admin; ``signed_in(superuser=…)`` signs a platform admin or support in, committed as
    the rows are, and they, their sessions and the events their requests recorded go after the test."""
    from live.models import OutboxEvent

    users = []

    def sign_in(*, superuser: bool = True):
        users.append(staff(client, superuser=superuser))
        return client

    yield sign_in
    with use_control():
        client.logout()
        OutboxEvent.objects.filter(payload__hub__in=[str(hub.pk) for hub in asides.hubs]).delete()
        for user in users:
            user.delete()


class TestAskedInTheHubAdmin:
    """The flow end to end: a platform admin asks it with «Restore to a separate copy…»
    (``control.hub.restore_aside``), the worker's pass makes it, and the Hub admin lists it, made, with its moment."""

    @staticmethod
    def ask(client, hub: Hub, temporary: Cluster):
        data = {
            "action": "restore_aside",
            "_selected_action": [str(hub.pk)],
            "apply": "yes",
            "cluster": str(temporary.pk),
            "at": THEN.isoformat(),
        }
        return client.post(HUBS, data, HTTP_HOST=PLATFORM, follow=True)

    def test_the_copy_is_made_and_listed_while_the_business_stays_open(self, asides, signed_in):
        client = signed_in()
        hub = asides.hub(source=None)
        a_record(hub.db_name, created_at=AFTER, updated_at=AFTER)

        answer = self.ask(client, hub, asides.cluster()).content.decode()
        assert "will get a separate copy" in answer
        [aside] = RestoredCopy.objects.filter(hub=hub)
        assert run(asides) == 1

        assert marker(aside.db_name) == [AS_THEN] and marker(hub.db_name) == [AS_THEN, SINCE]
        listed = client.get(COPIES, HTTP_HOST=PLATFORM)
        assert listed.status_code == 200
        page = listed.content.decode()
        assert hub.slug in page and "2026-11-09" in page and "Made" in page
        assert aside.db_name in client.get(f"{COPIES}{aside.pk}/change/", HTTP_HOST=PLATFORM).content.decode()

    def test_support_sees_the_copies_but_cannot_ask_one(self, asides, signed_in):
        client = signed_in(superuser=False)
        hub = asides.hub(source=None)
        asides.aside(hub, asides.cluster())

        page = client.get(HUBS, HTTP_HOST=PLATFORM).content.decode()
        assert 'value="restore_aside"' not in page
        assert client.get(COPIES, HTTP_HOST=PLATFORM).status_code == 200
        self.ask(client, hub, asides.cluster())
        assert RestoredCopy.objects.filter(hub=hub).count() == 1
