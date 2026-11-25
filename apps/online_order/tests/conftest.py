"""Fixtures of the online order tests: contexts per role and scope, and the room they start from.

The tables are made straight on Tables' models (``make_zone``, ``make_table``), as Tables' own tests make them: what is
under test is this app's operations, which read the tables through Tables' operations.

Every test with the database runs as production does: inside business A's own database (``hub_a``, entered by
``in_business_a``). Business B (``hub_b``) has its own database beside it; a test of B asks for ``hub_b`` and enters it.
"""

from live.context import OperationContext, Scope
from live.meta import all_live_app_configs, permissions_for_role
from live.operations import get

from apps.flow.tests.test_relay import listen
from apps.sale.tests.conftest import db_dsn, make_user
from apps.table.tests.conftest import make_table, make_zone
from base.tenancy.tests.business import HOST, HUB_DB, HUB_DB_COMMITTED, A, B, in_business_a

__all__ = [
    "B", "HOST", "HUB_DB", "HUB_DB_COMMITTED", "db_dsn", "in_business_a", "listen", "make_table", "make_user",
    "make_zone",
]


def ctx_for(
    role: str | None = "hub_admin",
    scope: Scope = A,
    *,
    permissions: set[str] | None = None,
    request=None,
) -> OperationContext:
    """The context a person with ``role`` on ``scope`` gets (owner and admin: every declared permission, as
    base.permissions; the others what each app's ``role_permissions`` gives them), or exactly ``permissions``."""
    configs = all_live_app_configs()
    if permissions is None:
        if role in ("hub_owner", "hub_admin"):
            permissions = {permission for config in configs for permission in config.permissions}
        else:
            permissions = permissions_for_role(configs, role) if role else set()
    return OperationContext(scope=scope, actor="tester", permissions=frozenset(permissions), request=request)


def run(name: str, data: dict | None = None, ctx: OperationContext | None = None):
    """Runs the operation ``name`` with ``data`` as its input, validated as a route would."""
    op = get(name)
    return op(ctx or ctx_for(), op.input.model_validate(data or {}))
