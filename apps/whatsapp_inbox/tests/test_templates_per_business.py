"""Each business's message templates are its own (WHATSAPP_INBOX-F27…F31, F33), in two real databases."""

import datetime as dt
import json
import uuid

import httpx
import pytest
import respx
from live.context import Scope
from live.errors import NotFound

from apps.whatsapp_inbox.models import Template
from apps.whatsapp_inbox.tests.conftest import NOW, ctx_for, receive, run, system, template
from base.tenancy.context import use_hub
from base.tenancy.tests import hubs

pytestmark = [
    pytest.mark.django_db(databases=hubs.HUB_DATABASES),
    pytest.mark.usefixtures("no_test_fallback"),
]

SAAS = "http://saas.test"
REGISTER = f"{SAAS}/internal/whatsapp/templates"
DELETE = f"{SAAS}/internal/whatsapp/templates/delete"


def photo(hub, version: int, templates: list | None, phone: str = "+34910000000") -> None:
    scope = Scope("host", hub.slug)
    with use_hub(hub):
        system(
            "whatsapp_inbox.channel.sync",
            {"version": version, "status": "connected", "phone_number": phone, "monthly_limit": 150, "templates": templates},
            scope,
        )


def listed(hub) -> list[tuple[str, str, str]]:
    with use_hub(hub):
        page = run("whatsapp_inbox.template.list", {}, ctx_for(scope=Scope("host", hub.slug)))
        return [(row.name, row.status, row.body) for row in page.rows]


def test_b_s_photo_never_marks_a_s_templates_deleted(hub_a, hub_b):
    photo(hub_a, 5, [template("recordatorio")])
    photo(hub_b, 7, [], phone="+34910000001")

    assert listed(hub_a) == [("recordatorio", "APPROVED", "Hola {{1}}, te esperamos el {{2}}.")]
    assert listed(hub_b) == []


def test_two_businesses_may_hold_a_template_of_the_same_name_each_with_its_own_text(hub_a, hub_b):
    photo(hub_a, 5, [template("recordatorio", body="Hola {{1}}, te esperamos el {{2}} en la peluquería.")])
    photo(hub_b, 7, [template("recordatorio", body="Hola {{1}}, tu mesa es el {{2}}.", meta_id="meta-b")], phone="+34910000001")

    assert listed(hub_a) == [("recordatorio", "APPROVED", "Hola {{1}}, te esperamos el {{2}} en la peluquería.")]
    assert listed(hub_b) == [("recordatorio", "APPROVED", "Hola {{1}}, tu mesa es el {{2}}.")]


def test_a_business_neither_edits_nor_deletes_nor_retries_another_s_template(hub_a, hub_b):
    photo(hub_b, 7, [template("recordatorio")], phone="+34910000001")
    with use_hub(hub_b):
        theirs = Template.objects.get()
    ref = {"id": str(theirs.id)}
    edit = {**ref, "category": "UTILITY", "body": "Hola", "submit_key": str(uuid.uuid7())}

    with use_hub(hub_a):
        for name, payload in (
            ("whatsapp_inbox.template.update", edit),
            ("whatsapp_inbox.template.delete", ref),
            ("whatsapp_inbox.template.retry", ref),
        ):
            with pytest.raises(NotFound) as raised:
                run(name, payload, ctx_for(scope=Scope("host", hub_a.slug)))
            assert raised.value.code == "whatsapp_inbox.template_not_found", name
    theirs.refresh_from_db()
    assert (theirs.deleted_at, theirs.body) == (None, "Hola {{1}}, te esperamos el {{2}}.")


def test_a_business_cannot_send_another_s_template(hub_a, hub_b):
    photo(hub_b, 7, [template("recordatorio")], phone="+34910000001")
    photo(hub_a, 5, [])
    with use_hub(hub_a):
        conversation = receive("wamid.a1", "34600111222", scope=Scope("host", hub_a.slug))
        with pytest.raises(NotFound) as raised:
            run(
                "whatsapp_inbox.message.send",
                {
                    "id": str(conversation.conversation_id),
                    "template": {"name": "recordatorio", "language": "es", "variables": ["Ana", "viernes"]},
                    "client_message_id": str(uuid.uuid7()),
                },
                ctx_for(scope=Scope("host", hub_a.slug)),
            )
        assert raised.value.code == "whatsapp_inbox.template_not_found"


