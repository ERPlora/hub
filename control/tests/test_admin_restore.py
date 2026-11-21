"""«Restore from a copy…» and «Restore to a separate copy…» on Admin › Hubs, and «Recover into the business…» on
Separate copies (BASE-F114): the platform's admins ask for each through its operation, and Separate copies and
Recoveries list how each goes, read only, for support too.
"""

import datetime as dt
import re
import uuid

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.utils.text import capfirst

from control import admin as control_admin
from control.models import Cluster, Hub
from control.tests import test_admin_move
from control.tests.conftest import events
from control.tests.test_admin import (
    HUBS,
    PLATFORM,
    a_cluster,
    cluster_cell,
    nothing_kept,
    page,
    read_only_values,
    root,
    row_of,
    support,
)

# Fixtures of test_admin.py, found by pytest under these names: its autouse one and the users the tests log in as.
__all__ = ["nothing_kept", "root", "support"]

pytestmark = pytest.mark.django_db
COPIES = "/admin/control/restoredcopy/"
RECOVERIES = "/admin/control/copyrecovery/"

#: The moment a temporary cluster's copy is of, written as its point-in-time restore takes it (aws ``restore-hub.sh``).
MOMENT = "2026-11-09T14:30:00Z"
AT_MOMENT = dt.datetime(2026, 11, 9, 14, 30, tzinfo=dt.UTC)


