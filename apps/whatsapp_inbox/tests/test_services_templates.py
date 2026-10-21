"""The business's message templates, made and changed in the Hub (WHATSAPP_INBOX-F27…F31).

The template is kept here and handed to erplora.com after the COMMIT (door 8: register or edit it at Meta;
door 9: delete it there), like a message: a short transaction keeps it, the HTTP call runs with no
transaction, and erplora.com's answer is recorded in another one. ``respx`` is the transport to erplora.com
only; Customers and the channel are the app's real operations. Cases of the product's tests: a template
saved again is never duplicated, an edit of an approved template keeps the approved one usable until Meta
takes the edit, Meta's verdict never lands on a text changed afterwards, a template deleted here is never
brought back, and «Meta did not answer» is never blamed on ERPlora (gh:hub#2731).
"""

import datetime as dt
import json
import uuid

import httpx
import pydantic
import pytest
import respx
from live.errors import Conflict, PermissionDenied
from live.models import OutboxEvent

from apps.whatsapp_inbox.models import Template
from apps.whatsapp_inbox.tests.conftest import NOW, connect, ctx_for, run, system, template

pytestmark = pytest.mark.django_db

SAAS = "http://saas.test"
REGISTER = f"{SAAS}/internal/whatsapp/templates"
DELETE = f"{SAAS}/internal/whatsapp/templates/delete"


def key() -> str:
    return str(uuid.uuid7())


def written(**fields) -> dict:
    """What the form sends for a new template."""
    body = {
        "name": "recordatorio_cita",
        "language": "es",
        "category": "UTILITY",
        "header": "Tu cita",
        "body": "Hola {{1}}, te esperamos el {{2}}.",
        "body_examples": ["Ana", "viernes"],
        "footer": "Peluquería Ana",
        "buttons": [{"type": "QUICK_REPLY", "text": "Confirmar"}, {"type": "QUICK_REPLY", "text": "Cambiar"}],
        "submit_key": key(),
    }
    body.update(fields)
    return body


def registering(status=200, body=None, **json_body):
    """erplora.com's door 8: by default, Meta took the template for review with a new id."""
    answer = body if body is not None else {"meta_id": "meta-1", "status": "PENDING", **json_body}
    return respx.post(REGISTER).mock(return_value=httpx.Response(status, json=answer))


def deleting(status=200, body=None):
    return respx.post(DELETE).mock(return_value=httpx.Response(status, json=body if body is not None else {"deleted": True}))


@pytest.fixture
def delivered(django_capture_on_commit_callbacks):
    """Run a write and then what it left for after its COMMIT (the call to erplora.com)."""

    def run_and_deliver(write):
        with django_capture_on_commit_callbacks(execute=True):
            return write()

    return run_and_deliver


def create(payload=None, ctx=None):
    return run("whatsapp_inbox.template.create", written(**(payload or {})), ctx)


def update(row: Template, **fields):
    body = {
        "id": str(row.id),
        "category": row.category,
        "header": row.header,
        "body": row.body,
        # A template synced from Meta may come without its examples: the form asks for one per variable.
        "body_examples": row.body_examples or ["Ana", "viernes", "10:00"][: row.variables],
        "footer": row.footer,
        "buttons": row.buttons,
        "submit_key": key(),
    }
    body.update(fields)
    return run("whatsapp_inbox.template.update", body)


def listed(**params):
    return run("whatsapp_inbox.template.list", params).rows


def events(name: str) -> list[dict]:
    return [event.payload for event in OutboxEvent.objects.filter(name=name).order_by("id")]


# ── Creating (F29) ──────────────────────────────────────────────────────────────────────────────


