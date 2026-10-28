"""base/catalog.py: what the Hub registers of its modules in the SaaS (round 16, PLAN §21; spec §4).

``user_part`` cuts the customer's part of a WORKBOOK (§4.1); ``build_registry`` reads every module's
metadata, catalogue, baked icon and documentation without touching a database or the network
(§4.2), gathering one error per rule; ``AppImagesFinder`` publishes ``apps/<id>/docs/img/`` as
``catalog/<id>/img/`` (§4.4); ``known_verticals`` and ``template_apps`` derive the templates of
PLAN §15.2 (§4.7). The last block runs it all on the real modules: the check of CI (§4.8).
"""

import array
import hashlib
import struct
from pathlib import Path
from types import SimpleNamespace

import pytest
from django.contrib.staticfiles import finders
from live.meta import Category

from base.catalog import (
    AppEntry,
    AppImagesFinder,
    RegistryError,
    WorkbookError,
    build_registry,
    en_header,
    known_verticals,
    prose_lines,
    source_hash,
    stale_translations,
    template_apps,
    user_part,
)

CUT = "## Para quien lo mantiene"
WORKBOOK = f"""\
# Workbook — Things (app)
Prefijo: THING
Alcance MVP: fase 1
Estado de la app: en construcción

> Manual de usuario y especificación. Ver [los cambios](#cambios-frente-al-producto-actual).

## Para qué sirve

Guarda **cosas**. Ver [cómo se usa](#cómo-se-usa).

![Lista de cosas](docs/img/list.png)

## Cómo se usa

### Paso a paso
Estado: hecho

{CUT}

- Notas internas.

## Cambios frente al producto actual

- Nada.
"""
USER_PART = """\
## Para qué sirve

Guarda **cosas**. Ver [cómo se usa](#cómo-se-usa).

![Lista de cosas](docs/img/list.png)

## Cómo se usa

### Paso a paso
Estado: hecho
"""
ICONS = {
    "ion:cube-outline": "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 512 512'><path d='M1 1'/></svg>",
    "mdi:cart": "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'><path d='M2 2'/></svg>",
}
SPANISH = {
    "Things": "Cosas",
    "Keep your things.": "Guarda tus cosas.",
    "Every thing in one place.": "Cada cosa en su sitio.",
}


# ── Helpers: a module of apps/ on disk, with its compiled Spanish catalogue ────────────────────


