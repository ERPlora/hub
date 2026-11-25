"""The space a hub's prefix takes and the plan's limit on it, also over HTTP (``base.files.space``)."""

import pytest
from django.core.files.base import ContentFile
from django.utils import translation
from live.context import system_context
from live.errors import Conflict
from live.operations import get

from base import files, registry
from base.models import Hub
from base.schemas.hub_registry import HubStateIn
from base.storage import hub_prefix
from base.tenancy.tests import business
from base.tenancy.tests.business import HUB_DB, in_business_a
from base.tests.test_files import A, B, put, store
from base.tests.test_files_api import b64, http, owner, raw

__all__ = ["in_business_a", "store"]


def test_the_space_used_is_the_whole_prefix_of_the_hub_and_only_its_own(store):
    put(store, A, "a.pdf", b"x" * 10)
    store.save(f"{hub_prefix(A)}/website/img/abc.png", ContentFile(b"y" * 7))
    put(store, B, "b.pdf", b"z" * 1000)
    assert files.listing.listing(store, A, "")["used_bytes"] == 17


def test_past_the_plan_s_space_one_refusal_says_the_same_for_every_app_that_keeps_files(store):
    # Files, the website's images and WhatsApp's header samples all refuse through this one check, with its code and
    # its sentence.
    put(store, A, "a.pdf", b"x" * 60)
    assert files.space.refuse_past_the_space(store, A, 40, limit_bytes=100) is None  # up to the limit, it lets it in
    assert files.space.refuse_past_the_space(store, A, 10**12, limit_bytes=None) is None  # no limit in the plan: none
    assert files.space.refuse_past_the_space(store, B, 100, limit_bytes=100) is None  # A's files are not B's space

    said = {}
    for language in ("en", "es"):
        with translation.override(language), pytest.raises(Conflict) as refused:
            files.space.refuse_past_the_space(store, A, 1024**3 - 59, limit_bytes=1024**3)
        assert (refused.value.status, refused.value.code, refused.value.fields) == (409, "base.file_no_space", None)
        said[language] = refused.value.message
    assert said == {
        "en": "There is no space left for that file: your plan includes 1 GB.",
        "es": "No queda espacio para ese archivo: tu plan incluye 1 GB.",
    }


KEPT = {"a.pdf": b"a" * 60, "b.pdf": b"b" * 60, "Facturas/c.pdf": b"c" * 60}
BOUGHT_DOWN_SPACE = {"used_bytes": 180, "limit_bytes": 100}


def with_space(slug, space):
    """A newer photo of ``slug`` whose plan includes ``space`` bytes, through the door the SaaS uses."""
    hub = Hub.objects.get(slug=slug)
    answer = get("base.hub.state_apply")(
        system_context(registry.REGISTRY_SCOPE),
        HubStateIn(id=hub.id, version=hub.state_version + 1, photo={"plan": {"max_storage_bytes": space}}),
    )
    assert answer.applied


def post_files(client, action, host=f"{business.HOST}:8000", **body):
    return http(client, "post", f"/api/files/{action}", host=host, data=body, content_type="application/json")


def upload_over_http(client, name, size, host=f"{business.HOST}:8000"):
    return post_files(client, "upload", host=host, folder="", name=name, content_base64=b64(b"x" * size))


def listed(client):
    return [http(client, "get", "/api/files", data={"folder": folder}).json() for folder in ("", "Facturas")]


def assert_reads(client, path, content):
    response = raw(client, path)
    assert response.status_code == 200
    assert b"".join(response.streaming_content) == content


@pytest.fixture
def bought_down(client, make_user, store):
    """``KEPT`` under a plan of 1 MB, then bought down to 100 bytes: 180 used, 100 allowed. Over HTTP and with the
    SaaS's photo, because the plan only reaches the files through the operations. Gives what was listed before."""
    for path, content in KEPT.items():
        put(store, Hub.objects.get(slug=business.A.key).id, path, content)
    owner(client, make_user)
    with_space(business.A.key, 1024**2)
    before = listed(client)
    with_space(business.A.key, 100)
    return before


@HUB_DB
def test_a_lower_plan_loses_no_file_and_only_refuses_one_more(client, make_user, bought_down, hub_b):
    # What exceeds the new plan stays and is used; nothing more goes in until it is under the limit.
    frozen = [{**seen, "space": BOUGHT_DOWN_SPACE} for seen in bought_down]
    assert listed(client) == frozen
    for path, content in KEPT.items():
        assert_reads(client, path, content)

    refused = upload_over_http(client, "one-more.pdf", 1)
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "base.file_no_space"
    assert listed(client) == frozen

    # Under the limit again, what fits goes in and what does not stays out.
    for path in ("a.pdf", "b.pdf"):
        assert post_files(client, "delete", path=path).status_code == 200
    assert upload_over_http(client, "too-big.pdf", 41).status_code == 409
    assert upload_over_http(client, "fits.pdf", 40).status_code == 200

    # Another business's plan is its own: this business's lower plan refuses it nothing.
    owner(client, make_user, business.B.key)
    assert upload_over_http(client, "theirs.pdf", 1024, host=f"{business.B.key}.localhost:8000").status_code == 200


@HUB_DB
def test_a_lower_plan_leaves_what_is_there_in_use(client, bought_down):
    # What exceeds the plan is still used: none of these adds a byte, and BASE-F73 and BASE-F75 give no refusal for
    # the space.
    assert post_files(client, "folder", parent="", name="Contratos").status_code == 200
    assert post_files(client, "rename", path="a.pdf", name="renombrado.pdf").status_code == 200
    assert post_files(client, "move", path="b.pdf", to="Facturas").status_code == 200

    assert_reads(client, "renombrado.pdf", KEPT["a.pdf"])
    assert_reads(client, "Facturas/b.pdf", KEPT["b.pdf"])
    top, in_facturas = listed(client)
    assert {folder["path"] for folder in top["folders"]} == {"Contratos", "Facturas"}
    assert top["space"] == in_facturas["space"] == BOUGHT_DOWN_SPACE
