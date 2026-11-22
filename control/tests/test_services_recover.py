"""What a business lost, brought back from one of its separate copies."""

import datetime as dt
import uuid

import pytest
from django.utils import timezone
from live.context import OperationContext
from live.errors import Conflict, InvalidPayload, NotFound, PermissionDenied

from base.registry import REGISTRY_SCOPE
from control import services
from control.tests.conftest import SERVICES_MARKS, a_ready_hub, as_actor, events, person

pytestmark = SERVICES_MARKS


class TestRecover:
    """``control.copy.recover`` asks the worker to bring back into a business what one of its separate copies holds and
    the business lacks, app by app (``base.tenancy.recovery``): a ``CopyRecovery`` row
    with the apps asked, the staff member and their language. Only from a made copy, of apps that answer
    ``recoverable_from_copy``, and one recovery of a copy at a time; nothing of the business is touched by the ask."""

    MOMENT = dt.datetime(2026, 11, 9, 14, 30, tzinfo=dt.UTC)

    def a_copy(self, status: str = "made", **fields):
        from base.tenancy import names
        from base.tenancy.connections import control_name
        from control.models import RestoredCopy

        copy_id = uuid.uuid7()
        values = {
            "id": copy_id,
            "hub": a_ready_hub(**fields),
            "restore_point": self.MOMENT,
            "db_name": names.copy_db_name(control_name(), copy_id),
            "status": status,
            "made_at": self.MOMENT + dt.timedelta(hours=1) if status == "made" else None,
            "asked_by": "root",
        }
        return RestoredCopy.objects.create(**values)

    def ask(self, ctx, copy, *apps: str):
        from control.schemas import CopyRecoverIn

        return services.copy_recover(ctx, CopyRecoverIn(copy_id=copy.pk, apps=list(apps or ["customer"])))

    def test_asks_the_worker_to_bring_back_the_customers_and_says_who_asked(self, admin_ctx):
        from control.models import CopyRecovery

        copy = self.a_copy()
        in_spanish = OperationContext(
            scope=REGISTRY_SCOPE, actor=admin_ctx.actor, permissions=frozenset(), language="es"
        )

        out = self.ask(in_spanish, copy, "customer", "customer")

        [row] = CopyRecovery.objects.all()
        assert (row.copy_id, row.apps, row.status, row.asked_by, row.language) == (
            copy.pk,
            ["customer"],
            "asked",
            "root",
            "es",
        )
        assert (row.results, row.done_at, row.last_error, row.lease_owner) == ([], None, "", "")
        assert (out.id, out.copy_id, out.hub, out.slug, out.apps, out.status) == (
            row.pk,
            copy.pk,
            copy.hub_id,
            "acme",
            ["customer"],
            "asked",
        )
        assert events("control.copy.recovery_requested") == [
            {"id": str(row.pk), "copy": str(copy.pk), "hub": str(copy.hub_id), "slug": "acme", "apps": ["customer"]}
        ]

    @pytest.mark.parametrize("status", ["copying", "failed"])
    def test_only_a_made_copy_gives_anything_back(self, admin_ctx, status):
        from control.models import CopyRecovery

        copy = self.a_copy(status)

        with pytest.raises(Conflict) as refused:
            self.ask(admin_ctx, copy)

        assert refused.value.code == "control.copy_not_made"
        assert not CopyRecovery.objects.exists()

    def test_only_apps_that_say_what_they_give_back_are_asked(self, admin_ctx):
        from control.models import CopyRecovery

        copy = self.a_copy()

        for apps in (("verifactu",), ("customer", "no_such_app")):
            with pytest.raises(InvalidPayload) as refused:
                self.ask(admin_ctx, copy, *apps)
            assert refused.value.code == "control.copy_app_not_recoverable"
            assert set(refused.value.fields) == {"apps"}
        assert not CopyRecovery.objects.exists()

    def test_asking_for_nothing_is_refused_by_its_input(self):
        import pydantic

        from control.schemas import CopyRecoverIn

        with pytest.raises(pydantic.ValidationError):
            CopyRecoverIn(copy_id=uuid.uuid7(), apps=[])

    def test_one_recovery_of_a_copy_at_a_time_and_a_done_one_does_not_stop_the_next(self, admin_ctx):
        from control.models import CopyRecovery

        copy = self.a_copy()
        first = self.ask(admin_ctx, copy)

        with pytest.raises(Conflict) as refused:
            self.ask(admin_ctx, copy)

        assert refused.value.code == "control.copy_recovery_pending"
        CopyRecovery.objects.filter(pk=first.id).update(status=CopyRecovery.Status.DONE, done_at=timezone.now())
        self.ask(admin_ctx, copy)
        assert CopyRecovery.objects.filter(copy=copy).count() == 2

    def test_support_may_not_and_an_unknown_copy_is_not_found(self, admin_ctx):
        from control.models import CopyRecovery
        from control.schemas import CopyRecoverIn

        copy = self.a_copy()

        with pytest.raises(PermissionDenied):
            self.ask(as_actor(person("support", is_staff=True)), copy)
        with pytest.raises(NotFound):
            services.copy_recover(admin_ctx, CopyRecoverIn(copy_id=uuid.uuid7(), apps=["customer"]))
        assert not CopyRecovery.objects.exists()

    def test_the_recovery_is_an_internal_command_of_control(self):
        from live.operations import INTERNAL
        from live.operations import get as get_operation

        op = get_operation("control.copy.recover")
        assert (op.kind, op.app_label, op.ai_spec(), op.fn.__module__) == (
            "command",
            "control",
            INTERNAL,
            "control.services",
        )