def write_mo(path: Path, messages: dict[str, str]) -> None:
    """A GNU ``.mo`` catalogue with ``messages`` (what ``msgfmt`` writes for a .po without plurals)."""
    entries = {"": "Content-Type: text/plain; charset=UTF-8\n", **messages}
    keys = sorted(entries)
    ids = b"".join(key.encode() + b"\0" for key in keys)
    strs = b"".join(entries[key].encode() + b"\0" for key in keys)
    key_start = 7 * 4 + 16 * len(keys)
    value_start = key_start + len(ids)
    offsets, key_offset, value_offset = [], [], []
    position_key = position_value = 0
    for key in keys:
        key_bytes, value_bytes = key.encode(), entries[key].encode()
        key_offset += [len(key_bytes), key_start + position_key]
        value_offset += [len(value_bytes), value_start + position_value]
        position_key += len(key_bytes) + 1
        position_value += len(value_bytes) + 1
    offsets = key_offset + value_offset
    header = struct.pack(
        "Iiiiiii", 0x950412DE, 0, len(keys), 7 * 4, 7 * 4 + len(keys) * 8, 0, 0
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(header + array.array("i", offsets).tobytes() + ids + strs)


def module(
    root: Path,
    label: str = "things",
    *,
    workbook: str | None = WORKBOOK,
    en: str | None = None,
    spanish: dict[str, str] | None = None,
    images: tuple[str, ...] = (),
    **fields,
) -> SimpleNamespace:
    """A module of ``apps/`` on disk: what ``build_registry`` reads of a ``LiveAppConfig``."""
    path = root / label
    path.mkdir(parents=True)
    if workbook is not None:
        (path / "WORKBOOK.md").write_text(workbook)
    if en is not None:
        (path / "WORKBOOK.en.md").write_text(en)
    write_mo(
        path / "locale" / "es" / "LC_MESSAGES" / "django.mo",
        SPANISH if spanish is None else spanish,
    )
    for image in images:
        (path / image).parent.mkdir(parents=True, exist_ok=True)
        (path / image).write_bytes(b"\x89PNG")
    config = {
        "label": label,
        "name": f"apps.{label}",
        "path": str(path),
        "kind": "app",
        "verbose_name": "Things",
        "summary": "Keep your things.",
        "description": "Every thing in one place.",
        "icon": "ion:cube-outline",
        "category": Category.CATALOG,
        "premium": False,
        "requires": [],
        "verticals": [],
        "listed": True,
    }
    return SimpleNamespace(**(config | fields))


def translated(
    source: str, body: str = "## What it is for\n\nKeeps **things**.\n"
) -> str:
    """A ``WORKBOOK.en.md`` generated from ``source`` (the Spanish user part)."""
    return f"{en_header(source_hash(source))}\n\n{body}"


def problems(configs, icons=ICONS) -> list[str]:
    with pytest.raises(RegistryError) as raised:
        build_registry(configs, icons=icons)
    return raised.value.problems


# ── user_part (§4.1) ───────────────────────────────────────────────────────────────────────────


def test_user_part_runs_from_the_first_section_to_the_maintainers_heading():
    assert user_part(WORKBOOK) == USER_PART


def test_user_part_drops_the_title_and_the_header():
    part = user_part(WORKBOOK)
    for line in (
        "# Workbook",
        "Prefijo:",
        "Alcance MVP:",
        "Estado de la app:",
        "> Manual de usuario",
    ):
        assert line not in part
    # The flows' «Estado:» lines are published as they are: only the HTML comments go.
    assert "Estado: hecho" in part


def test_user_part_does_not_cut_before_the_exact_heading():
    text = WORKBOOK.replace(
        "## Cómo se usa\n",
        "## Cómo se usa\n\nPara quien lo mantiene, nada.\n\n## Para quien lo mantiene la tienda\n",
    )
    part = user_part(
        text.replace("(#cómo-se-usa)", "(#para-quien-lo-mantiene-la-tienda)")
    )
    assert "## Para quien lo mantiene la tienda" in part
    assert "Notas internas" not in part


def test_user_part_fails_without_the_maintainers_heading():
    with pytest.raises(WorkbookError, match="Para quien lo mantiene"):
        user_part(WORKBOOK.replace(CUT, "## Notas"))


def test_user_part_fails_when_nothing_is_above_the_heading():
    with pytest.raises(WorkbookError, match="nothing"):
        user_part(f"# Workbook\n\n{CUT}\n\n- Notas.\n")


def test_the_heading_inside_a_code_block_does_not_cut():
    fenced = WORKBOOK.replace(
        "### Paso a paso\n",
        f"### Paso a paso\n\n```markdown\n{CUT}\n```\n\n~~~\n{CUT}\n~~~\n",
    )
    part = user_part(fenced)
    assert part.count(CUT) == 2
    assert "Estado: hecho" in part
    assert "Notas internas" not in part


#: A line that looks like a fence inside a block and closes nothing: of the other character, shorter, or with an info string.
NOT_CLOSING = {"other-character": ("```", "~~~"), "shorter": ("````", "```"), "info-string": ("```", "```text")}


@pytest.mark.parametrize(("fence", "inner"), NOT_CLOSING.values(), ids=NOT_CLOSING)
def test_only_a_fence_like_the_opening_one_closes_its_code_block(fence, inner):
    fenced = WORKBOOK.replace("### Paso a paso\n", f"### Paso a paso\n\n{fence}\n{inner}\n{CUT}\n{fence}\n")
    part = user_part(fenced)
    assert CUT in part
    assert "Estado: hecho" in part


@pytest.mark.parametrize(("fence", "inner"), NOT_CLOSING.values(), ids=NOT_CLOSING)
def test_the_prose_lines_are_the_numbered_ones_outside_the_fenced_code_blocks(fence, inner):
    """What ``translate_workbooks --check`` reads for a Spanish date: an unclosed block runs to the end."""
    text = f"Before.\n{fence}\n{inner}\nDD/MM/AAAA\n{fence}\nAfter.\n~~~\nDD/MM/AAAA"
    assert list(prose_lines(text)) == [(1, "Before."), (6, "After.")]


def test_a_dangling_anchor_fails_and_names_it():
    with pytest.raises(WorkbookError, match="#no-existe"):
        user_part(WORKBOOK.replace("(#cómo-se-usa)", "(#no-existe)"))


def test_an_anchor_to_a_heading_the_cut_leaves_out_fails():
    with pytest.raises(WorkbookError, match="#cambios-frente-al-producto-actual"):
        user_part(
            WORKBOOK.replace("(#cómo-se-usa)", "(#cambios-frente-al-producto-actual)")
        )


# The «<!-- origen: … -->» and «<!-- código: … -->» of a WORKBOOK tie it to MIGRATION.md and to its
# sources, never reaching shared.app_doc nor the assistant (PLAN-MIGRATIONS §5).
ORIGIN = "<!-- origen: old-hub:HUB-F212 gh:sales#131 -->"


@pytest.mark.parametrize(
    ("text", "commented"),
    [
        # On a line of its own, under a flow's title: the line goes with it.
        ("### Paso a paso\n", f"### Paso a paso\n{ORIGIN}\n"),
        # Between blank lines, over several lines: no blank line is doubled.
        (
            "## Cómo se usa\n\n",
            "## Cómo se usa\n\n<!-- código:\n  https://example.com/a.py\n-->\n\n",
        ),
        # Inside a line: the text around it is joined by one space, as it reads.
        ("**cosas**. Ver", "**cosas**. <!-- código: https://example.com/a.py --> Ver"),
        ("**cosas**. Ver", "**cosas**. <!-- a --> Ver<!-- b -->"),
        # Closed before the text of a line.
        ("### Paso a paso\n", "### Paso a paso\n<!-- origen:\n  old-hub:HUB-F212 --> "),
        # At the end of a line, and opened there to close lines below.
        ("list.png)\n", "list.png) <!-- código: https://example.com/a.py -->\n"),
        ("list.png)\n", "list.png) <!-- código:\n  https://example.com/a.py\n-->\n"),
    ],
)
def test_user_part_leaves_out_the_html_comments(text, commented):
    assert WORKBOOK.count(text) == 1
    assert user_part(WORKBOOK.replace(text, commented)) == USER_PART


def test_a_comment_inside_a_code_block_is_published_as_it_is():
    blocks = f"```html\n{ORIGIN}\n```\n\n~~~\n<!-- varias\nlíneas -->\n~~~\n"
    part = user_part(WORKBOOK.replace("Estado: hecho\n", f"Estado: hecho\n\n{blocks}"))
    assert part == f"{USER_PART}\n{blocks}"


def test_inside_a_comment_the_heading_does_not_cut_nor_a_fence_open_a_block():
    hidden = f"### Paso a paso\n<!--\n{CUT}\n```\n-->\n"
    assert user_part(WORKBOOK.replace("### Paso a paso\n", hidden)) == USER_PART


def test_a_comment_that_never_closes_fails_naming_its_line():
    # Line 17 of WORKBOOK, right under «### Paso a paso».
    unclosed = WORKBOOK.replace("### Paso a paso\n", "### Paso a paso\n<!-- origen:\n")
    with pytest.raises(WorkbookError, match=r"\b17\b"):
        user_part(unclosed)


def test_a_comment_left_open_below_the_cut_is_never_read():
    assert user_part(f"{WORKBOOK}\nAbre un comentario con `<!--`.\n") == USER_PART


# ── build_registry (§4.2) ──────────────────────────────────────────────────────────────────────


def test_a_module_becomes_one_entry_with_both_languages_its_icon_and_its_documentation(
    tmp_path,
):
    config = module(
        tmp_path,
        en=translated(USER_PART),
        requires=["stock", "catalog"],
        verticals=["restaurant", "hair_salon"],
        premium=True,
        images=("docs/img/list.png",),
    )

    [entry] = build_registry([config], icons=ICONS)

    assert entry == AppEntry(
        id="things",
        name_en="Things",
        name_es="Cosas",
        summary_en="Keep your things.",
        summary_es="Guarda tus cosas.",
        description_en="Every thing in one place.",
        description_es="Cada cosa en su sitio.",
        icon="ion:cube-outline",
        icon_svg=ICONS["ion:cube-outline"],
        category="catalog",
        premium=True,
        requires=["catalog", "stock"],
        verticals=["hair_salon", "restaurant"],
        listed=True,
        docs={"es": USER_PART, "en": "## What it is for\n\nKeeps **things**.\n"},
    )


def test_without_a_translation_there_is_no_english_document(tmp_path):
    [entry] = build_registry([module(tmp_path)], icons=ICONS)
    assert entry.docs == {"es": USER_PART}


def test_the_documentation_is_registered_without_the_workbooks_comments(tmp_path):
    commented = WORKBOOK.replace("### Paso a paso\n", f"### Paso a paso\n{ORIGIN}\n")
    [entry] = build_registry([module(tmp_path, workbook=commented)], icons=ICONS)
    assert entry.docs == {"es": USER_PART}


def test_a_comment_does_not_make_the_translation_stale(tmp_path):
    # Tying a flow to its origin is no change for the customer: nothing to translate again.
    commented = WORKBOOK.replace("### Paso a paso\n", f"### Paso a paso\n{ORIGIN}\n")
    config = module(tmp_path, workbook=commented, en=translated(USER_PART))
    [entry] = build_registry([config], icons=ICONS)
    assert set(entry.docs) == {"es", "en"}


def test_a_text_without_its_spanish_msgstr_fails_naming_the_app_and_the_field(tmp_path):
    spanish = {
        key: value for key, value in SPANISH.items() if key != "Keep your things."
    }
    [problem] = problems([module(tmp_path, spanish=spanish)])
    assert problem.startswith("things: summary:")
    assert "msgstr" in problem and "compilemessages" in problem


def test_a_name_that_is_the_same_in_both_languages_still_needs_its_msgstr(tmp_path):
    assert build_registry(
        [module(tmp_path, verbose_name="Demo", spanish={**SPANISH, "Demo": "Demo"})],
        icons=ICONS,
    )
    [problem] = problems([module(tmp_path / "other", verbose_name="Demo")])
    assert problem.startswith("things: verbose_name:")


def test_a_spanish_text_longer_than_its_column_fails(tmp_path):
    spanish = {**SPANISH, "Keep your things.": "x" * 121}
    [problem] = problems([module(tmp_path, spanish=spanish)])
    assert problem.startswith("things: summary:") and "120" in problem


def test_an_english_text_longer_than_its_column_fails_too(tmp_path):
    # live.E007 checks it in `manage.py check`; register_apps() also runs where no check ran (the worker).
    name = "N" * 81
    [problem] = problems(
        [module(tmp_path, verbose_name=name, spanish={**SPANISH, name: "Cosas"})]
    )
    assert (
        problem.startswith("things: verbose_name:")
        and "English" in problem
        and "80" in problem
    )


def test_an_icon_that_is_not_baked_fails_with_the_command_that_bakes_it(tmp_path):
    [problem] = problems([module(tmp_path, icon="lucide:box")])
    assert problem.startswith("things: icon:")
    assert "lucide:box" in problem and "pnpm gen:app-icons" in problem


def test_a_workbook_without_the_maintainers_heading_fails(tmp_path):
    [problem] = problems([module(tmp_path, workbook=WORKBOOK.replace(CUT, "## Notas"))])
    assert problem.startswith("things: WORKBOOK.md:")
    assert "Para quien lo mantiene" in problem


def test_a_module_without_workbook_fails(tmp_path):
    [problem] = problems([module(tmp_path, workbook=None)])
    assert problem.startswith("things: WORKBOOK.md:")


#: The command of PLAN-MIGRATIONS §24-D that prints the first line of a hand-made WORKBOOK.en.md.
HEADER_COMMAND = (
    'uv run python manage.py shell --no-imports -c "from django.apps import apps; from base import catalog; '
    "print(catalog.en_header(catalog.source_hash(catalog.workbook_translation(apps.get_app_config('{}')).source)))\""
)


def test_a_stale_translation_fails_telling_to_translate_it_by_hand_with_its_header(tmp_path):
    """ERPlora uses no ANTHROPIC_API_KEY (PLAN-MIGRATIONS §24-D): never a command that calls the API.

    The command ends the line: copied to its end, it runs (a full stop after its quote would be Python).
    """
    stale = translated(USER_PART.replace("cosas", "objetos"))
    [problem] = problems([module(tmp_path, en=stale)])
    assert problem == (
        "things: WORKBOOK.en.md: out of date with WORKBOOK.md: translate by hand the part of WORKBOOK.md "
        "that changed into WORKBOOK.en.md and make its first line the header this prints: "
        f"{HEADER_COMMAND.format('things')}"
    )
    assert "translate_workbooks" not in problem


def test_a_translation_without_its_header_is_stale(tmp_path):
    [problem] = problems([module(tmp_path, en="## What it is for\n")])
    assert problem.startswith("things: WORKBOOK.en.md: out of date with WORKBOOK.md:")
    assert HEADER_COMMAND.format("things") in problem


def test_a_translation_with_a_dangling_anchor_fails(tmp_path):
    en = translated(USER_PART, "## What it is for\n\nSee [how](#how-to-use-it).\n")
    [problem] = problems([module(tmp_path, en=en)])
    assert problem.startswith("things: WORKBOOK.en.md:") and "#how-to-use-it" in problem


@pytest.mark.parametrize(
    "image", ["docs/img/diagram.svg", "docs/img/sub/notes.txt", "docs/img/photo.bmp"]
)
def test_an_image_with_another_extension_fails(tmp_path, image):
    [problem] = problems([module(tmp_path, images=("docs/img/list.png", image))])
    assert problem.startswith("things: docs/img:")
    assert image.removeprefix("docs/img/") in problem


def test_allowed_images_hidden_files_and_files_outside_docs_img_pass(tmp_path):
    images = (
        "docs/img/a.png",
        "docs/img/b.JPG",
        "docs/img/c.jpeg",
        "docs/img/d.webp",
        "docs/img/sub/e.gif",
    )
    others = ("docs/img/.DS_Store", "docs/notes.txt", "docs/diagram.svg")
    assert build_registry([module(tmp_path, images=images + others)], icons=ICONS)


def test_only_modules_are_registered(tmp_path):
    platform = module(tmp_path, "base", kind="platform")
    entries = build_registry([platform, module(tmp_path, "things")], icons=ICONS)
    assert [entry.id for entry in entries] == ["things"]


def test_the_order_is_by_label_whatever_the_order_of_the_apps(tmp_path):
    configs = [module(tmp_path, label) for label in ("zeta", "alpha", "mid")]
    assert [entry.id for entry in build_registry(configs, icons=ICONS)] == [
        "alpha",
        "mid",
        "zeta",
    ]


def test_every_problem_of_every_module_is_gathered(tmp_path):
    broken = [
        module(tmp_path, "beta", icon="lucide:box", workbook=None),
        module(tmp_path, "alpha", spanish={}),
    ]
    found = problems(broken)
    assert [problem.split(":")[0] for problem in found] == [
        "alpha",
        "alpha",
        "alpha",
        "beta",
        "beta",
    ]
    assert str(RegistryError(found)).count("\n") == len(found)


def test_the_baked_icons_are_read_from_the_generated_json(tmp_path, settings):
    settings.BASE_DIR = tmp_path
    (tmp_path / "frontend" / "generated").mkdir(parents=True)
    (tmp_path / "frontend" / "generated" / "app-icons.json").write_text(
        '{"ion:cube-outline": "<svg/>"}'
    )
    [entry] = build_registry([module(tmp_path / "apps")])
    assert entry.icon_svg == "<svg/>"


def test_without_the_generated_json_every_icon_fails(tmp_path, settings):
    settings.BASE_DIR = tmp_path
    [problem] = problems([module(tmp_path / "apps")], icons=None)
    assert "pnpm gen:app-icons" in problem


def test_stale_translations_lists_the_modules_to_translate_again(tmp_path):
    configs = [
        module(tmp_path, "current", en=translated(USER_PART)),
        module(tmp_path, "stale", en=translated("otra cosa\n")),
        module(tmp_path, "untranslated"),
    ]
    assert stale_translations(configs) == ["stale"]


# ── AppImagesFinder (§4.4) ─────────────────────────────────────────────────────────────────────


def test_the_finder_publishes_docs_img_under_catalog_and_nothing_else(tmp_path):
    files = (
        "docs/img/list.png",
        "docs/img/sub/photo.webp",
        "docs/img/diagram.svg",
        "docs/img/.hidden.png",
        "docs/img/.cache/x.png",
        "docs/img/script.py",
        "docs/other.png",
        "WORKBOOK.md",
        "WORKBOOK.en.md",
        "apps.py",
    )
    finder = AppImagesFinder(configs=[module(tmp_path, images=files)])

    listed = sorted(f"{storage.prefix}/{path}" for path, storage in finder.list(None))

    assert listed == [
        "catalog/things/img/list.png",
        "catalog/things/img/sub/photo.webp",
    ]


def test_the_finder_finds_one_image_by_its_static_path(tmp_path):
    config = module(tmp_path, images=("docs/img/list.png", "docs/img/diagram.svg"))
    finder = AppImagesFinder(configs=[config])

    assert finder.find("catalog/things/img/list.png") == str(
        tmp_path / "things" / "docs" / "img" / "list.png"
    )
    assert finder.find("catalog/things/img/list.png", find_all=True) == [
        str(tmp_path / "things" / "docs" / "img" / "list.png")
    ]
    for missing in ("catalog/things/img/diagram.svg", "catalog/things/img/nope.png", "catalog/other/img/list.png",
                    "catalog/things/img/../WORKBOOK.md", "catalog/things/WORKBOOK.md", "spa/main.js"):  # fmt: skip
        assert finder.find(missing) == []


def test_the_finder_skips_ignored_patterns(tmp_path):
    finder = AppImagesFinder(
        configs=[module(tmp_path, images=("docs/img/a.png", "docs/img/b.gif"))]
    )
    assert [path for path, _ in finder.list(["*.gif"])] == ["a.png"]


def test_the_finder_skips_platform_apps_and_modules_without_images(tmp_path):
    configs = [
        module(tmp_path, "base", kind="platform", images=("docs/img/a.png",)),
        module(tmp_path, "things"),
    ]
    assert list(AppImagesFinder(configs=configs).list(None)) == []


# ── Symbolic links: never followed (review L8) ─────────────────────────────────────────────────


def outside_files(tmp_path: Path) -> None:
    """What lies outside a module: the settings an attacker wants and folders with an image."""
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "settings.py").write_text("SECRET_KEY = 'leaked'\n")
    (tmp_path / "outside" / "img").mkdir(parents=True)
    (tmp_path / "outside" / "a.png").write_bytes(b"\x89PNG")
    (tmp_path / "outside" / "img" / "a.png").write_bytes(b"\x89PNG")


