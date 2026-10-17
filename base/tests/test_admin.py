"""Django admin of base: Memberships are managed there in phase 1, and the scheduled tasks' clock can be seen
and brought forward; the deep link chooses a hub (PLAN §18.1).

The admin lives only on the platform host (``hubs.localhost``); on a hub host it is not found (PLAN §18.1.3).
"""

import datetime as dt
import re
from pathlib import Path

import pytest
from django.contrib import admin

from base.admin import ADMIN_HUB_SESSION_KEY, HubAdmin, MembershipAdmin, TaskScheduleAdmin
from base.models import Hub, Membership, TaskSchedule

pytestmark = pytest.mark.django_db
HOST = "a.localhost:8000"
PLATFORM = "hubs.localhost:8000"
BANNER = 'id="admin-hub"'


def test_membership_is_registered():
    assert isinstance(admin.site._registry[Membership], MembershipAdmin)


class TestHubRegistry:
    """The registry of hubs (plan 2026-10-17, §1.1): read only; the SaaS writes it through /internal/hubs/{id}."""

    def test_is_registered(self):
        assert isinstance(admin.site._registry[Hub], HubAdmin)

    def test_lists_the_hubs_with_their_status(self, client, superuser):
        Hub.objects.create(slug="acme", name="Acme Bar", status="cancelled", vertical="restaurant")
        client.force_login(superuser)
        html = client.get("/admin/base/hub/", HTTP_HOST=PLATFORM).content.decode()
        assert "acme" in html and "restaurant" in html and "Cancelled" in html

    def test_filters_by_status_and_demo_and_searches_by_slug_name_or_id(self, client, superuser):
        acme = Hub.objects.create(slug="acme", name="Acme Bar", status="cancelled")
        Hub.objects.create(slug="demo-0000beef", status="ready", is_demo=True)
        client.force_login(superuser)
        cancelled = client.get("/admin/base/hub/?status__exact=cancelled", HTTP_HOST=PLATFORM).content.decode()
        assert "acme" in cancelled and "demo-0000beef" not in cancelled
        demos = client.get("/admin/base/hub/?is_demo__exact=1", HTTP_HOST=PLATFORM).content.decode()
        assert "demo-0000beef" in demos and "/admin/base/hub/{}/".format(acme.pk) not in demos
        for query in ("Acme", str(acme.pk)):
            found = client.get("/admin/base/hub/", {"q": query}, HTTP_HOST=PLATFORM).content.decode()
            assert f"/admin/base/hub/{acme.pk}/" in found

    def test_nothing_is_added_changed_or_deleted_by_hand(self, client, superuser):
        hub = Hub.objects.create(slug="acme", status="ready")
        client.force_login(superuser)
        assert client.get("/admin/base/hub/add/", HTTP_HOST=PLATFORM).status_code == 403
        assert client.get(f"/admin/base/hub/{hub.pk}/delete/", HTTP_HOST=PLATFORM).status_code == 403
        page = client.get(f"/admin/base/hub/{hub.pk}/change/", HTTP_HOST=PLATFORM)
        assert page.status_code == 200 and 'name="slug"' not in page.content.decode()
        client.post(f"/admin/base/hub/{hub.pk}/change/", {"slug": "other", "status": "purged"}, HTTP_HOST=PLATFORM)
        hub.refresh_from_db()
        assert (hub.slug, hub.status) == ("acme", "ready")


def scheduled_task() -> TaskSchedule:
    return TaskSchedule.objects.create(
        app_label="verifactu",
        name="process_queue",
        operation="verifactu.contingency.process",
        cron="* * * * *",
        next_run=dt.datetime(2026, 10, 15, 10, 1, tzinfo=dt.UTC),
    )


def test_the_scheduled_tasks_are_registered():
    assert isinstance(admin.site._registry[TaskSchedule], TaskScheduleAdmin)


def test_the_scheduled_tasks_are_listed_with_their_clock(client, superuser):
    scheduled_task()
    client.force_login(superuser)

    html = client.get("/admin/base/taskschedule/", HTTP_HOST=PLATFORM).content.decode()

    assert "verifactu.contingency.process" in html and "* * * * *" in html


def test_a_scheduled_task_is_not_added_by_hand(client, superuser):
    # The apps declare them and the worker writes them when it starts.
    client.force_login(superuser)

    assert client.get("/admin/base/taskschedule/add/", HTTP_HOST=PLATFORM).status_code == 403


def test_the_next_run_can_be_brought_forward_and_the_declaration_stays(client, superuser):
    task = scheduled_task()
    client.force_login(superuser)

    response = client.post(
        f"/admin/base/taskschedule/{task.pk}/change/",
        # The admin speaks the server's time (Europe/Madrid): 11:00 there is 09:00 UTC.
        {"next_run_0": "2026-10-15", "next_run_1": "11:00:00", "cron": "0 0 * * *", "operation": "x.y.z"},
        HTTP_HOST=PLATFORM,
    )

    assert response.status_code == 302
    task.refresh_from_db()
    assert task.next_run == dt.datetime(2026, 10, 15, 9, 0, tzinfo=dt.UTC)
    assert (task.cron, task.operation) == ("* * * * *", "verifactu.contingency.process")


