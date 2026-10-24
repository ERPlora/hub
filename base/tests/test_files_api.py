"""Files' operations and routes (APP-BASE-8, BASE-G82…G86): ``base.file.*``, on the hub of the request only.

Everyone of the hub sees and opens the files (``base.view_files``); who runs it (owner, admin) also uploads, makes
folders and renames (``base.upload_files``) and deletes (``base.delete_files``; moving takes both, as the old hub).
Every write records its event (``base.file.<fact>``) in its transaction, and the live listing follows it after the
COMMIT. A file is read at ``/api/files/raw`` with the session, never cached, sandboxed and, unless it is a type that is
safe to show, as an attachment: never from ``/p/media/`` (public), never a URL of the bucket (saas#968, saas#972).
"""

import base64
import json

import pytest
from django.core.files.base import ContentFile
from django.core.files.storage import storages
from django.urls import resolve
from live.context import OperationContext, Scope
from live.errors import InvalidPayload, NotFound, OperationError, PermissionDenied
from live.live_registry import live_registry
from live.meta import all_live_app_configs, permissions_for_role
from live.models import OutboxEvent
from live.operations import get

from base import events, files
from base.models import Hub
from base.storage import hub_prefix

A = Scope("host", "a")
B = Scope("host", "b")
VIEW, UPLOAD, DELETE = "base.view_files", "base.upload_files", "base.delete_files"
PDF = b"%PDF-1.7\n" + b"x" * 64
OPERATIONS = {
    "base.file.list": ("query", VIEW),
    "base.file.read": ("query", VIEW),
    "base.file.upload": ("command", UPLOAD),
    "base.file.create_folder": ("command", UPLOAD),
    "base.file.rename": ("command", UPLOAD),
    "base.file.move": ("command", DELETE),
    "base.file.delete": ("command", DELETE),
}
FILE_EVENTS = [
    "base.file.uploaded",
    "base.file.folder_created",
    "base.file.renamed",
    "base.file.moved",
    "base.file.deleted",
]


@pytest.fixture(autouse=True)
def store(settings):
    settings.STORAGES = {**settings.STORAGES, "hub_files": {"BACKEND": "django.core.files.storage.InMemoryStorage"}}
    return storages["hub_files"]


def ctx(*permissions, scope=A):
    return OperationContext(
        scope=scope, actor="ana", permissions=frozenset(permissions or (VIEW, UPLOAD, DELETE)), language="en"
    )


def run(op_name, context=None, /, **data):
    op = get(op_name)
    return op(context or ctx(), op.input.model_validate(data)).model_dump(mode="json")


def hub(slug="a") -> Hub:
    return Hub.objects.get(slug=slug)


def put(store, slug, path, content=PDF):
    store.save(f"{hub_prefix(hub(slug).id)}/files/{path}", ContentFile(content))


def b64(content=PDF):
    return base64.b64encode(content).decode()


def recorded(*names):
    return list(OutboxEvent.objects.filter(name__in=names or FILE_EVENTS).values_list("scope_key", "name", "payload"))


# ── Declarations ─────────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(("name", "declared"), sorted(OPERATIONS.items()))
def test_each_operation_has_its_permission_and_the_assistant_knows_it(name, declared):
    op = get(name)
    assert (op.kind, op.permission) == declared
    assert op.ai and op.ai["description"]
    # Integrations reach the files with an API key too (read for the queries, write for the commands).
    assert op.expose_api


def test_everyone_sees_the_files_who_runs_the_business_changes_them():
    configs = all_live_app_configs()
    for role in ("hub_manager", "hub_employee"):
        granted = permissions_for_role(configs, role)
        assert VIEW in granted
        assert not {UPLOAD, DELETE} & set(granted)
    base = next(config for config in configs if config.label == "base")
    assert {VIEW, UPLOAD, DELETE} <= set(base.permissions)


def test_the_listing_follows_every_write_of_the_files_and_the_photo():
    assert set(live_registry.subscribable["base.file.list"]) == {*FILE_EVENTS, events.HUB_STATE_APPLIED}
    assert [name for name in events.ALL if name.startswith("base.file.")] == FILE_EVENTS