def link(config, path: str, target: str | Path) -> Path:
    """A symbolic link ``path`` (relative to the module) pointing at ``target``."""
    linked = Path(config.path) / path
    linked.parent.mkdir(parents=True, exist_ok=True)
    linked.symlink_to(target)
    return linked


# (the link, where it points (relative to tmp_path unless it starts with ".."), the static path through it)
SYMLINKS = [
    ("docs/img/x.png", "../../../config/settings.py", "catalog/things/img/x.png"),
    ("docs/img/sub", "outside", "catalog/things/img/sub/a.png"),
    ("docs/img/gone.png", "nowhere.png", "catalog/things/img/gone.png"),
    ("docs/img", "outside", "catalog/things/img/a.png"),
    ("docs", "outside", "catalog/things/img/a.png"),
]


def linked_module(tmp_path, path, target):
    outside_files(tmp_path)
    config = module(tmp_path)
    link(config, path, target if target.startswith("..") else tmp_path / target)
    return config


def test_the_attack_link_resolves_to_the_settings(tmp_path):
    """The premise of the tests below: without the check, x.png would be the settings file."""
    config = linked_module(tmp_path, "docs/img/x.png", "../../../config/settings.py")

    assert (
        Path(config.path) / "docs/img/x.png"
    ).read_text() == "SECRET_KEY = 'leaked'\n"


