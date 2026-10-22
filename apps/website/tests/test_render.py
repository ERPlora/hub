"""``render_site``: the same content painted by any of the four templates, always with «Log in»; what is hidden is not
painted, nothing the owner typed becomes HTML or a script, and the page carries no nonce and no inline script."""

import json
import re
import uuid
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path

import pytest

from apps.website.palettes import PALETTES, resolve, rgb
from apps.website.render import local_day, render_site
from apps.website.schemas import SECTIONS, TEMPLATES
from apps.website.tests.conftest import WEBSITE_CSS, WEBSITE_JS, catalog_snapshot, full_content

pytestmark = pytest.mark.usefixtures("website_manifest")

THEME = {"palette": "ocean", "custom": None, "mode": "light"}
LOGIN = re.compile(r'<a\b[^>]*href="/auth/login"[^>]*>\s*(?:<[^>]+>\s*)*([^<]+?)\s*<')
IMAGE_URL = f"/p/media/{uuid.uuid4().hex}/website/img/0123456789abcdef.png"


def render(template="classic", content=None, lang="en", catalog=None, preview=False, theme=None, today=None) -> str:
    return render_site(
        template,
        theme or THEME,
        full_content() if content is None else content,
        lang,
        hub="a",
        catalog=catalog_snapshot() if catalog is None else catalog,
        preview=preview,
        today=today,
    )


def sections(html: str) -> list[str]:
    return re.findall(r'data-ep-section="([a-z]+)"', html)


@pytest.mark.parametrize("template", TEMPLATES)
def test_every_template_renders_the_same_content_with_the_login_button(template):
    html = render(template)
    assert sections(html) == list(SECTIONS)
    # «Log in» in the top bar and in the footer, to the Hub's own jump to the login.
    assert LOGIN.findall(html) == ["Log in", "Log in"]
    for text in (
        "Pepe&#x27;s Bistro",
        "Fresh food every day",
        "Since 1998 in Gran Vía",
        "<strong>everything</strong>",
        "Gran Vía 1",
        "28013 Madrid",
        "Pepe Bistro S.L.",
        "Monday",
        "09:00–14:00",
        "Sunday",
        "Closed",
    ):
        assert text in html, (template, text)
    assert 'href="tel:+34600123456"' in html
    assert 'href="https://wa.me/34600123456"' in html
    assert 'href="mailto:hola@pepe.es"' in html
    assert 'href="https://instagram.com/pepe"' in html
    assert 'href="https://maps.google.com/?q=Gran+Via+1"' in html
    assert f'<body class="ws-{template} text-break" data-ep-template="{template}"' in html


@pytest.mark.parametrize("template", TEMPLATES)
def test_the_catalog_comes_from_the_snapshot_in_a_block_the_bundle_refreshes(template):
    html = render(template)
    block = re.search(r'<div[^>]*data-ep-block="catalog"[^>]*>', html).group(0)
    assert 'data-ep-source="service"' in block
    assert "data-ep-empty=" in block
    for text in ("Hair", "Cut", "30 min", "€15.00", "Colour", "From €40.00", "Consultation", "Free"):
        assert text in html, text


def test_the_four_templates_are_four_different_pages():
    pages = {template: render(template).replace(template, "TEMPLATE") for template in TEMPLATES}
    assert len(set(pages.values())) == 4


@pytest.mark.parametrize("template", TEMPLATES)
def test_a_hidden_section_is_not_painted(template):
    content = full_content(
        about={"hidden": True}, catalog={"hidden": True}, contact={"hidden": True}, location={"hidden": True}
    )
    html = render(template, content)
    assert sections(html) == ["topbar", "hero", "footer"]
    for gone in ("We cook", "data-ep-block", "Gran Vía 1", "hola@pepe.es", "Monday"):
        assert gone not in html, gone
    assert LOGIN.findall(html) == ["Log in", "Log in"]


def test_a_catalog_without_a_source_is_not_painted_and_an_empty_one_says_so():
    assert "catalog" not in sections(render(content=full_content(catalog={"source": None})))
    empty = render(catalog={"source": "service", "show_prices": True, "groups": []})
    assert "catalog" in sections(empty)
    assert "Nothing to show here yet." in empty