@respx.mock
def test_a_new_template_is_kept_unsent_and_registered_at_meta_only_after_the_commit(django_capture_on_commit_callbacks):
    connect()
    route = registering()
    with django_capture_on_commit_callbacks(execute=False) as pending:
        out = create()
    row = Template.objects.get(pk=out.id)
    assert (row.status, row.submit_state) == ("DRAFT", "queued")
    assert route.call_count == 0  # nothing waits for erplora.com inside the transaction
    for callback in pending:
        callback()
    request = route.calls.last.request
    assert request.headers["Idempotency-Key"] == str(row.submit_key)
    assert json.loads(request.content) == {
        "hub": "a",
        "name": "recordatorio_cita",
        "language": "es",
        "category": "UTILITY",
        "header": "Tu cita",
        "body": "Hola {{1}}, te esperamos el {{2}}.",
        "body_examples": ["Ana", "viernes"],
        "footer": "Peluquería Ana",
        "buttons": [{"type": "QUICK_REPLY", "text": "Confirmar"}, {"type": "QUICK_REPLY", "text": "Cambiar"}],
        "meta_id": "",
    }
    row.refresh_from_db()
    assert (row.status, row.meta_id, row.submit_state, row.submit_error_code) == ("PENDING", "meta-1", "", "")
    assert row.variables == 2
    assert events("whatsapp_inbox.template.created") == [{"id": str(row.id)}]
    assert {"id": str(row.id)} in events("whatsapp_inbox.template.updated")


@respx.mock
def test_saving_the_same_template_twice_with_its_key_is_one_template_and_one_registration(delivered):
    connect()
    route = registering()
    payload = written()
    first = delivered(lambda: run("whatsapp_inbox.template.create", payload))
    second = delivered(lambda: run("whatsapp_inbox.template.create", payload))
    assert first.id == second.id
    assert route.call_count == 1
    assert Template.objects.count() == 1


@respx.mock
def test_a_name_and_language_already_taken_is_refused_and_nothing_is_kept():
    connect(templates=[template("recordatorio_cita")])
    route = registering()
    with pytest.raises(Conflict) as excinfo:
        create()
    assert excinfo.value.code == "whatsapp_inbox.template_exists"
    assert route.call_count == 0
    assert Template.objects.count() == 1


@pytest.mark.parametrize(
    ("channel", "code"),
    [({"status": "not_connected"}, "whatsapp_inbox.channel_not_connected"), (None, "whatsapp_inbox.channel_not_connected")],
)
@respx.mock
def test_without_a_connected_number_no_template_is_kept(channel, code):
    if channel is not None:
        connect(**channel)
    with pytest.raises(Conflict) as excinfo:
        create()
    assert excinfo.value.code == code
    assert not Template.objects.exists()


def test_without_erplora_com_no_template_is_kept(settings):
    connect()
    settings.SAAS_INTERNAL_URL = ""
    with pytest.raises(Conflict) as excinfo:
        create()
    assert excinfo.value.code == "whatsapp_inbox.saas_unconfigured"
    assert not Template.objects.exists()


def test_the_month_spent_does_not_stop_making_templates():
    connect(monthly_limit=150, monthly_usage=150)
    assert create().status == "DRAFT"


@pytest.mark.parametrize(
    ("fields", "field"),
    [
        ({"name": "Recordatorio Cita"}, "name"),
        ({"name": "x" * 513}, "name"),
        ({"category": "AUTHENTICATION"}, "category"),
        ({"body": ""}, "body"),
        ({"body": "Hola {{1}} y {{3}}", "body_examples": ["a", "b"]}, "body"),
        ({"body": "Hola {{nombre}}", "body_examples": []}, "body"),
        ({"body": "Hola {{1}} y {{dia}}", "body_examples": ["a"]}, "body"),
        ({"body": "Hola {{1}}", "body_examples": []}, "body_examples"),
        ({"body": "Hola {{1}}", "body_examples": ["   "]}, "body_examples"),
        ({"header": "Hola {{1}}"}, "header"),
        ({"header": "x" * 61}, "header"),
        ({"footer": "x" * 61}, "footer"),
        ({"buttons": [{"type": "QUICK_REPLY", "text": "x" * 26}]}, "buttons"),
        ({"buttons": [{"type": "URL", "text": "Web"}]}, "buttons"),
        ({"buttons": [{"type": "URL", "text": "Web", "url": "http://peluqueria.test"}]}, "buttons"),
        ({"buttons": [{"type": "URL", "text": "Web", "url": "https://p.test/{{1}}"}]}, "buttons"),
        ({"buttons": [{"type": "PHONE_NUMBER", "text": "Llamar", "phone_number": "910000000"}]}, "buttons"),
        ({"buttons": [{"type": "QUICK_REPLY", "text": f"Opción {n}"} for n in range(11)]}, "buttons"),
        ({"buttons": [{"type": "URL", "text": f"Web {n}", "url": f"https://p.test/{n}"} for n in range(3)]}, "buttons"),
        (
            {
                "buttons": [
                    {"type": "QUICK_REPLY", "text": "Sí"},
                    {"type": "URL", "text": "Web", "url": "https://p.test"},
                    {"type": "QUICK_REPLY", "text": "No"},
                ]
            },
            "buttons",
        ),
    ],
)
def test_what_meta_would_refuse_is_refused_here_under_its_field(fields, field):
    connect()
    with pytest.raises(pydantic.ValidationError) as excinfo:
        create(fields)
    assert field in {str(error["loc"][0]) for error in excinfo.value.errors()}
    assert not Template.objects.exists()