class TestRestoreFromACopy:
    """«Restore from a copy…» (BASE-F114): the platform's admins choose hubs, then the temporary cluster their
    copy is on (one closed to new hubs) and the moment it is of, on a confirmation page; each is asked through
    ``control.hub.restore`` with that moment, and what the operation refuses is said hub by hub. Support never sees it,
    and the operation itself refuses anyone but the platform's admins (403)."""

    @pytest.fixture(autouse=True)
    def small(self, monkeypatch):
        from control import queries

        monkeypatch.setattr(queries, "measure", lambda cluster, names: {name: 1024 for name in names})

    a_hub = staticmethod(test_admin_move.TestMoveToCluster.a_hub)

    @staticmethod
    def a_temporary_cluster() -> Cluster:
        return a_cluster(name="restore-1", host="restore-1.example", is_open=False)

    @staticmethod
    def choose(client, *hubs, **more):
        data = {"action": "restore_from_a_copy", "_selected_action": [str(hub.pk) for hub in hubs]} | more
        return client.post(HUBS, data, HTTP_HOST=PLATFORM, follow=True)

    def test_asks_for_a_temporary_cluster_and_the_moment_first_and_changes_nothing(self, client, root):
        hub = self.a_hub("acme")
        temporary = self.a_temporary_cluster()
        a_cluster(name="cluster-open", host="writer-2.example")

        html = self.choose(client, hub).content.decode()

        assert "Restore from a copy" in html and "acme" in html
        assert f'value="{temporary.pk}"' in html and "cluster-open" not in html
        assert 'name="at"' in html and 'name="apply"' in html
        hub.refresh_from_db()
        assert hub.restoring_from_id is None

    def test_confirmed_each_hub_is_asked_through_its_operation_with_the_moment(self, client, root):
        first, second = self.a_hub("acme"), self.a_hub("bistro")
        temporary = self.a_temporary_cluster()

        html = self.choose(client, first, second, apply="yes", cluster=str(temporary.pk), at=MOMENT).content.decode()

        assert "2 hubs will be restored from restore-1 as they were at 2026-11-09 14:30 UTC" in html
        for hub in (first, second):
            hub.refresh_from_db()
            assert (hub.restoring_from_id, hub.restore_point) == (temporary.pk, AT_MOMENT)
        assert [event["at"] for event in events("control.hub.restore_requested")] == [AT_MOMENT.isoformat()] * 2
        assert "← restore-1" in cluster_cell(row_of(page(client, HUBS), ">acme<"))

    def test_a_hub_the_operation_refuses_is_named_with_why_and_the_others_are_asked(self, client, root):
        ready, demo = self.a_hub("acme"), self.a_hub("bistro", is_demo=True)
        temporary = self.a_temporary_cluster()

        html = self.choose(client, ready, demo, apply="yes", cluster=str(temporary.pk), at=MOMENT).content.decode()

        # The admin writes each message with its first letter in capitals.
        assert "Bistro: A demo is not restored: it ends on its own." in html
        assert "1 hub will be restored from restore-1 as it was at 2026-11-09 14:30 UTC" in html
        demo.refresh_from_db()
        assert demo.restoring_from_id is None

    def test_a_moment_still_to_come_is_the_operations_to_refuse(self, client, root):
        hub = self.a_hub("acme")
        temporary = self.a_temporary_cluster()
        later = (timezone.now() + dt.timedelta(days=1)).isoformat()

        html = self.choose(client, hub, apply="yes", cluster=str(temporary.pk), at=later).content.decode()

        assert "Acme: That moment has not come yet." in html
        hub.refresh_from_db()
        assert hub.restoring_from_id is None

    @pytest.mark.parametrize("given", ["cluster", "at"])
    def test_without_the_cluster_or_the_moment_it_asks_again(self, client, root, given):
        hub = self.a_hub("acme")
        both = {"cluster": str(self.a_temporary_cluster().pk), "at": MOMENT}

        html = self.choose(client, hub, apply="yes", **{given: both[given]}).content.decode()

        assert 'name="apply"' in html and "errorlist" in html
        hub.refresh_from_db()
        assert hub.restoring_from_id is None

    def test_support_neither_sees_it_nor_runs_it(self, client, support):
        hub = self.a_hub("acme")
        temporary = self.a_temporary_cluster()

        assert "restore_from_a_copy" not in page(client, HUBS)
        self.choose(client, hub, apply="yes", cluster=str(temporary.pk), at=MOMENT)

        hub.refresh_from_db()
        assert hub.restoring_from_id is None

    def test_anyone_who_is_not_staff_is_answered_403_and_nothing_is_asked(self, client):
        client.force_login(get_user_model().objects.create_user(username="owner", password="pw"))
        hub = self.a_hub("acme")
        temporary = self.a_temporary_cluster()

        response = client.post(
            HUBS,
            {"action": "restore_from_a_copy", "_selected_action": [str(hub.pk)], "apply": "yes",
             "cluster": str(temporary.pk), "at": MOMENT},
            HTTP_HOST=PLATFORM,
        )

        assert response.status_code == 403
        hub.refresh_from_db()
        assert hub.restoring_from_id is None and not events("control.hub.restore_requested")

    def test_past_the_admins_door_its_operation_still_refuses_support_with_403(self, client, support, monkeypatch):
        from live.errors import OperationError

        refused: list[int] = []
        real = control_admin.hub_restore

        def asked(ctx, data):
            try:
                return real(ctx, data)
            except OperationError as error:
                refused.append(error.status)
                raise

        monkeypatch.setattr(control_admin.HubAdmin, "has_restore_permission", lambda self, request: True)
        monkeypatch.setattr(control_admin, "hub_restore", asked)
        hub = self.a_hub("acme")
        temporary = self.a_temporary_cluster()

        html = self.choose(client, hub, apply="yes", cluster=str(temporary.pk), at=MOMENT).content.decode()

        assert refused == [403] and "Acme: Only the platform may do this." in html
        hub.refresh_from_db()
        assert hub.restoring_from_id is None and not events("control.hub.restore_requested")