def test_prices_can_be_left_out():
    html = render(catalog={**catalog_snapshot(), "show_prices": False})
    assert "Cut" in html
    assert "€15.00" not in html and "From" not in html


def test_the_page_speaks_the_visitors_language():
    html = render(lang="es")
    assert '<html lang="es"' in html
    assert LOGIN.findall(html) == ["Entrar", "Entrar"]
    for text in ("Lunes", "Domingo", "Cerrado", "15,00\xa0€", "Desde 40,00\xa0€", "Gratis", "Sobre nosotros"):
        assert text in html, text
    chrome = ("Quiénes somos", "Lo que ofrecemos", "Hablemos", "Visítanos", "Escríbenos por WhatsApp", "Cómo llegar")
    for text in chrome:
        assert text in html, text
    assert ">Hoy</span>" in render(lang="es", today="mon")
    assert "Contáctanos" in render(lang="es", content=full_content(contact={"whatsapp": ""}))


@pytest.mark.parametrize("template", TEMPLATES)
def test_the_page_has_no_inline_script_and_no_nonce_and_links_its_own_bundle(template):
    html = render(template)
    assert "nonce" not in html
    scripts = re.findall(r"<script\b[^>]*>", html)
    assert scripts and all(" src=" in tag for tag in scripts)
    assert f'<script type="module" src="{WEBSITE_JS}"></script>' in html
    assert f'<link rel="stylesheet" href="{WEBSITE_CSS}">' in html
    # The theme: one <style>, only the palette's colours as Bootstrap's variables, light and dark.
    styles = re.findall(r"<style>(.*?)</style>", html, re.S)
    assert len(styles) == 1
    assert "--bs-primary:#0b5cad;" in styles[0] and "--bs-primary:#7db8f0;" in styles[0]


def test_what_the_owner_types_is_text_never_html():
    content = full_content(
        hero={"title": "<script>alert(1)</script>"},
        about={"text": 'Hi <img src=x onerror="alert(1)"> <script>alert(2)</script> [link](javascript:alert(3))'},
    )
    html = render(content=content)
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "onerror" not in html and "alert(2)" not in html and "javascript:" not in html


def test_the_draft_is_validated_again_before_painting():
    # A row written by hand (the admin, a migration) cannot smuggle a colour that breaks out of the <style>.
    with pytest.raises(ValueError):
        render(theme={"palette": "ocean", "custom": {"primary": "red;}</style><script>", "accent": "#000000"}})
    with pytest.raises(ValueError):
        render(theme={"palette": "custom", "mode": "light"})


def test_the_images_are_the_uploads_urls():
    content = full_content(
        topbar={"logo": {"id": str(uuid.uuid4()), "url": IMAGE_URL}},
        hero={"cover": {"id": str(uuid.uuid4()), "url": IMAGE_URL}},
        about={"image": {"id": str(uuid.uuid4()), "url": IMAGE_URL}},
    )
    assert render(content=content).count(f'src="{IMAGE_URL}"') == 3


def style_of(html: str) -> str:
    return re.search(r"<style>(.*?)</style>", html, re.S).group(1)


def mode_block(style: str, mode: str) -> str:
    """The declarations the page takes in ``mode`` (Bootstrap's colour modes: ``data-bs-theme``)."""
    selector = re.escape(f"html[data-bs-theme={mode}],html [data-bs-theme={mode}]")
    return re.search(selector + r"\{(.*?)\}", style).group(1)


def declarations(block: str) -> dict[str, str]:
    return dict(part.split(":", 1) for part in block.split(";") if part)