def test_a_call_and_a_link_button_go_together_and_quick_replies_apart():
    connect()
    out = create(
        {
            "buttons": [
                {"type": "URL", "text": "Web", "url": "https://peluqueria.test/citas"},
                {"type": "PHONE_NUMBER", "text": "Llamar", "phone_number": "+34910000000"},
            ]
        }
    )
    assert [button["type"] for button in Template.objects.get(pk=out.id).buttons] == ["URL", "PHONE_NUMBER"]


@pytest.mark.parametrize("role", ["hub_manager", "hub_employee"])
def test_only_who_configures_makes_changes_or_deletes_templates(role):
    connect(templates=[template("recordatorio")])
    row = Template.objects.get()
    with pytest.raises(PermissionDenied):
        create(ctx=ctx_for(role))
    with pytest.raises(PermissionDenied):
        run("whatsapp_inbox.template.delete", {"id": str(row.id)}, ctx_for(role))


# ── erplora.com's answer (F29, F30) ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("code", "kept", "words"),
    [
        ("whatsapp.template_invalid", "whatsapp_inbox.template_refused", "Template name already exists"),
        ("whatsapp.meta_unreachable", "whatsapp_inbox.meta_unreachable", "Meta did not answer"),
        ("whatsapp.meta_rate_limited", "whatsapp_inbox.meta_rate_limited", "Meta asks to wait"),
    ],
)
@respx.mock
def test_a_refusal_keeps_the_template_unsent_with_its_reason_never_blaming_erplora(delivered, code, kept, words):
    """gh:hub#2731: with Meta down the screen says Meta did not answer, not that ERPlora failed."""
    connect()
    registering(409, {"error": {"code": code, "message": "Template name already exists"}})
    out = delivered(create)
    row = Template.objects.get(pk=out.id)
    assert (row.status, row.submit_state, row.submit_error_code) == ("DRAFT", "failed", kept)
    assert words in row.submit_error
    assert "ERPlora" not in row.submit_error and "erplora.com" not in row.submit_error


@pytest.mark.parametrize(
    ("answer", "code"),
    [
        (httpx.ConnectError("refused"), "whatsapp_inbox.saas_unreachable"),
        (httpx.ReadTimeout("slow"), "whatsapp_inbox.send_unknown"),
    ],
)
@respx.mock
def test_without_an_answer_it_stays_on_its_way_and_a_retry_hands_it_with_the_same_key(delivered, answer, code):
    connect()
    route = respx.post(REGISTER).mock(side_effect=[answer, httpx.Response(200, json={"meta_id": "m", "status": "PENDING"})])
    out = delivered(create)
    row = Template.objects.get(pk=out.id)
    assert (row.status, row.submit_state, row.submit_error_code) == ("DRAFT", "sending", code)
    first_key = route.calls[0].request.headers["Idempotency-Key"]
    delivered(lambda: run("whatsapp_inbox.template.retry", {"id": str(row.id)}))
    assert route.calls[1].request.headers["Idempotency-Key"] == first_key
    row.refresh_from_db()
    assert (row.status, row.submit_state, row.meta_id) == ("PENDING", "", "m")


