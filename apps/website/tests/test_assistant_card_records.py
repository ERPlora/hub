"""FIX-HUB-WEBSITE-ASSISTANT-CARD-LEAVES-OUT-ITS-RECORDS (hub#679): the card of a save of the website says each image
it keeps — the logo, the cover, the photo of «About us», each photo of the gallery — by the name of its file, as it was
uploaded, and each category of the catalog by its name, read as whoever asks, never by its id; one this person may not
read or that is not there is left out. Each value of a closed list of the theme or the content (the palette, the page's
background, what the catalog shows, the days of the opening hours) is said by the word the editor shows
(``test_choices``), never by its code.
"""

import gettext
import json
from pathlib import Path

import pytest
from django.conf import settings
from django.utils import translation
from django.utils.text import capfirst
from live.operations import get, registry

from apps.website.models import Image, Site
from apps.website.schemas import PALETTE_IDS
from apps.website.tests.conftest import B, ctx_for, full_content
from apps.website.tests.test_choices import editor_words
from apps.website.tests.test_queries import products_catalog, services_catalog, source_off  # noqa: F401 (fixtures)
from apps.website.tests.test_services import png_bytes, upload
from base import assistant
from base.tests.test_assistant import technical_names
from base.tests.test_assistant_card_values import AN_ID

pytestmark = pytest.mark.django_db

SAVE = "website.site.save"
A_MISSING_ID = "0192f0b2-3333-7000-8000-000000000003"


def a_save(content: dict | None = None, palette: str = "ocean", mode: str = "auto") -> dict:
    """What the assistant sends to save the site: the whole of it, as website.site.get answers it."""
    return {
        "template": "classic",
        "theme": {"palette": palette, "custom": None, "mode": mode},
        "content": full_content() if content is None else content,
    }


def said(arguments: dict, language: str = "en", ctx=None) -> dict:
    """Each datum of the card of the save, in words."""
    card = assistant.card(get(SAVE), arguments, language, ctx or ctx_for())
    return {field["name"]: field["value"] for field in card["fields"]}


def an_image(filename: str, shade: int = 0, ctx=None) -> dict:
    """An upload of its own (``shade`` makes its bytes, so its record, another one), as the content keeps it."""
    image = upload(png_bytes(colour=(shade, 30, 30)), filename=filename, ctx=ctx)
    return {"id": str(image.id), "url": image.url}


# ── An image by the name of its file ──────────────────────────────────────────────────────────────────────────────────


def test_each_image_of_the_site_is_said_by_the_name_of_its_file(hub_files):
    """The case the issue names, «website.site.save:content.topbar.logo.id»: «logo-pepe.png», never its id."""
    logo, cover, photo = an_image("logo-pepe.png", 1), an_image("portada.jpg", 2), an_image("cocina.webp", 3)
    first, second = an_image("sala.png", 4), an_image("terraza.png", 5)
    content = full_content(
        topbar={"logo": logo}, hero={"cover": cover}, about={"image": photo}, gallery={"images": [first, second]}
    )
    shown = said(a_save(content))["content"]
    assert shown["topbar"]["logo"]["id"] == "logo-pepe.png"
    assert shown["hero"]["cover"]["id"] == "portada.jpg"
    assert shown["about"]["image"]["id"] == "cocina.webp"
    assert [image["id"] for image in shown["gallery"]["images"]] == ["sala.png", "terraza.png"]
    assert not AN_ID.search(json.dumps(shown))


def test_the_same_image_uploaded_again_keeps_the_name_it_was_first_uploaded_with(hub_files):
    """The same bytes are the same upload (website.image.upload keeps one file): its first name stays."""
    logo = an_image("logo.png", 1)
    again = an_image("otro-nombre.png", 1)
    assert again["id"] == logo["id"]
    assert said(a_save(full_content(topbar={"logo": again})))["content"]["topbar"]["logo"]["id"] == "logo.png"


def test_an_image_uploaded_before_its_name_was_kept_is_said_by_its_format_and_size(hub_files):
    """An upload of before hub#679 has no name of its file: the card says what it is, «PNG 4 × 3», not its id."""
    logo = an_image("logo.png", 1)
    Image.objects.filter(pk=logo["id"]).update(filename="")
    assert said(a_save(full_content(topbar={"logo": logo})))["content"]["topbar"]["logo"]["id"] == "PNG 4 × 3"


def test_an_image_of_another_business_or_not_there_is_left_out(hub_files):
    """Read as whoever asks, in their business: an upload of B, or an id nobody uploaded, is no name for a card of A."""
    theirs = an_image("suyo.png", 1, ctx=ctx_for(scope=B))
    content = full_content(topbar={"logo": theirs}, hero={"cover": {"id": A_MISSING_ID, "url": ""}})
    shown = said(a_save(content))["content"]
    assert "id" not in shown["topbar"]["logo"]
    assert "id" not in shown["hero"]["cover"]
    assert not AN_ID.search(json.dumps(shown))


