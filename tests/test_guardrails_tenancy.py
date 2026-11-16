"""Guardrails of the tenancy, one database per hub: rules (e) and (g) of the Hub's guardrails. The rest, and the
scanning they share (``source_files``, ``_offenders``), are ``tests/test_guardrails.py``.

(e) The tenancy: no ``CREATE``/``DROP DATABASE`` built by string formatting (``base.tenancy.names``:
    ``sql.Identifier``); ``connections.settings`` never changed in place (a copy is swapped in); ``apps/`` never
    imports ``base.tenancy`` (the context is the platform's); no ``LISTEN`` outside ``live.broker``; the old shared
    database (``use_shared_database``) is gone and nobody brings it back; the tests' fallback never set outside the
    tests; no ``hub_id`` column in a hub's model but the listed ones; no bare ``transaction.on_commit`` in ``apps/``
    (``live.operations.on_commit``); no migration of ``base/`` or ``apps/`` asks the router whether a model migrates
    (a ``RunPython``'s hints choose its database).
(g) Operations that need the hub's own database: in a hub that still shares control's (``db_name=""``) each
    refuses with its domain error before it reads or writes anything of the business in ``default``, and an API key
    is refused for that reason (never let through by a session). Production no longer serves such a business at
    all; the checks stay, the suite's fallback still has one (``base/tenancy/tests/
    legacy.py``). Unlike (a)–(f), these run operations on the test database.
"""

import ast
import re
from pathlib import Path

import pytest
from test_guardrails import HUB_DIR, _offenders, _receiver_name, is_migration, source_files

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