class TestRestoreToASeparateCopy:
    """«Restore to a separate copy…» (BASE-F114): the same confirmation page and form as «Restore from a
    copy…», each hub asked through ``control.hub.restore_aside``; the hubs are not touched, and Separate copies lists
    the copies, read only, for support too. Support never sees the action."""

    small = TestRestoreFromACopy.small
    a_hub = staticmethod(test_admin_move.TestMoveToCluster.a_hub)
    a_temporary_cluster = staticmethod(TestRestoreFromACopy.a_temporary_cluster)

    @staticmethod
    def choose(client, *hubs, **more):
        data = {"action": "restore_aside", "_selected_action": [str(hub.pk) for hub in hubs]} | more
        return client.post(HUBS, data, HTTP_HOST=PLATFORM, follow=True)

    @staticmethod
    def a_copy(hub: Hub, **fields):
        """A separate copy of ``hub`` of the moment, as ``control.hub.restore_aside`` asks it."""
        from control.models import RestoredCopy

        values = {"restore_point": AT_MOMENT, "db_name": f"hub_copy_{uuid.uuid7().hex}", "asked_by": "root"}
        return RestoredCopy.objects.create(hub=hub, **(values | fields))

    def test_asks_for_a_temporary_cluster_and_the_moment_first_and_changes_nothing(self, client, root):
        from control.models import RestoredCopy

        hub = self.a_hub("acme")
        temporary = self.a_temporary_cluster()

        html = self.choose(client, hub).content.decode()

        assert "Restore to a separate copy" in html and "acme" in html and 'value="Make the copies"' in html
        assert f'value="{temporary.pk}"' in html and 'name="at"' in html
        assert not RestoredCopy.objects.exists()

    def test_confirmed_each_hub_gets_its_copy_asked_and_stays_as_it_is(self, client, root):
        from control.models import RestoredCopy

        first, second = self.a_hub("acme"), self.a_hub("bistro", is_demo=True)
        temporary = self.a_temporary_cluster()

        html = self.choose(client, first, second, apply="yes", cluster=str(temporary.pk), at=MOMENT).content.decode()

        assert "Bistro: A demo is not restored: it ends on its own." in html
        assert "1 hub will get a separate copy as it was at 2026-11-09 14:30 UTC, made from restore-1" in html
        [copy] = RestoredCopy.objects.all()
        assert (copy.hub_id, copy.source_id, copy.restore_point) == (first.pk, temporary.pk, AT_MOMENT)
        first.refresh_from_db()
        assert first.restoring_from_id is None
        assert "←" not in cluster_cell(row_of(page(client, HUBS), ">acme<"))

    def test_support_neither_sees_it_nor_runs_it_but_reads_the_copies(self, client, support):
        from control.models import RestoredCopy

        hub = self.a_hub("acme")
        temporary = self.a_temporary_cluster()
        self.a_copy(hub, source=temporary)

        assert "restore_aside" not in page(client, HUBS)
        self.choose(client, hub, apply="yes", cluster=str(temporary.pk), at=MOMENT)

        assert RestoredCopy.objects.count() == 1
        listed = page(client, COPIES)
        assert "acme" in listed and "2026-11-09 14:30 UTC" in listed and "Being made" in listed
        assert "addlink" not in listed

    def test_the_copies_are_listed_read_only_with_until_when_they_are_kept(self, client, root):
        from control.models import RestoredCopy

        hub = self.a_hub("acme")
        made = AT_MOMENT + dt.timedelta(hours=1)
        copy = self.a_copy(hub, status=RestoredCopy.Status.MADE, made_at=made)

        listed = page(client, COPIES)
        assert "acme" in listed and "2026-11-09 14:30 UTC" in listed
        assert "Made" in listed and "2026-11-16 15:30 UTC" in listed
        assert copy.db_name in page(client, COPIES, q=copy.db_name)
        its_page = client.get(f"{COPIES}{copy.pk}/change/", HTTP_HOST=PLATFORM).content.decode()
        assert copy.db_name in its_page and "default server" in its_page
        assert 'name="_save"' not in its_page and "deletelink" not in its_page
        assert client.post(f"{COPIES}{copy.pk}/delete/", {"post": "yes"}, HTTP_HOST=PLATFORM).status_code == 403
        assert RestoredCopy.objects.filter(pk=copy.pk).exists()

    def test_each_copy_says_its_business_and_moment_on_two_lines_as_recoveries_do(self, client, root):
        """Five columns in one line each do not fit a phone (375 px), even with the last error broken: its business and
        moment share the first cell, the one Recoveries shows for the same copy, and the last error keeps the room."""
        from control.models import RestoredCopy

        copy = self.a_copy(self.a_hub("acme"), status=RestoredCopy.Status.MADE, made_at=AT_MOMENT)

        listed = page(client, COPIES)

        assert re.findall(r'<th scope="col"[^>]*class="([^"]*)"', listed) == [
            "action-checkbox-column",
            "sortable column-made_from",
            "sortable column-status",
            "column-kept_until",
            "sortable column-last_error",
        ]
        assert TestRecoverIntoTheBusiness.copy_cell(copy) in row_of(listed, ">acme<")

    def test_a_long_last_error_breaks_inside_its_cell_by_the_sheet_copies_load(self, client, root):
        """Why a copy could not be made names its database in one piece: Separate copies load control's admin sheet,
        whose rule on the last error's cells breaks it into lines there instead of pushing the list sideways on a
        phone or a tablet (hub#1345). The browser measures it at 375, 768, 820 and 1280 px
        (tests/e2e/base-copies-aside-long-error.spec.ts); this keeps the sheet loaded and its rule on the cells the list
        draws."""
        from pathlib import Path

        from django.contrib.staticfiles import finders
        from django.templatetags.static import static

        from control.models import RestoredCopy

        copy = self.a_copy(self.a_hub("acme"), status=RestoredCopy.Status.FAILED)
        copy.last_error = f"restore_aside_restore_failed: pg_restore into {copy.db_name} failed (exit 1)"
        copy.save(update_fields=["last_error"])

        listed = page(client, COPIES)

        assert f'href="{static("control/admin.css")}"' in listed
        assert 'class="field-last_error"' in row_of(listed, ">acme<")
        sheet = Path(finders.find("control/admin.css")).read_text()
        rule = re.search(r"([^{}]*)\{[^}]*overflow-wrap:\s*anywhere", sheet)
        assert rule and "#result_list td.field-last_error" in rule.group(1)


