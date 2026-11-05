"""Deleting a row that a module hangs from, in a business that does not have that module's tables (hub#778, out of
hub#608): the row goes away as usual, because nothing hangs from a table that is not there, and a module whose tables
are there keeps its PROTECT, its CASCADE and its SET_NULL.

Django's ``Collector`` walks every relation with ``.using()``, so the ``TenantRouter`` never sees those queries and
``AppNotCreated`` does not cover them: they reached Postgres as ``relation … does not exist``.

Real databases, committed (no test case: the migrator registers its own aliases): businesses cloned from a template with
the platform alone, confirmed by the migrator as every ready hub is, each with the modules its test names.
"""

import datetime as dt
import uuid

import pytest
from django.apps import apps
from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.core.cache import cache
from django.db import IntegrityError, connections
from django.db.models import ForeignKey, ProtectedError
from django.db.models.deletion import Collector, get_candidate_relations_to_delete
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from live.operations import atomic

from apps.attendance.models import Record
from apps.inventory.models import Category
from apps.service.models import Assignment, Service
from apps.staff.models import Member, TimeOff
from apps.task.models import Project
from apps.tax.models import TaxCategory
from base.activation import CREATED_APPS_CACHE
from base.tenancy import connections as tenancy_connections
from base.tenancy import inventory, migrator
from base.tenancy.context import use_control, use_hub
from base.tenancy.tests.test_app_not_created import counted_cache
from base.tests.test_worker_activations import (  # noqa: F401 (fixtures)
    business,
    fresh,
    nothing_checked_yet,
    platform_template,
)
from control.models import Hub

pytestmark = pytest.mark.usefixtures("no_test_fallback")


@pytest.fixture
def with_modules(business):  # noqa: F811
    """``with_modules(*labels)``: a ready business whose database has the platform, ``labels`` and what they require."""

    def make(*labels: str) -> Hub:
        hub = business("-".join(label.replace("_", "-") for label in labels))
        migrator.ensure_schema(hub, add=labels)
        return fresh(hub)

    return make


def a_tax_category(key: str = "mine") -> TaxCategory:
    return TaxCategory.objects.create(key=key, name=key.title())


def a_held_tax_category() -> TaxCategory:
    """A category with one of Inventory's rows on it, which its PROTECT holds."""
    category = a_tax_category()
    Category.objects.create(name="Drinks", tax_category=category)
    return category


def behind_the_database(hub: Hub) -> Hub:
    """``hub``'s row, with a kept list saying the same: neither knows the Inventory tables its database does have."""
    behind = fresh(hub)
    behind.schema_apps = {label: name for label, name in hub.schema_apps.items() if label != "inventory"}
    cache.set(CREATED_APPS_CACHE + hub.slug, sorted(behind.schema_apps), 60)
    return behind


def a_member() -> Member:
    return Member.objects.create(first_name="Ana", last_name="Ruiz")


def a_working_day(member: Member) -> Record:
    now = timezone.now()
    return Record.objects.create(member=member, work_date=now.date(), clock_in_at=now)


def what_hangs_from_a_tax_category() -> list[str]:
    """Where nothing is passed over, a business needs them all, or the walk meets a table it does not have."""
    return sorted({
        relation.related_model._meta.app_label
        for relation in get_candidate_relations_to_delete(TaxCategory._meta)
        if relation.related_model._meta.app_label != TaxCategory._meta.app_label
    })


def table_exists(hub: Hub, table: str) -> bool:
    with use_hub(hub):
        return table in connections[tenancy_connections.open_hub_alias(hub)].introspection.table_names()


# ── What the business lacks: the row goes away ──────────────────────────────────────────────────────────────────────


def test_a_tax_category_goes_away_in_a_business_without_inventory(with_modules):
    """The issue's reproduction. The factory categories are held by their own rules (below): this one has none."""
    only_tax = with_modules("tax")
    assert not table_exists(only_tax, "inventory_category")

    with use_hub(only_tax):
        category = a_tax_category()
        deleted = category.delete()
        left = TaxCategory.objects.filter(key="mine").exists()

    assert deleted == (1, {"tax.TaxCategory": 1})
    assert left is False