@pytest.mark.parametrize("palette", list(PALETTES))
def test_the_palette_reaches_the_page_as_bootstraps_variables_in_both_modes(palette):
    style = style_of(render(theme={"palette": palette}))
    colours = resolve(palette, None)
    for mode in ("light", "dark"):
        block = declarations(mode_block(style, mode))
        expected = colours[mode]
        assert block["--bs-primary"] == expected["primary"]
        assert block["--bs-primary-rgb"] == rgb(expected["primary"])
        assert block["--bs-secondary"] == expected["accent"]
        assert (block["--bs-body-bg"], block["--bs-body-color"]) == (expected["bg"], expected["text"])
        assert block["--bs-body-bg-rgb"] == rgb(expected["bg"])
        assert block["--bs-tertiary-bg"] == block["--bs-secondary-bg"] == expected["surface"]
        assert block["--bs-secondary-color"] == expected["muted"]
        assert (block["--bs-link-color"], block["--bs-link-color-rgb"]) == (expected["link"], rgb(expected["link"]))
        assert block["--bs-border-color"] == expected["border"]
        assert (block["--ws-on-primary"], block["--ws-on-accent"]) == (expected["on_primary"], expected["on_accent"])
        # Only variables: Bootstrap's and the few ws-* it has none of; never a rule of their own.
        assert all(name.startswith(("--bs-", "--ws-")) or name == "color-scheme" for name in block), block
    assert declarations(mode_block(style, "dark"))["color-scheme"] == "dark"


@pytest.mark.parametrize("mode", ["light", "dark"])
def test_the_owners_colours_over_a_palette_reach_the_page_as_bootstraps_variables(mode):
    tweak = {"primary": "#ffeb3b", "accent": "#0d47a1"}
    style = style_of(render(theme={"palette": "forest", "custom": tweak}))
    block = declarations(mode_block(style, mode))
    expected = resolve("forest", tweak)[mode]
    assert block["--bs-primary"] == expected["primary"] and block["--bs-secondary"] == "#0d47a1"
    assert (block["--bs-body-bg"], block["--bs-body-color"]) == (expected["bg"], expected["text"])
    assert block["--bs-link-color"] == expected["link"]
    # The palette's own colours are gone: the owner's replace them.
    assert block["--bs-primary"] != PALETTES["forest"][mode]["primary"]
    if mode == "light":
        # Text on the colours stays readable: black on yellow, white on dark blue.
        assert (block["--ws-on-primary"], block["--ws-on-accent"]) == ("#000000", "#ffffff")



@pytest.mark.parametrize(
    ("mode", "first_paint", "scheme"), [("light", "light", "light"), ("dark", "dark", "dark"), ("auto", "light", "light dark")]
)
def test_the_mode_light_dark_or_auto_reaches_the_page(mode, first_paint, scheme):
    html = render(theme={"palette": "forest", "mode": mode})
    # Auto paints light until the bundle reads the device's preference (frontend/website.ts): no inline script.
    assert f'<html lang="en" data-bs-theme="{first_paint}" data-ep-mode="{mode}">' in html
    assert f'<meta name="color-scheme" content="{scheme}">' in html


def test_the_preview_is_marked_and_kept_out_of_search_engines():
    preview = render(preview=True)
    assert "data-ep-preview" in preview and '<meta name="robots" content="noindex">' in preview
    public = render()
    assert "data-ep-preview" not in public and "noindex" not in public


def test_an_empty_draft_still_renders_with_the_hubs_name_and_log_in():
    html = render(content={})
    assert sections(html) == ["topbar", "hero", "footer"]
    assert LOGIN.findall(html) == ["Log in", "Log in"]
    assert "<title>a</title>" in html


@pytest.mark.parametrize("template", TEMPLATES)
def test_the_top_bar_collapses_its_section_links_on_a_phone_and_keeps_log_in_outside(template):
    html = render(template, content=full_content(location={"hidden": True}))
    nav = re.search(r'<nav class="navbar navbar-expand-md[^"]*"[^>]*>.*?</nav>', html, re.S).group(0)
    toggler = re.search(r'<button[^>]*class="navbar-toggler[^"]*"[^>]*>', nav).group(0)
    assert 'data-bs-toggle="collapse"' in toggler and 'data-bs-target="#ws-nav"' in toggler
    assert 'aria-controls="ws-nav"' in toggler and 'aria-expanded="false"' in toggler and 'aria-label="Menu"' in toggler
    collapse = re.search(r'<div class="collapse navbar-collapse[^"]*" id="ws-nav">(.*?)</div>', nav, re.S).group(1)
    # One link per visible section, by its heading; the hidden one has none.
    assert re.findall(r'href="#([a-z]+)"', collapse) == ["about", "catalog", "contact"]
    assert "About us" in collapse and "Our services" in collapse
    # «Log in» stays on the bar, never folded into the menu.
    assert "/auth/login" not in collapse and "/auth/login" in nav


