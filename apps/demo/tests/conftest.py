"""Fixtures of the demo tests: contexts per role and scope.

Every test with the database runs as production does: inside business A's own database (``hub_a``, entered by
``in_business_a``). Business B (``hub_b``) has its own database beside it; a test of B asks for ``hub_b`` and enters it.
"""

from live.context import OperationContext, Scope
from live.meta import all_live_app_configs, permissions_for_role

from apps.flow.tests.test_relay import listen
from apps.invoice.tests.conftest import catalog_of
from apps.sale.tests.conftest import db_dsn, make_user
from base.tenancy.tests.business import HOST, HUB_DB, HUB_DB_COMMITTED, A, B, in_business_a
from base.tenancy.tests.concurrency import hub_staff, plan_with_room

#: The marks, scopes and fixtures of the businesses' own databases, and what other apps' tests already make of them
#: (users with a role on a host and the raw DSN of control as Sales makes them, a session LISTENing on a scope's channel
#: as Automations opens it, the assistant's catalogue of a person of business A), that these tests take from here.
__all__ = [
    "B", "HOST", "HUB_DB", "HUB_DB_COMMITTED", "catalog_of", "db_dsn", "hub_staff", "in_business_a", "listen",
    "make_user", "plan_with_room",
]


def ctx_for(role: str = "hub_admin", scope: Scope = A, actor: str = "tester") -> OperationContext:
    """The context a user with ``role`` on ``scope`` gets (permissions from the apps' AppConfig)."""
    return OperationContext(scope=scope, actor=actor, permissions=permissions_for_role(all_live_app_configs(), role))
