"""What the tests of the task app's reads share: how a read is run, the titles of a page and who runs it. Each
module of ``queries/`` has its own tests, in ``test_queries_<module>.py``."""

from live.operations import get

from .conftest import ctx_for


def run(name, data=None, ctx=None):
    op = get(name)
    return op(ctx or ctx_for(), op.input.model_validate(data or {}))


def titles(page):
    return [row.title for row in page.rows]


def as_employee(team):
    return ctx_for("hub_employee", actor=team["worker"])


def as_manager(team):
    return ctx_for("hub_manager", actor=team["boss"])
