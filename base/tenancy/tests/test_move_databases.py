"""What a move runs on a server's databases (``base.tenancy.move.databases``): only the name of a copy a hub left
behind is ever dropped. The hubs are ``test_move.py``'s; their databases, ``conftest.py``'s."""

import pytest

from base.tenancy import move, names
from base.tenancy.tests.hubs import marker
from base.tenancy.tests.s3 import aws_test_credentials, dumps_bucket, moto_s3
from base.tenancy.tests.test_move import MARKER, nothing_checked_yet

#: The moves' own autouse fixture and the bucket the ``moves`` of ``conftest.py`` asks for.
__all__ = ["aws_test_credentials", "dumps_bucket", "moto_s3", "nothing_checked_yet"]


class TestTheCopiesGoAfterTheirDays:
    def test_only_a_moved_copys_name_is_ever_dropped(self, moves):
        hub = moves.hub(to=None)

        with pytest.raises(names.InvalidDatabaseName):
            move.databases._drop_copy(hub.db_name, None)
        assert marker(hub.db_name) == [MARKER]
