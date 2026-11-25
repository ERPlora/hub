"""«My profile»: one's own name, contact email, photo, language and appearance in this hub.

The profile is always the person's who has the session. The name and the contact email are this business's: the
contact email is not the one to sign in with and never gives nor takes any access. The language and the appearance
follow the person on any device of the hub; empty = the business's.

The hub is ``hub_a``, on a database of its own as every business is: its profiles, PINs and events are read there,
inside its context.
"""

import base64
import io
import json

import pytest
from django.conf import settings
from django.core.files.storage import storages
from live.models import OutboxEvent
from PIL import Image as PILImage

from base.models.access import Credential
from base.models import Hub, Membership
from base.models.profile import Profile
from base.tenancy.context import use_hub
from base.tests.test_auth_views import A, HOST, ON_HUB_A

pytestmark = ON_HUB_A


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
    user = make_user("saas:1", host=A, role=Membership.Role.MANAGER, first_name="Ana", email="ana@erplora.test")
    client.force_login(user)
    yield user
    storages._storages.pop("hub_files", None)


def test_without_a_profile_it_is_the_account_s_name_and_the_business_s_preferences(client, ana):
    answer = get(client)
    assert (answer["first_name"], answer["last_name"], answer["contact_email"]) == ("Ana", "", "")
    assert (answer["language"], answer["theme_mode"], answer["palette"], answer["avatar_url"]) == ("", "", "", "")
    assert answer["ui_scale"] == 100
    assert (answer["role"], answer["has_pin"], answer["pin_length"]) == ("hub_manager", False, 4)


def test_saving_my_data_names_me_so_in_this_hub(client, ana, hub_a):
    response = post(client, "/me/profile/update", {"first_name": " Ana María ", "last_name": "López", "contact_email": "ana@bar.example"})
    assert response.status_code == 200
    assert (response.json()["first_name"], response.json()["last_name"]) == ("Ana María", "López")
    assert client.get("/api/me", HTTP_HOST=HOST).json()["user"]["label"] == "Ana María López"
    with use_hub(hub_a):
        assert OutboxEvent.objects.filter(name="base.profile.updated").count() == 1


def test_a_wrong_contact_email_says_so_in_its_own_words_never_taking_django_s_message_from_other_apps(client, ana):
    # «Enter a valid email address.» is Django's, which other apps' catalogues translate their own way (Personal's
    # member form): base's catalogue comes first, so translating it here changed theirs (apps/staff test_schemas).
    response = client.post(
        "/api/me/profile/update",
        json.dumps({"first_name": "Ana", "last_name": "", "contact_email": "nope"}),
        content_type="application/json",
        HTTP_HOST=HOST,
        HTTP_ACCEPT_LANGUAGE="es",
    )
    assert response.json()["error"]["code"] == "base.email_invalid"
    assert response.json()["error"]["message"] == "Escribe un correo de contacto válido."
    catalogue = settings.BASE_DIR / "base" / "locale" / "es" / "LC_MESSAGES" / "django.po"
    assert 'msgid "Enter a valid email address."' not in catalogue.read_text()


def test_the_contact_email_must_be_an_email_and_gives_no_access(client, ana):
    assert post(client, "/me/profile/update", {"first_name": "Ana", "last_name": "", "contact_email": "nope"}).status_code == 422
    post(client, "/me/profile/update", {"first_name": "Ana", "last_name": "", "contact_email": "boss@bar.example"})
    assert ana.__class__.objects.get(pk=ana.pk).email == "ana@erplora.test"


def test_the_language_and_the_appearance_are_kept_and_the_language_applies_at_once(client, ana, hub_a):
    response = post(client, "/me/preferences", {"language": "en", "theme_mode": "dark", "palette": "forest", "ui_scale": 100})
    assert response.status_code == 200
    assert response.cookies[settings.LANGUAGE_COOKIE_NAME].value == "en"
    with use_hub(hub_a):
        profile = Profile.objects.get(username="saas:1")
    assert (profile.language, profile.theme_mode, profile.palette) == ("en", "dark", "forest")
    back = post(client, "/me/preferences", {"language": "", "theme_mode": "", "palette": "", "ui_scale": 100})
    business = Hub.objects.get(pk=hub_a.pk).language or settings.LANGUAGE_CODE
    assert back.cookies[settings.LANGUAGE_COOKIE_NAME].value == business


