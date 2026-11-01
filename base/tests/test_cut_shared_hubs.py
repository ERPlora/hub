"""``manage.py cut_shared_hubs``: the cut of S5, every business still on control's database given its own.

Phase 1 kept every business in control's database (``Hub.db_name`` empty). The cut gives each one, by name, a mode:
``--copy-all`` (its database, cloned from its template, with every row control's tables of the hubs' apps hold copied
into it: in production those tables hold one business's data in practice; only once, for one hub), ``--recreate`` (its
database from its template, seeded from the SaaS's photo, nothing copied) or ``--skip`` (a cancelled business, left
without one). ``--dry-run`` says what each would get. Before the first cut, a copy of control goes to the dumps bucket
(``<control>/<time>-cut.dump``), refused without one unless ``--no-dump``. While a business is cut its host answers 503;
a business already with its own database is left alone, and a cut that broke is done again from the start.

These tests make real databases next to the session's (``base/tenancy/tests/hubs.py``) and read control's tables of the
hubs' apps from another connection, so they write committed rows (no test case; ``django_db_blocker``) and clean up.
"""

import datetime as dt
import io
import subprocess
import uuid
from types import SimpleNamespace

import pytest
from django.core.management import CommandError, call_command
from django.test import Client
from django.utils import timezone
from live.models import OutboxEvent

from apps.printing.models import PrintDevice, Printer, Usage
from base.models import AppActivation, EventDelivery, HubUser
from base.tenancy import connections as tenancy_connections
from base.tenancy import cut, identity, names
from base.tenancy.context import use_control, use_hub
from base.tenancy.tests import hubs
from base.tenancy.tests.legacy import use_legacy
from base.tenancy.tests.s3 import aws_test_credentials, body, dumps_bucket, moto_s3, no_dumps_bucket, objects  # noqa: F401
from control.models import Hub

pytestmark = pytest.mark.usefixtures("no_test_fallback")

ALICE = uuid.UUID("01a17000-0000-7000-8000-0000000000a1")
PRINTER = {"kind": Printer.Kind.NETWORK, "address": "10.0.0.9", "port": 9100, "usage": Usage.choices[0][0]}


@pytest.fixture(autouse=True, scope="session")
def on_the_tests_control_database(django_db_setup):
    """These tests make and drop real databases next to control's: only ever the tests' own (as test_provision)."""
    from django.conf import settings

    control = tenancy_connections.control_name()
    if not control.startswith(settings.DATABASES["default"]["TEST"]["NAME"]):
        pytest.fail(f"The control database is {control!r}, not the tests': run this module whole, not one test of it.")


@pytest.fixture(autouse=True)
def nothing_checked_yet(monkeypatch):
    monkeypatch.setattr(identity, "_verified", set())


@pytest.mark.django_db
def test_the_module_sets_the_tests_databases_up():
    """pytest-django sets the test databases up only for a session with a ``django_db`` test: this one."""
    assert tenancy_connections.control_name().startswith("test_")


def photo(*members: uuid.UUID) -> dict:
    return {
        "members": [
            {"user_id": str(member), "role": "hub_owner", "email": "alice@example.com", "name": "Alice"}
            for member in members
        ]
    }


@pytest.fixture
def phase_one(django_db_blocker, hub_databases):
    """Businesses of phase 1 (``db_name=""``) and rows of their apps in control's tables, committed; deleted after the
    test with every database the cut made and every event it recorded."""
    started = timezone.now()
    made: list[Hub] = []
    control = tenancy_connections.control_name()

    def business(name: str, *, status: str = Hub.Status.READY, members=(ALICE,), **fields) -> Hub:
        hub_id = uuid.uuid7()
        values = {
            "id": hub_id,
            "slug": f"{name}-{hub_id.hex[-8:]}",
            "status": status,
            "db_name": "",
            "vertical": hubs.TEMPLATE_VERTICAL,
            "ready_at": started,
            "state": photo(*members),
            "state_version": 1,
            "cancelled_at": started if status == Hub.Status.CANCELLED else None,
        }
        made.append(row := Hub.objects.create(**(values | fields)))
        return row

    def rows_of(slug: str) -> SimpleNamespace:
        """A printer reached by a device (a many-to-many row with a serial key), a person, the apps' rows and two
        events: one of ``slug`` and one of another business; all in control's tables, as phase 1 kept them."""
        with use_legacy():
            printer = Printer.objects.create(name=f"Bar {slug}", **PRINTER)
            device = PrintDevice.objects.create(name=f"Till {slug}")
            device.printers.add(printer)
            person = HubUser.objects.create(username=f"saas:{uuid.uuid7()}", name="Bob", account_id=uuid.uuid7())
            AppActivation.objects.create(host=slug, app="printing", state="on", chosen=True)
            own = OutboxEvent.objects.create(scope_kind="host", scope_key=slug, name="printing.printer.created")
            delivery = EventDelivery.objects.create(event=own, app_label="flow", next_attempt_at=timezone.now())
            other = OutboxEvent.objects.create(scope_kind="host", scope_key="elsewhere", name="printing.printer.created")
        return SimpleNamespace(printer=printer, device=device, person=person, own=own, delivery=delivery, other=other)

    with django_db_blocker.unblock():
        yield SimpleNamespace(business=business, rows_of=rows_of)
        with hubs._maintenance() as conn:
            for row in made:
                hubs._drop(conn, names.hub_db_name(control, row.id), control)
        with use_legacy():
            OutboxEvent.objects.filter(created_at__gte=started).delete()
            for model in (AppActivation, HubUser, PrintDevice, Printer):
                model.objects.all().delete()
        Hub.objects.filter(pk__in=[row.pk for row in made]).delete()
        with use_control():
            OutboxEvent.objects.filter(created_at__gte=started).delete()