def test_without_sections_the_top_bar_has_no_menu():
    html = render(content={})
    assert "navbar-toggler" not in html and "ws-nav" not in html


@pytest.mark.parametrize("template", TEMPLATES)
def test_only_bolds_bar_and_footer_stay_dark_the_rest_follow_the_page(template):
    html = render(template)
    nav = re.search(r"<nav[^>]*>", html).group(0)
    footer = re.search(r"<footer[^>]*>", html).group(0)
    if template == "bold":
        assert 'data-bs-theme="dark"' in nav and 'data-bs-theme="dark"' in footer
    else:
        assert "data-bs-theme" not in nav and "data-bs-theme" not in footer


def hero_of(html: str) -> str:
    return re.search(r'<section[^>]*data-ep-section="hero".*?</section>', html, re.S).group(0)


def section_of(html: str, name: str) -> str:
    return re.search(rf'<section id="{name}"[^>]*data-ep-section="{name}".*?</section>', html, re.S).group(0)


def calls_to_action(html: str) -> list[tuple[str, str, str]]:
    """The hero's buttons: (classes, link, label)."""
    return re.findall(
        r'<a class="(btn\b[^"]*)" href="([^"]+)"[^>]*>\s*(?:<span[^>]*></span>\s*)?([^<]+?)\s*</a>', hero_of(html)
    )


@pytest.mark.parametrize("template", TEMPLATES)
def test_the_hero_offers_two_pills_whatsapp_or_contact_and_find_us(template):
    # Ioan's redesign (2026-10-22): the header invites to write (WhatsApp, else the contact section) and to come.
    ctas = calls_to_action(render(template))
    assert [(href, label) for _classes, href, label in ctas] == [
        ("https://wa.me/34600123456", "Chat on WhatsApp"),
        ("#location", "Find us"),
    ]
    assert all("rounded-pill" in classes.split() for classes, _href, _label in ctas)
    whatsapp = re.search(r'<a [^>]*href="https://wa.me/34600123456"[^>]*>', hero_of(render(template))).group(0)
    assert 'target="_blank"' in whatsapp and 'rel="noopener noreferrer"' in whatsapp
    no_whatsapp = calls_to_action(render(template, content=full_content(contact={"whatsapp": ""})))
    assert [(href, label) for _c, href, label in no_whatsapp] == [("#contact", "Contact us"), ("#location", "Find us")]
    # Without the contact and the address on the page, the first section shown; with nothing, no button.
    elsewhere = render(template, content=full_content(contact={"hidden": True}, location={"hidden": True}))
    assert [(href, label) for _c, href, label in calls_to_action(elsewhere)] == [("#about", "About us")]
    assert calls_to_action(render(template, content={})) == []


@pytest.mark.parametrize("template", TEMPLATES)
def test_the_hero_paints_the_cover_under_an_overlay_and_a_palette_gradient_without_one(template):
    cover = {"id": str(uuid.uuid4()), "url": IMAGE_URL}
    hero = hero_of(render(template, content=full_content(hero={"cover": cover})))
    images = re.findall(r"<img\b[^>]*>", hero)
    assert len(images) == 1 and f'src="{IMAGE_URL}"' in images[0]
    assert "object-fit-cover" in images[0] and 'alt=""' in images[0]
    assert "ws-hero-overlay" in hero and "ws-hero-glow" not in hero
    plain = hero_of(render(template))
    assert "<img" not in plain and "ws-hero-overlay" not in plain and "ws-hero-glow" in plain


@pytest.mark.parametrize("template", TEMPLATES)
def test_the_hero_title_is_display_type_and_the_tagline_a_lead(template):
    hero = hero_of(render(template))
    title = re.search(r'<h1 class="([^"]*)">([^<]*)</h1>', hero)
    assert re.search(r"\bdisplay-[1-6]\b", title.group(1)) and "ws-display" in title.group(1)
    assert title.group(2) == "Fresh food every day"
    assert re.search(r'<p class="[^"]*\blead\b[^"]*">Since 1998 in Gran Vía</p>', hero)


def test_the_minimal_hero_stays_quiet():
    # Minimal's two calls to action are an outline pill and a link, never a filled button.
    ctas = calls_to_action(render("minimal"))
    assert len(ctas) == 2
    assert all(" btn-primary" not in f" {classes} " for classes, _href, _label in ctas)
    assert "btn-outline-primary" in ctas[0][0].split() and "btn-link" in ctas[1][0].split()