class TestRecoverIntoTheBusiness:
    """«Recover into the business…» on Separate copies (BASE-F114): a confirmation page with what the apps
    give back from a copy (Customers today), ticked; confirmed, each chosen copy is asked through
    ``control.copy.recover`` and Recoveries lists how each goes, read only, for support too. Support never sees it."""

    a_hub = staticmethod(test_admin_move.TestMoveToCluster.a_hub)

    def made(self, slug: str = "acme", **fields):
        from control.models import RestoredCopy

        made_at = AT_MOMENT + dt.timedelta(hours=1)
        values = {"status": RestoredCopy.Status.MADE, "made_at": made_at} | fields
        return TestRestoreToASeparateCopy.a_copy(self.a_hub(slug), **values)

    @staticmethod
    def choose(client, *copies, **more):
        data = {"action": "recover_into_the_business", "_selected_action": [str(copy.pk) for copy in copies]} | more
        return client.post(COPIES, data, HTTP_HOST=PLATFORM, follow=True)

    @staticmethod
    def copy_cell(copy) -> str:
        """What Recoveries says of a copy: its business and its moment on two lines, the results' column room on a
        phone (375 px)."""
        return f">{copy.hub.slug}<br>2026-11-09 14:30 UTC</a>"

    @staticmethod
    def a_recovery(copy, **fields):
        from control.models import CopyRecovery

        return CopyRecovery.objects.create(copy=copy, **({"apps": ["customer"], "asked_by": "root"} | fields))

    def test_asks_what_to_bring_back_first_and_changes_nothing(self, client, root):
        from control.models import CopyRecovery

        copy = self.made()

        html = self.choose(client, copy).content.decode()

        assert "Recover into the business" in html and 'value="Recover"' in html
        assert re.search(r'<input[^>]*name="apps"[^>]*value="customer"[^>]*checked', html)
        assert "Customers" in html
        # And the appointments, after the customers they are booked for.
        assert re.search(r'<input[^>]*name="apps"[^>]*value="appointment"[^>]*checked', html)
        assert html.index('value="customer"') < html.index('value="appointment"')
        assert str(copy) in html and f'<div class="readonly">{copy.db_name}</div>' in html
        assert "admin/css/forms.css" in html
        # Before confirming, what will not happen: what comes back greets nobody.
        assert "What comes back is nothing new to the business: it starts none of its automations" in html
        # And the one thing it touches of what the business has: a category that comes back takes back what it had.
        assert "but for one thing: a category that comes back takes back what it had inside" in html
        assert not CopyRecovery.objects.exists()

    def test_confirmed_each_copy_is_asked_and_recoveries_says_how_it_goes(self, client, root):
        from control.models import CopyRecovery

        copy = self.made("acme")
        not_made = TestRestoreToASeparateCopy.a_copy(self.a_hub("bistro"))

        html = self.choose(client, copy, not_made, apply="yes", apps="customer").content.decode()

        # The admin says each message with its first letter in capitals, as «Bistro: A demo is not restored…».
        assert f"{capfirst(str(not_made))}: Only a separate copy that is made gives anything back." in html
        assert "1 separate copy will give back Customers into its business within a few minutes" in html
        [asked] = CopyRecovery.objects.all()
        assert (asked.copy_id, asked.apps, asked.asked_by, asked.language) == (copy.pk, ["customer"], "root", "en")
        # Its row, never the admin's menu (which names Customers too): asked, and what it brings back.
        row = row_of(page(client, RECOVERIES), self.copy_cell(copy))
        assert "Asked" in row and "Customers" in row

    def test_with_nothing_ticked_it_asks_again(self, client, root):
        from control.models import CopyRecovery

        copy = self.made()

        html = self.choose(client, copy, apply="yes").content.decode()

        assert 'value="Recover"' in html and "This field is required." in html
        assert not CopyRecovery.objects.exists()

    def test_a_recovery_done_says_what_came_back_and_why_some_did_not(self, client, root):
        copy = self.made()
        why = {"id": str(uuid.uuid7()), "reason": "customer.phone_invalid: This phone is not valid."}
        done = self.a_recovery(
            copy,
            status="done",
            done_at=AT_MOMENT + dt.timedelta(days=1),
            results=[{"app": "customer", "created": 2, "not_created": 1, "reasons": [why], "refused": ""}],
        )

        listed = page(client, RECOVERIES)
        assert "Done" in listed and "Customers: 2 created, 1 not created" in listed
        # Three columns, what a phone shows at a glance (375 px): when it was asked and done is on its page.
        assert re.findall(r'<th scope="col"[^>]*class="([^"]*)"', listed) == [
            "sortable column-made_from",
            "sortable column-status",
            "column-outcome",
        ]
        its_page = client.get(f"{RECOVERIES}{done.pk}/change/", HTTP_HOST=PLATFORM).content.decode()
        assert why["id"] in its_page and "customer.phone_invalid: This phone is not valid." in its_page
        assert "2026-11-10 14:30 UTC" in its_page and "Customers" in read_only_values(its_page, "what")
        assert 'name="_save"' not in its_page and "deletelink" not in its_page
        assert client.post(f"{RECOVERIES}{done.pk}/delete/", {"post": "yes"}, HTTP_HOST=PLATFORM).status_code == 403
        assert f'href="{RECOVERIES}add/"' not in listed

    def test_a_recovery_says_how_many_came_back_the_same_apart_from_those_created(self, client, root):
        # A card the business deleted and still held comes back the same card (CUSTOMER-F33).
        self.a_recovery(
            self.made("acme"),
            status="done",
            results=[
                {"app": "customer", "restored": 1, "created": 2, "not_created": 1, "reasons": [], "refused": ""}
            ],
        )
        self.a_recovery(
            self.made("bistro"),
            status="done",
            results=[
                {"app": "customer", "restored": 2, "created": 0, "not_created": 0, "reasons": [], "refused": ""}
            ],
        )

        listed = page(client, RECOVERIES)
        assert "Customers: 1 restored, 2 created, 1 not created" in row_of(listed, ">acme<br>")
        # Only what came back is said: no «0 created» beside what was restored.
        assert "Customers: 2 restored<" in row_of(listed, ">bistro<br>")

    def test_an_app_that_gave_nothing_back_says_why_and_a_failed_one_its_error(self, client, root):
        refused = self.a_recovery(
            self.made("acme"),
            status="done",
            results=[
                {
                    "app": "customer",
                    "created": 0,
                    "not_created": 0,
                    "reasons": [],
                    "refused": "app_inactive: Customers is turned off in this business.",
                }
            ],
        )
        failed = self.a_recovery(
            self.made("bistro"), status="failed", last_error="recover_copy_unreadable: it is gone"
        )

        listed = page(client, RECOVERIES)
        assert "Customers: nothing (app_inactive: Customers is turned off in this business.)" in row_of(
            listed, ">acme<br>"
        )
        assert "recover_copy_unreadable: it is gone" in row_of(listed, ">bistro<br>")

    def test_an_app_stopped_halfway_says_what_came_back_and_why_it_stopped(self, client, root):
        self.a_recovery(
            self.made("acme"),
            status="done",
            results=[
                {
                    "app": "customer",
                    "created": 2,
                    "not_created": 0,
                    "reasons": [],
                    "refused": "base.hub_busy: The business is busy.",
                }
            ],
        )

        # What was restored before it stopped is said too, never «nothing».
        self.a_recovery(
            self.made("bistro"),
            status="done",
            results=[
                {
                    "app": "customer",
                    "restored": 1,
                    "created": 0,
                    "not_created": 0,
                    "reasons": [],
                    "refused": "base.hub_busy: The business is busy.",
                }
            ],
        )

        listed = page(client, RECOVERIES)
        assert "Customers: 2 created, then stopped (base.hub_busy: The business is busy.)" in row_of(
            listed, ">acme<br>"
        )
        assert "Customers: 1 restored, then stopped (base.hub_busy: The business is busy.)" in row_of(
            listed, ">bistro<br>"
        )

    def test_each_thing_an_app_gives_back_is_said_apart_by_its_own_name(self, client, root):
        # Services gives back its categories before its services: each says how it went.
        nothing = {"app": "service", "restored": 0, "not_created": 0, "reasons": [], "refused": ""}
        self.a_recovery(
            self.made("acme"),
            apps=["service"],
            status="done",
            results=[
                nothing | {"label": "Service categories", "created": 1},
                nothing | {"label": "Services", "created": 2, "not_created": 1},
            ],
        )
        # One noted before each thing was counted apart is said as it was then: one count, under the names of all the
        # app declares, together.
        self.a_recovery(self.made("bistro"), apps=["service"], status="done", results=[nothing | {"created": 3}])

        listed = page(client, RECOVERIES)
        assert "Service categories: 1 created; Services: 2 created, 1 not created<" in row_of(listed, ">acme<br>")
        assert (
            "Service categories, Services, Service links to categories, Subcategory links to categories: 3 created<"
            in row_of(listed, ">bistro<br>")
        )

    def test_what_a_record_came_back_without_is_counted_in_its_result_and_said_on_its_page(self, client, root):
        # A service made again without a professional who performed it in the copy and has left since (SERVICE-F31).
        member, service = uuid.uuid7(), str(uuid.uuid7())
        left = f"service.member_terminated: came back without the professional {member}: terminated in Staff"
        gone = f"service.member_not_in_business: came back without the professional {member}: no longer in Staff"
        nothing = {"app": "service", "restored": 0, "not_created": 0, "reasons": [], "refused": ""}
        noted = self.a_recovery(
            self.made("acme"),
            apps=["service"],
            status="done",
            results=[
                nothing | {"label": "Service categories", "created": 1},
                nothing
                | {
                    "label": "Services",
                    "created": 2,
                    "noted": 1,
                    "notes": [{"id": service, "note": left}, {"id": service, "note": gone}],
                },
            ],
        )
        # One where nothing came back without anything says no note.
        plain = self.a_recovery(
            self.made("bistro"),
            apps=["service"],
            status="done",
            results=[nothing | {"label": "Services", "created": 1}],
        )

        listed = page(client, RECOVERIES)
        assert "Service categories: 1 created; Services: 2 created, 1 with notes<" in row_of(listed, ">acme<br>")
        assert "Services: 1 created<" in row_of(listed, ">bistro<br>")
        its_page = client.get(f"{RECOVERIES}{noted.pk}/change/", HTTP_HOST=PLATFORM).content.decode()
        [said] = read_only_values(its_page, "notes")
        assert said == f"<ul><li>{service}: {left}</li><li>{service}: {gone}</li></ul>"
        # Never as a record that did not come back.
        assert left not in "".join(read_only_values(its_page, "why_not"))
        plain_page = client.get(f"{RECOVERIES}{plain.pk}/change/", HTTP_HOST=PLATFORM).content.decode()
        assert read_only_values(plain_page, "notes") == read_only_values(plain_page, "why_not")

    def test_support_neither_sees_it_nor_runs_it_but_reads_the_recoveries(self, client, support):
        from control.models import CopyRecovery

        copy = self.made()

        assert "recover_into_the_business" not in page(client, COPIES)
        self.choose(client, copy, apply="yes", apps="customer")

        assert not CopyRecovery.objects.exists()
        self.a_recovery(copy)
        assert self.copy_cell(copy) in page(client, RECOVERIES)

    def test_a_long_result_breaks_inside_its_cell_by_the_sheet_recoveries_load(self, client, root):
        """A result can be long and in one piece (why a recovery failed names its copy's database): Recoveries load
        control's admin sheet, whose rule on the results' cells breaks it into lines there instead of pushing the list
        sideways on a phone. The browser measures it at 375, 768 and 1280 px
        (tests/e2e/base-recoveries-long-result.spec.ts); this keeps the sheet loaded and its rule on the cells the list
        draws."""
        from pathlib import Path

        from django.contrib.staticfiles import finders
        from django.templatetags.static import static

        copy = self.made()
        self.a_recovery(copy, status="failed", last_error=f"recover_copy_unreadable: {copy.db_name!r} is gone")

        listed = page(client, RECOVERIES)

        assert f'href="{static("control/admin.css")}"' in listed
        assert 'class="field-outcome"' in row_of(listed, self.copy_cell(copy))
        sheet = Path(finders.find("control/admin.css")).read_text()
        assert re.search(r"#result_list td\.field-outcome\s*\{[^}]*overflow-wrap:\s*anywhere", sheet)


