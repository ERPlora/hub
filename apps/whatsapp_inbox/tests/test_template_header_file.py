"""WHATSAPP_INBOX-F29, F30 · A template whose header is a photo, a video or a document.

The file is chosen in the template's sheet and kept in the hub's file store (``storages["hub_files"]``, under
``hub-<hex>/whatsapp_inbox/samples/``, named by its content, as the website keeps its images); the template names it,
and its hand-over to erplora.com (door 8, after the COMMIT, with no transaction open) carries it in base64 so that
erplora.com uploads it to Meta as the header's sample before registering the template. Meta asks for the sample on
every review, so an edit and «Send to Meta again» carry it too, with the same key. The file takes the plan's space
for files as Files counts it, and past it is refused as Files refuses. Sending such a template is F33
(``test_template_send_header_file.py``). Cases of the old product (gh:hub#2232, gh:saas#2377) and «Meta did not
answer» never blamed on ERPlora (gh:hub#2731).
"""

import base64
import json
from pathlib import Path

import httpx
import pydantic
import pytest
import respx
from django.apps import apps
from django.core.files.storage import storages
from live.errors import Conflict, InvalidPayload, OperationError
from live.models import OutboxEvent

from apps.whatsapp_inbox.models import Template, TemplateSample
from apps.whatsapp_inbox.tests.conftest import B, connect, ctx_for, run, template
from apps.whatsapp_inbox.tests.test_services_templates import (  # noqa: F401 - shared helpers and fixtures
    delivered,
    key,
    registering,
    written,
)
from base import files
from base.models import Hub

pytestmark = pytest.mark.django_db

JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00" + b"\x01" * 64
OTHER_JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00" + b"\x02" * 64
MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64
PDF = b"%PDF-1.7\n" + b"\x00" * 64
MB = 1024 * 1024


@pytest.fixture(autouse=True)
def hub_files(settings):
    """``storages["hub_files"]`` in memory, empty for each test."""
    settings.STORAGES = {**settings.STORAGES, "hub_files": {"BACKEND": "django.core.files.storage.InMemoryStorage"}}
    storages._storages.pop("hub_files", None)
    yield storages["hub_files"]
    storages._storages.pop("hub_files", None)


def b64(content: bytes) -> str:
    return base64.b64encode(content).decode()


def upload(content: bytes = JPEG, header_format: str = "IMAGE", name: str = "carta.jpg", ctx=None):
    return run(
        "whatsapp_inbox.template_sample.upload",
        {"header_format": header_format, "name": name, "content_base64": b64(content)},
        ctx,
    )


def with_file(sample_id, header_format: str = "IMAGE", **fields) -> dict:
    return written(**{"header": "", "header_format": header_format, "header_sample": str(sample_id), **fields})


def create(payload: dict, ctx=None):
    return run("whatsapp_inbox.template.create", payload, ctx)


def door_8(route) -> dict:
    return json.loads(route.calls.last.request.content)


def approved_with_photo(delivered) -> Template:
    """A template made here with a photo header, which Meta took and approved."""
    connect()
    registering()
    sample = upload()
    out = delivered(lambda: create(with_file(sample.id)))
    row = Template.objects.get(pk=out.id)
    Template.objects.filter(pk=row.pk).update(status=Template.Status.APPROVED)
    row.refresh_from_db()
    return row


# ── The file, kept in the hub's store ───────────────────────────────────────────────────────────


def test_a_photo_for_the_header_is_kept_in_the_hubs_file_store(hub_files):
    out = upload()

    row = TemplateSample.objects.get(pk=out.id)
    assert (out.header_format, out.content_type, out.size, out.name) == ("IMAGE", "image/jpeg", len(JPEG), "carta.jpg")
    hub = Hub.objects.get(slug="a")
    assert row.key.startswith(f"hub-{hub.id.hex}/whatsapp_inbox/samples/") and row.key.endswith(".jpg")
    with hub_files.open(row.key, "rb") as kept:
        assert kept.read() == JPEG
    assert [e.payload for e in OutboxEvent.objects.filter(name="whatsapp_inbox.template_sample.uploaded")] == [
        {"id": str(row.id)}
    ]