def test_a_queryset_goes_away_the_same(with_modules):
    only_tax = with_modules("tax")

    with use_hub(only_tax):
        a_tax_category("one")
        a_tax_category("two")
        deleted = TaxCategory.objects.filter(key__in=["one", "two"]).delete()
        left = TaxCategory.objects.filter(key__in=["one", "two"]).exists()

    assert deleted == (2, {"tax.TaxCategory": 2})
    assert left is False


def test_every_kind_of_relation_to_a_missing_table_is_passed_over(with_modules):
    """``staff.Member`` is the row with all of them: what ``collect`` reads (PROTECT, attendance), what it deletes at once
    (CASCADE, service) and what it leaves for later and writes (SET_NULL, task)."""
    only_staff = with_modules("staff")

    with use_hub(only_staff):
        member = a_member()
        deleted = member.delete()
        left = Member.objects.exists()

    assert deleted == (1, {"staff.Member": 1})
    assert left is False


def test_inside_an_operation_s_transaction_it_deletes_and_the_transaction_goes_on(with_modules):
    """What an operation's ``.delete()`` runs in. No statement reached the missing table, so nothing aborted it."""
    only_tax = with_modules("tax")

    with use_hub(only_tax):
        with atomic():
            a_tax_category().delete()
            asked_after = TaxCategory.objects.filter(key="mine").exists()
        left = TaxCategory.objects.filter(key="mine").exists()

    assert asked_after is False
    assert left is False


# ── What the business has: every protection stays ───────────────────────────────────────────────────────────────────


def test_the_same_delete_is_refused_in_the_business_that_has_inventory_and_a_row_on_it(with_modules):
    with_inventory, only_tax = with_modules("inventory"), with_modules("tax")

    with use_hub(only_tax):
        gone = a_tax_category()
        gone.delete()
        gone_left = TaxCategory.objects.filter(key="mine").exists()
    with use_hub(with_inventory):
        held = a_held_tax_category()
        with pytest.raises(ProtectedError):
            held.delete()
        held_left = TaxCategory.objects.filter(key="mine").exists()
        its_category = Category.objects.get(name="Drinks").tax_category_id

    assert gone_left is False
    assert held_left is True
    assert its_category == held.pk


def test_a_module_with_tables_keeps_its_protect_while_the_missing_ones_are_passed_over(with_modules):
    with_attendance = with_modules("attendance")
    assert not table_exists(with_attendance, "task_project")

    with use_hub(with_attendance):
        member = a_member()
        a_working_day(member)
        with pytest.raises(ProtectedError):
            member.delete()
        left = Member.objects.count()
        days = Record.objects.count()

    assert (left, days) == (1, 1)


def test_a_module_with_tables_keeps_its_cascade_while_the_missing_ones_are_passed_over(with_modules):
    with_service = with_modules("service")
    assert not table_exists(with_service, "attendance_record")

    with use_hub(with_service):
        member = a_member()
        Assignment.objects.create(member=member, service=Service.objects.create(name="Cut"))
        deleted = member.delete()
        assignments = Assignment.objects.count()
        services = Service.objects.count()

    assert deleted == (2, {"service.Assignment": 1, "staff.Member": 1})
    assert (assignments, services) == (0, 1)


def test_a_module_with_tables_keeps_its_set_null_while_the_missing_ones_are_passed_over(with_modules):
    with_task = with_modules("task")
    assert not table_exists(with_task, "attendance_record")

    with use_hub(with_task):
        member = a_member()
        project = Project.objects.create(code="OPEN", name="Opening", owner=member)
        member.delete()
        project.refresh_from_db()
        left = Member.objects.count()

    assert project.owner_id is None
    assert left == 0


def test_the_business_s_own_module_keeps_its_protection_and_its_cascade(with_modules):
    """A module is passed over only when it is the one that is missing, never because a relation is another's or its
    own: the rules that hold a factory category and a person's time off, in businesses with nothing else."""
    only_tax, only_staff = with_modules("tax"), with_modules("staff")

    with use_hub(only_tax):
        factory = TaxCategory.objects.filter(rules__isnull=False).first()
        with pytest.raises(ProtectedError):
            factory.delete()
    with use_hub(only_staff):
        member = a_member()
        today = timezone.now().date()
        TimeOff.objects.create(member=member, start_date=today, end_date=today + dt.timedelta(days=1))
        deleted = member.delete()

    assert deleted[1] == {"staff.TimeOff": 1, "staff.Member": 1}


