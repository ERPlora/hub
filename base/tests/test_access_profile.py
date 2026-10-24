"""BASE-G125: «My profile»: one's own name, contact email, photo, language and appearance in this hub.

The profile is always the person's who has the session. The name and the contact email are this business's: the
contact email is not the one to sign in with and never gives nor takes any access. The language and the appearance
follow the person on any device of the hub; empty = the business's.
"""

import base64
import io
import json

import pytest
from django.conf import settings
from django.core.files.storage import storages
from live.models import OutboxEvent
from PIL import Image as PILImage

from base.models import Credential, Hub, Membership, Profile

pytestmark = pytest.mark.django_db

HOST = "a.localhost:8000"


def get(client):
    response = client.get("/api/me/profile", HTTP_HOST=HOST)
    assert response.status_code == 200, response.content
    return response.json()


def post(client, path, body):
    return client.post(f"/api{path}", json.dumps(body), content_type="application/json", HTTP_HOST=HOST)


def png(side=8) -> str:
    buffer = io.BytesIO()
    PILImage.new("RGB", (side, side), "teal").save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode()


@pytest.fixture
def ana(client, make_user, settings):
    # ``storages["hub_files"]`` in memory, empty for each test (as apps/website/tests/conftest.py does).
    settings.STORAGES = {**settings.STORAGES, "hub_files": {"BACKEND": "django.core.files.storage.InMemoryStorage"}}
    storages._storages.pop("hub_files", None)
    user = make_user("saas:1", host="a", role=Membership.Role.MANAGER, first_name="Ana", email="ana@erplora.test")
    client.force_login(user)
    yield user
    storages._storages.pop("hub_files", None)


def test_without_a_profile_it_is_the_account_s_name_and_the_business_s_preferences(client, ana):
    answer = get(client)
    assert (answer["first_name"], answer["last_name"], answer["contact_email"]) == ("Ana", "", "")
    assert (answer["language"], answer["theme_mode"], answer["palette"], answer["avatar_url"]) == ("", "", "", "")
    assert (answer["role"], answer["has_pin"], answer["pin_length"]) == ("hub_manager", False, 4)


def test_saving_my_data_names_me_so_in_this_hub(client, ana):
    response = post(client, "/me/profile/update", {"first_name": " Ana María ", "last_name": "López", "contact_email": "ana@bar.example"})
    assert response.status_code == 200
    assert (response.json()["first_name"], response.json()["last_name"]) == ("Ana María", "López")
    assert client.get("/api/me", HTTP_HOST=HOST).json()["user"]["label"] == "Ana María López"
    assert OutboxEvent.objects.filter(name="base.profile.updated").count() == 1


def test_the_contact_email_must_be_an_email_and_gives_no_access(client, ana):
    assert post(client, "/me/profile/update", {"first_name": "Ana", "last_name": "", "contact_email": "nope"}).status_code == 422
    post(client, "/me/profile/update", {"first_name": "Ana", "last_name": "", "contact_email": "boss@bar.example"})
    assert ana.__class__.objects.get(pk=ana.pk).email == "ana@erplora.test"


def test_the_language_and_the_appearance_are_kept_and_the_language_applies_at_once(client, ana):
    response = post(client, "/me/preferences", {"language": "en", "theme_mode": "dark", "palette": "forest"})
    assert response.status_code == 200
    assert response.cookies[settings.LANGUAGE_COOKIE_NAME].value == "en"
    profile = Profile.objects.get(username="saas:1")
    assert (profile.language, profile.theme_mode, profile.palette) == ("en", "dark", "forest")
    back = post(client, "/me/preferences", {"language": "", "theme_mode": "", "palette": ""})
    business = Hub.objects.get(slug="a").language or settings.LANGUAGE_CODE
    assert back.cookies[settings.LANGUAGE_COOKIE_NAME].value == business


@pytest.mark.parametrize("body", [{"language": "fr", "theme_mode": "", "palette": ""}, {"language": "", "theme_mode": "neon", "palette": ""}, {"language": "", "theme_mode": "", "palette": "pink"}])
def test_a_preference_it_does_not_offer_is_refused(client, ana, body):
    assert post(client, "/me/preferences", body).status_code == 422


def test_a_photo_is_kept_in_the_hub_s_files_and_shown_to_its_people_only(client, ana):
    response = post(client, "/me/avatar", {"content_type": "image/png", "data_base64": png()})
    assert response.status_code == 200
    url = response.json()["avatar_url"]
    assert url.startswith("/p/media/") and "/avatars/" in url
    assert client.get(url, HTTP_HOST=HOST).status_code == 200
    assert type(client)().get(url, HTTP_HOST=HOST).status_code == 404
    assert get(client)["avatar_url"] == url


def test_a_file_that_is_no_photo_or_too_heavy_is_refused(client, ana):
    not_png = base64.b64encode(b"hello").decode()
    assert post(client, "/me/avatar", {"content_type": "image/png", "data_base64": not_png}).status_code == 422
    assert post(client, "/me/avatar", {"content_type": "image/gif", "data_base64": png()}).status_code == 422
    heavy = base64.b64encode(b"\x00" * (2 * 1024 * 1024 + 1)).decode()
    assert post(client, "/me/avatar", {"content_type": "image/png", "data_base64": heavy}).status_code == 422


def test_removing_the_photo(client, ana):
    post(client, "/me/avatar", {"content_type": "image/png", "data_base64": png()})
    assert post(client, "/me/avatar/remove", {}).status_code == 200
    assert get(client)["avatar_url"] == ""


def test_it_says_whether_i_have_a_pin(client, ana):
    Credential.objects.create(username="saas:1", pin_hash="argon2$x")
    assert get(client)["has_pin"] is True


def test_without_a_session_there_is_no_profile(client, db):
    assert client.get("/api/me/profile", HTTP_HOST=HOST).status_code == 401
