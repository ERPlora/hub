"""``/p/media/<hub>/<name>``: the Hub serves the files of its file store (``storages["hub_files"]``, base.storage).

The bucket stays private: a hub's public website shows its images from its own host, by a content-hashed name that
never changes (cached for a year, immutable). No session and no permission (a visitor of the website sees them),
but only the host's own hub: a URL naming another hub's id is not found, whatever its files (one hub never serves
another's, the tenancy rule). A name that climbs out of the hub's prefix is not found either, nor one outside the
folders the modules publish (``website/img/``): a private file of the store is never served.
"""

import pytest
from django.core.files.base import ContentFile
from django.core.files.storage import InMemoryStorage, storages
from storages.utils import clean_name, safe_join

from base.models import Hub
from base.storage import hub_prefix, media_url

pytestmark = pytest.mark.django_db

PNG = b"\x89PNG\r\n\x1a\n" + b"pixels" * 100
YEAR = "public, max-age=31536000, immutable"


class S3NamedInMemoryStorage(InMemoryStorage):
    """In memory, but it reads a name as ``S3Storage._open`` does: backslashes become slashes and ``..`` folds
    (``storages.utils.clean_name`` and ``safe_join``), so ``hub-a/../hub-b/x`` is ``hub-b/x`` there too."""

    def _open(self, name, mode="rb"):
        return super()._open(safe_join("", clean_name(name)), mode)


@pytest.fixture
def hub_files(settings):
    """The hub file store (Django resets ``storages`` when STORAGES changes)."""
    backend = f"{__name__}.S3NamedInMemoryStorage"
    settings.STORAGES = {**settings.STORAGES, "hub_files": {"BACKEND": backend}}
    return storages["hub_files"]


@pytest.fixture
def a(hub_files) -> Hub:
    hub = Hub.objects.get(slug="a")
    hub_files.save(f"{hub_prefix(hub.id)}/website/img/3f2a9c.png", ContentFile(PNG))
    return hub


def get(client, url, host="a.localhost:8000", method="get"):
    return getattr(client, method)(url, HTTP_HOST=host)


def test_a_hub_s_file_is_served_from_its_host_cached_for_a_year(client, a):
    response = get(client, media_url(a.id, "website/img/3f2a9c.png"))
    assert response.status_code == 200
    assert b"".join(response.streaming_content) == PNG
    assert (response["Content-Type"], response["Cache-Control"]) == ("image/png", YEAR)
    assert response["Content-Length"] == str(len(PNG))


def test_it_sets_no_cookie_and_needs_no_session(client, a):
    response = get(client, media_url(a.id, "website/img/3f2a9c.png"))
    assert response.status_code == 200
    assert not response.cookies
    assert "Set-Cookie" not in response.headers


def test_opened_on_its_own_a_file_runs_nothing(client, a):
    # A document opened by its URL (an SVG, an HTML a module might keep one day) is sandboxed: no script, no form.
    response = get(client, media_url(a.id, "website/img/3f2a9c.png"))
    assert response["Content-Security-Policy"] == "default-src 'none'; sandbox"
    assert response["X-Content-Type-Options"] == "nosniff"


def test_head_answers_the_headers(client, a):
    response = get(client, media_url(a.id, "website/img/3f2a9c.png"), method="head")
    assert (response.status_code, response["Content-Type"], response["Cache-Control"]) == (200, "image/png", YEAR)


def test_a_type_mimetypes_does_not_know_is_plain_bytes(client, a, hub_files):
    hub_files.save(f"{hub_prefix(a.id)}/website/img/data.zzz-unknown", ContentFile(b"bytes"))
    response = get(client, media_url(a.id, "website/img/data.zzz-unknown"))
    assert (response.status_code, response["Content-Type"]) == (200, "application/octet-stream")


def test_a_missing_file_is_not_found(client, a):
    assert get(client, media_url(a.id, "website/img/000000.png")).status_code == 404


def test_another_hub_s_files_are_never_served_from_this_host(client, a, hub_files):
    b = Hub.objects.get(slug="b")
    hub_files.save(f"{hub_prefix(b.id)}/website/img/b0b0b0.png", ContentFile(PNG))
    # b's URL on a's host: not found, though the file exists.
    assert get(client, media_url(b.id, "website/img/b0b0b0.png")).status_code == 404
    # a's id with a name only b has: a's prefix holds no such file.
    assert get(client, media_url(a.id, "website/img/b0b0b0.png")).status_code == 404
    # On its own host, b's file is served (the store holds it).
    assert get(client, media_url(b.id, "website/img/b0b0b0.png"), host="b.localhost:8000").status_code == 200