def run(*args: str) -> str:
    out = io.StringIO()
    call_command("cut_shared_hubs", *args, stdout=out)
    return out.getvalue()


def fresh(hub: Hub) -> Hub:
    return Hub.objects.select_related("cluster").get(pk=hub.pk)


def databases() -> set[str]:
    control = tenancy_connections.control_name()
    with hubs._maintenance() as conn:
        return {row[0] for row in conn.execute("SELECT datname FROM pg_database") if row[0].startswith(control)}


# ── The two businesses of production: one gets control's rows, one is made again; a cancelled one is skipped ───────


def test_copy_all_gives_a_business_its_database_with_every_row_of_controls_tables_and_its_own_events(phase_one):
    aurora = phase_one.business("aurora")
    rows = phase_one.rows_of(aurora.slug)

    said = run("--copy-all", aurora.slug, "--no-dump")

    aurora = fresh(aurora)
    assert aurora.db_name == names.hub_db_name(tenancy_connections.control_name(), aurora.id)
    assert aurora.status == Hub.Status.READY and aurora.schema_state == Hub.SchemaState.CURRENT
    assert {"base", "printing"} <= set(aurora.schema_apps)
    with use_hub(aurora):
        printer = Printer.objects.get(pk=rows.printer.pk)
        assert printer.name == rows.printer.name
        assert list(PrintDevice.objects.get(pk=rows.device.pk).printers.all()) == [printer]
        assert HubUser.objects.filter(pk=rows.person.pk).exists()
        assert AppActivation.objects.get(host=aurora.slug, app="printing").state == "on"
        # Its own events, with their deliveries, go with it; another business's stay behind.
        assert set(OutboxEvent.objects.values_list("pk", flat=True)) >= {rows.own.pk}
        assert not OutboxEvent.objects.filter(pk=rows.other.pk).exists()
        assert EventDelivery.objects.get(pk=rows.delivery.pk).event_id == rows.own.pk
        # The serial key of a many-to-many table goes on after the rows copied: a new link is no clash.
        PrintDevice.objects.create(name="Kitchen").printers.add(printer)
        # The SaaS's photo is applied over what was copied.
        assert HubUser.objects.get(account_id=ALICE).is_active
    assert f"{aurora.slug}: copy-all done" in said
    with use_control():
        cut_event = OutboxEvent.objects.get(name="base.hub.cut", payload__slug=aurora.slug)
    assert cut_event.payload["mode"] == cut.COPY_ALL
    assert cut_event.payload["copied"]["printing_printer"] >= 1


def test_recreate_gives_a_business_an_empty_database_from_its_template_and_the_saas_photo(phase_one):
    elpa = phase_one.business("elpa")
    rows = phase_one.rows_of(elpa.slug)

    said = run("--recreate", elpa.slug, "--no-dump")

    elpa = fresh(elpa)
    assert elpa.db_name == names.hub_db_name(tenancy_connections.control_name(), elpa.id)
    assert elpa.status == Hub.Status.READY and elpa.schema_state == Hub.SchemaState.CURRENT
    with use_hub(elpa):
        assert not Printer.objects.exists()
        assert not OutboxEvent.objects.filter(pk=rows.own.pk).exists()
        assert list(HubUser.objects.values_list("account_id", flat=True)) == [ALICE]
    assert f"{elpa.slug}: recreate done" in said
    with use_control():
        assert OutboxEvent.objects.get(name="base.hub.cut", payload__slug=elpa.slug).payload["copied"] == {}


