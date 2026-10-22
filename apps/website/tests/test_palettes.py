"""The website's palettes (``palettes.json``, shared with the editor): eight curated ones. Each gives a light and a dark
set of colours, and every pair a visitor reads passes WCAG AA (4.5:1) in both modes: the text and the muted text on
the page and on the bands, the links, the buttons' text on the main colour and the badges' text on the second one. The
owner may change a palette's two colours (``theme.custom``): the surfaces are then derived from them and nudged only as
far as AA needs, whatever pair was picked."""

import json
from pathlib import Path

import pytest

from apps.website.palettes import PALETTES, contrast, readable_on, resolve
from apps.website.schemas import PALETTE_IDS

AA = 4.5
ROLES = {
    "primary",
    "on_primary",
    "accent",
    "on_accent",
    "bg",
    "surface",
    "text",
    "muted",
    "link",
    "link_hover",
    "border",
    "primary_subtle",
    "primary_border_subtle",
}
#: Owners' colours that are hard to read on: yellow, pale, mid grey, black, white, neon, and an ordinary blue.
HARD_COLOURS = ["#ffff00", "#f5f5dc", "#777777", "#000000", "#ffffff", "#39ff14", "#ff00ff", "#2563eb", "#7f7f00"]


def aa_failures(colours: dict[str, str]) -> list[str]:
    """The pairs of ``colours`` (one mode) a visitor reads that fall under AA."""
    pairs = [
        ("text", "bg"),
        ("text", "surface"),
        ("muted", "bg"),
        ("muted", "surface"),
        ("link", "bg"),
        ("link", "surface"),
        ("link", "primary_subtle"),
        ("on_primary", "primary"),
        ("on_accent", "accent"),
    ]
    return [
        f"{fg} on {bg}: {contrast(colours[fg], colours[bg]):.2f}"
        for fg, bg in pairs
        if contrast(colours[fg], colours[bg]) < AA
    ]


def test_the_curated_palettes_in_their_order_are_the_only_ones():
    assert list(PALETTES) == ["ocean", "forest", "terracotta", "slate", "rose", "sand", "midnight", "olive"]
    assert PALETTE_IDS == tuple(PALETTES)


def test_the_editor_and_the_server_read_the_same_file():
    raw = json.loads((Path(__file__).resolve().parents[1] / "palettes.json").read_text())
    assert raw == PALETTES


def test_contrast_is_wcags_ratio():
    assert contrast("#000000", "#ffffff") == pytest.approx(21)
    assert contrast("#ffffff", "#000000") == pytest.approx(21)
    assert contrast("#777777", "#ffffff") == pytest.approx(4.48, abs=0.01)
    assert readable_on("#ffff00") == "#000000" and readable_on("#0b5cad") == "#ffffff"


@pytest.mark.parametrize("palette", list(PALETTES))
@pytest.mark.parametrize("mode", ["light", "dark"])
def test_every_curated_palette_reads_at_aa_in_both_modes(palette, mode):
    colours = resolve(palette, None)[mode]
    assert set(colours) == ROLES
    assert aa_failures(colours) == []


@pytest.mark.parametrize("palette", list(PALETTES))
def test_a_curated_palette_is_painted_as_it_is_written(palette):
    written, colours = PALETTES[palette], resolve(palette, None)
    for mode in ("light", "dark"):
        for role in ("primary", "bg", "surface", "text", "link", "border"):
            assert colours[mode][role] == written[mode][role], (mode, role)
        assert colours[mode]["accent"] == written["accent"]


@pytest.mark.parametrize("primary", HARD_COLOURS)
@pytest.mark.parametrize("accent", ["#ffff00", "#777777", "#000000", "#f59e0b"])
@pytest.mark.parametrize("mode", ["light", "dark"])
def test_a_palette_with_the_owners_colours_derives_its_surfaces_and_reads_at_aa(primary, accent, mode):
    colours = resolve("ocean", {"primary": primary, "accent": accent})[mode]
    assert set(colours) == ROLES
    assert aa_failures(colours) == []


def test_an_owners_colour_that_reads_well_is_kept_as_the_owner_chose_it():
    colours = resolve("rose", {"primary": "#0b5cad", "accent": "#f59e0b"})
    assert colours["light"]["primary"] == "#0b5cad" and colours["light"]["link"] == "#0b5cad"
    assert colours["light"]["accent"] == colours["dark"]["accent"] == "#f59e0b"
    assert colours["light"]["bg"] == "#ffffff"
    # The dark page is a dark tint of the owner's colour, its links a light one.
    assert contrast(colours["dark"]["bg"], "#000000") < 1.3
    assert contrast(colours["dark"]["link"], colours["dark"]["bg"]) >= AA


def test_the_owners_colours_are_painted_the_same_over_any_palette():
    colours = {"primary": "#7f7f00", "accent": "#ff00ff"}
    assert resolve("ocean", colours) == resolve("midnight", colours)
    assert resolve("ocean", colours) != resolve("ocean", None)


def test_an_unknown_palette_is_not_resolved():
    for unknown in ("custom", "sepia"):
        with pytest.raises(ValueError):
            resolve(unknown, None)
        with pytest.raises(ValueError):
            resolve(unknown, {"primary": "#112233", "accent": "#445566"})

