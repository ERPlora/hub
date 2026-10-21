"""Each business's message templates are its own (WHATSAPP_INBOX-F27…F31, F33), as its number is (F01).

Phase 1 shares the tables, so a template belongs to the business of the context that made it or whose photo listed it
(its ``host``): another business's photo, list, edit, deletion or send never reaches it. Regression of the shared
copy where business b's photo of Meta's list marked business a's templates «Deleted in WhatsApp Manager».
"""

import datetime as dt
import json
import uuid

import httpx
import pytest
import respx
from live.context import Scope
from live.errors import NotFound

from apps.whatsapp_inbox.models import Template
from apps.whatsapp_inbox.tests.conftest import NOW, A, B, ctx_for, receive, run, system, template

pytestmark = pytest.mark.django_db

SAAS = "http://saas.test"
REGISTER = f"{SAAS}/internal/whatsapp/templates"
DELETE = f"{SAAS}/internal/whatsapp/templates/delete"


def photo(scope, version: int, templates: list | None, phone: str = "+34910000000") -> None:
    """erplora.com's photo of ``scope``'s number, with Meta's list of its templates."""
    system(
        "whatsapp_inbox.channel.sync",
        {"version": version, "status": "connected", "phone_number": phone, "monthly_limit": 150, "templates": templates},
        scope,
    )


def listed(scope) -> list[tuple[str, str, str]]:
    page = run("whatsapp_inbox.template.list", {}, ctx_for(scope=scope))
    return [(row.name, row.status, row.body) for row in page.rows]


def test_b_s_photo_never_marks_a_s_templates_deleted():
    photo(A, 5, [template("recordatorio")])
    photo(B, 7, [], phone="+34910000001")

    assert listed(A) == [("recordatorio", "APPROVED", "Hola {{1}}, te esperamos el {{2}}.")]
    assert listed(B) == []


def test_two_businesses_may_hold_a_template_of_the_same_name_each_with_its_own_text():
    photo(A, 5, [template("recordatorio", body="Hola {{1}}, te esperamos el {{2}} en la peluquería.")])
    photo(B, 7, [template("recordatorio", body="Hola {{1}}, tu mesa es el {{2}}.", meta_id="meta-b")], phone="+34910000001")

    assert listed(A) == [("recordatorio", "APPROVED", "Hola {{1}}, te esperamos el {{2}} en la peluquería.")]
    assert listed(B) == [("recordatorio", "APPROVED", "Hola {{1}}, tu mesa es el {{2}}.")]
    assert set(Template.objects.values_list("host", flat=True)) == {"a", "b"}


def test_a_business_neither_edits_nor_deletes_nor_retries_another_s_template():
    photo(B, 7, [template("recordatorio")], phone="+34910000001")
    photo(A, 5, [])
    theirs = Template.objects.get(host="b")
    ref = {"id": str(theirs.id)}
    edit = {**ref, "category": "UTILITY", "body": "Hola", "submit_key": str(uuid.uuid7())}

    for name, payload in (
        ("whatsapp_inbox.template.update", edit),
        ("whatsapp_inbox.template.delete", ref),
        ("whatsapp_inbox.template.retry", ref),
    ):
        with pytest.raises(NotFound) as raised:
            run(name, payload, ctx_for(scope=A))
        assert raised.value.code == "whatsapp_inbox.template_not_found", name
    theirs.refresh_from_db()
    assert (theirs.deleted_at, theirs.body) == (None, "Hola {{1}}, te esperamos el {{2}}.")


def test_a_business_cannot_send_another_s_template():
    photo(B, 7, [template("recordatorio")], phone="+34910000001")
    photo(A, 5, [])
    conversation = receive("wamid.a1", "34600111222", scope=A)

    with pytest.raises(NotFound) as raised:
        run(
            "whatsapp_inbox.message.send",
            {
                "id": str(conversation.conversation_id),
                "template": {"name": "recordatorio", "language": "es", "variables": ["Ana", "viernes"]},
                "client_message_id": str(uuid.uuid7()),
            },
            ctx_for(scope=A),
        )
    assert raised.value.code == "whatsapp_inbox.template_not_found"


