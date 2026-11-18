"""Guardrails of the tenancy, one database per hub: rules (e) and (g) of the Hub's guardrails. The rest, and the
scanning they share (``source_files``, ``_offenders``), are ``tests/test_guardrails.py``.

(e) The tenancy: no ``CREATE``/``DROP DATABASE`` built by string formatting (``base.tenancy.names``:
    ``sql.Identifier``); ``connections.settings`` never changed in place (a copy is swapped in); ``apps/`` never
    imports ``base.tenancy`` (the context is the platform's); no ``LISTEN`` outside ``live.broker``; the old shared
    database (``use_shared_database``) is gone and nobody brings it back; no ``hub_id`` column in a hub's model but the listed ones; no bare ``transaction.on_commit`` in ``apps/``
    (``live.operations.on_commit``); no migration of ``base/`` or ``apps/`` asks the router whether a model migrates
    (a ``RunPython``'s hints choose its database); no test counts queries on control's database without naming it
    (a business's reads go to its own).
(g) Operations that need the hub's own database: a business that still shares control's (``db_name=""``, not cut
    yet) is not served at all. Each of them asked at its host, even by its administrator, answers 503 maintenance
    having read nothing of any business, only its row in control's registry; an API key there is refused alike
    (never let through by a session). Unlike (a)–(f), these send requests on the test database.
"""

import ast
import re
from pathlib import Path

import pytest
from test_guardrails import HUB_DIR, _dotted, _offenders, _receiver_name, is_migration, source_files, suite_files

# ── (e) The tenancy ────────────────────────────────────────────────────────────────────────────

#: ``CREATE DATABASE``/``DROP DATABASE`` in a string: its name may only come through ``sql.Identifier``.
DATABASE_DDL_RE = re.compile(r"\b(?:CREATE|DROP|ALTER)\s+DATABASE\b", re.IGNORECASE)
#: Methods that change a dict in place.
DICT_MUTATORS = frozenset({"update", "pop", "popitem", "setdefault", "clear", "__setitem__", "__delitem__"})
#: A ``LISTEN``/``UNLISTEN`` statement, alone in its string (a docstring that mentions it is no statement).
LISTEN_RE = re.compile(r"(?:UN)?LISTEN(?:\s+\S+)?\s*;?")
#: ``transaction.on_commit`` in the modules, by file and count: with the hub's own database the operation's transaction
#: is on the hub's alias and a bare one registers on ``default`` (it would run at once, also after a rollback). The
#: last ones moved to ``live.operations.on_commit``: it stays empty.
BARE_ON_COMMIT_ALLOWED: dict[str, int] = {}
#: Hub models that still have a ``hub_id`` column, each with its reason (the border between hubs is the database).
HUB_ID_COLUMNS: dict[str, str] = {
    "base.hubidentity": "the identity of the hub's database itself.",
    "website.site": "left from when hubs shared one database, so that a hub's website was not another's /.",
    "website.image": "left from when hubs shared one database, with the site's.",
    "verifactu.config": "not tenancy: the business's id in the SaaS.",
}


def bare_on_commit_touches(source: str) -> list[tuple[int, str]]:
    """``(line, what)`` for every ``transaction.on_commit(`` and every import of Django's ``on_commit``."""
    found: set[tuple[int, str]] = set()
    for node in ast.walk(ast.parse(source)):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "on_commit"
            and _receiver_name(node.func.value) == "transaction"
        ):
            found.add((node.lineno, "transaction.on_commit("))
        elif (
            isinstance(node, ast.ImportFrom)
            and node.module == "django.db.transaction"
            and any(alias.name == "on_commit" for alias in node.names)
        ):
            found.add((node.lineno, "from django.db.transaction import on_commit"))
    return sorted(found)


def database_ddl_touches(source: str) -> list[tuple[int, str]]:
    """``(line, what)`` for every ``CREATE``/``DROP``/``ALTER DATABASE`` built by formatting a string."""
    found: set[tuple[int, str]] = set()
    for node in ast.walk(ast.parse(source)):
        texts: list[str] = []
        if isinstance(node, ast.JoinedStr):
            texts = [part.value for part in node.values if isinstance(part, ast.Constant) and isinstance(part.value, str)]
        elif isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Mod, ast.Add)):
            texts = [side.value for side in (node.left, node.right) if isinstance(side, ast.Constant) and isinstance(side.value, str)]
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "format"
            and isinstance(node.func.value, ast.Constant)
            and isinstance(node.func.value.value, str)
        ):
            texts = [node.func.value.value]
        if any(DATABASE_DDL_RE.search(text) for text in texts):
            found.add((node.lineno, "database DDL by string formatting"))
    return sorted(found)