@pytest.mark.parametrize("scale", [80, 90, 100, 110, 120])
def test_every_interface_scale_is_saved_returned_and_read_back(client, ana, hub_a, scale):
    response = post(client, "/me/preferences", {"language": "", "theme_mode": "", "palette": "", "ui_scale": scale})
    assert response.status_code == 200
    assert response.json()["ui_scale"] == scale
    with use_hub(hub_a):
        assert Profile.objects.get(username="saas:1").ui_scale == scale
    assert get(client)["ui_scale"] == scale


@pytest.mark.parametrize(
    "body",
    [
        {"language": "fr", "theme_mode": "", "palette": "", "ui_scale": 100},
        {"language": "", "theme_mode": "neon", "palette": "", "ui_scale": 100},
        {"language": "", "theme_mode": "", "palette": "pink", "ui_scale": 100},
        *[
            {"language": "", "theme_mode": "", "palette": "", "ui_scale": scale}
            for scale in [75, 85, 95, 105, 115, 125, 130]
        ],
    ],
)
def test_a_preference_it_does_not_offer_is_refused(client, ana, body):
    assert post(client, "/me/preferences", body).status_code == 422


#: What «My profile» keeps for a person who chose each of their preferences.
CHOSEN = {"language": "es", "theme_mode": "dark", "palette": "forest", "ui_scale": 120}


@pytest.mark.parametrize(
    "change",
    [
        {"language": "en"},
        {"theme_mode": "light"},
        {"palette": "ocean"},
        {"ui_scale": 90},
        # Back to the business's is a choice as any other: only the one that is sent.
        {"language": ""},
        {"theme_mode": ""},
        {"palette": ""},
    ],
)
def test_a_preference_that_is_not_sent_stays_as_it_was(client, ana, hub_a, change):
    assert post(client, "/me/preferences", CHOSEN).status_code == 200
    response = post(client, "/me/preferences", change)
    assert response.status_code == 200, response.content
    with use_hub(hub_a):
        profile = Profile.objects.get(username="saas:1")
    expected = {**CHOSEN, **change}
    assert {name: getattr(profile, name) for name in expected} == expected
    answer = response.json()
    assert {name: answer[name] for name in ("theme_mode", "palette", "ui_scale")} == {
        name: expected[name] for name in ("theme_mode", "palette", "ui_scale")
    }


def test_a_preference_sent_as_null_stays_as_it_was(client, ana):
    assert post(client, "/me/preferences", CHOSEN).status_code == 200
    body = {"language": "en", "theme_mode": None, "palette": None, "ui_scale": None}
    assert post(client, "/me/preferences", body).status_code == 200
    answer = get(client)
    assert {name: answer[name] for name in CHOSEN} == {**CHOSEN, "language": "en"}


@pytest.mark.parametrize("body", [{}, {"language": None, "ui_scale": None}])
def test_preferences_that_name_none_are_refused_and_change_nothing(client, ana, hub_a, body):
    assert post(client, "/me/preferences", CHOSEN).status_code == 200
    response = post(client, "/me/preferences", body)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_payload"
    with use_hub(hub_a):
        assert OutboxEvent.objects.filter(name="base.profile.updated").count() == 1
    answer = get(client)
    assert {name: answer[name] for name in CHOSEN} == CHOSEN


def test_the_first_preference_of_a_person_leaves_the_others_as_the_business_s(client, ana):
    assert post(client, "/me/preferences", {"theme_mode": "dark"}).status_code == 200
    answer = get(client)
    assert {name: answer[name] for name in CHOSEN} == {"language": "", "theme_mode": "dark", "palette": "", "ui_scale": 100}


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


def test_it_says_whether_i_have_a_pin(client, ana, hub_a):
    with use_hub(hub_a):
        Credential.objects.create(username="saas:1", pin_hash="argon2$x")
    assert get(client)["has_pin"] is True


def test_without_a_session_there_is_no_profile(client, db):
    assert client.get("/api/me/profile", HTTP_HOST=HOST).status_code == 401