def test_a_cancelled_business_is_skipped_without_a_database_and_both_others_are_cut_in_one_run(phase_one):
    aurora, elpa = phase_one.business("aurora"), phase_one.business("elpa")
    gone = phase_one.business("yfn", status=Hub.Status.CANCELLED)
    phase_one.rows_of(aurora.slug)
    before = databases()

    said = run("--copy-all", aurora.slug, "--recreate", elpa.slug, "--skip", gone.slug, "--no-dump")

    assert fresh(gone).db_name == "" and fresh(gone).status == Hub.Status.CANCELLED
    assert databases() - before == {fresh(aurora).db_name, fresh(elpa).db_name}
    assert f"{gone.slug}: skipped" in said
    with use_hub(fresh(elpa)):
        assert not Printer.objects.exists()


# ── What it refuses: nothing is cut then ──────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("status", "mode", "why"),
    [
        (Hub.Status.CANCELLED, "--recreate", "only a ready business is cut"),
        (Hub.Status.CANCELLED, "--copy-all", "only a ready business is cut"),
        (Hub.Status.READY, "--skip", "only a cancelled business is skipped"),
    ],
)
def test_a_mode_its_status_does_not_take_is_refused_and_nothing_is_cut(phase_one, status, mode, why):
    hub = phase_one.business("odd", status=status)
    other = phase_one.business("fine")
    before = databases()

    with pytest.raises(CommandError, match=why):
        run(mode, hub.slug, "--recreate", other.slug, "--no-dump")

    assert databases() == before
    assert fresh(other).db_name == ""


def test_an_unknown_business_a_demo_and_one_named_twice_are_refused(phase_one):
    hub = phase_one.business("named")
    demo = phase_one.business("demo", is_demo=True, expires_at=timezone.now() + dt.timedelta(hours=1))

    with pytest.raises(CommandError, match="no business"):
        run("--recreate", "nobody-here", "--no-dump")
    with pytest.raises(CommandError, match="a demo is not cut"):
        run("--recreate", demo.slug, "--no-dump")
    with pytest.raises(CommandError, match="named more than once"):
        run("--recreate", hub.slug, "--skip", hub.slug, "--no-dump")
    with pytest.raises(CommandError, match="no business to cut"):
        run("--no-dump")
    assert fresh(hub).db_name == ""


def test_control_s_rows_are_copied_only_once_into_one_business(phase_one):
    first, second = phase_one.business("first"), phase_one.business("second")
    run("--copy-all", first.slug, "--no-dump")

    with pytest.raises(CommandError, match=f"already went to {first.slug}"):
        run("--copy-all", second.slug, "--no-dump")
    assert fresh(second).db_name == ""


# ── The dry run, and running it again ─────────────────────────────────────────────────────────────────────────────


def test_the_dry_run_says_each_business_s_mode_tables_and_rows_and_writes_nothing(phase_one, dumps_bucket, moto_s3):
    aurora, elpa = phase_one.business("aurora"), phase_one.business("elpa")
    gone, left = phase_one.business("yfn", status=Hub.Status.CANCELLED), phase_one.business("left")
    phase_one.rows_of(aurora.slug)
    before = databases()

    said = run("--dry-run", "--copy-all", aurora.slug, "--recreate", elpa.slug, "--skip", gone.slug)

    assert f"{aurora.slug} (ready): copy-all" in said
    assert "printing_printer: 1" in said and "base_hubuser: 1" in said
    # Only its own events and their deliveries: the other business's event stays in control.
    assert "live_outboxevent: 1" in said and "base_eventdelivery: 1" in said
    assert f"{elpa.slug} (ready): recreate, nothing copied" in said
    assert f"{gone.slug} (cancelled): skip" in said
    assert f"{left.slug} (ready): no mode" in said
    assert f"s3://{dumps_bucket}/{tenancy_connections.control_name()}/" in said
    assert "Dry run: nothing was written." in said
    assert databases() == before
    assert {fresh(hub).db_name for hub in (aurora, elpa, gone, left)} == {""}
    assert objects(moto_s3, dumps_bucket) == {}


def test_running_it_again_leaves_a_business_already_cut_as_it_is(phase_one):
    aurora = phase_one.business("aurora")
    run("--recreate", aurora.slug, "--no-dump")
    with use_hub(fresh(aurora)):
        kept = Printer.objects.create(name="Made after the cut", **PRINTER)

    said = run("--recreate", aurora.slug, "--no-dump")

    assert f"{aurora.slug}: already has its own database" in said
    with use_hub(fresh(aurora)):
        assert Printer.objects.filter(pk=kept.pk).exists()