@respx.mock
def test_a_refused_template_is_fixed_and_saved_again_with_a_new_key(delivered):
    connect()
    route = registering(409, {"error": {"code": "whatsapp.template_invalid", "message": "Bad body"}})
    out = delivered(create)
    row = Template.objects.get(pk=out.id)
    route.mock(return_value=httpx.Response(200, json={"meta_id": "m2", "status": "PENDING"}))
    delivered(lambda: update(row, body="Hola {{1}}, tu cita es el {{2}}."))
    row.refresh_from_db()
    assert (row.status, row.body, row.submit_state) == ("PENDING", "Hola {{1}}, tu cita es el {{2}}.", "")
    keys = [call.request.headers["Idempotency-Key"] for call in route.calls]
    assert len(set(keys)) == 2


@respx.mock
def test_a_retry_of_a_refused_template_goes_as_a_new_save_with_a_new_key(delivered):
    """Refused (Meta asked to wait): with the same key erplora.com would repeat the same refusal."""
    connect()
    route = registering(409, {"error": {"code": "whatsapp.meta_rate_limited", "message": "Too many calls"}})
    row = Template.objects.get(pk=delivered(create).id)
    assert row.submit_state == "failed"
    route.mock(return_value=httpx.Response(200, json={"meta_id": "m3", "status": "PENDING"}))
    delivered(lambda: run("whatsapp_inbox.template.retry", {"id": str(row.id)}))
    keys = [call.request.headers["Idempotency-Key"] for call in route.calls]
    assert len(keys) == 2 and keys[0] != keys[1]
    row.refresh_from_db()
    assert (row.status, row.submit_state, row.meta_id) == ("PENDING", "", "m3")


# ── Editing (F30)───────────────────────────────────────────────────────────────────────────────


def approved(**fields) -> Template:
    """A connected number whose only template is ``recordatorio`` as Meta has it (approved unless told)."""
    connect(templates=[template("recordatorio", **fields)])
    return Template.objects.get(name="recordatorio")


@respx.mock
def test_an_edit_of_an_approved_template_keeps_the_approved_one_until_meta_takes_the_edit(delivered):
    row = approved()
    route = respx.post(REGISTER).mock(side_effect=httpx.ConnectError("refused"))
    delivered(lambda: update(row, body="Hola {{1}}, recuerda tu cita del {{2}}.", body_examples=["Ana", "lunes"]))
    row.refresh_from_db()
    assert (row.status, row.body) == ("APPROVED", "Hola {{1}}, te esperamos el {{2}}.")
    assert row.draft["body"] == "Hola {{1}}, recuerda tu cita del {{2}}."
    assert json.loads(route.calls.last.request.content)["meta_id"] == "meta-recordatorio"
    # Still sendable as Meta approved it.
    assert [t.name for t in listed(status="APPROVED", sendable=True)] == ["recordatorio"]
    route.side_effect = None
    route.mock(return_value=httpx.Response(200, json={"meta_id": "meta-recordatorio", "status": "PENDING"}))
    delivered(lambda: run("whatsapp_inbox.template.retry", {"id": str(row.id)}))
    row.refresh_from_db()
    assert (row.status, row.body, row.draft, row.rejected_reason) == (
        "PENDING",
        "Hola {{1}}, recuerda tu cita del {{2}}.",
        None,
        "",
    )


@respx.mock
def test_meta_s_verdict_never_lands_on_a_text_changed_afterwards(delivered):
    row = approved()
    respx.post(REGISTER).mock(side_effect=httpx.ConnectError("refused"))
    delivered(lambda: update(row, body="Hola {{1}}, nuevo texto {{2}}."))
    connect(version=2, templates=[template("recordatorio", status="APPROVED", body="Hola {{1}}, otro {{2}}.")])
    row.refresh_from_db()
    assert row.body == "Hola {{1}}, otro {{2}}."  # what Meta has
    assert row.draft["body"] == "Hola {{1}}, nuevo texto {{2}}."  # what is waiting to go