@respx.mock
def test_a_template_made_by_a_business_is_its_own_and_goes_to_meta_for_it(hub_a, hub_b, django_capture_on_commit_callbacks):
    route = respx.post(REGISTER).mock(return_value=httpx.Response(200, json={"meta_id": "meta-1", "status": "PENDING"}))
    photo(hub_b, 7, [])
    made = {
        "name": "aviso",
        "language": "es",
        "category": "UTILITY",
        "body": "Hola {{1}}",
        "body_examples": ["Ana"],
        "submit_key": str(uuid.uuid7()),
    }

    with use_hub(hub_b) as active, django_capture_on_commit_callbacks(execute=True, using=active.alias):
        run("whatsapp_inbox.template.create", made, ctx_for(scope=Scope("host", hub_b.slug)))

    assert [name for name, _, _ in listed(hub_b)] == ["aviso"] and listed(hub_a) == []
    assert b'"hub":"tenant-b"' in route.calls.last.request.content


@respx.mock
def test_each_worker_pass_resumes_only_its_own_templates(hub_a, hub_b, django_capture_on_commit_callbacks, fixed_clock, monkeypatch):
    photo(hub_a, 5, [template("recordatorio")])
    photo(hub_b, 7, [template("recordatorio", meta_id="meta-b", body="Hola {{1}}, tu mesa es el {{2}}.")], phone="+34910000001")
    made = {}
    for hub, body in ((hub_a, "Hola {{1}}, tu cita en la peluquería"), (hub_b, "Hola {{1}}, tu mesa en el restaurante")):
        with use_hub(hub):
            made[hub.slug] = run(
                "whatsapp_inbox.template.create",
                {"name": f"aviso_{'a' if hub is hub_a else 'b'}", "language": "es", "category": "UTILITY", "body": body,
                 "body_examples": ["Ana"], "submit_key": str(uuid.uuid7())},
                ctx_for(scope=Scope("host", hub.slug)),
            )
            theirs = Template.objects.get(name="recordatorio")
            run("whatsapp_inbox.template.delete", {"id": str(theirs.id)}, ctx_for(scope=Scope("host", hub.slug)))
    registered = respx.post(REGISTER).mock(
        side_effect=lambda request: httpx.Response(
            200, json={"meta_id": f"meta-new-{json.loads(request.content)['hub']}", "status": "PENDING"}
        )
    )
    deleted = respx.post(DELETE).mock(return_value=httpx.Response(200, json={"deleted": True}))
    monkeypatch.setattr(fixed_clock, "now", lambda: NOW + dt.timedelta(minutes=3))

    for hub in (hub_a, hub_b):
        with use_hub(hub) as active, django_capture_on_commit_callbacks(execute=True, using=active.alias):
            resumed = system("whatsapp_inbox.delivery.resume", {}, Scope("host", hub.slug))
        assert (resumed.templates, resumed.template_deletions) == (1, 1)

    sent = sorted((body["hub"], body["name"], body["body"]) for body in (json.loads(c.request.content) for c in registered.calls))
    assert sent == [
        ("tenant-a", "aviso_a", "Hola {{1}}, tu cita en la peluquería"),
        ("tenant-b", "aviso_b", "Hola {{1}}, tu mesa en el restaurante"),
    ]
    gone = sorted((body["hub"], body["meta_id"]) for body in (json.loads(c.request.content) for c in deleted.calls))
    assert gone == [("tenant-a", "meta-recordatorio"), ("tenant-b", "meta-b")]
    for hub in (hub_a, hub_b):
        with use_hub(hub):
            row = Template.objects.get(pk=made[hub.slug].id)
            assert (row.status, row.meta_id) == ("PENDING", f"meta-new-{hub.slug}")
            assert Template.objects.get(name="recordatorio").delete_state == "done"