def test_a_cut_that_broke_leaves_the_business_on_control_and_the_next_run_does_it_again_from_the_start(
    phase_one, monkeypatch
):
    aurora = phase_one.business("aurora")
    rows = phase_one.rows_of(aurora.slug)
    copy = cut.copy_rows

    def broken(*args, **kwargs):
        raise RuntimeError("the network went away")

    monkeypatch.setattr(cut, "copy_rows", broken)
    with pytest.raises(CommandError, match="the network went away"):
        run("--copy-all", aurora.slug, "--no-dump")
    assert fresh(aurora).db_name == ""
    with use_control():
        assert not OutboxEvent.objects.filter(name="base.hub.cut", payload__slug=aurora.slug).exists()

    monkeypatch.setattr(cut, "copy_rows", copy)
    run("--copy-all", aurora.slug, "--no-dump")

    with use_hub(fresh(aurora)):
        assert Printer.objects.filter(pk=rows.printer.pk).count() == 1


def test_while_a_business_is_cut_its_host_answers_503_and_after_it_its_own_database(phase_one, monkeypatch, settings):
    aurora = phase_one.business("aurora")
    phase_one.rows_of(aurora.slug)
    copy = cut.copy_rows
    heard = []

    def watched(*args, **kwargs):
        heard.append(Client().get("/api/session/me", HTTP_HOST=f"{aurora.slug}.localhost:8000").status_code)
        return copy(*args, **kwargs)

    monkeypatch.setattr(cut, "copy_rows", watched)
    run("--copy-all", aurora.slug, "--no-dump")

    assert heard == [503]
    assert Client().get("/api/session/me", HTTP_HOST=f"{aurora.slug}.localhost:8000").status_code != 503


# ── Control's copy before the first cut ──────────────────────────────────────────────────────────────────────────


def test_before_the_first_cut_control_is_copied_to_the_bucket(phase_one, dumps_bucket, moto_s3, tmp_path):
    elpa = phase_one.business("elpa")

    said = run("--recreate", elpa.slug)

    stored = objects(moto_s3, dumps_bucket)
    control = tenancy_connections.control_name()
    [key] = stored
    assert key.startswith(f"{control}/") and key.endswith("-cut.dump") and stored[key] > 0
    copy = tmp_path / "control.dump"
    copy.write_bytes(body(moto_s3, dumps_bucket, key))
    listed = subprocess.run(["pg_restore", "--list", str(copy)], capture_output=True, text=True, check=True).stdout
    assert "TABLE public base_hub " in listed
    assert key in said
    with use_control():
        assert OutboxEvent.objects.get(name="base.hub.cut", payload__slug=elpa.slug).payload["dump"] == key


def test_without_a_bucket_the_cut_is_refused_before_anything_unless_no_dump_is_said(phase_one, no_dumps_bucket):
    elpa = phase_one.business("elpa")
    before = databases()

    with pytest.raises(CommandError, match="HUB_DUMPS_BUCKET.*--no-dump"):
        run("--recreate", elpa.slug)
    assert databases() == before and fresh(elpa).db_name == ""

    run("--recreate", elpa.slug, "--no-dump")
    assert fresh(elpa).db_name


def test_a_cut_s_last_step_refuses_a_business_that_got_its_database_meanwhile(phase_one):
    """Two cuts of one business at once: the second's last step finds it made and leaves the first one's."""
    from live.context import system_context
    from live.errors import Conflict
    from live.operations import get

    from base import registry
    from base.schemas import HubCutFinishIn

    hub = phase_one.business("raced")
    made = names.hub_db_name(tenancy_connections.control_name(), hub.id)
    with use_control():
        Hub.objects.filter(pk=hub.pk).update(db_name=made)
        finish = get("base.hub.cut_finish")
        with pytest.raises(Conflict) as refused:
            finish(
                system_context(registry.REGISTRY_SCOPE),
                HubCutFinishIn(id=hub.id, mode=cut.RECREATE, database=made, schema_apps={}, copied={}, dump=""),
            )
    assert refused.value.code == "base.hub_already_cut"
    with use_control():
        assert not OutboxEvent.objects.filter(name="base.hub.cut", payload__slug=hub.slug).exists()


def test_only_the_platform_finishes_a_cut(phase_one):
    from live.context import OperationContext, Scope
    from live.errors import PermissionDenied
    from live.operations import get

    from base.schemas import HubCutFinishIn

    hub = phase_one.business("asked")
    owner = OperationContext(scope=Scope("host", hub.slug), actor="saas:1", permissions=frozenset({"*"}), language="en")
    with use_legacy(), pytest.raises(PermissionDenied):
        get("base.hub.cut_finish")(
            owner, HubCutFinishIn(id=hub.id, mode=cut.RECREATE, database="x", schema_apps={}, copied={}, dump="")
        )
    assert fresh(hub).db_name == ""
