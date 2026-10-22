"""``render_site``: the same content painted by any of the four templates, always with «Log in»; what is hidden is not
painted, nothing the owner typed becomes HTML or a script, and the page carries no nonce and no inline script."""

import re
import uuid

import pytest

from apps.website.palettes import PALETTES, resolve, rgb
from apps.website.render import render_site
from apps.website.schemas import SECTIONS, TEMPLATES
from apps.website.tests.conftest import WEBSITE_CSS, WEBSITE_JS, catalog_snapshot, full_content

pytestmark = pytest.mark.usefixtures("website_manifest")

THEME = {"palette": "ocean", "custom": None, "mode": "light"}
LOGIN = re.compile(r'<a\b[^>]*href="/auth/login"[^>]*>\s*(?:<[^>]+>\s*)*([^<]+?)\s*<')
IMAGE_URL = f"/p/media/{uuid.uuid4().hex}/website/img/0123456789abcdef.png"


def render(template="classic", content=None, lang="en", catalog=None, preview=False, theme=None) -> str:
    return render_site(
        template,
        theme or THEME,
        full_content() if content is None else content,
        lang,
        hub="a",
        catalog=catalog_snapshot() if catalog is None else catalog,
        preview=preview,
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


@pytest.mark.parametrize("template", ["classic", "modern", "bold"])
def test_the_hero_invites_to_the_first_section_shown(template):
    hero = re.search(r'<section[^>]*data-ep-section="hero".*?</section>', render(template), re.S).group(0)
    assert re.search(r'<a class="btn[^"]*" href="#about">About us</a>', hero)
    hidden = render(template, content=full_content(about={"hidden": True}))
    hero = re.search(r'<section[^>]*data-ep-section="hero".*?</section>', hidden, re.S).group(0)
    assert re.search(r'<a class="btn[^"]*" href="#catalog">Our services</a>', hero)
    alone = render(template, content={})
    assert 'href="#' not in re.search(r'<section[^>]*data-ep-section="hero".*?</section>', alone, re.S).group(0)


def test_the_minimal_hero_stays_quiet():
    hero = re.search(r'<section[^>]*data-ep-section="hero".*?</section>', render("minimal"), re.S).group(0)
    assert "btn" not in hero


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