# ── See (BASE-G82) ───────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_the_listing_says_the_plan_s_space_and_what_the_person_may_do(store):
    put(store, "a", "Facturas/marzo.pdf")
    state = hub("a")
    state.state = {"plan": {"slug": "starter", "max_storage_bytes": 5 * 1024**3}}
    state.save(update_fields=["state"])

    listing = run("base.file.list", folder="Facturas")

    assert [item["name"] for item in listing["files"]] == ["marzo.pdf"]
    assert listing["space"] == {"used_bytes": len(PDF), "limit_bytes": 5 * 1024**3}
    assert listing["can"] == {"upload": True, "delete": True}
    seen = run("base.file.list", ctx(VIEW))
    assert seen["can"] == {"upload": False, "delete": False}


@pytest.mark.django_db
@pytest.mark.parametrize("plan", [None, {}, {"max_storage_bytes": None}, {"max_storage_bytes": 0}, {"max_storage_bytes": "1"}])
def test_without_a_space_in_the_plan_there_is_no_limit(plan):
    state = hub("a")
    state.state = {"plan": plan} if plan is not None else {}
    state.save(update_fields=["state"])
    assert run("base.file.list")["space"]["limit_bytes"] is None


@pytest.mark.django_db
def test_a_hub_lists_its_own_files_only(store):
    put(store, "b", "Secreto/nominas.pdf")
    listing = run("base.file.list")
    assert (listing["folders"], listing["files"], listing["space"]["used_bytes"]) == ([], [], 0)
    assert run("base.file.list", ctx(scope=B))["folders"][0]["name"] == "Secreto"


# ── Upload and new folder (BASE-G83) ─────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_an_upload_keeps_the_file_and_records_its_event(store):
    saved = run("base.file.upload", folder="", name="marzo.pdf", content_base64=b64())
    assert saved == {"path": "marzo.pdf", "name": "marzo.pdf", "size": len(PDF)}
    with store.open(f"{hub_prefix(hub('a').id)}/files/marzo.pdf") as stored:
        assert stored.read() == PDF
    assert recorded() == [("a", "base.file.uploaded", {"path": "marzo.pdf"})]


@pytest.mark.django_db
def test_an_upload_lands_in_the_hub_of_the_request_only(store):
    run("base.file.upload", ctx(scope=B), folder="", name="b.pdf", content_base64=b64())
    assert store.exists(f"{hub_prefix(hub('b').id)}/files/b.pdf")
    assert not store.exists(f"{hub_prefix(hub('a').id)}/files/b.pdf")
    # Its event is b's: a's live queries are never told.
    assert recorded() == [("b", "base.file.uploaded", {"path": "b.pdf"})]


@pytest.mark.django_db
def test_an_upload_that_is_not_base64_is_refused():
    with pytest.raises(InvalidPayload) as refused:
        run("base.file.upload", folder="", name="a.pdf", content_base64="not base64!")
    assert refused.value.code == "base.file_not_base64"
    assert recorded() == []


@pytest.mark.django_db
def test_an_upload_past_the_plan_s_space_is_refused(store):
    state = hub("a")
    state.state = {"plan": {"max_storage_bytes": len(PDF) + 10}}
    state.save(update_fields=["state"])
    put(store, "a", "a.pdf")
    with pytest.raises(OperationError) as refused:
        run("base.file.upload", folder="", name="b.pdf", content_base64=b64(b"x" * 11))
    assert (refused.value.status, refused.value.code) == (409, "base.file_no_space")


@pytest.mark.django_db
def test_a_new_folder_records_its_event():
    assert run("base.file.create_folder", parent="", name="Facturas") == {"path": "Facturas", "name": "Facturas"}
    assert recorded() == [("a", "base.file.folder_created", {"path": "Facturas"})]


@pytest.mark.django_db
def test_who_does_not_run_the_business_neither_uploads_nor_makes_folders():
    for name, data in (
        ("base.file.upload", {"folder": "", "name": "a.pdf", "content_base64": b64()}),
        ("base.file.create_folder", {"parent": "", "name": "x"}),
        ("base.file.rename", {"path": "a.pdf", "name": "b.pdf"}),
    ):
        op = get(name)
        with pytest.raises(PermissionDenied):
            op(ctx(VIEW), op.input.model_validate(data))
    assert recorded() == []


# ── Read (BASE-G84) ──────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_reading_describes_the_file_of_this_hub(store):
    put(store, "a", "Facturas/marzo.pdf")
    assert run("base.file.read", path="Facturas/marzo.pdf") == {
        "path": "Facturas/marzo.pdf",
        "name": "marzo.pdf",
        "size": len(PDF),
        "content_type": "application/pdf",
        "preview": "pdf",
    }
    with pytest.raises(NotFound):
        run("base.file.read", ctx(scope=B), path="Facturas/marzo.pdf")