@respx.mock
def test_meta_s_list_never_overwrites_a_new_template_still_on_its_way(delivered):
    """Meta lists one of that name before the Hub hears back: what was written stays and goes with its key."""
    connect()
    route = respx.post(REGISTER).mock(side_effect=httpx.ConnectError("refused"))
    row = Template.objects.get(pk=delivered(create).id)
    connect(version=2, templates=[template("recordatorio_cita", status="REJECTED", body="Otro {{1}} {{2}}.")])
    row.refresh_from_db()
    assert (row.status, row.submit_state, row.body) == ("DRAFT", "sending", "Hola {{1}}, te esperamos el {{2}}.")
    assert Template.objects.filter(name="recordatorio_cita").count() == 1
    route.side_effect = None
    route.mock(return_value=httpx.Response(200, json={"meta_id": "m4", "status": "PENDING"}))
    delivered(lambda: run("whatsapp_inbox.template.retry", {"id": str(row.id)}))
    keys = [call.request.headers["Idempotency-Key"] for call in route.calls]
    assert keys[0] == keys[1]
    row.refresh_from_db()
    assert (row.status, row.meta_id, row.body) == ("PENDING", "m4", "Hola {{1}}, te esperamos el {{2}}.")


@pytest.mark.parametrize(
    ("fields", "code"),
    [
        ({"status": "PENDING"}, "whatsapp_inbox.template_in_review"),
        ({"status": "DISABLED"}, "whatsapp_inbox.template_read_only"),
        ({"category": "AUTHENTICATION"}, "whatsapp_inbox.template_read_only"),
        ({"header_format": "IMAGE", "header": ""}, "whatsapp_inbox.template_read_only"),
        ({"buttons": [{"type": "URL", "text": "Web", "url": "https://p.test/{{1}}"}]}, "whatsapp_inbox.template_read_only"),
        ({"buttons": [{"type": "COPY_CODE", "text": "Copiar"}]}, "whatsapp_inbox.template_read_only"),
    ],
)
@respx.mock
def test_what_only_whatsapp_manager_changes_is_read_only_here(fields, code):
    row = approved(**fields)
    route = registering()
    with pytest.raises(Conflict) as excinfo:
        # What the form can write; the template Meta holds is what makes it read-only.
        update(row, category="UTILITY", buttons=[], footer="Nuevo pie")
    assert excinfo.value.code == code
    assert route.call_count == 0


@respx.mock
def test_a_template_on_its_way_to_meta_is_not_changed_until_it_lands(django_capture_on_commit_callbacks):
    connect()
    with django_capture_on_commit_callbacks(execute=False):
        out = create()
    with pytest.raises(Conflict) as excinfo:
        update(Template.objects.get(pk=out.id), footer="Otro")
    assert excinfo.value.code == "whatsapp_inbox.template_submitting"


@respx.mock
def test_the_category_changes_only_while_meta_has_not_judged_it_or_rejected_it(delivered):
    connect(templates=[template("recordatorio"), template("rechazada", status="REJECTED", rejected_reason="INVALID_FORMAT")])
    row, rejected = Template.objects.get(name="recordatorio"), Template.objects.get(name="rechazada")
    registering()
    with pytest.raises(Conflict) as excinfo:
        update(row, category="MARKETING")
    assert excinfo.value.code == "whatsapp_inbox.template_category_fixed"
    delivered(lambda: update(rejected, category="MARKETING"))
    rejected.refresh_from_db()
    assert (rejected.category, rejected.status) == ("MARKETING", "PENDING")


# ── Deleting (F31) ──────────────────────────────────────────────────────────────────────────────


@respx.mock
def test_deleting_takes_it_off_the_list_and_deletes_that_one_at_meta_after_the_commit(delivered):
    row = approved()
    route = deleting()
    delivered(lambda: run("whatsapp_inbox.template.delete", {"id": str(row.id)}))
    assert json.loads(route.calls.last.request.content) == {
        "hub": "a",
        "name": "recordatorio",
        "language": "es",
        "meta_id": "meta-recordatorio",
    }
    row.refresh_from_db()
    assert (row.delete_state, row.deleted_at) == ("done", NOW)
    assert listed() == []
    assert events("whatsapp_inbox.template.deleted") == [{"id": str(row.id)}]