def test_a_row_read_before_the_tables_were_made_keeps_the_protection(with_modules):
    """The context may hold a row of before the module's tables: what it lacks is asked of control, as the router does."""
    business_row = with_modules("tax")
    read_before = fresh(business_row)
    migrator.ensure_schema(fresh(business_row), add=["inventory"])
    assert "inventory" not in read_before.schema_apps

    with use_hub(read_before):
        category = a_held_tax_category()
        with pytest.raises(ProtectedError):
            category.delete()


# ── Whose context decides ───────────────────────────────────────────────────────────────────────────────────────────


def test_the_context_of_another_business_never_decides_what_this_one_has(with_modules):
    """B's context (no Inventory) holding A's object: A's own database answers, and A has the row that protects it."""
    with_everything, only_tax = with_modules(*what_hangs_from_a_tax_category()), with_modules("tax")
    with use_hub(with_everything):
        category = a_held_tax_category()

    with use_hub(only_tax), pytest.raises(ProtectedError):
        category.delete()

    with use_hub(with_everything):
        assert TaxCategory.objects.filter(key="mine").exists()


def test_the_migrator_s_alias_is_never_passed_over(with_modules):
    """On a ``…__ddl`` alias the tables are being made: what control says of the business decides nothing there. Here
    control says the business lacks Inventory (a list behind the database) and its row is still protected."""
    hub = with_modules(*what_hangs_from_a_tax_category())
    with use_hub(hub):
        category = a_held_tax_category()
    behind = behind_the_database(hub)
    ddl_alias = tenancy_connections.register_ddl_alias(hub.db_name)

    with use_hub(behind):
        on_the_migrators = TaxCategory.objects.using(ddl_alias).get(pk=category.pk)
        with pytest.raises(ProtectedError):
            on_the_migrators.delete()


def test_with_no_context_nothing_is_passed_over(with_modules):
    """Nothing says what that database has: the relation is walked, never guessed (a migration's ``RunPython``)."""
    only_tax = with_modules("tax")
    field = Category._meta.get_field("tax_category")
    alias = tenancy_connections.register_ddl_alias(only_tax.db_name)

    walked = Collector(using=alias).related_objects(Category, [field], [TaxCategory(key="any")])

    assert walked.query.is_empty() is False


def test_a_row_the_migrator_never_confirmed_says_nothing_and_nothing_is_passed_over(with_modules):
    """As with the router: such a row (``migrator.is_behind`` says so too) lists no app, and that is no list of what is
    missing. The next ``migrate_hubs`` confirms it."""
    hub = with_modules("tax")
    never_confirmed = fresh(hub)
    never_confirmed.schema_apps = {}
    field = Category._meta.get_field("tax_category")

    with use_hub(never_confirmed) as active:
        walked = Collector(using=active.alias).related_objects(Category, [field], [TaxCategory(key="any")])

    assert walked.query.is_empty() is False


@pytest.mark.django_db
def test_on_control_a_row_is_deleted_as_ever():
    """Control's models and its context have no business to ask about: their own relations go on as they were."""
    hub_id = uuid.uuid7()
    with use_control():
        hub = Hub.objects.create(id=hub_id, slug=f"gone-{hub_id.hex[-8:]}", status=Hub.Status.READY)
        hub.delete()
        assert not Hub.objects.filter(pk=hub_id).exists()


# ── If the reading is ever behind the database: never a row left hanging ───────────────────────────────────────────


def test_a_list_behind_the_database_stops_at_the_foreign_key_and_leaves_no_row_hanging(with_modules):
    """Up to its minute a cached list can say «no tables» of a module just made. The protection the ``Collector`` then
    passes over is still the database's: its foreign key refuses the ``COMMIT``, and both rows stay."""
    hub = with_modules("inventory")
    with use_hub(hub):
        category = a_held_tax_category()

    with use_hub(behind_the_database(hub)), pytest.raises(IntegrityError):
        category.delete()

    with use_hub(fresh(hub)):
        assert TaxCategory.objects.filter(key="mine").exists()
        assert Category.objects.get(name="Drinks").tax_category_id == category.pk


def test_every_relation_of_a_hub_s_tables_has_its_constraint_in_the_database():
    """What the test above stands on, for every model: a ``db_constraint=False`` could leave a row hanging."""
    without_one = [
        f"{model._meta.label}.{field.name}"
        for model in apps.get_models(include_auto_created=True)
        for field in model._meta.local_fields
        if isinstance(field, ForeignKey)
        and not field.db_constraint
        and inventory.classify(model) != inventory.CONTROL
    ]

    assert without_one == []


