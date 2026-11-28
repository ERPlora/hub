"""What the tests of an app's part of a business's export share: its owner, the operations called as them, the file
Settings › Data › Export gives and loading it back, as a person does it on that screen."""

import pytest
from django.contrib.auth import get_user_model
from live.context import OperationContext, Scope
from live.operations import get

from base import blueprint
from base.models import Membership
from base.permissions import access_for
from base.tenancy.tests.business import A


def owner_of(scope: Scope, username: str) -> OperationContext:
    """The context of a new owner of ``scope``."""
    user = get_user_model().objects.create_user(username=username, password="pw")
    Membership.objects.create(user=user, host=scope.key, role=Membership.Role.OWNER)
    return OperationContext(scope=scope, actor=user, permissions=access_for(user, scope), language="en")


@pytest.fixture
def ctx() -> OperationContext:
    """The owner of business A, as whom a test writes the app's rows, exports them and loads the file back."""
    return owner_of(A, "olga")


def call(ctx: OperationContext, operation: str, /, **data):
    op = get(operation)
    return op(ctx, op.input(**data))


def exported(ctx: OperationContext, apps: list[str], *, purpose: str = "backup") -> str:
    """The file Settings › Data › Export gives with ``apps`` marked with their data, in base64."""
    return call(ctx, "base.blueprint.export", name="Bar Olga", language="en", purpose=purpose, apps=apps, data=apps).content_base64


def data_of(ctx: OperationContext, apps: list[str], *, purpose: str = "backup") -> dict[str, list[dict]]:
    """The rows that file carries, by dataset."""
    return blueprint.archive.read_base64(exported(ctx, apps, purpose=purpose)).data


def loaded_back(ctx: OperationContext, file: str) -> dict:
    """The report of loading ``file`` from Settings › Data › Import."""
    return call(ctx, "base.blueprint.import", file_base64=file).model_dump()["report"]


def app_report(report: dict, app: str) -> dict:
    """What a load's report says of ``app``."""
    return next(row for row in report["apps"] if row["id"] == app)