@respx.mock
def test_a_deletion_meta_has_not_confirmed_stays_listed_as_deleting_with_its_reason(delivered):
    row = approved()
    deleting(409, {"error": {"code": "whatsapp.meta_unreachable", "message": "timeout"}})
    delivered(lambda: run("whatsapp_inbox.template.delete", {"id": str(row.id)}))
    row.refresh_from_db()
    assert (row.delete_state, row.submit_error_code) == ("pending", "whatsapp_inbox.meta_unreachable")
    [shown] = listed()
    assert (shown.id, shown.deleting) == (row.id, True)
    # Not sendable while it is being deleted.
    assert listed(status="APPROVED", sendable=True) == []


@respx.mock
def test_a_template_meta_never_had_is_deleted_without_asking_erplora(delivered):
    connect()
    registering(409, {"error": {"code": "whatsapp.template_invalid", "message": "Bad"}})
    out = delivered(create)
    route = deleting()
    delivered(lambda: run("whatsapp_inbox.template.delete", {"id": str(out.id)}))
    assert route.call_count == 0
    assert Template.objects.get(pk=out.id).delete_state == "done"


@respx.mock
def test_a_template_deleted_here_is_never_brought_back_but_a_new_one_of_that_name_is(delivered):
    row = approved()
    deleting(409, {"error": {"code": "whatsapp.meta_unreachable", "message": "timeout"}})
    delivered(lambda: run("whatsapp_inbox.template.delete", {"id": str(row.id)}))
    connect(version=2, templates=[template("recordatorio")])
    assert listed() == [] or all(t.deleting for t in listed())
    assert Template.objects.filter(name="recordatorio", deleted_at__isnull=True).count() == 0
    # Meta confirmed it and, weeks later, the business makes another one with that name in WhatsApp Manager.
    deleting()
    delivered(lambda: run("whatsapp_inbox.template.retry", {"id": str(row.id)}))
    connect(version=3, templates=[template("recordatorio", meta_id="meta-new")])
    [again] = listed()
    assert (again.meta_id, again.deleting) == ("meta-new", False)
    assert again.id != row.id


# ── Sending what Meta approved (F33) ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "fields",
    [
        {"header_format": "IMAGE", "header": ""},
        # gh:whatsapp_inbox#226, #230: a variable in the title.
        {"header": "Tu cita, {{1}}", "body": "Te esperamos el {{2}}."},
        # gh:whatsapp_inbox#186: named variables; the Hub fills them by number only.
        {"body": "Hola {{nombre}}, te esperamos el {{dia}}."},
    ],
)
@respx.mock
def test_a_template_made_in_whatsapp_manager_the_hub_cannot_fill_is_brought_but_not_sent(fields):
    connect(templates=[template("de_manager", **fields), template("sencilla")])
    assert {t.name for t in listed(status="APPROVED")} == {"de_manager", "sencilla"}
    assert [t.name for t in listed(status="APPROVED", sendable=True)] == ["sencilla"]
    system("whatsapp_inbox.message.receive", {
        "wa_message_id": "wamid.IN", "from": "34600111222", "contact_name": "Ana", "type": "text",
        "text": "Hola", "sent_at": (NOW - dt.timedelta(minutes=5)).isoformat(),
    })
    with pytest.raises(Conflict) as excinfo:
        run(
            "whatsapp_inbox.message.send",
            {"conversation": "Ana", "template": {"name": "de_manager", "variables": ["a", "b"]}, "client_message_id": key()},
        )
    assert excinfo.value.code == "whatsapp_inbox.template_not_sendable"


# ── The worker hands again what never ended (phase 1 runs its scheduled task too) ───────────────


@respx.mock
def test_the_worker_hands_again_the_templates_whose_delivery_never_ended(delivered, fixed_clock, monkeypatch):
    with_pending = approved()
    registering()
    # A creation and a deletion whose after-COMMIT call never ran (the process died).
    out = create()
    run("whatsapp_inbox.template.delete", {"id": str(with_pending.id)})
    deleting()
    monkeypatch.setattr(fixed_clock, "now", lambda: NOW + dt.timedelta(minutes=3))
    resumed = delivered(lambda: system("whatsapp_inbox.delivery.resume", {}))
    assert (resumed.templates, resumed.template_deletions) == (1, 1)
    assert Template.objects.get(pk=out.id).status == "PENDING"
    assert Template.objects.get(pk=with_pending.id).delete_state == "done"