# ── Rename and move (BASE-G85) ───────────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_renaming_records_where_it_went(store):
    put(store, "a", "a.pdf")
    assert run("base.file.rename", path="a.pdf", name="b.pdf") == {"path": "b.pdf", "name": "b.pdf"}
    assert recorded() == [("a", "base.file.renamed", {"path": "b.pdf", "from": "a.pdf"})]


@pytest.mark.django_db
def test_moving_records_where_it_went(store):
    put(store, "a", "a.pdf")
    run("base.file.create_folder", parent="", name="Facturas")
    assert run("base.file.move", path="a.pdf", to="Facturas") == {"path": "Facturas/a.pdf", "name": "a.pdf"}
    assert recorded("base.file.moved") == [("a", "base.file.moved", {"path": "Facturas/a.pdf", "from": "a.pdf"})]


@pytest.mark.django_db
def test_moving_takes_both_deleting_where_it_was_and_uploading_where_it_goes(store):
    put(store, "a", "a.pdf")
    with pytest.raises(PermissionDenied):
        run("base.file.move", ctx(VIEW, DELETE), path="a.pdf", to="")
    assert recorded() == []


# ── Delete (BASE-G86) ────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_deleting_records_its_event(store):
    put(store, "a", "Facturas/a.pdf")
    assert run("base.file.delete", path="Facturas") == {"path": "Facturas", "folder": True}
    assert recorded() == [("a", "base.file.deleted", {"path": "Facturas", "folder": True})]


@pytest.mark.django_db
def test_who_may_not_delete_does_not(store):
    put(store, "a", "a.pdf")
    op = get("base.file.delete")
    with pytest.raises(PermissionDenied):
        op(ctx(VIEW, UPLOAD), op.input.model_validate({"path": "a.pdf"}))
    assert store.exists(f"{hub_prefix(hub('a').id)}/files/a.pdf")


# ── Over HTTP ────────────────────────────────────────────────────────────────────────────────────────────────

ROUTES = {
    ("GET", "/api/files", "base.file.list"),
    ("GET", "/api/files/raw", "base.file.read"),
    ("POST", "/api/files/upload", "base.file.upload"),
    ("POST", "/api/files/folder", "base.file.create_folder"),
    ("POST", "/api/files/rename", "base.file.rename"),
    ("POST", "/api/files/move", "base.file.move"),
    ("POST", "/api/files/delete", "base.file.delete"),
}


@pytest.mark.parametrize(("method", "path", "operation"), sorted(ROUTES))
def test_each_route_is_bound_to_its_operation(method, path, operation):
    from base.api import router

    [route] = router.path_operations[path.removeprefix("/api")].operations
    assert (route.methods, route.operation_id) == ([method], operation)
    assert resolve(path).url_name


def test_the_spa_s_route_map_names_the_files_routes(settings):
    spa = json.loads((settings.BASE_DIR / "frontend" / "generated" / "operations.json").read_text())
    mine = {(route["method"].upper(), route["path"], op) for op, route in spa.items() if op.startswith("base.file.")}
    assert mine == ROUTES


def owner(client, make_user, slug="a"):
    client.force_login(make_user(f"ana-{slug}", host=slug, role="hub_owner"))
    return client


def http(client, method, path, host="a.localhost:8000", **kwargs):
    return getattr(client, method)(path, HTTP_HOST=host, **kwargs)


@pytest.mark.django_db
def test_an_owner_uploads_and_lists_over_http(client, make_user):
    owner(client, make_user)
    body = {"folder": "", "name": "marzo.pdf", "content_base64": b64()}
    response = http(client, "post", "/api/files/upload", data=body, content_type="application/json")
    assert response.status_code == 200, response.content
    listing = http(client, "get", "/api/files").json()
    assert [item["name"] for item in listing["files"]] == ["marzo.pdf"]


@pytest.mark.django_db
def test_a_file_as_heavy_as_the_ceiling_goes_up_over_http(client, make_user, monkeypatch):
    # The body is the file in base64 and its JSON: more than Django's 2.5 MB for any other view.
    monkeypatch.setattr(files, "MAX_FILE_BYTES", 3 * 1024 * 1024)
    owner(client, make_user)
    heavy = b"x" * (3 * 1024 * 1024)
    body = json.dumps({"folder": "", "name": "big.bin", "content_base64": b64(heavy)})
    response = http(client, "post", "/api/files/upload", data=body, content_type="application/json")
    assert response.status_code == 200, response.content
    assert response.json()["size"] == len(heavy)