@respx.mock
def test_a_template_made_by_a_business_is_its_own_and_goes_to_meta_for_it(django_capture_on_commit_callbacks):
    route = respx.post(REGISTER).mock(return_value=httpx.Response(200, json={"meta_id": "meta-1", "status": "PENDING"}))
    photo(A, 5, [])
    photo(B, 7, [], phone="+34910000001")
    made = {
        "name": "aviso",
        "language": "es",
        "category": "UTILITY",
        "body": "Hola {{1}}",
        "body_examples": ["Ana"],
        "submit_key": str(uuid.uuid7()),
    }

    with django_capture_on_commit_callbacks(execute=True):
        run("whatsapp_inbox.template.create", made, ctx_for(scope=B))

    assert [name for name, _, _ in listed(B)] == ["aviso"] and listed(A) == []
    assert b'"hub":"b"' in route.calls.last.request.content
    # A's own photo, listing nothing, leaves B's template as it was.
    photo(A, 6, [])
    assert listed(B) == [("aviso", "PENDING", "Hola {{1}}")]


@respx.mock
def test_one_run_of_the_worker_resumes_every_business_s_stuck_templates_each_for_its_own(
    django_capture_on_commit_callbacks, fixed_clock, monkeypatch, settings
):
    """Phase 1's worker runs ``delivery.resume`` on one fixed scope (``WORKER_SCOPE_SLUG``, base/scheduler.py): a
    creation and a deletion of every business whose after-COMMIT call never ran go to erplora.com again in that one
    run, each for its own business and with its own content (review of hub#151: they were only the worker's host's)."""
    photo(A, 5, [template("recordatorio")])
    photo(B, 7, [template("recordatorio", meta_id="meta-b", body="Hola {{1}}, tu mesa es el {{2}}.")], phone="+34910000001")
    made = {}
    for scope, body in ((A, "Hola {{1}}, tu cita en la peluquería"), (B, "Hola {{1}}, tu mesa en el restaurante")):
        made[scope.key] = run(
            "whatsapp_inbox.template.create",
            {"name": f"aviso_{scope.key}", "language": "es", "category": "UTILITY", "body": body,
             "body_examples": ["Ana"], "submit_key": str(uuid.uuid7())},
            ctx_for(scope=scope),
        )
        theirs = Template.objects.get(host=scope.key, name="recordatorio")
        run("whatsapp_inbox.template.delete", {"id": str(theirs.id)}, ctx_for(scope=scope))
    registered = respx.post(REGISTER).mock(
        side_effect=lambda request: httpx.Response(
            200, json={"meta_id": f"meta-new-{json.loads(request.content)['hub']}", "status": "PENDING"}
        )
    )
    deleted = respx.post(DELETE).mock(return_value=httpx.Response(200, json={"deleted": True}))
    monkeypatch.setattr(fixed_clock, "now", lambda: NOW + dt.timedelta(minutes=3))
    worker = Scope("host", settings.WORKER_SCOPE_SLUG)
    assert worker.key not in {"a", "b"}

    with django_capture_on_commit_callbacks(execute=True):
        resumed = system("whatsapp_inbox.delivery.resume", {}, worker)

    assert (resumed.templates, resumed.template_deletions) == (2, 2)
    sent = sorted((body["hub"], body["name"], body["body"]) for body in (json.loads(c.request.content) for c in registered.calls))
    assert sent == [
        ("a", "aviso_a", "Hola {{1}}, tu cita en la peluquería"),
        ("b", "aviso_b", "Hola {{1}}, tu mesa en el restaurante"),
    ]
    gone = sorted((body["hub"], body["meta_id"]) for body in (json.loads(c.request.content) for c in deleted.calls))
    assert gone == [("a", "meta-recordatorio"), ("b", "meta-b")]
    for host in ("a", "b"):
        row = Template.objects.get(pk=made[host].id)
        assert (row.host, row.status, row.meta_id) == (host, "PENDING", f"meta-new-{host}")
        assert Template.objects.get(host=host, name="recordatorio").delete_state == "done"