def _is_connections_settings(node: ast.AST) -> bool:
    return isinstance(node, ast.Attribute) and node.attr == "settings" and _receiver_name(node.value) == "connections"


def settings_mutation_touches(source: str) -> list[tuple[int, str]]:
    """``(line, what)`` for every change in place of ``connections.settings`` (an item set or deleted, a mutator)."""
    found: set[tuple[int, str]] = set()
    for node in ast.walk(ast.parse(source)):
        targets = []
        if isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        elif isinstance(node, ast.Delete):
            targets = node.targets
        for target in targets:
            if isinstance(target, ast.Subscript) and _is_connections_settings(target.value):
                found.add((node.lineno, "connections.settings[...] changed in place"))
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in DICT_MUTATORS
            and _is_connections_settings(node.func.value)
        ):
            found.add((node.lineno, f"connections.settings.{node.func.attr}("))
    return sorted(found)


def tenancy_import_touches(source: str) -> list[tuple[int, str]]:
    """``(line, what)`` for every import of ``base.tenancy``."""
    found: set[tuple[int, str]] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found |= {(node.lineno, a.name) for a in node.names if a.name.startswith("base.tenancy")}
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module.startswith("base.tenancy") or (
                node.module == "base" and any(a.name == "tenancy" for a in node.names)
            ):
                found.add((node.lineno, node.module))
    return sorted(found)


def listen_touches(source: str) -> list[tuple[int, str]]:
    """``(line, "LISTEN")`` for every SQL string that starts with ``LISTEN``/``UNLISTEN``."""
    return sorted(
        {
            (node.lineno, "LISTEN")
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and LISTEN_RE.fullmatch(node.value.strip())
        }
    )


def shared_database_touches(source: str) -> list[tuple[int, str]]:
    """``(line, "use_shared_database")`` for every use of the old shared database (a call or an import)."""
    found: set[tuple[int, str]] = set()
    for node in ast.walk(ast.parse(source)):
        if (isinstance(node, ast.Name) and node.id == "use_shared_database") or (
            isinstance(node, ast.Attribute) and node.attr == "use_shared_database"
        ):
            found.add((node.lineno, "use_shared_database"))
        elif isinstance(node, ast.alias) and node.name == "use_shared_database":
            found.add((getattr(node, "lineno", 0), "use_shared_database"))
    return sorted(found)


def router_question_touches(source: str) -> list[tuple[int, str]]:
    """``(line, what)`` for every ``router.allow_migrate…(`` call. A ``RunPython`` already runs only where the router
    lets its hints through: asking it again inside is a branch that, on a business's database, always goes one way."""
    return sorted(
        {
            (node.lineno, f"router.{node.func.attr}(")
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr.startswith("allow_migrate")
            and _receiver_name(node.func.value) == "router"
        }
    )


#: pytest-django's fixtures that count queries: on ``default``, control's database, unless given ``connection=``.
QUERY_COUNT_FIXTURES = frozenset({"django_assert_num_queries", "django_assert_max_num_queries"})


def _counted_on(node: ast.Call, position: int) -> ast.AST | None:
    """The connection a count of queries is given: its argument at ``position``, or ``connection=``."""
    if len(node.args) > position:
        return node.args[position]
    return next((keyword.value for keyword in node.keywords if keyword.arg == "connection"), None)


def _is_django_connection(node: ast.AST | None) -> bool:
    """Django's ``connection``: the one on ``default``, control's database."""
    return node is not None and _dotted(node) in {"connection", "db.connection", "django.db.connection"}