def test_the_recovery_speaks_spanish(client, root):
    from django.utils import translation
    from django.utils.translation import ngettext

    copy = TestRecoverIntoTheBusiness().made()
    with translation.override("es"):
        assert (
            str(control_admin.RestoredCopyAdmin.recover_into_the_business.short_description)
            == "Recuperar en el negocio…"
        )
        assert ngettext(
            "%(count)d separate copy will give back %(what)s into its business within a few minutes: Recoveries says "
            "how it went.",
            "%(count)d separate copies will give back %(what)s into their businesses within a few minutes: Recoveries "
            "says how each went.",
            1,
        ) % {"count": 1, "what": "Clientes"} == (
            "1 copia aparte devolverá Clientes a su negocio en unos minutos: Recuperaciones dice cómo fue."
        )
    html = client.post(
        COPIES,
        {"action": "recover_into_the_business", "_selected_action": [str(copy.pk)]},
        HTTP_HOST=PLATFORM,
        HTTP_ACCEPT_LANGUAGE="es",
    ).content.decode()
    assert 'value="Recuperar"' in html and "Clientes" in html and "nunca se copia" in html
    # What the business deleted and still holds comes back the same, with its history.
    assert "vuelve tal como era, con su historial" in html
    # And it starts none of the business's automations.
    assert "Lo que vuelve no es nada nuevo para el negocio: no arranca ninguna de sus automatizaciones" in html
    with translation.override("es"):
        said = control_admin.CopyRecoveryAdmin.result_said(
            {"app": "customer", "restored": 2, "created": 1, "not_created": 1, "reasons": [], "refused": ""}
        )
    assert said == "Clientes: se restauraron 2, se creó 1, 1 sin crear"
    listed = client.get(RECOVERIES, HTTP_HOST=PLATFORM, HTTP_ACCEPT_LANGUAGE="es").content.decode()
    assert "Recuperaciones" in listed or "recuperaciones" in listed


