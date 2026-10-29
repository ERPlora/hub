"""The website's routes: each bound to its operation and named in the SPA's route map; the editor's flows over HTTP,
the preview the editor frames, the QR as a file, and the public reads without a session, counted per visitor."""

import base64
import io
import json
import os

import pytest
from django.conf import settings
from live.ninja import ensure_api_parity
from PIL import Image as PILImage

from apps.website.api import router
from apps.website.queries import PUBLIC_LIMIT
from apps.website.tests.conftest import full_content
from config.api import api

ROUTES = {
    ("GET", "/website/site", "website.site.get"),
    ("POST", "/website/site", "website.site.save"),
    ("POST", "/website/site/publish", "website.site.publish"),
    ("POST", "/website/site/unpublish", "website.site.unpublish"),
    ("GET", "/website/site/preview", "website.site.preview"),
    ("POST", "/website/images", "website.image.upload"),
    ("GET", "/website/qr", "website.qr.get"),
    ("GET", "/website/catalog/categories", "website.catalog.categories"),
    ("GET", "/website/public/site", "website.public.site"),
    ("GET", "/website/public/catalog", "website.public.catalog"),
    ("GET", "/website/public/reviews", "website.public.reviews"),
}
HOST = "a.localhost"


def get(client, path, **params):
    headers = params.pop("headers", {})
    return client.get(f"/api{path}", params, HTTP_HOST=HOST, **headers)


def post(client, path, data=None, **headers):
    return client.post(f"/api{path}", json.dumps(data or {}), content_type="application/json", HTTP_HOST=HOST, **headers)


@pytest.fixture
def admin_client(client, make_user):
    client.force_login(make_user("boss", role="hub_admin"))
    return client


@pytest.fixture
def manager_client(client, make_user):
    client.force_login(make_user("mia", role="hub_manager"))
    return client


def save_and_publish(client):
    assert post(client, "/website/site", {"template": "modern", "theme": {}, "content": full_content()}).status_code == 200
    assert post(client, "/website/site/publish").status_code == 200


def test_every_route_is_bound_to_its_operation():
    routes = {
        (method, path, route.operation_id)
        for path, view in router.path_operations.items()
        for route in view.operations
        for method in route.methods
    }
    assert routes == ROUTES


def test_the_api_keeps_parity():
    assert ensure_api_parity(api) == []


def test_every_operation_has_a_route_and_is_open_to_api_keys():
    from live.operations import registry

    ops = {name for name in registry if name.startswith("website.")}
    assert ops == {operation for _m, _p, operation in ROUTES}
    assert all(registry[name].expose_api for name in ops)


def test_the_spas_route_map_names_every_website_route():
    # frontend/generated/operations.json: the op → route map the SDK's client uses (hand-written until V3).
    spa = json.loads((settings.BASE_DIR / "frontend" / "generated" / "operations.json").read_text())
    mine = {(route["method"].upper(), route["path"].removeprefix("/api"), op) for op, route in spa.items() if op.startswith("website.")}
    assert mine == ROUTES


@pytest.mark.django_db
def test_the_owner_saves_and_publishes_and_a_manager_only_reads(admin_client, make_user, client):
    save_and_publish(admin_client)
    site = get(admin_client, "/website/site").json()
    assert (site["template"], site["published_version"], site["is_live"], site["has_changes"]) == ("modern", 1, True, False)
    client.logout()
    client.force_login(make_user("mia", role="hub_manager"))
    assert get(client, "/website/site").status_code == 200
    refused = post(client, "/website/site", {"template": "bold", "theme": {}, "content": {}})
    assert (refused.status_code, refused.json()["error"]["code"]) == (403, "permission_denied")
    assert post(client, "/website/site/publish").status_code == 403


@pytest.mark.django_db
def test_a_section_that_cannot_hide_is_a_422_on_its_field(admin_client):
    response = post(admin_client, "/website/site", {"template": "classic", "theme": {}, "content": {"hero": {"hidden": True}}})
    assert response.status_code == 422
    assert "content.hero.hidden" in response.json()["error"]["fields"]


@pytest.mark.django_db
@pytest.mark.usefixtures("website_manifest")
def test_preview_needs_website_manage_and_allows_framing_by_the_spa(admin_client, client, make_user):
    post(admin_client, "/website/site", {"template": "bold", "theme": {}, "content": full_content()})
    response = get(admin_client, "/website/site/preview")
    assert response.status_code == 200
    assert response["Content-Type"] == "text/html; charset=utf-8"
    assert '<body class="ws-bold text-break"' in response.content.decode()
    csp = response["Content-Security-Policy"]
    assert "frame-ancestors 'self'" in csp and "script-src 'self';" in csp and "nonce" not in csp
    assert response["X-Frame-Options"] == "SAMEORIGIN"
    assert response["Cache-Control"] == "no-store"
    admin_client.logout()
    assert get(admin_client, "/website/site/preview").status_code == 401
    client.force_login(make_user("mia", role="hub_manager"))
    refused = get(client, "/website/site/preview")
    assert (refused.status_code, refused.json()["error"]["code"]) == (403, "permission_denied")


@pytest.mark.django_db
def test_the_qr_downloads_as_a_file_or_comes_as_json(manager_client):
    png = get(manager_client, "/website/qr", format="png")
    assert png.status_code == 200
    assert png["Content-Type"] == "image/png"
    assert png["Content-Disposition"] == 'attachment; filename="website-qr-a.png"'
    assert png.content.startswith(b"\x89PNG")
    svg = get(manager_client, "/website/qr", format="svg")
    assert svg["Content-Type"] == "image/svg+xml" and svg.content.startswith(b"<svg")
    as_json = get(manager_client, "/website/qr", format="svg", headers={"HTTP_ACCEPT": "application/json"})
    assert as_json.json()["url"] == "http://a.localhost/"