def control_count_touches(source: str) -> list[tuple[int, str]]:
    """``(line, what)`` for every count of queries on control's database that does not name it: a
    ``CaptureQueriesContext`` over Django's ``connection``, or a counting fixture without another ``connection=``."""
    found: set[tuple[int, str]] = set()
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        called = _receiver_name(node.func)
        if called == "CaptureQueriesContext" and _is_django_connection(_counted_on(node, 0)):
            found.add((node.lineno, "CaptureQueriesContext(connection)"))
        elif called in QUERY_COUNT_FIXTURES and (_counted_on(node, 1) is None or _is_django_connection(_counted_on(node, 1))):
            found.add((node.lineno, f"{called}( on control"))
    return sorted(found)


# ── (e) The tenancy: positive controls ─────────────────────────────────────────────────────────

TENANCY_OFFENDER = """\
from base.tenancy.context import use_hub
from base import tenancy
import base.tenancy.router
from base.tenancy.context import use_shared_database
cursor.execute(f"CREATE DATABASE {name} TEMPLATE {template}")
cursor.execute("DROP DATABASE %s" % name)
cursor.execute("ALTER DATABASE {} RENAME".format(name))
connections.settings[alias] = cfg
connections.settings.update({alias: cfg})
del connections.settings[alias]
cursor.execute("LISTEN hub_x")
transaction.on_commit(partial(notify, scope), robust=True)
from django.db.transaction import on_commit
elsewhere = not router.allow_migrate_model(schema_editor.connection.alias, Hub)
captured = CaptureQueriesContext(connection)
captured = utils.CaptureQueriesContext(connection=db.connection)
counting = django_assert_num_queries(1)
counting = django_assert_max_num_queries(3, connection=connection)
"""
TENANCY_LOOKALIKES = """\
\"\"\"LISTEN on control, never CREATE DATABASE by hand.\"\"\"
query = sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name))
connections.settings = {**connections.settings, alias: cfg}
settings = dict(connections.settings)
operations.on_commit(partial(notify, scope))
transaction.atomic(using=alias)
migrations.RunPython(add_prefix, remove_prefix, hints={"model_name": "membership"})
TenantRouter().allow_migrate(alias, "base")
captured = CaptureQueriesContext(connections[current_alias()])
on_control = CaptureQueriesContext(connections["default"])
statements = CaptureQueriesContext(ddl)
counting = django_assert_num_queries(1, connection=connections[current_alias()])
counting = django_assert_max_num_queries(3, connections["default"])
"""


def test_the_tenancy_scanners_see_what_they_must_and_nothing_else():
    assert database_ddl_touches(TENANCY_OFFENDER) == [(5, "database DDL by string formatting")] * 1 + [
        (6, "database DDL by string formatting"),
        (7, "database DDL by string formatting"),
    ]
    assert settings_mutation_touches(TENANCY_OFFENDER) == [
        (8, "connections.settings[...] changed in place"),
        (9, "connections.settings.update("),
        (10, "connections.settings[...] changed in place"),
    ]
    assert tenancy_import_touches(TENANCY_OFFENDER) == [
        (1, "base.tenancy.context"),
        (2, "base"),
        (3, "base.tenancy.router"),
        (4, "base.tenancy.context"),
    ]
    assert listen_touches(TENANCY_OFFENDER) == [(11, "LISTEN")]
    assert shared_database_touches(TENANCY_OFFENDER) == [(4, "use_shared_database")]
    assert bare_on_commit_touches(TENANCY_OFFENDER) == [
        (12, "transaction.on_commit("),
        (13, "from django.db.transaction import on_commit"),
    ]
    assert router_question_touches(TENANCY_OFFENDER) == [(14, "router.allow_migrate_model(")]
    assert control_count_touches(TENANCY_OFFENDER) == [
        (15, "CaptureQueriesContext(connection)"),
        (16, "CaptureQueriesContext(connection)"),
        (17, "django_assert_num_queries( on control"),
        (18, "django_assert_max_num_queries( on control"),
    ]
    for check in (
        database_ddl_touches,
        settings_mutation_touches,
        tenancy_import_touches,
        listen_touches,
        shared_database_touches,
        bare_on_commit_touches,
        router_question_touches,
        control_count_touches,
    ):
        assert check(TENANCY_LOOKALIKES) == [], check.__name__


# ── (e) The tenancy: the real tree ─────────────────────────────────────────────────────────────


def _everywhere(check) -> list[str]:
    return _offenders(lambda path: check((HUB_DIR / path).read_text()), source_files(HUB_DIR))