def test_the_people_of_the_hub_open_the_file_and_a_visitor_never_does(client):
    # FIX-HUB-BASE-MEDIA-DOES-NOT-SERVE-WHATSAPP-INBOX-SAMPLES: the inbox declares its samples' folder for the hub's
    # sessions (``members_media``), so the template's sheet can show the photo; a visitor gets what a missing file gets.
    from django.contrib.auth import get_user_model

    from base.middleware import SESSION_HOST_KEY
    from base.models import Membership
    from base.storage import hub_prefix, media_url

    row = TemplateSample.objects.get(pk=upload().id)
    hub = Hub.objects.get(slug="a")
    url = media_url(hub.id, row.key.removeprefix(f"{hub_prefix(hub.id)}/"))
    assert client.get(url, HTTP_HOST="a.localhost:8000").status_code == 404
    user = get_user_model().objects.create_user(username="saas:41", password="pw")
    Membership.objects.create(user=user, host="a", role=Membership.Role.EMPLOYEE)
    client.force_login(user)
    session = client.session
    session[SESSION_HOST_KEY] = "a"
    session.save()
    response = client.get(url, HTTP_HOST="a.localhost:8000")
    assert (response.status_code, response["Content-Type"]) == (200, "image/jpeg")
    assert b"".join(response.streaming_content) == JPEG
    assert response["Cache-Control"].startswith("private")


def sign_in(client, host: str = "a") -> None:
    """A session of ``host``'s hub, as its people have after the jump from erplora.com."""
    from django.contrib.auth import get_user_model

    from base.middleware import SESSION_HOST_KEY
    from base.models import Membership

    user = get_user_model().objects.create_user(username=f"saas:{host}-42", password="pw")
    Membership.objects.create(user=user, host=host, role=Membership.Role.EMPLOYEE)
    client.force_login(user)
    session = client.session
    session[SESSION_HOST_KEY] = host
    session.save()


def test_the_file_says_where_its_hubs_people_open_it_and_nobody_else_does(client):
    # FIX-HUB-WHATSAPP-INBOX-TEMPLATE-SHEET-SHOWS-NO-HEADER-THUMBNAIL: the sheet shows the header's photo from the
    # address the file comes with, under the inbox's members' folder of /p/media/: a session of its hub opens it, a
    # visitor gets a 404, and another business's file names its own hub, which this host never serves.
    out = upload()
    hub = Hub.objects.get(slug="a")
    assert out.url.startswith(f"/p/media/{hub.id.hex}/whatsapp_inbox/samples/") and out.url.endswith(".jpg")
    assert client.get(out.url, HTTP_HOST="a.localhost:8000").status_code == 404

    sign_in(client)
    response = client.get(out.url, HTTP_HOST="a.localhost:8000")
    assert (response.status_code, response["Content-Type"]) == (200, "image/jpeg")
    assert b"".join(response.streaming_content) == JPEG

    foreign = upload(OTHER_JPEG, name="de-b.jpg", ctx=ctx_for(scope=B))
    assert foreign.url.startswith(f"/p/media/{Hub.objects.get(slug='b').id.hex}/whatsapp_inbox/samples/")
    assert client.get(foreign.url, HTTP_HOST="a.localhost:8000").status_code == 404


@respx.mock
def test_the_template_and_its_edit_on_its_way_carry_the_address_of_their_file(
    django_capture_on_commit_callbacks, delivered
):
    row = approved_with_photo(delivered)
    first = run("whatsapp_inbox.template.list", {}).rows[0].header_sample
    new = upload(OTHER_JPEG, name="carta-otono.jpg")

    with django_capture_on_commit_callbacks(execute=False):
        run("whatsapp_inbox.template.update", {**with_file(new.id), "id": str(row.id)})

    [listed] = run("whatsapp_inbox.template.list", {}).rows
    kept = TemplateSample.objects.get(pk=row.header_sample_id)
    assert listed.header_sample.url == first.url == upload(name="otra.jpg").url != new.url
    assert first.url.endswith(f"/{kept.key.rsplit('/', 1)[1]}")
    assert listed.draft.header_sample.url == new.url


@pytest.mark.parametrize("key", ["", "website/img/ab.jpg", "hub-zz/whatsapp_inbox/samples/ab.jpg", "hub-%s/website/img/ab.jpg"])
def test_a_key_that_is_no_samples_of_a_hub_has_no_address(key):
    from apps.whatsapp_inbox import samples

    hub = Hub.objects.get(slug="a")
    assert samples.sample_url(key.replace("%s", hub.id.hex)) == ""
    assert samples.sample_url(f"hub-{hub.id.hex}/whatsapp_inbox/samples/ab.jpg") == (
        f"/p/media/{hub.id.hex}/whatsapp_inbox/samples/ab.jpg"
    )