@pytest.mark.parametrize(("path", "target", "static"), SYMLINKS)
def test_a_symbolic_link_fails_the_registry_naming_the_app_and_the_link(
    tmp_path, path, target, static
):
    [problem] = problems([linked_module(tmp_path, path, target)])

    assert problem.startswith("things: docs/img:")
    assert "symbolic link" in problem
    assert f"replace {path} " in problem


@pytest.mark.parametrize(("path", "target", "static"), SYMLINKS)
def test_the_finder_publishes_nothing_through_a_symbolic_link(
    tmp_path, path, target, static
):
    finder = AppImagesFinder(configs=[linked_module(tmp_path, path, target)])

    assert list(finder.list(None)) == []
    assert finder.find(static) == []
    assert finder.find(static, find_all=True) == []


def test_a_real_image_next_to_a_symbolic_link_is_still_published(tmp_path):
    outside_files(tmp_path)
    config = module(tmp_path, images=("docs/img/list.png",))
    link(config, "docs/img/x.png", "../../../config/settings.py")
    finder = AppImagesFinder(configs=[config])

    assert [path for path, _ in finder.list(None)] == ["list.png"]
    assert finder.find("catalog/things/img/list.png") == str(
        Path(config.path) / "docs" / "img" / "list.png"
    )
    assert finder.find("catalog/things/img/x.png") == []
    [problem] = problems([config])
    assert "replace docs/img/x.png " in problem
    assert "list.png" not in problem


