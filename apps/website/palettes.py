"""The website's palettes: the colours a page is painted with, light and dark (round 2026-10-22).

``palettes.json`` holds the eight curated palettes (the editor shows the same file as swatch cards): for each, the
second colour (``accent``) and a light and a dark set of the main colour (``primary``: buttons, the bold hero), the
page (``bg``), the bands and cards (``surface``), the text, the links and the borders, written so that every pair a
visitor reads passes WCAG AA (4.5:1; ``tests/test_palettes.py`` checks each).

The owner may change the chosen palette's two colours (the theme's ``custom``, W8 of the same round): the page, the
bands and the text are then derived from those two, whatever the palette, and a colour is nudged toward black or white
only as far as AA needs (a dark blue is kept as chosen; a yellow button gets a darker yellow or black text, whichever
is closer). No pair is refused: an unreadable one is made readable.

:func:`resolve` gives both modes with the derived roles the page also needs (the text on the main and the second
colour, the muted text, the links' hover, the main colour's subtle tint); ``render`` writes them as Bootstrap's CSS
variables.
"""

import json
from pathlib import Path

#: The curated palettes, in the order the editor shows them.
PALETTES: dict[str, dict] = json.loads((Path(__file__).resolve().parent / "palettes.json").read_text())
#: WCAG AA for normal text.
AA = 4.5
#: The ratio the body text keeps on a page derived from the owner's colours: AAA, as the curated ones.
BODY = 7.0
BLACK, WHITE = "#000000", "#ffffff"
#: Where a derived dark page and its bands start from, before the owner's colour tints them.
DARK_BG, DARK_SURFACE, DARK_TEXT = "#0e1013", "#181b20", "#e8eaed"
LIGHT_TEXT = "#14181d"


def _channels(colour: str) -> tuple[int, int, int]:
    return int(colour[1:3], 16), int(colour[3:5], 16), int(colour[5:7], 16)


def _hex(red: float, green: float, blue: float) -> str:
    return "#" + "".join(f"{round(max(0, min(255, value))):02x}" for value in (red, green, blue))


def rgb(colour: str) -> str:
    """``#0b5cad`` as Bootstrap's ``*-rgb`` variables take it: ``11,92,173``."""
    return ",".join(str(channel) for channel in _channels(colour))


def mix(colour: str, other: str, weight: float) -> str:
    """``weight`` of ``colour`` and the rest of ``other`` (``weight=0.1``: a 10 % tint of ``colour`` on ``other``)."""
    return _hex(*(a * weight + b * (1 - weight) for a, b in zip(_channels(colour), _channels(other), strict=True)))


def _luminance(colour: str) -> float:
    def linear(channel: int) -> float:
        value = channel / 255
        return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4

    red, green, blue = (linear(channel) for channel in _channels(colour))
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast(colour: str, other: str) -> float:
    """WCAG 2's contrast ratio of two colours, from 1 (the same) to 21 (black on white)."""
    lighter, darker = sorted((_luminance(colour), _luminance(other)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def readable_on(colour: str) -> str:
    """Black or white, whichever reads better on ``colour``."""
    return BLACK if contrast(BLACK, colour) >= contrast(WHITE, colour) else WHITE


def _toward(colour: str, target: str, backgrounds: list[str], minimum: float) -> str:
    """``colour``, moved toward ``target`` (black or white) in small steps until it reads at ``minimum`` on every one
    of ``backgrounds``; ``colour`` itself when it already does."""
    for step in range(51):
        candidate = mix(target, colour, step / 50)
        if all(contrast(candidate, background) >= minimum for background in backgrounds):
            return candidate
    return target


def _fill(colour: str) -> tuple[str, str]:
    """A fill for text (a button, a badge) close to ``colour`` and its text, black or white, at AA at least: the
    colour moves toward black or toward white, whichever reaches AA in fewer steps."""
    for step in range(51):
        for target in (BLACK, WHITE):
            candidate = mix(target, colour, step / 50)
            text = readable_on(candidate)
            if contrast(text, candidate) >= AA:
                return candidate, text
    return BLACK, WHITE


def _mode(primary: str, accent: str, bg: str, surface: str, text: str, link: str, border: str) -> dict[str, str]:
    """One mode's colours with the roles derived from them."""
    subtle = mix(primary, bg, 0.12)
    toward_text = BLACK if _luminance(bg) > _luminance(text) else WHITE
    return {
        "primary": primary,
        "on_primary": readable_on(primary),
        "accent": accent,
        "on_accent": readable_on(accent),
        "bg": bg,
        "surface": surface,
        "text": text,
        "muted": _toward(mix(text, surface, 0.72), toward_text, [bg, surface], AA),
        "link": link,
        "link_hover": mix(text, link, 0.35),
        "border": border,
        "primary_subtle": subtle,
        "primary_border_subtle": mix(primary, bg, 0.3),
    }


def own_colours(palette: str) -> dict[str, str]:
    """The two colours of ``palette`` the owner may change: its main colour (the light one) and its second colour."""
    return {"primary": PALETTES[palette]["light"]["primary"], "accent": PALETTES[palette]["accent"]}


def _derived(primary: str, accent: str) -> dict[str, dict[str, str]]:
    """The page, bands and text from the owner's two colours, each nudged only as far as AA needs."""
    accent_fill = _fill(accent)[0]

    light_bg, light_surface = WHITE, mix(primary, WHITE, 0.06)
    light_primary = _fill(primary)[0]
    light_subtle = mix(light_primary, light_bg, 0.12)
    light = _mode(
        light_primary,
        accent_fill,
        light_bg,
        light_surface,
        _toward(LIGHT_TEXT, BLACK, [light_bg, light_surface], BODY),
        _toward(primary, BLACK, [light_bg, light_surface, light_subtle], AA),
        mix(primary, WHITE, 0.18),
    )

    # The dark page is a dark tint of the owner's colour; its links and buttons, a light one (a dark fill would vanish).
    dark_bg, dark_surface = mix(primary, DARK_BG, 0.08), mix(primary, DARK_SURFACE, 0.1)
    dark_link = _toward(primary, WHITE, [dark_bg, dark_surface], AA)
    dark_primary = _fill(dark_link)[0]
    dark_subtle = mix(dark_primary, dark_bg, 0.12)
    dark = _mode(
        dark_primary,
        accent_fill,
        dark_bg,
        dark_surface,
        _toward(DARK_TEXT, WHITE, [dark_bg, dark_surface], BODY),
        _toward(dark_link, WHITE, [dark_bg, dark_surface, dark_subtle], AA),
        mix(primary, dark_bg, 0.25),
    )
    return {"light": light, "dark": dark}


def resolve(palette: str, custom: dict | None) -> dict[str, dict[str, str]]:
    """The ``light`` and ``dark`` colours of ``palette``, or of the owner's ``custom`` primary and accent over it.

    Raises ``ValueError`` for an unknown palette."""
    if palette not in PALETTES:
        raise ValueError(f"Unknown website palette {palette!r}.")
    if custom:
        return _derived(custom["primary"], custom["accent"])
    written = PALETTES[palette]

    return {mode: _mode(accent=written["accent"], **written[mode]) for mode in ("light", "dark")}