def test_the_same_file_twice_is_one_object_in_the_store(hub_files):
    first, second = upload(name="carta.jpg"), upload(name="menu.jpg")

    assert first.id != second.id
    assert TemplateSample.objects.get(pk=first.id).key == TemplateSample.objects.get(pk=second.id).key
    assert (second.name, len(hub_files.listdir(TemplateSample.objects.get(pk=first.id).key.rsplit("/", 1)[0])[1])) == (
        "menu.jpg",
        1,
    )


@pytest.mark.parametrize(
    ("content", "header_format", "said"),
    [
        (PDF, "IMAGE", "JPEG or PNG"),
        (JPEG, "VIDEO", "MP4"),
        (MP4, "DOCUMENT", "PDF"),
        (b"GIF89a" + b"\x00" * 64, "IMAGE", "JPEG or PNG"),
        (JPEG + b"\x00" * (5 * MB), "IMAGE", "5 MB"),
        (MP4 + b"\x00" * (16 * MB), "VIDEO", "16 MB"),
        (PDF + b"\x00" * (25 * MB), "DOCUMENT", "25 MB"),
    ],
)
def test_a_file_its_header_does_not_take_is_refused_under_its_field_and_nothing_is_kept(
    hub_files, content, header_format, said
):
    with pytest.raises(InvalidPayload) as refused:
        upload(content, header_format)

    assert said in refused.value.fields["content_base64"]
    assert not TemplateSample.objects.exists()
    assert hub_files.listdir("")[0] == []


def test_a_file_that_did_not_arrive_whole_is_said_so():
    with pytest.raises(InvalidPayload) as refused:
        run(
            "whatsapp_inbox.template_sample.upload",
            {"header_format": "IMAGE", "name": "carta.jpg", "content_base64": "@@not base64@@"},
        )

    assert "whole" in refused.value.fields["content_base64"]


def test_whoever_answers_uploads_a_file_but_a_viewer_does_not():
    """Choosing the header's file is part of sending a template (F33, also the employee's), not of Settings."""
    from dataclasses import replace

    from live.errors import PermissionDenied

    assert upload(ctx=ctx_for("hub_employee")).name == "carta.jpg"
    with pytest.raises(PermissionDenied):
        upload(ctx=replace(ctx_for("hub_employee"), permissions=frozenset({"whatsapp_inbox.view"})))


# ── The plan's space for files, the same as Files ───────────────────────────────────────────────


def plan_space(limit: int, slug: str = "a") -> None:
    """The SaaS's photo of ``slug`` includes ``limit`` bytes for the business's files."""
    Hub.objects.filter(slug=slug).update(state={"plan": {"max_storage_bytes": limit}})


def files_upload(content: bytes, name: str = "lleno.pdf", ctx=None):
    """Files (``base.file.upload``) keeps ``content`` at the root of the business's files."""
    return run("base.file.upload", {"folder": "", "name": name, "content_base64": b64(content)}, ctx)


def test_a_file_past_the_plans_space_is_refused_with_the_reason_and_code_of_files(hub_files):
    plan_space(len(PDF) + 10)
    files_upload(PDF)

    said = {}
    for language in ("en", "es"):
        with pytest.raises(Conflict) as refused:
            upload(ctx=ctx_for(language=language))
        with pytest.raises(Conflict) as by_files:
            files_upload(JPEG, "carta.jpg", ctx_for(language=language))
        assert (refused.value.status, refused.value.code) == (409, "base.file_no_space")
        assert refused.value.message == by_files.value.message
        said[language] = refused.value.message

    assert said["en"] != said["es"]
    assert not TemplateSample.objects.exists()
    assert hub_files.listdir(f"hub-{Hub.objects.get(slug='a').id.hex}")[0] == ["files"]


def test_up_to_the_plans_space_the_file_is_kept_and_files_counts_it(hub_files):
    plan_space(len(PDF) + len(JPEG))
    files_upload(PDF)

    out = upload()

    assert TemplateSample.objects.get(pk=out.id).size == len(JPEG)
    with pytest.raises(Conflict) as full:
        files_upload(b"%PDF-1.7\n", "otro.pdf")
    assert full.value.code == "base.file_no_space"