@pytest.mark.parametrize("template", TEMPLATES)
def test_the_top_bar_is_a_sticky_glass_bar_with_the_logo_and_an_outline_pill_to_log_in(template):
    logo = {"id": str(uuid.uuid4()), "url": IMAGE_URL}
    html = render(template, content=full_content(topbar={"logo": logo}))
    header = re.search(r'<header[^>]*data-ep-section="topbar"[^>]*>.*?</header>', html, re.S).group(0)
    assert re.search(r'<header\b[^>]*\bclass="[^"]*\bsticky-top\b', header)
    assert "ws-glass" in header
    assert re.search(rf'<img class="[^"]*ws-logo[^"]*" src="{IMAGE_URL}" alt="Pepe&#x27;s Bistro">', header)
    login = re.search(r'<a class="([^"]*)" href="/auth/login"', header).group(1).split()
    assert {"btn", "btn-outline-primary", "rounded-pill"} <= set(login)
    assert "<img" not in re.search(r"<header.*?</header>", render(template), re.S).group(0)


EYEBROWS = {"about": "Who we are", "catalog": "What we offer", "contact": "Get in touch", "location": "Visit us"}


@pytest.mark.parametrize("template", TEMPLATES)
def test_each_section_has_an_eyebrow_over_its_heading_and_its_content_in_rounded_cards(template):
    html = render(template, content=full_content(about={"image": {"id": str(uuid.uuid4()), "url": IMAGE_URL}}))
    for name, eyebrow in EYEBROWS.items():
        section = section_of(html, name)
        assert re.search(rf'<p class="[^"]*\bws-eyebrow\b[^"]*">{eyebrow}</p>\s*<h2\b', section), (name, section)
        assert "rounded-4" in section and "shadow-sm" in section, name


@pytest.mark.parametrize("template", TEMPLATES)
def test_about_puts_its_photo_in_a_rounded_frame_beside_the_text(template):
    html = render(template, content=full_content(about={"image": {"id": str(uuid.uuid4()), "url": IMAGE_URL}}))
    about = section_of(html, "about")
    photo = re.search(rf'<img class="([^"]*)" src="{IMAGE_URL}"', about)
    assert "object-fit-cover" in photo.group(1) or "img-fluid" in photo.group(1)
    # The photo's nearest frame is rounded.
    before = about[: photo.start()]
    assert "rounded-4" in before[before.rfind("<div") :]
    assert about.count("col-lg-6") == 2
    assert "col-lg-6" not in section_of(render(template), "about")


def test_the_catalog_is_a_grid_of_cards_with_a_placeholder_a_price_pill_and_category_pills():
    html = render()
    block = re.search(r'<div data-ep-block="catalog".*?</section>', html, re.S).group(0)
    assert 'class="row row-cols-1 row-cols-md-2 row-cols-lg-3 g-4"' in block
    assert block.count('class="card ') == 3
    assert re.search(r'<span class="badge rounded-pill[^"]*">€15.00</span>', block)
    # No photo in the catalog: a gradient with the item's initial.
    assert re.search(r'<div class="ratio ratio-21x9 ws-thumb" aria-hidden="true"><span class="[^"]*">C</span>', block)
    # One named category: no pills to jump between categories; two or more: one pill each.
    assert "nav-pills" not in block
    named = [{**group, "name": group["name"] or "Other"} for group in catalog_snapshot()["groups"]]
    two = {**catalog_snapshot(), "groups": named}
    pills = re.search(r'<ul class="nav nav-pills[^"]*">.*?</ul>', render(catalog=two), re.S).group(0)
    assert re.findall(r'<a class="nav-link[^"]*" href="(#ws-cat-\d)">([^<]+)</a>', pills) == [
        ("#ws-cat-1", "Hair"),
        ("#ws-cat-2", "Other"),
    ]