def test_a_hidden_symbolic_link_is_neither_published_nor_reported(tmp_path):
    outside_files(tmp_path)
    config = module(tmp_path, images=("docs/img/list.png",))
    link(config, "docs/img/.x.png", "../../../config/settings.py")

    assert build_registry([config], icons=ICONS)
    assert [path for path, _ in AppImagesFinder(configs=[config]).list(None)] == [
        "list.png"
    ]


# ── Verticals (§4.7) ───────────────────────────────────────────────────────────────────────────


@pytest.fixture
def vertical_modules(tmp_path):
    return [
        module(tmp_path, "booking", verticals=["hair_salon"], requires=["customer"]),
        module(tmp_path, "customer", requires=["contact"]),
        module(tmp_path, "contact"),
        module(tmp_path, "sale", verticals=["restaurant", "hair_salon"]),
        module(tmp_path, "table", verticals=["restaurant"]),
        module(tmp_path, "base", kind="platform"),
    ]


def test_known_verticals_are_the_union_of_the_modules_verticals(vertical_modules):
    assert known_verticals(vertical_modules) == ["hair_salon", "restaurant"]


def test_a_template_has_the_modules_of_its_vertical_closed_by_requires(
    vertical_modules,
):
    assert template_apps("hair_salon", vertical_modules) == [
        "booking",
        "contact",
        "customer",
        "sale",
    ]
    assert template_apps("restaurant", vertical_modules) == ["sale", "table"]