def test_the_same_file_again_takes_no_more_space(hub_files):
    plan_space(len(JPEG))
    first = upload(name="carta.jpg")

    again = upload(name="menu.jpg")

    assert TemplateSample.objects.get(pk=again.id).key == TemplateSample.objects.get(pk=first.id).key


def test_without_a_space_in_its_plan_another_business_keeps_its_file(hub_files):
    plan_space(len(JPEG) - 1)

    assert upload(ctx=ctx_for(scope=B)).name == "carta.jpg"


def test_the_plans_space_is_base_s_one_check_and_its_sentence_is_not_the_inbox_s(hub_files, monkeypatch):
    # FIX-HUB-WHATSAPP-INBOX-PLAN-SPACE-CHECK-STILL-COPIED: the inbox copied Files' check and its sentence, so a change
    # of the limit or of what it says was to be made here too. Now the header's file asks base's own check.
    asked = []
    monkeypatch.setattr(
        files, "refuse_past_the_space", lambda store, hub, size, *, limit_bytes: asked.append((hub, size, limit_bytes))
    )
    plan_space(len(JPEG) - 1)

    upload()  # base's check (here, one that lets everything in) decides: the inbox keeps the file

    assert asked == [(Hub.objects.get(slug="a").id, len(JPEG), len(JPEG) - 1)]
    upload(name="menu.jpg")  # the same file again is the same object: no space asked for
    assert len(asked) == 1
    catalogue = Path(apps.get_app_config("whatsapp_inbox").path, "locale", "es", "LC_MESSAGES", "django.po").read_text()
    assert 'msgid "There is no space left for that file: your plan includes %(space)s."' not in catalogue


def test_the_store_not_answering_while_the_space_is_measured_keeps_nothing(hub_files, monkeypatch):
    """Files' own 503: the space could not be measured, so nothing is taken for «empty» and nothing is kept."""
    plan_space(10 * MB)

    def not_answering(*args, **kwargs):
        raise OSError("the store did not answer")

    monkeypatch.setattr(hub_files, "listdir", not_answering)
    with pytest.raises(OperationError) as failed:
        upload()

    assert (failed.value.status, failed.value.code) == (503, "base.file_store_unavailable")
    assert not TemplateSample.objects.exists()


# ── Creating a template with it (F29) ───────────────────────────────────────────────────────────


@respx.mock
def test_a_template_with_a_photo_header_goes_to_erplora_com_with_its_file(delivered):
    connect()
    route = registering()
    sample = upload()

    out = delivered(lambda: create(with_file(sample.id)))

    row = Template.objects.get(pk=out.id)
    assert (row.header_format, row.header, row.header_sample_id) == ("IMAGE", "", sample.id)
    sent = door_8(route)
    assert (sent["header_format"], sent["header"]) == ("IMAGE", "")
    assert sent["header_sample"] == {"name": "carta.jpg", "content_base64": b64(JPEG)}
    assert (out.header_format, out.header_sample.id, out.header_sample.name) == ("IMAGE", sample.id, "carta.jpg")


@pytest.mark.parametrize(("content", "header_format"), [(MP4, "VIDEO"), (PDF, "DOCUMENT")])
@respx.mock
def test_a_video_or_a_document_goes_the_same_way(delivered, content, header_format):
    connect()
    route = registering()
    sample = upload(content, header_format, name=f"archivo.{header_format.lower()}")

    delivered(lambda: create(with_file(sample.id, header_format)))

    assert door_8(route)["header_format"] == header_format
    assert base64.b64decode(door_8(route)["header_sample"]["content_base64"]) == content


@respx.mock
def test_a_text_header_goes_as_it_always_went(delivered):
    """A template without a file carries neither its kind nor a file: the door's body is the one it was."""
    connect()
    route = registering()

    delivered(lambda: create(written()))

    sent = door_8(route)
    assert "header_format" not in sent and "header_sample" not in sent
    assert sent["header"] == "Tu cita"