def fallback_touches(source: str) -> list[tuple[int, str]]:
    """``(line, "_test_fallback")`` for every assignment of the tests' fallback (an attribute or ``setattr``)."""
    found: set[tuple[int, str]] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, (ast.Assign, ast.AugAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(target, ast.Attribute) and target.attr == "_test_fallback" for target in targets):
                found.add((node.lineno, "_test_fallback"))
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "setattr"
            and len(node.args) >= 2
            and isinstance(node.args[1], ast.Constant)
            and node.args[1].value == "_test_fallback"
        ):
            found.add((node.lineno, "_test_fallback"))
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
context._test_fallback = SHARED
setattr(context, "_test_fallback", SHARED)
transaction.on_commit(partial(notify, scope), robust=True)
from django.db.transaction import on_commit
elsewhere = not router.allow_migrate_model(schema_editor.connection.alias, Hub)
"""
TENANCY_LOOKALIKES = """\
\"\"\"LISTEN on control, never CREATE DATABASE by hand.\"\"\"
query = sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name))
connections.settings = {**connections.settings, alias: cfg}
settings = dict(connections.settings)
fallback = context._test_fallback
operations.on_commit(partial(notify, scope))
transaction.atomic(using=alias)
migrations.RunPython(add_prefix, remove_prefix, hints={"model_name": "membership"})
TenantRouter().allow_migrate(alias, "base")
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
    assert fallback_touches(TENANCY_OFFENDER) == [(12, "_test_fallback"), (13, "_test_fallback")]
    assert bare_on_commit_touches(TENANCY_OFFENDER) == [
        (14, "transaction.on_commit("),
        (15, "from django.db.transaction import on_commit"),
    ]
    assert router_question_touches(TENANCY_OFFENDER) == [(16, "router.allow_migrate_model(")]
    for check in (
        database_ddl_touches,
        settings_mutation_touches,
        tenancy_import_touches,
        listen_touches,
        shared_database_touches,
        fallback_touches,
        bare_on_commit_touches,
        router_question_touches,
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


def test_the_tests_fallback_is_never_set_outside_the_tests():
    offenders = _everywhere(fallback_touches)

    assert offenders == [], f"Only the suite's conftest.py sets base.tenancy.context._test_fallback: {offenders}"


def test_no_migration_of_a_business_s_app_asks_the_router():
    files = [path for path in source_files(HUB_DIR) if is_migration(path) and path.parts[0] in ("base", "apps")]

    offenders = _offenders(lambda path: router_question_touches((HUB_DIR / path).read_text()), files)

    assert offenders == [], (
        "A migration of a business's app runs where its hints send it, so the router always answers the same there: "
        f"drop the branch, or split the step in two RunPython with their own hints: {offenders}"
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
    assert on_commit_problems({"apps/flow/services.py": 1}) == {"apps/flow/services.py": (1, 0)}
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
#: The operations that run only in a hub with its own database, with what each answers in one that still shares
#: control's (``db_name=""``): ``{operation: (payload, status, code)}``, a domain error that never names the
#: infrastructure. ``base.api_key.detail`` answers as for a key that does not exist (404, ``base/queries/``).
OWN_DATABASE_OPERATIONS: dict[str, tuple[dict, int, str]] = {
    "base.api_key.create": ({"name": "Till", "mode": "full"}, 409, "base.api_keys_unavailable"),
    "base.api_key.rotate": ({"id": ANY_KEY}, 409, "base.api_keys_unavailable"),
    "base.api_key.revoke": ({"id": ANY_KEY}, 409, "base.api_keys_unavailable"),
    "base.api_key.detail": ({"id": ANY_KEY}, 404, "not_found"),
    "base.hub.reset": ({"dry_run": False, "apps": ["sale"], "confirm": "a"}, 409, "base.reset_shared_database"),
    # A copy of the business's data: none is ever made in a business that shares its database.
    "base.hub.dump_link": ({"id": ANY_KEY}, 404, "not_found"),
    # An app's tables made when it is turned on: only a hub with its own database ever waits for them, so there is
    # nothing to try again.
    "base.app.retry": ({"app": "printing"}, 409, "base.app_not_failed"),
}
#: ``base.hub.reset_apply`` (the worker's emptying of a reset) and ``base.app.activation_settle`` (the worker's step
#: after making an app's tables) are not above: they are the platform's alone, refused to anyone else before
#: anything is read (review of hub#490), and to the platform itself on a business without its own database
#: (base/tests/test_worker_data.py::test_the_emptying_is_never_run_on_a_shared_database,
#: base/tests/test_app_activation_tables.py).
#: What the screens of those features read in any hub: in one without its own database the answer says «not available
#: yet» (the screen's notice; an error would paint its load failure) and holds nothing of the feature's.
OWN_DATABASE_READS: dict[str, tuple[dict, dict]] = {
    "base.api_key.list": ({}, {"available": False, "keys": []}),
    # Settings › Data's «Copies» and the last reset.
    "base.hub.dumps": ({}, {"available": False, "reset": None, "dumps": []}),
    # System's size of the business's database (BASE-F40): «Usage and plan» reads the same answer, whose people
    # and devices are control's (Membership, SessionOwner) and stay for every business.
    "base.plan.usage": ({}, {"database": {"available": False, "bytes": None, "day": None}}),
}
#: Tables of a hub that those operations may still read in control's database for a hub without its own, each with its
#: reason; anything else of a hub's there is the business's data and is never touched.
SHARED_MODE_READS: dict[str, str] = {
    "base_appactivation": (
        "what is on is read before any operation runs; a business without its own database exists only under the "
        "suite's fallback (base/tenancy/tests/legacy.py), where its apps are still turned on at once."
    ),
}


def _business_tables() -> set[str]:
    """Every table of a hub's model (and of the outbox), but those ``SHARED_MODE_READS`` lets through."""
    from django.apps import apps

    from base.tenancy import inventory

    return {
        model._meta.db_table
        for model in apps.get_models(include_auto_created=True)
        if inventory.classify(model) in (inventory.HUB, inventory.CONTEXTUAL)
    } - set(SHARED_MODE_READS)


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
    assert "base_hub" not in _business_tables() and "base_appactivation" not in _business_tables()
    assert {"base_apikey", "sale_order", "live_outboxevent"} <= _business_tables()


def test_the_operations_that_need_the_own_database_are_the_base_s_doors():
    """Their files are where the ORM is (``services.py``/``queries.py``), which ``test_nothing_runs_on_a_shared_database
    _any_more`` keeps off any shared database: there is none."""
    defined = {name: _defined_in(name) for name in [*OWN_DATABASE_OPERATIONS, *OWN_DATABASE_READS]}

    assert set(defined.values()) <= {"base/services/__init__.py", "base/queries/__init__.py"}, defined


def _as_admin_of(slug: str):
    from live.context import OperationContext, Scope

    return OperationContext(scope=Scope("host", slug), actor="ana", permissions=frozenset({"*"}), language="en")


def _run_in_a_hub_without_its_database(name: str, payload: dict):
    """``name`` as an administrator of ``a`` (``db_name=""``, no database of its own), in its context; ``(answer or
    error, sent)``.

    Production never enters such a business (``HubWithoutDatabase``, 503 at its door): only the suite's
    fallback does (``base/tenancy/tests/legacy.py``), and there these refusals still keep its data untouched."""
    from live.errors import OperationError
    from live.operations import get

    from base.models import Hub
    from base.tenancy import context
    from base.tenancy.tests import hubs

    hub = Hub.objects.get(slug="a")
    assert not hub.db_name and context.serves_hubs_without_database()
    op = get(name)
    with hubs.watched() as sent, context.use_hub(hub):
        try:
            outcome = op(_as_admin_of(hub.slug), op.input.model_validate(payload))
        except OperationError as error:
            outcome = error
    return outcome, sent


@pytest.mark.django_db
@pytest.mark.parametrize("name", sorted(OWN_DATABASE_OPERATIONS))
def test_in_a_hub_without_its_own_database_each_refuses_and_touches_no_business_data(name):
    from live.errors import OperationError

    payload, status, code = OWN_DATABASE_OPERATIONS[name]

    refused, sent = _run_in_a_hub_without_its_database(name, payload)

    assert isinstance(refused, OperationError), refused
    assert (refused.status, refused.code) == (status, code)
    assert set(sent) <= {"default"}, sent
    assert business_touches(sent, _business_tables()) == {}
    assert any('"base_hub"' in statement for statement in sent["default"])


@pytest.mark.django_db
@pytest.mark.parametrize("name", sorted(OWN_DATABASE_READS))
def test_in_a_hub_without_its_own_database_its_screen_reads_not_available_and_no_business_data(name):
    payload, answer = OWN_DATABASE_READS[name]

    read, sent = _run_in_a_hub_without_its_database(name, payload)

    assert read.model_dump(mode="json", include=set(answer)) == answer
    assert set(sent) <= {"default"}, sent
    assert business_touches(sent, _business_tables()) == {}


@pytest.mark.django_db
def test_an_api_key_on_a_hub_without_its_own_database_is_refused_for_that_reason_not_let_through_by_a_session(client):
    from django.contrib.auth import get_user_model

    from base.models import Membership

    user = get_user_model().objects.create_user(username="ana", password="pw")
    Membership.objects.create(user=user, host="a", role=Membership.Role.ADMIN)
    client.force_login(user)
    key = {"HTTP_AUTHORIZATION": "Bearer erpk_live_" + "x" * 43}

    refused = client.get("/api/demo/items", HTTP_HOST="a.localhost", **key)

    assert refused.status_code == 401
    assert refused.json()["error"]["code"] == "base.api_keys_unavailable"
    # Without the key, the same session goes on as always.
    assert client.get("/api/demo/items", HTTP_HOST="a.localhost").status_code == 200