def test_no_database_ddl_is_built_by_string_formatting():
    offenders = _everywhere(database_ddl_touches)

    assert offenders == [], (
        "A database's name reaches SQL only as sql.Identifier, validated by base.tenancy.names: "
        f"{offenders}"
    )


def test_connections_settings_is_never_changed_in_place():
    offenders = _everywhere(settings_mutation_touches)

    assert offenders == [], (
        "Other threads read connections.settings: swap in a copy under the lock (base.tenancy.connections): "
        f"{offenders}"
    )


def test_the_modules_never_import_the_tenancy():
    files = [path for path in source_files(HUB_DIR) if path.parts[0] == "apps"]

    offenders = _offenders(lambda path: tenancy_import_touches((HUB_DIR / path).read_text()), files)

    assert offenders == [], f"A module never chooses its database: @operation and use_hub do (CLAUDE.md): {offenders}"


def test_nothing_but_live_listens():
    offenders = _everywhere(listen_touches)

    assert offenders == [], f"One LISTEN per process, on control, in live.broker: {offenders}"


def test_nothing_runs_on_a_shared_database_any_more():
    offenders = _offenders(lambda path: shared_database_touches((HUB_DIR / path).read_text()), source_files(HUB_DIR))

    assert offenders == [], (
        "The shared database is gone (base.tenancy.cut): every business has its own; run in "
        f"use_hub(hub) or use_control(): {offenders}"
    )


def test_no_migration_of_a_business_s_app_asks_the_router():
    files = [path for path in source_files(HUB_DIR) if is_migration(path) and path.parts[0] in ("base", "apps")]

    offenders = _offenders(lambda path: router_question_touches((HUB_DIR / path).read_text()), files)

    assert offenders == [], (
        "A migration of a business's app runs where its hints send it, so the router always answers the same there: "
        f"drop the branch, or split the step in two RunPython with their own hints: {offenders}"
    )


def test_no_test_counts_queries_on_control_without_naming_it():
    offenders = _offenders(lambda path: control_count_touches((HUB_DIR / path).read_text()), suite_files(HUB_DIR))

    assert offenders == [], (
        "A business's reads go to its own database, so this count sees none of them and passes with any number of "
        "queries per row: count on that database (connections[current_alias()] inside the business; for a request to "
        "its host, which the test does not enter, connections[base.tenancy.connections.hub_alias(hub)]), giving "
        "django_assert_num_queries its connection=, or name connections['default'] when control's work is counted: "
        f"{offenders}"
    )


def test_no_hub_model_carries_its_hub_but_the_listed_ones():
    from django.apps import apps

    from base.tenancy import inventory

    found = sorted(
        model._meta.label_lower
        for model in apps.get_models()
        if inventory.classify(model) in (inventory.HUB, inventory.CONTEXTUAL)
        and any(getattr(field, "column", None) == "hub_id" for field in model._meta.concrete_fields)
    )

    assert found == sorted(HUB_ID_COLUMNS), (
        "The border between hubs is the database, not a column: drop hub_id, or add a reasoned entry "
        f"to HUB_ID_COLUMNS (and remove those that no longer have one): {found}"
    )


def _on_commit_counts(files) -> dict[str, int]:
    counts = {str(path): len(bare_on_commit_touches((HUB_DIR / path).read_text())) for path in files}
    return {path: count for path, count in counts.items() if count}


def on_commit_problems(counts: dict[str, int]) -> dict[str, tuple[int, int]]:
    """``{file: (found, listed)}`` wherever the bare calls differ from ``BARE_ON_COMMIT_ALLOWED``."""
    return {
        path: (counts.get(path, 0), BARE_ON_COMMIT_ALLOWED.get(path, 0))
        for path in set(counts) | set(BARE_ON_COMMIT_ALLOWED)
        if counts.get(path, 0) != BARE_ON_COMMIT_ALLOWED.get(path, 0)
    }


