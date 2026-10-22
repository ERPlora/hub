"""The website's content: a closed set of fixed sections, bounded texts and safe links, whatever the template."""

import uuid

import pydantic
import pytest

from apps.website.palettes import PALETTES
from apps.website.schemas import (
    MAX_GALLERY_IMAGES,
    PALETTE_IDS,
    SECTIONS,
    TEMPLATES,
    Content,
    ImageUploadIn,
    QrIn,
    SaveIn,
    Theme,
)


def test_content_is_a_closed_set_of_sections_and_topbar_and_hero_cannot_hide():
    assert SECTIONS == ("topbar", "hero", "about", "catalog", "gallery", "contact", "location", "footer")
    assert set(Content.model_fields) == set(SECTIONS)
    # An empty draft is a valid one: every section with its defaults, the optional ones shown.
    empty = Content()
    assert [name for name in SECTIONS if getattr(getattr(empty, name), "hidden", False)] == []
    # A section that is not one of the fixed ones is refused: no free blocks.
    with pytest.raises(pydantic.ValidationError):
        Content.model_validate({"blog": {}})
    # The top bar (with its «Log in»), the hero and the footer are always there.
    for fixed in ("topbar", "hero", "footer"):
        with pytest.raises(pydantic.ValidationError):
            Content.model_validate({fixed: {"hidden": True}})
    for optional in ("about", "catalog", "gallery", "contact", "location"):
        assert getattr(Content.model_validate({optional: {"hidden": True}}), optional).hidden is True


def test_texts_are_bounded_and_trimmed():
    assert Content.model_validate({"hero": {"title": "  Pepe's  "}}).hero.title == "Pepe's"
    Content.model_validate({"hero": {"title": "x" * 80, "tagline": "y" * 160}, "about": {"text": "z" * 4000}})
    for too_long in (
        {"hero": {"title": "x" * 81}},
        {"hero": {"tagline": "y" * 161}},
        {"about": {"text": "z" * 4001}},
        {"topbar": {"name": "n" * 81}},
        {"location": {"address_lines": ["a"] * 5}},
        {"location": {"address_lines": ["a" * 121]}},
    ):
        with pytest.raises(pydantic.ValidationError):
            Content.model_validate(too_long)


@pytest.mark.parametrize(
    "url",
    ["http://maps.example.com/x", "javascript:alert(1)", "https://", "https://exa mple.com", 'https://e.com/"x', "//e.com"],
)
def test_links_are_https_only(url):
    with pytest.raises(pydantic.ValidationError):
        Content.model_validate({"location": {"map_url": url}})
    with pytest.raises(pydantic.ValidationError):
        Content.model_validate({"contact": {"socials": {"instagram": url}}})


def test_a_https_link_and_an_empty_one_are_fine():
    content = Content.model_validate(
        {
            "location": {"map_url": "https://maps.google.com/?q=Gran+Via+1"},
            "contact": {"socials": {"instagram": "https://instagram.com/pepe", "x": ""}},
        }
    )
    assert content.location.map_url == "https://maps.google.com/?q=Gran+Via+1"
    assert content.contact.socials.instagram == "https://instagram.com/pepe"


def test_socials_are_a_closed_set():
    with pytest.raises(pydantic.ValidationError):
        Content.model_validate({"contact": {"socials": {"myspace": "https://myspace.com/pepe"}}})
    assert set(type(Content().contact.socials).model_fields) == {"instagram", "facebook", "tiktok", "x"}


def test_contact_phone_and_email_are_checked():
    Content.model_validate({"contact": {"phone": "+34 600 123 456", "whatsapp": "600123456", "email": "hola@pepe.es"}})
    for wrong in ({"phone": "call me"}, {"whatsapp": "12"}, {"email": "not-an-email"}):
        with pytest.raises(pydantic.ValidationError):
            Content.model_validate({"contact": wrong})


def test_opening_hours_are_optional_one_row_per_day_and_never_open_and_close_at_once():
    assert Content().contact.hours == []
    hours = [
        {"day": "mon", "intervals": [{"opens": "09:00", "closes": "14:00"}, {"opens": "17:00", "closes": "20:30"}]},
        # A restaurant closing after midnight.
        {"day": "sat", "intervals": [{"opens": "20:00", "closes": "01:00"}]},
        {"day": "sun", "intervals": []},
    ]
    assert len(Content.model_validate({"contact": {"hours": hours}}).contact.hours) == 3
    for wrong in (
        [{"day": "mon", "intervals": []}, {"day": "mon", "intervals": []}],
        [{"day": "funday", "intervals": []}],
        [{"day": "mon", "intervals": [{"opens": "09:00", "closes": "09:00"}]}],
        [{"day": "mon", "intervals": [{"opens": "9", "closes": "10:00"}]}],
        [{"day": "mon", "intervals": [{"opens": "08:00", "closes": "09:00"}] * 4}],
    ):
        with pytest.raises(pydantic.ValidationError):
            Content.model_validate({"contact": {"hours": wrong}})


def test_the_catalog_names_a_known_source_and_a_bounded_list_of_categories():
    catalog = Content.model_validate({"catalog": {"source": "service", "category_ids": [str(uuid.uuid4())]}}).catalog
    assert (catalog.source, catalog.show_prices, len(catalog.category_ids)) == ("service", True, 1)
    assert Content().catalog.source is None
    with pytest.raises(pydantic.ValidationError):
        Content.model_validate({"catalog": {"source": "orders"}})
    with pytest.raises(pydantic.ValidationError):
        Content.model_validate({"catalog": {"category_ids": [str(uuid.uuid4()) for _ in range(51)]}})


