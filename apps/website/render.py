"""``render_site``: a site's page, the same for the public home (``public_home``) and the editor's preview.

The template is one of four Django templates (``templates/website/templates/<id>.html``, each with its own bar, header,
section frames and footer, in Bootstrap 5.3's classes only) that share one partial per body section
(``templates/website/sections/``) and ``templates/website/base.html``. The theme's palette is written as Bootstrap's
CSS variables for light and for dark (``_theme``, from ``palettes``); the content and the theme are
validated again before painting (a row written by hand cannot smuggle markup), and every text goes through Django's
escaping or, for ``about.text``, through ``live.markdown`` (nh3). The page carries no nonce, no inline script and no
CSRF token: it is rendered without a request so its HTML can be cached and shared (``public_home``), and its only
script is the public bundle, ``frontend/website.ts``. The chrome (« Log in », the days, the headings) speaks the
visitor's language; what the owner wrote is shown as written.

The catalog is painted from a snapshot (``published_content["catalog"]``, or the preview's fresh read) in a block the
bundle refreshes (``data-ep-block="catalog"``); :func:`catalog_view` prices it for the language, and the public
catalog API answers the same shape.
"""

from decimal import Decimal
from typing import Any

from babel.numbers import format_currency
from django.template.loader import render_to_string
from django.utils import translation
from django.utils.translation import gettext, pgettext
from live.markdown import render_markdown

from apps.website.palettes import BLACK, WHITE, mix, resolve, rgb
from apps.website.schemas import DAYS, TEMPLATES, Content, Theme

#: The currency of the prices (ERPlora sells in Spain; the sale's own default).
CURRENCY = "EUR"
#: The sections between the hero and the footer, in their order.
BODY_SECTIONS = ("about", "catalog", "contact", "location")


def _day_names() -> dict[str, str]:
    return {
        "mon": pgettext("website", "Monday"),
        "tue": pgettext("website", "Tuesday"),
        "wed": pgettext("website", "Wednesday"),
        "thu": pgettext("website", "Thursday"),
        "fri": pgettext("website", "Friday"),
        "sat": pgettext("website", "Saturday"),
        "sun": pgettext("website", "Sunday"),
    }


def render_site(
    template: str,
    theme: dict,
    content: dict,
    lang: str,
    *,
    hub: str,
    catalog: dict | None = None,
    request: Any = None,
    preview: bool = False,
) -> str:
    """The page of ``template`` with ``theme`` and ``content`` in ``lang``, for the hub whose slug is ``hub``.

    ``catalog`` is the snapshot the catalog section paints; ``preview`` marks the editor's preview (not indexed,
    links inert, no refresh). ``request`` is accepted for symmetry with Django's renderers and never used: the HTML
    must not depend on who asked. Raises ``ValueError`` for an unknown template or an invalid theme or content.
    """
    del request  # The cached HTML is the same for every visitor.
    if template not in TEMPLATES:
        raise ValueError(f"Unknown website template {template!r}.")
    valid_theme = Theme.model_validate(theme or {})
    valid_content = Content.model_validate(content or {})
    with translation.override(lang):
        body = _body(valid_content, catalog)
        context = {
            "lang": lang,
            "template": template,
            "preview": preview,
            "theme": _theme(valid_theme),
            "site_name": valid_content.topbar.name or hub,
            "content": valid_content,
            "body": body,
            # The hero's button: to the first section shown, by its heading.
            "cta": {"name": body[0]["name"], "title": body[0]["data"]["title"]} if body else None,
        }
        return render_to_string(f"website/templates/{template}.html", context)


def catalog_view(catalog: dict | None) -> dict:
    """``catalog`` (a snapshot) with each item's price label in the active language; ``{}`` without a source."""
    if not catalog or not catalog.get("source"):
        return {}
    show_prices = bool(catalog.get("show_prices", True))
    groups = [
        {
            "name": group.get("name", ""),
            "items": [
                {
                    "name": item["name"],
                    "price": item.get("price") if show_prices else None,
                    "price_kind": item.get("price_kind", "none") if show_prices else "none",
                    "minutes": item.get("minutes"),
                    "price_label": price_label(item) if show_prices else "",
                }
                for item in group.get("items", [])
            ],
        }
        for group in catalog.get("groups", [])
    ]
    return {"source": catalog["source"], "show_prices": show_prices, "groups": groups}


def price_label(item: dict) -> str:
    """How the page prints an item's price: «€15.00», «From €40.00», «€20.00 / hour», «Free» or nothing."""
    kind, price = item.get("price_kind", "none"), item.get("price")
    if kind == "free":
        return pgettext("website price", "Free")
    if kind == "none" or price is None:
        return ""
    amount = format_currency(
        Decimal(price).scaleb(-2), CURRENCY, locale=translation.to_locale(translation.get_language() or "en")
    )
    if kind == "from":
        return gettext("From %(price)s") % {"price": amount}
    if kind == "hourly":
        return gettext("%(price)s / hour") % {"price": amount}
    return amount


# The parts of the page