@pytest.mark.parametrize("template", TEMPLATES)
def test_the_contact_is_chips_with_icons_whatsapp_a_pill_and_the_socials_pills(template):
    contact = section_of(render(template), "contact")
    phone = re.search(r'<a class="([^"]*)" href="tel:\+34600123456">(.*?)</a>', contact, re.S)
    assert "ws-chip" in phone.group(1) and "rounded-4" in phone.group(1)
    glyph = r'<span class="[^"]*\bws-glyph\b[^"]*rounded-circle[^"]*" aria-hidden="true">'
    assert re.search(glyph + r'<span class="ws-icon ws-icon-call">', phone.group(2))
    assert "+34 600 123 456" in phone.group(2)
    email = re.search(r'<a class="[^"]*ws-chip[^"]*" href="mailto:hola@pepe.es">(.*?)</a>', contact, re.S).group(1)
    assert "ws-icon-mail" in email
    whatsapp = re.search(r'<a class="([^"]*)" href="https://wa.me/34600123456"[^>]*>(.*?)</a>', contact, re.S)
    assert {"btn", "rounded-pill"} <= set(whatsapp.group(1).split()) and "ws-icon-whatsapp" in whatsapp.group(2)
    assert "Chat on WhatsApp" in whatsapp.group(2)
    instagram = re.search(r'<a class="([^"]*)" href="https://instagram.com/pepe"[^>]*>(.*?)</a>', contact, re.S)
    assert {"btn", "rounded-pill"} <= set(instagram.group(1).split()) and "ws-icon-instagram" in instagram.group(2)


@pytest.mark.parametrize("template", TEMPLATES)
def test_the_opening_hours_are_a_flush_list_with_today_marked(template):
    contact = section_of(render(template, today="mon"), "contact")
    hours = re.search(r'<ul class="list-group list-group-flush[^"]*">(.*?)</ul>', contact, re.S).group(1)
    rows = re.findall(r"<li\b([^>]*)>(.*?)</li>", hours, re.S)
    assert [("Monday" in body, "aria-current" in attrs) for attrs, body in rows] == [(True, True), (False, False)]
    assert 'aria-current="date"' in rows[0][0] and "bg-primary-subtle" in rows[0][0]
    assert re.search(r'<span class="badge rounded-pill[^"]*">Today</span>', rows[0][1])
    assert "Today" not in rows[1][1]
    # On a phone the times wrap under the day; a day's name never breaks («Wednesda y», 2026-10-22).
    assert all("flex-wrap" in attrs for attrs, _body in rows)
    assert re.search(r'<span class="text-nowrap">Monday ', rows[0][1]) and '<span class="text-nowrap">Sunday</span>' in rows[1][1]
    assert "aria-current" not in section_of(render(template, today="tue"), "contact")
    assert "aria-current" not in section_of(render(template), "contact")


@pytest.mark.parametrize("template", TEMPLATES)
def test_the_location_is_a_card_with_an_open_the_map_pill(template):
    location = section_of(render(template), "location")
    assert re.search(r'class="card[^"]*rounded-4[^"]*"', location)
    map_url = re.escape("https://maps.google.com/?q=Gran+Via+1")
    link = re.search(rf'<a class="([^"]*)" href="{map_url}"[^>]*>(.*?)</a>', location, re.S)
    assert {"btn", "rounded-pill"} <= set(link.group(1).split()) and "Open the map" in link.group(2)


@pytest.mark.parametrize("template", TEMPLATES)
def test_the_footer_has_columns_the_sections_and_log_in(template):
    footer = footer_of(render(template))
    assert 'class="row' in footer and len(re.findall(r'class="col-', footer)) >= 2
    assert re.findall(r'href="#([a-z]+)"', footer) == ["about", "catalog", "contact", "location"]
    assert "small" in footer and "text-body-secondary" in footer
    login = re.search(r'<a class="([^"]*)" href="/auth/login"', footer).group(1).split()
    assert {"btn", "rounded-pill"} <= set(login)


@pytest.mark.parametrize("template", TEMPLATES)
def test_the_page_is_laid_out_with_bootstraps_grid_and_fluid_images(template):
    content = full_content(
        hero={"cover": {"id": str(uuid.uuid4()), "url": IMAGE_URL}},
        about={"image": {"id": str(uuid.uuid4()), "url": IMAGE_URL}},
    )
    html = render(template, content=content)
    assert '<meta name="viewport" content="width=device-width, initial-scale=1">' in html
    # The bar, the page and the footer sit in Bootstrap containers (minimal keeps one column for the whole page).
    assert html.count('class="container') >= 3 and 'class="row' in html and "col-md-" in html
    for image in re.findall(r"<img\b[^>]*>", html):
        # A photo fits its column, or fills a Bootstrap ratio box without stretching.
        assert "img-fluid" in image or "object-fit-cover" in image, image