def test_an_image_is_an_id_whose_url_the_server_writes():
    image = uuid.uuid4()
    content = Content.model_validate({"hero": {"cover": {"id": str(image), "url": "/p/media/x/y.png"}}})
    assert content.hero.cover.id == image
    with pytest.raises(pydantic.ValidationError):
        Content.model_validate({"hero": {"cover": {"url": "/p/media/x/y.png"}}})


def test_the_gallery_holds_up_to_twelve_uploaded_images_in_their_order():
    assert Content().gallery.model_dump() == {"hidden": False, "title": "", "images": []}
    ids = [uuid.uuid4() for _ in range(MAX_GALLERY_IMAGES)]
    gallery = Content.model_validate({"gallery": {"images": [{"id": str(id_)} for id_ in ids]}}).gallery
    assert [image.id for image in gallery.images] == ids
    assert MAX_GALLERY_IMAGES == 12
    with pytest.raises(pydantic.ValidationError):
        Content.model_validate({"gallery": {"images": [{"id": str(uuid.uuid4())} for _ in range(13)]}})
    # An image is an upload's id, as anywhere else: never a link typed by hand.
    with pytest.raises(pydantic.ValidationError):
        Content.model_validate({"gallery": {"images": [{"url": "https://evil.example/x.png"}]}})
    with pytest.raises(pydantic.ValidationError):
        Content.model_validate({"gallery": {"title": "x" * 81}})


def test_the_theme_is_a_palette_and_a_mode_auto_by_default():
    assert Theme().model_dump() == {"palette": "ocean", "custom": None, "mode": "auto"}
    for mode in ("light", "dark", "auto"):
        assert Theme(mode=mode).mode == mode
    assert PALETTE_IDS == ("ocean", "forest", "terracotta", "slate", "rose", "sand", "midnight", "olive")
    for palette in PALETTE_IDS:
        assert Theme(palette=palette).palette == palette


def test_any_palette_takes_the_owners_two_colours_over_its_own_and_none_goes_back_to_them():
    # Round 2026-10-22 (W8): the colours of the chosen palette, edited; custom = the owner's tweak of that palette.
    tweaked = Theme.model_validate({"palette": "forest", "custom": {"primary": "#AABBCC", "accent": "#112233"}})
    assert (tweaked.palette, tweaked.custom.model_dump()) == ("forest", {"primary": "#aabbcc", "accent": "#112233"})
    # «Reset colours»: no overrides, the palette's own colours.
    assert Theme.model_validate({"palette": "forest", "custom": None}).custom is None
    # Overrides that are the palette's own colours are no overrides: nothing to reset.
    own = {"primary": PALETTES["forest"]["light"]["primary"].upper(), "accent": PALETTES["forest"]["accent"]}
    assert Theme.model_validate({"palette": "forest", "custom": own}).custom is None
    # Only one of them changed: still an override (the other is the palette's own).
    one = Theme.model_validate({"palette": "forest", "custom": {**own, "accent": "#112233"}})
    assert one.custom.model_dump() == {"primary": PALETTES["forest"]["light"]["primary"], "accent": "#112233"}


def test_a_wrong_theme_is_refused():
    for wrong in (
        {"palette": "sepia"},
        {"mode": "sepia"},
        # «Your colours» is no palette any more: any palette takes the owner's colours (migration 0003).
        {"palette": "custom"},
        {"palette": "custom", "custom": {"primary": "#112233", "accent": "#445566"}},
        {"palette": "ocean", "custom": {"primary": "red", "accent": "#112233"}},
        {"palette": "ocean", "custom": {"primary": "#abc", "accent": "#112233"}},
        {"palette": "ocean", "custom": {"primary": "#112233"}},
        {"palette": "ocean", "custom": {"primary": "#112233", "accent": "#112233", "font": "x"}},
        # The colours of before the palettes are no theme any more (migration 0002 moved them to custom).
        {"primary": "#112233", "accent": "#445566", "mode": "light"},
    ):
        with pytest.raises(pydantic.ValidationError):
            Theme.model_validate(wrong)


def test_save_names_one_of_the_four_templates():
    assert TEMPLATES == ("classic", "modern", "minimal", "bold")
    saved = SaveIn.model_validate({"template": "bold", "theme": {}, "content": {}})
    assert saved.template == "bold"
    with pytest.raises(pydantic.ValidationError):
        SaveIn.model_validate({"template": "fancy", "theme": {}, "content": {}})


def test_an_upload_is_a_jpeg_png_or_webp_in_base64():
    ImageUploadIn.model_validate({"filename": "logo.png", "content_type": "image/png", "data_base64": "aGk="})
    with pytest.raises(pydantic.ValidationError):
        ImageUploadIn.model_validate({"filename": "x.gif", "content_type": "image/gif", "data_base64": "aGk="})


def test_the_qr_comes_as_png_or_svg():
    assert QrIn().format == "png"
    assert QrIn(format="svg").format == "svg"
    with pytest.raises(pydantic.ValidationError):
        QrIn(format="pdf")