def test_what_came_back_is_said_in_spanish_in_words_that_fit_customers_and_appointments_alike():
    """The counts follow the names of an app whose records are feminine in Spanish («Citas, Citas periódicas»: its
    appointments and its series, hub#1327) as well as one whose records are masculine («Clientes»): never «Citas: 2
    creados»."""
    from django.utils import translation

    said = control_admin.CopyRecoveryAdmin.result_said
    with translation.override("es"):
        assert said({"app": "appointment", "created": 2, "not_created": 1, "reasons": [], "refused": ""}) == (
            "Citas, Citas periódicas: se crearon 2, 1 sin crear"
        )
        assert said({"app": "customer", "created": 1, "not_created": 0, "reasons": [], "refused": ""}) == (
            "Clientes: se creó 1"
        )
        # And what comes back the same, whatever app restores it next.
        assert said({"app": "appointment", "restored": 1, "created": 0, "not_created": 0, "reasons": [], "refused": ""}) == (
            "Citas, Citas periódicas: se restauró 1"
        )


def test_each_thing_an_app_gives_back_is_said_in_spanish_by_its_own_name():
    """A result keeps the name of what it counts as the code writes it: Recoveries says it in the reader's language."""
    from django.utils import translation

    said = control_admin.CopyRecoveryAdmin.result_said
    nothing = {"restored": 0, "not_created": 0, "reasons": [], "refused": ""}
    with translation.override("es"):
        assert said(nothing | {"app": "service", "label": "Service categories", "created": 1}) == (
            "Categorías de servicios: se creó 1"
        )
        assert said(nothing | {"app": "service", "label": "Services", "created": 2}) == "Servicios: se crearon 2"
        assert said(nothing | {"app": "inventory", "label": "Product categories", "created": 1}) == (
            "Categorías de productos: se creó 1"
        )