def test_changelist_lists_memberships(client, superuser, make_user):
    make_user("ana", host="a", role="hub_employee")
    client.force_login(superuser)
    response = client.get("/admin/base/membership/", HTTP_HOST=PLATFORM)
    assert response.status_code == 200
    assert "ana" in response.content.decode()


def test_changelist_filters_and_search(client, superuser, make_user):
    # Usernames that appear nowhere else on the page ("ana" is inside "Manager").
    make_user("xavier", host="a", role="hub_employee")
    make_user("quentin", host="b", role="hub_admin")
    client.force_login(superuser)
    html = client.get("/admin/base/membership/?host=b", HTTP_HOST=PLATFORM).content.decode()
    assert "quentin" in html and "xavier" not in html
    html = client.get("/admin/base/membership/?q=xavier", HTTP_HOST=PLATFORM).content.decode()
    assert "xavier" in html and "quentin" not in html


def test_add_form_creates_a_membership(client, superuser, make_user):
    user = make_user("ana")
    client.force_login(superuser)
    response = client.post(
        "/admin/base/membership/add/", {"user": user.pk, "host": "a", "role": "hub_manager"}, HTTP_HOST=PLATFORM
    )
    assert response.status_code == 302
    assert Membership.objects.get(user=user).role == "hub_manager"


def test_admin_scripts_carry_the_csp_nonce(client, superuser):
    client.force_login(superuser)
    response = client.get("/admin/base/membership/add/", HTTP_HOST=PLATFORM)
    [nonce] = re.findall(r"'nonce-([^']+)'", response["Content-Security-Policy"])
    scripts = re.findall(r"<script\b[^>]*\bsrc=[^>]*>", response.content.decode())
    assert scripts
    assert all(f'nonce="{nonce}"' in tag for tag in scripts)


class TestDeepLink:
    """``/admin/hub/<slug>/``: where «Open in the Hub admin» of the SaaS admin lands (round 13, PLAN §18.1)."""

    def test_chooses_the_hub_and_opens_the_admin_index_with_its_banner(self, client, superuser):
        client.force_login(superuser)
        response = client.get("/admin/hub/a/", HTTP_HOST=PLATFORM)
        assert (response.status_code, response["Location"]) == (302, "/admin/")
        assert client.session[ADMIN_HUB_SESSION_KEY] == "a"
        html = client.get("/admin/", HTTP_HOST=PLATFORM).content.decode()
        assert BANNER in html and "Hub: a" in html
        # The admin's own branding stays.
        assert 'id="site-name"' in html

    def test_the_banner_is_on_every_admin_page(self, client, superuser):
        client.force_login(superuser)
        client.get("/admin/hub/acme/", HTTP_HOST=PLATFORM)
        assert "Hub: acme" in client.get("/admin/base/membership/", HTTP_HOST=PLATFORM).content.decode()

    def test_another_deep_link_replaces_the_choice(self, client, superuser):
        client.force_login(superuser)
        client.get("/admin/hub/a/", HTTP_HOST=PLATFORM)
        client.get("/admin/hub/b/", HTTP_HOST=PLATFORM)
        assert client.session[ADMIN_HUB_SESSION_KEY] == "b"

    def test_no_banner_without_a_choice(self, client, superuser):
        client.force_login(superuser)
        assert BANNER not in client.get("/admin/", HTTP_HOST=PLATFORM).content.decode()

    @pytest.mark.parametrize("slug", ["hubs", "hub", "www", "ab", "-a", "A", "xn--bcher-kva", ".."])
    def test_a_slug_that_is_no_hub_is_not_found(self, client, superuser, slug):
        client.force_login(superuser)
        assert client.get(f"/admin/hub/{slug}/", HTTP_HOST=PLATFORM).status_code == 404
        assert ADMIN_HUB_SESSION_KEY not in client.session

    def test_on_a_hub_host_it_is_not_found_and_chooses_nothing(self, client, superuser, make_user):
        # The admin lives only on the platform host (PLAN §18.1.3), even for the staff.
        assert client.get("/admin/hub/a/", HTTP_HOST=HOST).status_code == 404
        for user in (make_user("ana", host="a", role="hub_owner"), superuser):
            client.force_login(user)
            assert client.get("/admin/hub/a/", HTTP_HOST=HOST).status_code == 404
            assert ADMIN_HUB_SESSION_KEY not in client.session

    def test_the_banner_label_is_translated(self):
        catalogue = (Path(__file__).resolve().parents[1] / "locale" / "es" / "LC_MESSAGES" / "django.po").read_text()
        assert 'msgid "Hub: %(slug)s"' in catalogue