def test_an_image_is_left_out_for_whoever_may_not_read_the_website(hub_files):
    logo = an_image("logo.png", 1)
    nobody = ctx_for(permissions=frozenset())
    assert "id" not in said(a_save(full_content(topbar={"logo": logo})), ctx=nobody)["content"]["topbar"]["logo"]


# ── A category of the catalog by its name ─────────────────────────────────────────────────────────────────────────────


def test_each_category_of_a_catalog_of_services_is_said_by_its_name(services_catalog):
    chosen = [str(services_catalog["nails"].id), str(services_catalog["hair"].id)]
    content = full_content(catalog={"source": "service", "category_ids": chosen})
    assert said(a_save(content))["content"]["catalog"]["category_ids"] == ["Nails", "Hair"]


def test_each_category_of_a_catalog_of_products_is_said_by_its_name(products_catalog):
    chosen = [str(products_catalog["food"].id), str(products_catalog["drinks"].id)]
    content = full_content(catalog={"source": "inventory", "category_ids": chosen})
    assert said(a_save(content))["content"]["catalog"]["category_ids"] == ["Food", "Drinks"]


def test_a_category_not_there_says_no_name_and_no_id(services_catalog):
    chosen = [str(services_catalog["hair"].id), A_MISSING_ID]
    content = full_content(catalog={"source": "service", "category_ids": chosen})
    assert said(a_save(content))["content"]["catalog"]["category_ids"] == ["Hair", None]


def test_a_category_of_an_app_that_is_off_in_the_business_is_left_out(monkeypatch, services_catalog):
    """The website's own guard of its catalog: an app off is read for nothing (``read_catalog``)."""
    source_off(monkeypatch, "service")
    content = full_content(catalog={"source": "service", "category_ids": [str(services_catalog["hair"].id)]})
    assert said(a_save(content))["content"]["catalog"]["category_ids"] == [None]


# ── A closed list by the word of the editor ───────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("language", ["en", "es"])
@pytest.mark.parametrize("palette", PALETTE_IDS)
def test_the_palette_is_said_by_the_word_the_editor_shows(language, palette):
    """«website.site.save:theme.palette»: «Océano», never «ocean»."""
    assert said(a_save(palette=palette), language)["theme"]["palette"] == editor_words(language)["palette"][palette]


@pytest.mark.parametrize("language", ["en", "es"])
@pytest.mark.parametrize("mode", ["light", "dark", "auto"])
def test_the_background_of_the_page_is_said_by_the_word_the_editor_shows(language, mode):
    assert said(a_save(mode=mode), language)["theme"]["mode"] == editor_words(language)["mode"][mode]


@pytest.mark.parametrize("language", ["en", "es"])
@pytest.mark.parametrize("source", ["inventory", "service"])
def test_what_the_catalog_shows_is_said_by_the_word_the_editor_shows(language, source):
    content = full_content(catalog={"source": source})
    shown = said(a_save(content), language)["content"]["catalog"]["source"]
    assert shown == editor_words(language)["source"][source]


@pytest.mark.parametrize("language", ["en", "es"])
def test_each_day_of_the_opening_hours_is_said_by_the_word_the_editor_shows(language):
    days = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    content = full_content(contact={"hours": [{"day": day, "intervals": []} for day in days]})
    shown = said(a_save(content), language)["content"]["contact"]["hours"]
    assert [row["day"] for row in shown] == [editor_words(language)["day"][day] for day in days]


# ── Every datum of a write by a name of its own ───────────────────────────────────────────────────────────────────────


def website_writes():
    return [op for op in registry.values() if op.app_label == "website" and op.kind == "command" and assistant.is_tool(op)]


def test_no_datum_of_a_write_of_the_website_reaches_a_spanish_card_by_its_technical_name():
    """The three data of the save, by the website's own words (its catalog: «plantilla», «tema», «contenido»); publish
    and unpublish send none."""
    assert [op.name for op in website_writes()] == [SAVE, "website.site.publish", "website.site.unpublish"]
    assert technical_names(website_writes()) == {}
    card = assistant.card(get(SAVE), a_save(), "es", ctx_for())
    assert [field["label"] for field in card["fields"]] == ["Plantilla", "Tema", "Contenido"]


def test_each_datum_of_the_save_is_titled_by_the_website_s_own_catalog_not_another_app_s():
    """The predicate ``technical_names()`` cannot see (hub#927's review): «template» is translated by base and the
    WhatsApp inbox too, so a title the website forgot would still reach a Spanish card. Each one is in its own."""
    own = gettext.translation("django", localedir=Path(settings.BASE_DIR) / "apps/website/locale", languages=["es"])
    card = assistant.card(get(SAVE), a_save(), "es", ctx_for())
    for field in card["fields"]:
        with translation.override("en"):
            msgid = str(Site._meta.get_field(field["name"]).verbose_name)
        assert own.gettext(msgid) != msgid, field["name"]
        assert field["label"] == capfirst(own.gettext(msgid)), field["name"]