def test_an_unknown_vertical_has_no_template(vertical_modules):
    with pytest.raises(ValueError, match="bakery"):
        template_apps("bakery", vertical_modules)


# ── The real modules: the check of CI (§4.8) ──────────────────────────────────────────────────


def test_the_real_modules_build_their_registry():
    entries = build_registry()
    demo = next(entry for entry in entries if entry.id == "demo")
    assert (demo.name_en, demo.name_es) == ("Demo", "Demo")
    assert demo.listed is False
    assert demo.icon_svg.startswith("<svg")
    assert demo.docs["es"].startswith("## ")
    assert hashlib.sha256(demo.docs["es"].encode()).hexdigest() == source_hash(
        demo.docs["es"]
    )


def test_no_real_translation_is_stale():
    assert stale_translations() == []


def test_the_real_verticals_derive_from_the_modules():
    assert known_verticals() == sorted(
        {v for entry in build_registry() for v in entry.verticals}
    )


def test_the_static_files_pipeline_finds_the_real_demo_image():
    # What collectstatic copies into STATIC_ROOT in the image's build (settings.STATICFILES_FINDERS).
    found = finders.find("catalog/demo/img/items-list.png")
    assert found and found.endswith("apps/demo/docs/img/items-list.png")
    assert finders.find("catalog/demo/WORKBOOK.md") is None
