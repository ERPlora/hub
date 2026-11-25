"""Steps 1 and 2 of a move (``base.tenancy.move.closing``): while it moves the origin is closed to the app, and after
a failure it is the app's again. The hubs and the passes are ``test_move.py``'s; their databases, ``conftest.py``'s."""

import psycopg
import pytest
from django.db import connections as django_connections

from base.tenancy import connections as tenancy_connections
from base.tenancy import move, names
from base.tenancy.tests import hubs
from base.tenancy.tests.s3 import aws_test_credentials, dumps_bucket, moto_s3
from base.tenancy.tests.test_move import fresh, nothing_checked_yet, run

#: The moves' own autouse fixture and the bucket the ``moves`` of ``conftest.py`` asks for.
__all__ = ["aws_test_credentials", "dumps_bucket", "moto_s3", "nothing_checked_yet"]


class TestTheOriginIsClosedToTheApp:
    """While it moves, the environment's app roles cannot reach the origin; after it, the moved database is theirs and
    the copy is not; after a failure, the origin is theirs again. A role of this test's own plays ``hub_app``."""

    @pytest.fixture
    def app_role(self, moves):
        with hubs.an_app_role() as role:
            yield role

    def test_while_it_moves_the_app_is_out_and_after_it_reaches_the_moved_database_only(
        self, moves, app_role, monkeypatch
    ):
        hub = moves.hub(to=moves.cluster())
        hubs.grant_connect(app_role, hub.db_name)
        # A session of the app open on the origin before the move: ended by it.
        default = django_connections.settings["default"]
        open_session = psycopg.connect(
            dbname=hub.db_name, user=app_role, password="app", host=default["HOST"], port=default["PORT"]
        )
        seen: list[bool] = []
        real = move.bucket._dump_to_bucket

        def dump(key, source, cluster, heartbeat, cancelled=None):
            seen.append(hubs.reaches(app_role, source))
            real(key, source, cluster, heartbeat, cancelled)

        monkeypatch.setattr(move.bucket, "_dump_to_bucket", dump)

        run(roles=hubs.app_roles(app_role))

        assert seen == [False]
        assert open_session.closed or open_session.broken or self._dead(open_session)
        copy = names.moved_db_name(tenancy_connections.control_name(), hub.id)
        assert (hubs.reaches(app_role, hub.db_name), hubs.reaches(app_role, copy)) == (True, False)

    @staticmethod
    def _dead(session) -> bool:
        try:
            session.execute("SELECT 1")
        except psycopg.OperationalError:
            return True
        return False

    def test_after_a_failure_the_app_reaches_the_origin_again(self, moves, app_role, monkeypatch):
        hub = moves.hub(to=moves.cluster())
        hubs.grant_connect(app_role, hub.db_name)
        monkeypatch.setattr(move.bucket, "_restore_from_bucket", self.fails("restore"))

        run(roles=hubs.app_roles(app_role))

        assert fresh(hub).moving_to_id is None
        assert hubs.reaches(app_role, hub.db_name)

    @staticmethod
    def fails(step: str):
        def failing(*args, **kwargs):
            raise move.exceptions.MoveFailed(f"move_{step}_failed", f"the {step} broke on purpose")

        return failing