@pytest.mark.parametrize(
    "climb",
    [
        "../{b}/website/img/b0b0b0.png",
        "website/../../{b}/website/img/b0b0b0.png",
        "..\\{b}\\website\\img\\b0b0b0.png",
    ],
)
def test_a_name_never_climbs_into_another_hub_s_files(client, a, hub_files, climb):
    # The S3 store folds ``..`` and turns backslashes into slashes: a's prefix + ``../hub-b/…`` would be b's file.
    b = Hub.objects.get(slug="b")
    hub_files.save(f"{hub_prefix(b.id)}/website/img/b0b0b0.png", ContentFile(PNG))
    assert get(client, f"/p/media/{a.id.hex}/{climb.format(b=hub_prefix(b.id))}").status_code == 404


def test_a_null_byte_in_the_name_is_not_found_on_disk_either(client, settings, tmp_path):
    # Locally the store is the disk (MEDIA_ROOT), where a name with a null byte cannot even be opened.
    settings.STORAGES = {
        **settings.STORAGES,
        "hub_files": {"BACKEND": "django.core.files.storage.FileSystemStorage", "OPTIONS": {"location": tmp_path}},
    }
    hub = Hub.objects.get(slug="a")
    assert get(client, f"/p/media/{hub.id.hex}/website/img/3f2a9c.png%00.txt").status_code == 404


def test_the_hub_must_be_named_exactly(client, a):
    url = media_url(a.id, "website/img/3f2a9c.png")
    upper = url.replace(a.id.hex, a.id.hex.upper())
    dashed = url.replace(a.id.hex, str(a.id))
    assert [get(client, u).status_code for u in (upper, dashed)] == [404, 404]


@pytest.mark.parametrize(
    "name",
    [
        "website/../website/img/3f2a9c.png",
        "../hub-x/website/img/3f2a9c.png",
        "website/img/..",
        "website/./img/3f2a9c.png",
        "website//img/3f2a9c.png",
        "/website/img/3f2a9c.png",
        "website\\img\\3f2a9c.png",
    ],
)
def test_a_name_that_could_leave_the_hub_s_prefix_is_not_found(client, a, name):
    response = get(client, f"/p/media/{a.id.hex}/{name}")
    assert response.status_code == 404


@pytest.mark.parametrize(("length", "status"), [(200, 200), (201, 404)])
def test_a_name_is_200_characters_at_most(client, a, hub_files, length, status):
    name = "website/img/" + "b" * (length - len("website/img/") - len(".png")) + ".png"
    hub_files.save(f"{hub_prefix(a.id)}/{name}", ContentFile(PNG))
    assert (len(name), get(client, media_url(a.id, name)).status_code) == (length, status)


def test_only_get_and_head(client, a):
    url = media_url(a.id, "website/img/3f2a9c.png")
    assert [get(client, url, method=m).status_code for m in ("post", "put", "delete")] == [405, 405, 405]


@pytest.mark.parametrize("name", ["exports/invoice-0001.pdf", "website/private.png", "website/imgs/3f2a9c.png"])
def test_a_file_outside_the_public_folders_is_never_served(client, a, hub_files, name):
    # The store keeps the modules' private documents too (PLAN-HUB block 7): only what a module publishes is served.
    hub_files.save(f"{hub_prefix(a.id)}/{name}", ContentFile(PNG))
    assert get(client, media_url(a.id, name)).status_code == 404


@pytest.fixture
def on_disk(settings, tmp_path):
    """The store on disk (``MEDIA_ROOT`` locally), with a's image and a folder under its images."""
    settings.STORAGES = {
        **settings.STORAGES,
        "hub_files": {"BACKEND": "django.core.files.storage.FileSystemStorage", "OPTIONS": {"location": tmp_path}},
    }
    hub = Hub.objects.get(slug="a")
    storages["hub_files"].save(f"{hub_prefix(hub.id)}/website/img/3f2a9c.png", ContentFile(PNG))
    (tmp_path / hub_prefix(hub.id) / "website" / "img" / "album").mkdir()
    return hub


@pytest.mark.parametrize("name", ["website", "website/img", "website/img/album", "website/img/3f2a9c.png/x"])
def test_a_folder_on_disk_is_not_found_rather_than_an_error(client, on_disk, name):
    assert get(client, f"/p/media/{on_disk.id.hex}/{name}").status_code == 404


def test_the_image_on_disk_is_served(client, on_disk):
    assert get(client, media_url(on_disk.id, "website/img/3f2a9c.png")).status_code == 200