def test_a_new_bare_on_commit_in_the_modules_is_caught_listed_file_or_not():
    assert BARE_ON_COMMIT_ALLOWED == {}, "it stays empty: a module never goes back to a bare on_commit"
    assert on_commit_problems({}) == {}
    assert on_commit_problems({"apps/demo/services.py": 1}) == {"apps/demo/services.py": (1, 0)}
    # Moved off (flow's and the inbox's through base.outbound, website's to live.operations.on_commit): none comes back.
    assert on_commit_problems({"apps/flow/services/calls.py": 1}) == {"apps/flow/services/calls.py": (1, 0)}
    assert on_commit_problems({"apps/whatsapp_inbox/services.py": 1}) == {"apps/whatsapp_inbox/services.py": (1, 0)}
    assert on_commit_problems({"apps/website/services.py": 4}) == {"apps/website/services.py": (4, 0)}


def test_the_modules_run_after_the_commit_only_through_live():
    files = [path for path in source_files(HUB_DIR) if path.parts[0] == "apps"]

    problems = on_commit_problems(_on_commit_counts(files))

    assert problems == {}, (
        "A module runs after the COMMIT with live.operations.on_commit, on its operation's alias; a bare "
        f"transaction.on_commit registers on default, outside the hub's transaction: {{file: (found, listed)}} {problems}"
    )


# ── (g) Operations that need the hub's own database ───────────────────────────────────────────────────────────────

#: Any key's id: no key exists in a hub without its own database.
ANY_KEY = "0193a2b4-0000-7000-8000-000000000001"
#: The operations that run only in a hub with its own database, with what their screen sends: ``{operation:
#: payload}``. A business that still shares control's database (``db_name=""``, not cut yet) has nothing of them: it is
#: not served at all, its host answers 503 maintenance to anyone until its cut gives it a database of its own.
OWN_DATABASE_OPERATIONS: dict[str, dict] = {
    "base.api_key.create": {"name": "Till", "mode": "full"},
    "base.api_key.rotate": {"id": ANY_KEY},
    "base.api_key.revoke": {"id": ANY_KEY},
    "base.api_key.detail": {"id": ANY_KEY},
    "base.hub.reset": {"dry_run": False, "apps": ["sale"], "confirm": "a"},
    # A copy of the business's data.
    "base.hub.dump_link": {"id": ANY_KEY},
    # An app's tables made when it is turned on, in the hub's own database.
    "base.app.retry": {"app": "printing"},
}
#: ``base.hub.reset_apply`` (the worker's emptying of a reset) and ``base.app.activation_settle`` (the worker's step
#: after making an app's tables) are not above: they are the platform's alone, refused to anyone else before
#: anything is read (review of hub#490), and to the platform itself on a business without its own database
#: (base/tests/test_worker_data.py::test_the_emptying_is_never_run_on_a_shared_database,
#: base/tests/test_app_activation_tables.py).
#: What the screens of those features read in any hub: ``{operation: payload}``.
OWN_DATABASE_READS: dict[str, dict] = {
    "base.api_key.list": {},
    # Settings › Data's «Copies» and the last reset.
    "base.hub.dumps": {},
    # System's size of the business's database (BASE-F40).
    "base.plan.usage": {},
}


def _business_tables() -> set[str]:
    """Every table of a hub's model (and of the outbox)."""
    from django.apps import apps

    from base.tenancy import inventory

    return {
        model._meta.db_table
        for model in apps.get_models(include_auto_created=True)
        if inventory.classify(model) in (inventory.HUB, inventory.CONTEXTUAL)
    }


def business_touches(sent: dict[str, list[str]], tables: set[str]) -> dict[str, list[str]]:
    """``{alias: [table, …]}`` for every statement of ``sent`` that names one of ``tables`` (quoted, as Django does)."""
    found = {
        alias: sorted({table for statement in statements for table in tables if f'"{table}"' in statement})
        for alias, statements in sent.items()
    }
    return {alias: names for alias, names in found.items() if names}


def _defined_in(name: str) -> str:
    import inspect

    from live.operations import get

    return Path(inspect.getsourcefile(get(name).fn)).resolve().relative_to(HUB_DIR).as_posix()