@pytest.mark.parametrize("sample", ["none", "another_kind", "another_business"])
@respx.mock
def test_a_file_header_needs_its_file_of_its_kind_and_of_its_business(sample):
    connect()
    route = registering()
    ids = {
        "none": None,
        "another_kind": upload(MP4, "VIDEO", name="visita.mp4").id,
        "another_business": upload(ctx=ctx_for(scope=B)).id,
    }

    payload = written(header="", header_format="IMAGE", header_sample=str(ids[sample]) if ids[sample] else None)
    with pytest.raises(InvalidPayload) as refused:
        create(payload)

    assert "file" in refused.value.fields["header_sample"]
    assert not Template.objects.exists()
    assert route.call_count == 0


def test_a_file_header_has_no_text():
    sample = upload()

    with pytest.raises(pydantic.ValidationError) as refused:
        create(with_file(sample.id, header="Tu cita"))

    assert [error["loc"] for error in refused.value.errors()] == [("header",)]


# ── Editing and sending it again (F30) ──────────────────────────────────────────────────────────


@respx.mock
def test_an_edit_of_an_approved_photo_template_sends_the_new_photo_and_keeps_the_approved_until_meta_takes_it(
    delivered,
):
    row = approved_with_photo(delivered)
    first = row.header_sample_id
    route = registering(meta_id=row.meta_id or "meta-1")
    new = upload(OTHER_JPEG, name="carta-otono.jpg")

    delivered(lambda: run("whatsapp_inbox.template.update", {**with_file(new.id), "id": str(row.id)}))

    row.refresh_from_db()
    assert row.header_sample_id == new.id, "Meta took the edit: the new photo is the template's"
    sent = door_8(route)
    assert base64.b64decode(sent["header_sample"]["content_base64"]) == OTHER_JPEG
    assert first != new.id


@respx.mock
def test_an_edit_that_keeps_the_photo_sends_it_again_for_metas_review(delivered):
    row = approved_with_photo(delivered)
    route = registering(meta_id="meta-1")

    delivered(
        lambda: run(
            "whatsapp_inbox.template.update",
            {**with_file(row.header_sample_id, body="Hola {{1}}, hasta el {{2}}."), "id": str(row.id)},
        )
    )

    assert base64.b64decode(door_8(route)["header_sample"]["content_base64"]) == JPEG


@respx.mock
def test_while_the_edit_is_on_its_way_the_approved_photo_stays_the_templates(django_capture_on_commit_callbacks, delivered):
    row = approved_with_photo(delivered)
    new = upload(OTHER_JPEG, name="carta-otono.jpg")

    with django_capture_on_commit_callbacks(execute=False):
        out = run("whatsapp_inbox.template.update", {**with_file(new.id), "id": str(row.id)})

    row.refresh_from_db()
    assert row.header_sample_id != new.id
    assert (out.header_sample.id, out.draft.header_sample.id, out.draft.header_format) == (
        row.header_sample_id,
        new.id,
        "IMAGE",
    )


@respx.mock
def test_send_to_meta_again_carries_the_same_file_with_the_same_key(delivered):
    connect()
    respx.post("http://saas.test/internal/whatsapp/templates").mock(side_effect=httpx.ConnectError("down"))
    sample = upload()
    out = delivered(lambda: create(with_file(sample.id)))
    row = Template.objects.get(pk=out.id)
    assert row.submit_state == "sending"
    kept_key = row.submit_key

    route = registering()
    delivered(lambda: run("whatsapp_inbox.template.retry", {"id": str(row.id)}))

    assert route.calls.last.request.headers["Idempotency-Key"] == str(kept_key)
    assert base64.b64decode(door_8(route)["header_sample"]["content_base64"]) == JPEG


@respx.mock
def test_meta_not_answering_the_upload_is_said_as_metas_never_erploras(delivered):
    """gh:hub#2731: erplora.com's 409 ``whatsapp.meta_unreachable`` while uploading the sample reads as Meta's."""
    connect()
    registering(status=409, body={"error": {"code": "whatsapp.meta_unreachable", "message": "Meta could not be reached."}})
    sample = upload()

    out = delivered(lambda: create(with_file(sample.id)))

    listed = run("whatsapp_inbox.template.list", {}).rows
    assert listed[0].submit_error_code == "whatsapp_inbox.meta_unreachable"
    assert "Meta" in listed[0].submit_error and "ERPlora" not in listed[0].submit_error
    assert Template.objects.get(pk=out.id).submit_state == "failed"