@pytest.mark.django_db
def test_an_employee_sees_but_does_not_upload_over_http(client, make_user):
    client.force_login(make_user("eva", host="a", role="hub_employee"))
    assert http(client, "get", "/api/files").status_code == 200
    body = {"folder": "", "name": "a.pdf", "content_base64": b64()}
    response = http(client, "post", "/api/files/upload", data=body, content_type="application/json")
    assert (response.status_code, response.json()["error"]["code"]) == (403, "permission_denied")


@pytest.mark.django_db
def test_without_a_session_nothing_is_listed_nor_read(client, store):
    put(store, "a", "a.pdf")
    assert http(client, "get", "/api/files").status_code == 401
    assert http(client, "get", "/api/files/raw", data={"path": "a.pdf"}).status_code == 401


def raw(client, path, inline=False, host="a.localhost:8000", accept="*/*"):
    data = {"path": path, **({"inline": "true"} if inline else {})}
    return client.get("/api/files/raw", data, HTTP_HOST=host, HTTP_ACCEPT=accept)


@pytest.mark.django_db
def test_a_file_is_downloaded_with_the_session_never_cached_and_sandboxed(client, make_user, store):
    put(store, "a", "Facturas/marzo 2026.pdf")
    owner(client, make_user)
    response = raw(client, "Facturas/marzo 2026.pdf")
    assert response.status_code == 200
    assert b"".join(response.streaming_content) == PDF
    assert response["Content-Type"] == "application/pdf"
    assert response["Content-Disposition"] == "attachment; filename*=UTF-8''marzo%202026.pdf"
    assert response["Cache-Control"] == "private, no-store"
    assert response["Content-Security-Policy"] == "default-src 'none'; sandbox"
    assert response["X-Content-Type-Options"] == "nosniff"
    assert not response.cookies


@pytest.mark.django_db
def test_a_file_safe_to_show_is_shown_inline_when_asked(client, make_user, store):
    put(store, "a", "notas.txt", b"hola")
    owner(client, make_user)
    response = raw(client, "notas.txt", inline=True)
    assert response["Content-Type"] == "text/plain; charset=utf-8"
    assert response["Content-Disposition"] == "inline; filename*=UTF-8''notas.txt"


@pytest.mark.django_db
@pytest.mark.parametrize("name", ["logo.svg", "pagina.zzz"])
def test_what_is_not_safe_to_show_is_always_an_attachment_of_plain_bytes(client, make_user, store, name):
    put(store, "a", name, b"<svg onload='alert(1)'/>")
    owner(client, make_user)
    response = raw(client, name, inline=True)
    assert response["Content-Type"] == "application/octet-stream"
    assert response["Content-Disposition"].startswith("attachment;")


@pytest.mark.django_db
def test_a_name_with_quotes_or_newlines_never_breaks_the_header(client, make_user, store):
    put(store, "a", 'a"b;c.txt', b"x")
    owner(client, make_user)
    assert raw(client, 'a"b;c.txt')["Content-Disposition"] == "attachment; filename*=UTF-8''a%22b%3Bc.txt"


@pytest.mark.django_db
def test_an_integration_that_asks_for_json_gets_the_description(client, make_user, store):
    put(store, "a", "a.pdf")
    owner(client, make_user)
    response = raw(client, "a.pdf", accept="application/json")
    assert response.json()["name"] == "a.pdf"


@pytest.mark.django_db
def test_another_hub_s_file_is_never_read_from_this_host(client, make_user, store):
    put(store, "b", "Secreto/nominas.pdf")
    owner(client, make_user)
    response = raw(client, "Secreto/nominas.pdf")
    assert (response.status_code, response.json()["error"]["code"]) == (404, "base.file_missing")
    climb = f"../../{hub_prefix(hub('b').id)}/files/Secreto/nominas.pdf"
    assert raw(client, climb).status_code == 422


@pytest.mark.django_db
def test_the_business_files_are_never_public(client, make_user, store):
    put(store, "a", "Facturas/marzo.pdf")
    a = hub("a")
    for path in ("files/Facturas/marzo.pdf", "website/img/../../files/Facturas/marzo.pdf"):
        assert http(client, "get", f"/p/media/{a.id.hex}/{path}").status_code == 404
    owner(client, make_user)
    assert http(client, "get", f"/p/media/{a.id.hex}/files/Facturas/marzo.pdf").status_code == 404