def test_what_a_record_came_back_without_is_said_in_spanish():
    """In words that fit a service as well as a card or an appointment: «1 con notas», never «1 notado»."""
    from django.utils import translation

    said = control_admin.CopyRecoveryAdmin.result_said
    nothing = {"restored": 0, "not_created": 0, "reasons": [], "refused": ""}
    note = {"id": str(uuid.uuid7()), "note": "service.member_terminated: …"}
    with translation.override("es"):
        assert said(nothing | {"app": "service", "label": "Services", "created": 2, "noted": 1, "notes": [note]}) == (
            "Servicios: se crearon 2, 1 con notas"
        )
        cards = {"app": "customer", "label": "Customers", "restored": 1, "created": 1}
        assert said(nothing | cards | {"noted": 2, "notes": [note]}) == "Clientes: se restauró 1, se creó 1, 2 con notas"
        assert str(control_admin.CopyRecoveryAdmin.notes.short_description) == "notas"


def test_the_separate_copy_speaks_spanish(client, root):
    from django.utils import translation
    from django.utils.translation import ngettext

    with translation.override("es"):
        assert str(control_admin.HubAdmin.restore_aside.short_description) == "Restaurar en una copia aparte…"
        assert ngettext(
            "%(count)d hub will get a separate copy as it was at %(moment)s, made from %(cluster)s: the business stays "
            "open as it is. Separate copies lists it, and says if it could not be made.",
            "%(count)d hubs will get a separate copy each as they were at %(moment)s, made from %(cluster)s: the "
            "businesses stay open as they are. Separate copies lists them, and says if one could not be made.",
            1,
        ).startswith("%(count)d hub tendrá una copia aparte")
    listed = client.get(COPIES, HTTP_HOST=PLATFORM, HTTP_ACCEPT_LANGUAGE="es").content.decode()
    assert "Copias aparte" in listed or "copias aparte" in listed