@respx.mock
def test_a_file_gone_from_the_store_is_said_and_fixed_with_edit(delivered, hub_files):
    connect()
    route = registering()
    sample = upload()
    hub_files.delete(TemplateSample.objects.get(pk=sample.id).key)

    out = delivered(lambda: create(with_file(sample.id)))

    assert route.call_count == 0
    row = Template.objects.get(pk=out.id)
    assert (row.submit_state, row.submit_error_code) == ("failed", "whatsapp_inbox.header_sample_missing")
    assert "Edit" in run("whatsapp_inbox.template.list", {}).rows[0].submit_error


@respx.mock
def test_the_store_not_answering_leaves_it_on_its_way_to_be_sent_again(delivered, hub_files, monkeypatch):
    """The file could not be read, not refused: nothing reaches erplora.com and it goes again with the same key."""
    connect()
    route = registering()
    sample = upload()

    def not_answering(*args, **kwargs):
        raise OSError("the store did not answer")

    monkeypatch.setattr(hub_files, "open", not_answering)
    out = delivered(lambda: create(with_file(sample.id)))

    assert route.call_count == 0
    row = Template.objects.get(pk=out.id)
    assert (row.submit_state, row.submit_error_code) == ("sending", "whatsapp_inbox.saas_unreachable")


# ── What the list says of it (F27, F28, F33) ────────────────────────────────────────────────────


@respx.mock
def test_a_photo_template_made_here_is_edited_and_sent_here_with_its_photo(delivered):
    approved_with_photo(delivered)

    [row] = run("whatsapp_inbox.template.list", {}).rows
    assert (row.editable, row.sendable, row.supported) == (True, True, True)
    assert row.header_sample.name == "carta.jpg"
    assert [r.id for r in run("whatsapp_inbox.template.list", {"sendable": True}).rows] == [row.id]


def test_a_photo_template_from_whatsapp_manager_stays_managed_there():
    connect(templates=[template("promo", header_format="IMAGE")])

    [row] = run("whatsapp_inbox.template.list", {}).rows
    assert (row.editable, row.header_sample) == (False, None)
    with pytest.raises(Conflict) as refused:
        run(
            "whatsapp_inbox.template.update",
            {**with_file(upload().id), "id": str(row.id), "body": row.body, "body_examples": ["Ana", "viernes"]},
        )
    assert refused.value.code == "whatsapp_inbox.template_read_only"


@respx.mock
def test_metas_list_with_another_header_forgets_the_file_kept_here(delivered):
    row = approved_with_photo(delivered)

    connect(version=2, templates=[template(row.name, language=row.language, header="Tu cita", header_format="TEXT")])

    row.refresh_from_db()
    assert (row.header_format, row.header_sample_id) == ("TEXT", None)


@respx.mock
def test_metas_list_with_the_same_photo_header_keeps_the_file(delivered):
    row = approved_with_photo(delivered)

    connect(version=2, templates=[template(row.name, language=row.language, header_format="IMAGE")])

    row.refresh_from_db()
    assert (row.header_format, row.header_sample_id is not None) == ("IMAGE", True)


# ── Never another business's file ───────────────────────────────────────────────────────────────


@respx.mock
def test_a_file_of_another_business_named_by_a_template_is_never_shown_nor_sent(delivered):
    """Phase 1 shares the tables: a template of ``a`` whose row or edit names ``b``'s file (which the operations never
    write: they check it) shows no file, and its hand-over carries none, said as a file to choose again."""
    connect()
    route = registering()
    out = delivered(lambda: create(with_file(upload().id)))
    foreign = upload(OTHER_JPEG, name="de-b.jpg", ctx=ctx_for(scope=B))
    row = Template.objects.get(pk=out.id)
    edit = {
        "category": row.category,
        "header_format": "IMAGE",
        "header": "",
        "header_sample": str(foreign.id),
        "body": row.body,
        "body_examples": row.body_examples,
        "footer": row.footer,
        "buttons": row.buttons,
    }
    Template.objects.filter(pk=row.pk).update(header_sample_id=foreign.id, draft=edit, submit_state="failed")
    calls = route.call_count

    [listed] = run("whatsapp_inbox.template.list", {}).rows
    assert (listed.header_sample, listed.draft.header_sample) == (None, None)

    delivered(lambda: run("whatsapp_inbox.template.retry", {"id": str(row.id)}))

    assert route.call_count == calls, "b's file never leaves for erplora.com"
    row.refresh_from_db()
    assert (row.submit_state, row.submit_error_code) == ("failed", "whatsapp_inbox.header_sample_missing")