def footer_of(html: str) -> str:
    return re.search(r'<footer\b[^>]*data-ep-section="footer".*?</footer>', html, re.S).group(0)


@pytest.mark.parametrize("template", TEMPLATES)
def test_the_footer_shows_its_line_only_when_the_owner_wrote_one(template):
    # Regression (2026-10-22): the demo's footer showed a lone «h», which was the owner's text; the line is the text
    # as written, in its own element, and with no text there is no line at all (no empty element left behind).
    footer = footer_of(render(template, content=full_content(footer={"text": "Pepe Bistro S.L. · CIF B12345678"})))
    lines = re.findall(r"<(\w+)\b[^>]*\bdata-ep-footer-text\b[^>]*>([^<]*)</\1>", footer)
    assert [text for _tag, text in lines] == ["Pepe Bistro S.L. · CIF B12345678"]
    empty = footer_of(render(template, content=full_content(footer={"text": ""})))
    assert "data-ep-footer-text" not in empty
    assert not re.search(r"<(p|span|small|div)\b[^>]*>\s*</\1>", empty), empty
    # The name and «Log in» stay.
    assert "Pepe&#x27;s Bistro" in empty and LOGIN.findall(empty) == ["Log in"]


def test_today_is_the_hubs_own_day_in_its_time_zone_or_madrids():
    # 2026-10-19 02:30 UTC: Monday in Madrid (04:30), still Sunday in New York (22:30).
    moment = datetime(2026, 10, 19, 2, 30, tzinfo=UTC)
    assert local_day("America/New_York", moment) == "sun"
    assert local_day("Europe/Madrid", moment) == "mon"
    # Without a time zone, or with one that does not exist: Spain's (ERPlora sells in Spain).
    assert local_day("", moment) == "mon"
    assert local_day("Mars/Olympus", moment) == "mon"
    assert local_day("../etc", moment) == "mon"


# The catalog's block, as the server paints it and as the public bundle rebuilds it (frontend/public/catalog.ts):
# both are checked against one fixture (frontend/public/catalog.fixture.json; catalog.test.ts reads it too).
CATALOG_FIXTURE = Path(__file__).resolve().parents[1] / "frontend" / "public" / "catalog.fixture.json"
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}


class _Tokens(HTMLParser):
    """HTML as a list: ``<tag a="…">`` (attributes sorted), ``</tag>`` and each text with its spaces collapsed."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tokens: list[str] = []

    def handle_starttag(self, tag, attrs):
        self.tokens.append("<" + " ".join([tag, *(f'{name}="{value or ""}"' for name, value in sorted(attrs))]) + ">")

    def handle_endtag(self, tag):
        self.tokens.append(f"</{tag}>")

    def handle_data(self, data):
        text = " ".join(data.split())
        if text:
            self.tokens.append(text)


def tokens(html: str) -> list[str]:
    parser = _Tokens()
    parser.feed(html)
    parser.close()
    return parser.tokens


def catalog_block_tokens(html: str) -> list[str]:
    """The tokens of what is inside ``[data-ep-block="catalog"]``."""
    found, depth, inside = [], 0, False
    for token in tokens(html):
        if not inside:
            inside = token.startswith("<div ") and 'data-ep-block="catalog"' in token
            continue
        if token.startswith("</"):
            depth -= 1
            if depth < 0:
                return found
        elif token.startswith("<") and token[1:].split(" ")[0].rstrip(">") not in VOID:
            depth += 1
        found.append(token)
    raise AssertionError("no catalog block")


def test_the_catalog_block_is_the_markup_the_public_bundle_rebuilds():
    fixture = json.loads(CATALOG_FIXTURE.read_text(encoding="utf-8"))
    assert {case["name"] for case in fixture["cases"]} == {"two categories", "one category", "empty"}
    for case in fixture["cases"]:
        assert catalog_block_tokens(render(catalog=case["catalog"])) == tokens(case["html"]), case["name"]