@pytest.mark.django_db
def test_an_image_bigger_than_djangos_ceiling_still_uploads(admin_client, hub_files):
    noise = PILImage.frombytes("RGB", (1000, 1000), os.urandom(3_000_000))
    buffer = io.BytesIO()
    noise.save(buffer, format="PNG")
    raw = buffer.getvalue()
    assert len(raw) > settings.DATA_UPLOAD_MAX_MEMORY_SIZE
    response = post(
        admin_client,
        "/website/images",
        {"filename": "noise.png", "content_type": "image/png", "data_base64": base64.b64encode(raw).decode()},
    )
    assert response.status_code == 201
    assert response.json()["url"].startswith("/p/media/")


@pytest.mark.django_db
def test_an_image_past_the_plans_space_answers_409_with_the_code_of_files(admin_client, hub_files):
    from apps.website.models import Image
    from base.models import Hub

    buffer = io.BytesIO()
    PILImage.new("RGB", (4, 3), (200, 30, 30)).save(buffer, format="PNG")
    body = {"filename": "logo.png", "content_type": "image/png", "data_base64": base64.b64encode(buffer.getvalue()).decode()}
    Hub.objects.filter(slug="a").update(state={"plan": {"max_storage_bytes": len(buffer.getvalue()) - 1}})

    response = post(admin_client, "/website/images", body)

    assert (response.status_code, response.json()["error"]["code"]) == (409, "base.file_no_space")
    assert not Image.objects.exists()
    Hub.objects.filter(slug="a").update(state={"plan": {"max_storage_bytes": len(buffer.getvalue())}})
    assert post(admin_client, "/website/images", body).status_code == 201


@pytest.mark.django_db
def test_an_upload_past_its_limit_is_refused_before_it_is_read(admin_client):
    response = post(admin_client, "/website/images", {"data_base64": "A" * 7_200_000})
    assert (response.status_code, response.json()["error"]["code"]) == (413, "payload_too_large")


@pytest.mark.django_db
def test_public_catalog_answers_without_a_session_only_when_published_and_is_rate_limited(admin_client, client):
    response = get(client, "/website/public/catalog")
    assert (response.status_code, response.json()["error"]["code"]) == (404, "website.not_published")
    save_and_publish(admin_client)
    admin_client.logout()
    first = get(client, "/website/public/catalog", headers={"REMOTE_ADDR": "203.0.113.7"})
    assert first.status_code == 200
    assert first.json()["source"] == "service"
    assert not first.cookies and "Set-Cookie" not in first.headers
    for _ in range(PUBLIC_LIMIT - 2):
        assert get(client, "/website/public/catalog", headers={"REMOTE_ADDR": "203.0.113.7"}).status_code == 200
    # The site counts towards the same limit: the 61st read of the minute is refused.
    assert get(client, "/website/public/site", headers={"REMOTE_ADDR": "203.0.113.7"}).status_code == 200
    limited = get(client, "/website/public/catalog", headers={"REMOTE_ADDR": "203.0.113.7"})
    assert (limited.status_code, limited.json()["error"]["code"]) == (429, "base.rate_limited")
    # Another visitor is not held back by the first.
    assert get(client, "/website/public/catalog", headers={"REMOTE_ADDR": "198.51.100.9"}).status_code == 200


@pytest.mark.django_db
def test_one_hubs_publication_is_not_another_hubs_public_site(admin_client, client):
    save_and_publish(admin_client)
    admin_client.logout()
    for path in ("/api/website/public/site", "/api/website/public/catalog", "/api/website/public/reviews"):
        response = client.get(path, HTTP_HOST="b.localhost")
        assert (response.status_code, response.json()["error"]["code"]) == (404, "website.not_published"), path
        assert client.get(path, HTTP_HOST=HOST).status_code == 200, path


@pytest.mark.django_db
def test_the_public_site_is_json_for_anyone_once_published(admin_client, client):
    save_and_publish(admin_client)
    admin_client.logout()
    body = get(client, "/website/public/site").json()
    assert (body["version"], body["template"], body["content"]["hero"]["title"]) == (1, "modern", "Fresh food every day")


@pytest.mark.django_db
def test_the_public_reviews_answer_without_a_session_once_published_in_the_visitors_language(admin_client, client):
    from django.core.cache import cache

    from apps.website import reviews
    from apps.website.tests.conftest import PLACE_ID, google_reviews

    assert post(admin_client, "/website/site", {"template": "modern", "theme": {}, "content": full_content(reviews={"place_ref": PLACE_ID})}).status_code == 200
    assert post(admin_client, "/website/site/publish").status_code == 200
    admin_client.logout()
    assert get(client, "/website/public/reviews").json() == {
        "available": False,
        "rating_label": "",
        "stars": [],
        "stars_label": "",
        "count_label": "",
        "maps_uri": "",
        "write_uri": "",
        "reviews": [],
    }
    cache.set(reviews.reviews_key("a", PLACE_ID), google_reviews(), reviews.TTL)
    response = client.get("/api/website/public/reviews", HTTP_HOST=HOST, HTTP_ACCEPT_LANGUAGE="es")
    body = response.json()
    assert response.status_code == 200 and "Set-Cookie" not in response.headers
    assert (body["available"], body["rating_label"], body["count_label"]) == (True, "4,7", "128 reseñas en Google")
    assert len(body["reviews"]) == 5 and body["reviews"][0]["author"] == "Cliente 0"