def test_the_own_database_checks_see_what_they_must():
    tables = {"sale_order", "base_apikey"}
    sent = {
        "default": ['SELECT "base_hub"."id" FROM "base_hub"', 'SELECT COUNT(*) FROM "sale_order"'],
        "hub_x": ['INSERT INTO "base_apikey" ("id") VALUES (%s)'],
    }
    assert business_touches(sent, tables) == {"default": ["sale_order"], "hub_x": ["base_apikey"]}
    assert business_touches({"default": ['SELECT "base_hub"."id" FROM "base_hub"']}, tables) == {}
    assert "base_hub" not in _business_tables()
    assert {"base_apikey", "base_appactivation", "sale_order", "live_outboxevent"} <= _business_tables()


def test_the_operations_that_need_the_own_database_are_the_base_s_doors():
    """Their files are where the ORM is (``services.py``/``queries.py``), which ``test_nothing_runs_on_a_shared_database
    _any_more`` keeps off any shared database: there is none."""
    defined = {name: _defined_in(name) for name in [*OWN_DATABASE_OPERATIONS, *OWN_DATABASE_READS]}

    assert set(defined.values()) <= {
        "base/services/api_keys.py",
        "base/services/apps.py",
        "base/services/reset.py",
        "base/queries/api_keys.py",
        "base/queries/dumps.py",
        "base/queries/usage.py",
    }, defined


@pytest.fixture
def not_cut(client):
    """A business that shared control's database and has none of its own yet (``db_name=""``), and ``client`` signed
    in as its administrator."""
    from django.contrib.auth import get_user_model

    from base.models import Membership
    from control.models import Hub

    hub = Hub.objects.create(slug="not-cut", status=Hub.Status.READY)
    assert not hub.db_name
    user = get_user_model().objects.create_user(username="ana", password="pw")
    Membership.objects.create(user=user, host=hub.slug, role=Membership.Role.ADMIN)
    client.force_login(user)
    return hub


def _asked_at_its_door(client, hub, name: str, payload: dict):
    """``name`` asked through its route on ``hub``'s host, as its screen asks it; ``(response, sent)``."""
    from base.api import router
    from base.tenancy.tests import hubs
    from base.tests.routes import bound_routes

    [(method, path)] = [(method, path) for method, path, operation in bound_routes(router) if operation == name]
    host = f"{hub.slug}.localhost"
    with hubs.watched() as sent:
        if method == "GET":
            response = client.get(f"/api{path}", payload, HTTP_HOST=host)
        else:
            response = client.post(f"/api{path}", payload, content_type="application/json", HTTP_HOST=host)
    return response, sent


def assert_refused_untouched(response, sent) -> None:
    """Refused as the business's host refuses a business not served (503 maintenance), having read nothing of any
    business: only its row in control's registry."""
    assert (response.status_code, response.json()["error"]["code"]) == (503, "base.hub_maintenance")
    assert set(sent) <= {"default"}, sent
    assert business_touches(sent, _business_tables()) == {}
    assert any('"base_hub"' in statement for statement in sent["default"])


@pytest.mark.django_db
@pytest.mark.parametrize("name", sorted(OWN_DATABASE_OPERATIONS))
def test_in_a_hub_without_its_own_database_each_refuses_and_touches_no_business_data(name, client, not_cut):
    assert_refused_untouched(*_asked_at_its_door(client, not_cut, name, OWN_DATABASE_OPERATIONS[name]))


@pytest.mark.django_db
@pytest.mark.parametrize("name", sorted(OWN_DATABASE_READS))
def test_in_a_hub_without_its_own_database_its_screen_reads_not_available_and_no_business_data(name, client, not_cut):
    assert_refused_untouched(*_asked_at_its_door(client, not_cut, name, OWN_DATABASE_READS[name]))


@pytest.mark.django_db
def test_an_api_key_on_a_hub_without_its_own_database_is_refused_for_that_reason_not_let_through_by_a_session(
    client, not_cut
):
    key = {"HTTP_AUTHORIZATION": "Bearer erpk_live_" + "x" * 43}
    host = f"{not_cut.slug}.localhost"

    refused = client.get("/api/demo/items", HTTP_HOST=host, **key)

    assert refused.status_code == 503
    assert refused.json()["error"]["code"] == "base.hub_maintenance"
    # Without the key, the administrator's own session is refused alike: nobody is let in.
    without_the_key = client.get("/api/demo/items", HTTP_HOST=host)
    assert (without_the_key.status_code, without_the_key.json()["error"]["code"]) == (503, "base.hub_maintenance")
