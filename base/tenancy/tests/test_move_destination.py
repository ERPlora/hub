"""Steps 3 and 4 of a move on its destination (``base.tenancy.move.destination``): its database is made from its
template there with nothing of the template's left, and it has to say it is the hub. The hubs and the passes are
``test_move.py``'s; their databases, ``conftest.py``'s."""

import uuid

from psycopg import sql

from base.tenancy import connections as tenancy_connections
from base.tenancy import move, names
from base.tenancy.tests import hubs
from base.tenancy.tests.hubs import marker, says_it_is
from base.tenancy.tests.s3 import aws_test_credentials, dumps_bucket, moto_s3
from base.tenancy.tests.test_move import MARKER, fresh, nothing_checked_yet, run

#: The moves' own autouse fixture and the bucket the ``moves`` of ``conftest.py`` asks for.
__all__ = ["aws_test_credentials", "dumps_bucket", "moto_s3", "nothing_checked_yet"]


class TestAMove:
    def test_the_destination_is_exactly_the_source_not_its_template(self, moves, hub_databases):
        # A template on the destination with a table of its own: the moved database has only what the hub had.
        vertical = f"w{uuid.uuid4().hex[:10]}"
        control = tenancy_connections.control_name()
        template = names.template_db_name(control, vertical)
        with hubs._maintenance() as conn:
            conn.execute(
                sql.SQL("CREATE DATABASE {} TEMPLATE {}").format(
                    names.identifier(template, control=control),
                    names.identifier(hub_databases.template, control=control),
                )
            )
        try:
            with hubs._maintenance(template) as conn:
                conn.execute("CREATE TABLE only_in_the_template (id int)")
            hub = moves.hub(to=moves.cluster(), vertical=vertical)

            run()

            assert fresh(hub).moving_to_id is None and fresh(hub).last_error == ""
            assert "only_in_the_template" not in hubs.table_names(hub.db_name)
            assert "w8a_marker" in hubs.table_names(hub.db_name)
            assert hubs.table_names(hub.db_name) == hubs.table_names(names.moved_db_name(control, hub.id))
        finally:
            hubs.drop_database(template)


class TestAFailurePutsEverythingBack:
    def test_a_destination_that_says_it_is_another_hub_is_refused(self, moves, monkeypatch):
        hub = moves.hub(to=moves.cluster())
        real = move.bucket._restore_from_bucket

        def restore_and_lie(key, name, cluster, heartbeat, cancelled=None):
            real(key, name, cluster, heartbeat, cancelled)
            with hubs._maintenance(name) as conn:
                conn.execute("UPDATE base_hub_identity SET hub_id = %s", [uuid.uuid7()])

        monkeypatch.setattr(move.bucket, "_restore_from_bucket", restore_and_lie)

        run()

        hub = fresh(hub)
        assert hub.moving_to_id is None and hub.last_error.startswith("move_identity_mismatch")
        assert says_it_is(hub.db_name) == [hub.id]

    def test_a_missing_template_on_the_destination_is_said(self, moves):
        hub = moves.hub(to=moves.cluster(), vertical="w8anotemplate")

        run()

        hub = fresh(hub)
        assert hub.moving_to_id is None and hub.last_error.startswith("move_template_missing")
        assert marker(hub.db_name) == [MARKER]