# ── What it costs ───────────────────────────────────────────────────────────────────────────────────────────────────


def test_deleting_what_a_business_has_asks_neither_control_nor_the_cache(with_modules, monkeypatch):
    """The row the context holds says so for free, on every relation of every delete."""
    with_everything = with_modules(*what_hangs_from_a_tax_category())
    with use_hub(with_everything):
        category = a_tax_category()
        cache_calls = counted_cache(monkeypatch)

        with CaptureQueriesContext(connections["default"]) as on_control:
            category.delete()

    assert len(on_control) == 0
    assert cache_calls == []


def test_every_relation_passed_over_in_one_delete_reads_control_once(with_modules, monkeypatch):
    only_tax = with_modules("tax")
    with use_hub(only_tax):
        category = a_tax_category()
        cache_calls = counted_cache(monkeypatch)

        with CaptureQueriesContext(connections["default"]) as on_control:
            category.delete()

    assert len(on_control) == 1
    assert cache_calls.count("set") == 1


# ── The admin: what reaches this today ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def staff_client(client, django_db_blocker):
    """``client`` logged in as a superuser of control, on committed data: both gone after the test."""
    with django_db_blocker.unblock():
        user = get_user_model().objects.create_superuser(f"root-{uuid.uuid7().hex[-12:]}", "root@example.com", "pw")
        client.force_login(user)
        yield client
        Session.objects.filter(session_key=client.session.session_key).delete()
        user.delete()


def admin_page(client, hub: Hub, path: str):
    client.get(f"/admin/hub/{hub.slug}/", HTTP_HOST="hubs.localhost")
    return client.get(path, HTTP_HOST="hubs.localhost", HTTP_ACCEPT="text/html")


def test_the_admin_asks_to_confirm_and_deletes_in_a_business_without_inventory(with_modules, staff_client):
    only_tax = with_modules("tax")
    with use_hub(only_tax):
        category = a_tax_category()
    path = f"/admin/tax/taxcategory/{category.pk}/delete/"

    page = admin_page(staff_client, only_tax, path)
    posted = staff_client.post(path, {"post": "yes"}, HTTP_HOST="hubs.localhost", HTTP_ACCEPT="text/html")

    assert page.status_code == 200
    assert page.context["protected"] == []
    assert posted.status_code == 302
    with use_hub(only_tax):
        assert not TaxCategory.objects.filter(key="mine").exists()


def test_the_admin_s_bulk_action_deletes_in_a_business_without_inventory(with_modules, staff_client):
    only_tax = with_modules("tax")
    with use_hub(only_tax):
        ids = [str(a_tax_category("one").pk), str(a_tax_category("two").pk)]
    admin_page(staff_client, only_tax, "/admin/tax/taxcategory/")
    selection = {"action": "delete_selected", "_selected_action": ids}

    page = staff_client.post("/admin/tax/taxcategory/", selection, HTTP_HOST="hubs.localhost", HTTP_ACCEPT="text/html")
    posted = staff_client.post(
        "/admin/tax/taxcategory/", selection | {"post": "yes"}, HTTP_HOST="hubs.localhost", HTTP_ACCEPT="text/html"
    )

    assert page.status_code == 200
    assert posted.status_code == 302
    with use_hub(only_tax):
        assert not TaxCategory.objects.filter(key__in=["one", "two"]).exists()


def test_the_admin_says_what_protects_it_in_the_business_that_has_inventory(with_modules, staff_client):
    with_inventory = with_modules("inventory")
    with use_hub(with_inventory):
        category = a_held_tax_category()
    path = f"/admin/tax/taxcategory/{category.pk}/delete/"

    page = admin_page(staff_client, with_inventory, path)
    posted = staff_client.post(path, {"post": "yes"}, HTTP_HOST="hubs.localhost", HTTP_ACCEPT="text/html")

    assert page.status_code == 200
    assert len(page.context["protected"]) == 1
    assert "Drinks" in str(page.context["protected"][0])
    assert posted.status_code == 200, "Django paints the page again with what protects it, and deletes nothing"
    assert len(posted.context["protected"]) == 1
    with use_hub(with_inventory):
        assert TaxCategory.objects.filter(key="mine").exists()
