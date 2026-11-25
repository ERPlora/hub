"""What a move's steps raise (``base.tenancy.move.exceptions``): a failure names its step's code, which the hub's
``last_error`` starts with, and says why after it."""

from base.tenancy import move


def test_a_failure_says_its_code_and_why():
    failed = move.exceptions.MoveFailed("move_dump_failed", "the bucket is gone")

    assert (failed.code, str(failed)) == ("move_dump_failed", "move_dump_failed: the bucket is gone")
