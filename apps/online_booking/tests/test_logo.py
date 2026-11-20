"""The booking page's logo: the owner uploads it in Settings (a JPG, PNG or WebP, as the website takes its images),
saves it with the page's other settings and the page shows it from the business's own address, the only one its
Content Security Policy loads images from. An address of somewhere else is no longer taken."""

import base64
import hashlib
import io
import os

import pytest
from django.conf import settings as django_settings
from django.core.files.base import ContentFile
from live.errors import InvalidPayload, PermissionDenied
from PIL import Image as PILImage

from apps.flow.tests.test_api import post
from apps.online_booking.models import Settings
from base.storage import hub_prefix
from base.tenancy.context import use_hub
from base.tests.test_images import hub_files as hub_files
from base.tests.test_public_door import B_HOST, door
from control.models import Hub

from .conftest import HOST, HUB_DB, A, B, make_page, public, run
from .test_api import admin_client as admin_client

pytestmark = HUB_DB

FOLDER = "online_booking/logo/"


def png(colour=(200, 30, 30)) -> bytes:
    buffer = io.BytesIO()
    PILImage.new("RGB", (60, 20), colour).save(buffer, "PNG")
    return buffer.getvalue()


def upload(raw: bytes, **options):
    data = {"filename": "logo.png", "content_type": "image/png", "data_base64": base64.b64encode(raw).decode()}
    return run("online_booking.settings.upload_logo", data, **options)


def hub_of(scope):
    return Hub.objects.get(slug=scope.key).id


def name_of(raw: bytes) -> str:
    return f"{hashlib.sha256(raw).hexdigest()[:16]}.png"


def test_the_owner_uploads_a_logo_and_it_is_kept_in_the_business_s_public_folder(hub_files):
    raw = png()

    logo = upload(raw)

    assert logo.id == name_of(raw)
    assert logo.url == f"/p/media/{hub_of(A).hex}/{FOLDER}{name_of(raw)}"
    assert hub_files.open(f"{hub_prefix(hub_of(A))}/{FOLDER}{name_of(raw)}").read() == raw
    # Uploading is not saving: the page keeps its logo until the settings are saved.
    assert not Settings.objects.exists()


def test_only_who_saves_the_settings_uploads_a_logo(hub_files):
    with pytest.raises(PermissionDenied):
        upload(png(), role="hub_manager")
    assert not hub_files.exists(f"{hub_prefix(hub_of(A))}/{FOLDER}")


def test_a_file_that_is_no_image_is_refused_on_its_field(hub_files):
    with pytest.raises(InvalidPayload) as refused:
        run(
            "online_booking.settings.upload_logo",
            {"filename": "logo.png", "content_type": "image/png", "data_base64": base64.b64encode(b"text").decode()},
        )
    assert set(refused.value.fields) == {"data_base64"}


def test_the_saved_logo_is_in_the_settings_and_on_the_page_from_the_business_s_own_address(hub_files):
    make_page()
    logo = upload(png())

    saved = run("online_booking.settings.update", {"logo": logo.id})

    assert (saved.logo, saved.logo_url) == (logo.id, logo.url)
    assert run("online_booking.settings.get").logo_url == logo.url
    assert Settings.objects.get().logo == logo.id
    page_logo = public("page").logo_url
    assert page_logo == logo.url
    assert page_logo.startswith("/p/media/")


def test_removing_the_logo_leaves_the_page_without_one(hub_files):
    make_page()
    run("online_booking.settings.update", {"logo": upload(png()).id})

    saved = run("online_booking.settings.update", {"logo": ""})

    assert (saved.logo, saved.logo_url) == ("", "")
    assert public("page").logo_url == ""


def test_a_logo_never_uploaded_is_refused_on_its_field_and_nothing_is_saved(hub_files):
    make_page(page_title="Salón Lucía")
    never = name_of(png(colour=(1, 2, 3)))

    with pytest.raises(InvalidPayload) as refused:
        run("online_booking.settings.update", {"logo": never, "page_title": "Otro"})

    assert set(refused.value.fields) == {"logo"}
    assert (Settings.objects.get().logo, Settings.objects.get().page_title) == ("", "Salón Lucía")


@pytest.mark.parametrize(
    "logo", ["https://salon.example/logo.png", "../avatars/0123456789abcdef.png", "0123456789abcdef.gif", "logo.png"]
)
def test_a_logo_that_is_no_name_of_an_upload_is_refused_on_its_field(admin_client, logo):
    refused = post(admin_client, "/online_booking/settings", {"logo": logo})

    assert (refused.status_code, set(refused.json()["error"]["fields"])) == (422, {"logo"})
    assert refused.json()["error"]["fields"]["logo"] == "That logo was not uploaded to this business: upload it again."


def test_an_address_of_somewhere_else_is_no_longer_taken(admin_client):
    refused = post(admin_client, "/online_booking/settings", {"logo_url": "https://salon.example/logo.png"})

    assert (refused.status_code, set(refused.json()["error"]["fields"])) == (422, {"logo_url"})
    assert not Settings.objects.exists()


def test_a_logo_bigger_than_djangos_ceiling_still_uploads(admin_client, hub_files):
    buffer = io.BytesIO()
    PILImage.frombytes("RGB", (1000, 1000), os.urandom(3_000_000)).save(buffer, format="PNG")
    raw = buffer.getvalue()
    assert len(raw) > django_settings.DATA_UPLOAD_MAX_MEMORY_SIZE
    body = {"filename": "logo.png", "content_type": "image/png", "data_base64": base64.b64encode(raw).decode()}

    response = post(admin_client, "/online_booking/settings/logo", body)

    assert (response.status_code, response.json()["id"]) == (201, name_of(raw))


def test_another_business_s_logo_is_never_taken_nor_shown(hub_files, hub_b):
    make_page()
    with use_hub(hub_b):
        make_page()
        theirs = upload(png(colour=(9, 9, 9)), scope=B)
        run("online_booking.settings.update", {"logo": theirs.id}, scope=B)

    with pytest.raises(InvalidPayload) as refused:
        run("online_booking.settings.update", {"logo": theirs.id})

    assert set(refused.value.fields) == {"logo"}
    assert public("page").logo_url == ""
    with use_hub(hub_b):
        assert theirs.url.startswith(f"/p/media/{hub_of(B).hex}/")


def test_the_page_shows_the_logo_a_visitor_can_open_on_the_business_s_address(client, hub_files, hub_b):
    raw = png()
    make_page()
    run("online_booking.settings.update", {"logo": upload(raw).id})
    hub_files.save(f"{hub_prefix(hub_of(B))}/{FOLDER}{name_of(raw)}", ContentFile(raw))

    url = door(client, "online_booking.public.page").json()["logo_url"]
    served = client.get(url, HTTP_HOST=HOST)

    assert served.status_code == 200
    assert b"".join(served.streaming_content) == raw
    # From another business's address, even the same file is not its to serve.
    assert client.get(url, HTTP_HOST=B_HOST).status_code == 404