def _theme(theme: Theme) -> dict[str, str]:
    """The page's mode and its palette as Bootstrap's CSS variables, for light and for dark (``base.html``).

    ``auto`` paints light first: the public bundle sets ``data-bs-theme`` from the visitor's device and follows it."""
    colours = resolve(theme.palette, theme.custom.model_dump() if theme.custom else None)
    blocks = "".join(
        f"html[data-bs-theme={mode}],html [data-bs-theme={mode}]{{{'color-scheme:dark;' if mode == 'dark' else ''}"
        + "".join(f"{name}:{value};" for name, value in _variables(colours[mode]).items())
        + "}"
        for mode in ("light", "dark")
    )
    return {
        "mode": theme.mode,
        "first_paint": "light" if theme.mode == "auto" else theme.mode,
        "color_scheme": "light dark" if theme.mode == "auto" else theme.mode,
        "css": blocks,
    }


def _variables(colours: dict[str, str]) -> dict[str, str]:
    """One mode's colours as the Bootstrap 5.3 variables they set; ``--ws-*`` for what Bootstrap has no variable of
    (the text on the main and the second colour, the main colour's hover). Every value is a validated ``#rrggbb``."""
    shade = BLACK if colours["on_primary"] == WHITE else WHITE
    variables = {
        "--bs-primary": colours["primary"],
        "--bs-secondary": colours["accent"],
        "--bs-body-bg": colours["bg"],
        "--bs-body-color": colours["text"],
        "--bs-emphasis-color": colours["text"],
        "--bs-secondary-color": colours["muted"],
        "--bs-tertiary-color": colours["muted"],
        "--bs-secondary-bg": colours["surface"],
        "--bs-tertiary-bg": colours["surface"],
        "--bs-link-color": colours["link"],
        "--bs-link-hover-color": colours["link_hover"],
    }
    variables = {
        **{key: value for name, colour in variables.items() for key, value in ((name, colour), (f"{name}-rgb", rgb(colour)))},
        "--bs-border-color": colours["border"],
        "--bs-primary-bg-subtle": colours["primary_subtle"],
        "--bs-primary-border-subtle": colours["primary_border_subtle"],
        "--bs-primary-text-emphasis": colours["link"],
        "--bs-focus-ring-color": f"rgba({rgb(colours['primary'])},.35)",
        "--ws-on-primary": colours["on_primary"],
        "--ws-on-accent": colours["on_accent"],
        "--ws-primary-hover": mix(shade, colours["primary"], 0.15),
        "--ws-primary-active": mix(shade, colours["primary"], 0.25),
    }
    return variables


def _body(content: Content, catalog: dict | None) -> list[dict]:
    """The sections between the hero and the footer that are shown and have something to show."""
    builders = {"about": _about, "catalog": _catalog, "contact": _contact, "location": _location}
    body = []
    for name in BODY_SECTIONS:
        section = getattr(content, name)
        if section.hidden:
            continue
        data = builders[name](section, catalog) if name == "catalog" else builders[name](section)
        if data is not None:
            body.append({"name": name, "partial": f"website/sections/{name}.html", "data": data})
    return body


def _about(section) -> dict | None:
    if not section.text and section.image is None:
        return None
    return {
        "title": section.title or pgettext("website", "About us"),
        "html": render_markdown(section.text),
        "image": section.image,
    }


def _catalog(section, catalog: dict | None) -> dict | None:
    if section.source is None:
        return None
    view = catalog_view(catalog) or {"source": section.source, "show_prices": section.show_prices, "groups": []}
    default_title = (
        pgettext("website", "Our services") if section.source == "service" else pgettext("website", "Our products")
    )
    return {"title": section.title or default_title, **view}


def _contact(section) -> dict | None:
    socials = [
        (label, getattr(section.socials, key))
        for key, label in (("instagram", "Instagram"), ("facebook", "Facebook"), ("tiktok", "TikTok"), ("x", "X"))
        if getattr(section.socials, key)
    ]
    if not (section.phone or section.whatsapp or section.email or socials or section.hours):
        return None
    days = _day_names()
    return {
        "title": section.title or pgettext("website", "Contact"),
        "phone": section.phone,
        "phone_href": "tel:" + _dialable(section.phone) if section.phone else "",
        "whatsapp": section.whatsapp,
        "whatsapp_href": "https://wa.me/" + _dialable(section.whatsapp).lstrip("+") if section.whatsapp else "",
        "email": section.email,
        "socials": socials,
        "hours": [
            {
                "day": days[row.day],
                "times": ", ".join(f"{interval.opens}–{interval.closes}" for interval in row.intervals)
                or pgettext("opening hours", "Closed"),
            }
            for row in sorted(section.hours, key=lambda row: DAYS.index(row.day))
        ],
    }


def _dialable(number: str) -> str:
    """``number`` as a link dials it: its digits, and the ``+`` in front if it has one."""
    digits = "".join(char for char in number if char.isdigit())
    return f"+{digits}" if number.startswith("+") else digits


def _location(section) -> dict | None:
    if not section.address_lines and not section.map_url:
        return None
    return {
        "title": section.title or pgettext("website", "Find us"),
        "address_lines": section.address_lines,
        "map_url": section.map_url,
    }