def test_the_restore_speaks_spanish():
    from django.utils import translation

    with translation.override("es"):
        assert str(control_admin.HubAdmin.restore_from_a_copy.short_description) == "Restaurar desde una copia…"


@pytest.mark.parametrize(
    "action, said, button",
    [
        ("restore_from_a_copy", "Cada hub elegido vuelve a como estaba en el momento", "Restaurarlos"),
        ("restore_aside", "nada de ella se envía a Hacienda", "Hacer las copias"),
    ],
)
def test_its_restore_page_speaks_spanish(client, root, action, said, button):
    hub = Hub.objects.create(slug="acme", status=Hub.Status.READY, db_name=f"hub_{uuid.uuid7().hex}")
    a_cluster(name="restore-1", host="restore-1.example", is_open=False)

    html = client.post(
        HUBS,
        {"action": action, "_selected_action": [str(hub.pk)]},
        HTTP_HOST=PLATFORM,
        HTTP_ACCEPT_LANGUAGE="es",
    ).content.decode()

    assert said in html and f'value="{button}"' in html
    assert "Clúster temporal" in html and "Momento" in html


@pytest.mark.parametrize("action", ["move_to_cluster", "restore_from_a_copy", "restore_aside"])
def test_a_confirmation_page_wraps_a_long_database_name_as_a_hubs_own_page_does(client, root, action):
    """The chosen hubs are read-only rows of an aligned fieldset: the admin's forms sheet is what wraps a database name
    wider than a phone (375 px) instead of pushing the page sideways."""
    hub = Hub.objects.create(slug="acme", status=Hub.Status.READY, db_name=f"hub_{uuid.uuid7().hex}")

    html = client.post(HUBS, {"action": action, "_selected_action": [str(hub.pk)]}, HTTP_HOST=PLATFORM).content.decode()

    assert 'class="module aligned"' in html and f'<div class="readonly">{hub.db_name}</div>' in html
    assert "admin/css/forms.css" in html
