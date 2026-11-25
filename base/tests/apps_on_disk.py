"""Modules of ``apps/`` on disk for the catalog's tests: a WORKBOOK and its translation, the compiled
Spanish catalogue, images under ``docs/img/`` and symbolic links out of the module."""

import array
import struct
from pathlib import Path
from types import SimpleNamespace

import pytest
from live.meta import Category

from base.catalog.app_registry import build_registry
from base.catalog.errors import RegistryError
from base.workbook_sections import mark, marked, sections

CUT = "## Para quien lo mantiene"
WORKBOOK = f"""\
# Workbook — Things (app)
Prefijo: THING
Alcance MVP: núcleo
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
#: The same part before a change of its first section.
OLD_PART = USER_PART.replace("cosas", "objetos")
#: The translation of ``USER_PART``, without its marks.
ENGLISH = """\
## What it is for

Keeps **things**. See [how to use it](#how-to-use-it).

![List of things](docs/img/list.png)

## How to use it

### Step by step
Status: done
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
#: A line that looks like a fence inside a block and closes nothing: of the other character, shorter, or with an info string.
NOT_CLOSING = {"other-character": ("```", "~~~"), "shorter": ("````", "```"), "info-string": ("```", "```text")}
# The «<!-- origen: … -->» and «<!-- código: … -->» of a WORKBOOK tie it to MIGRATION.md and to its
# sources, never reaching shared.app_doc nor the assistant.
ORIGIN = "<!-- origen: old-hub:HUB-F212 gh:sales#131 -->"
# (the link, where it points (relative to tmp_path unless it starts with ".."), the static path through it)
SYMLINKS = [
    ("docs/img/x.png", "../../../config/settings.py", "catalog/things/img/x.png"),
    ("docs/img/sub", "outside", "catalog/things/img/sub/a.png"),
    ("docs/img/gone.png", "nowhere.png", "catalog/things/img/gone.png"),
    ("docs/img", "outside", "catalog/things/img/a.png"),
    ("docs", "outside", "catalog/things/img/a.png"),
]


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


def translated(source: str, body: str = ENGLISH) -> str:
    """A ``WORKBOOK.en.md`` generated from ``source`` (the Spanish user part), which has the headings of ``body``."""
    text = marked(source, body)
    assert text is not None
    return text


def problems(configs, icons=ICONS) -> list[str]:
    with pytest.raises(RegistryError) as raised:
        build_registry(configs, icons=icons)
    return raised.value.problems


def by_hand(*headings: str, file: str = "WORKBOOK.en.md") -> str:
    """What to do with the stale translation ``file``, behind in the sections of ``USER_PART`` with these ``headings``."""
    marks = {section.partition("\n")[0]: mark(section) for section in sections(USER_PART)}
    return (
        f"translate by hand into {file} each section of WORKBOOK.md that changed, with its mark on the line under its "
        f"heading (the same headings, in the same order): {'; '.join(f'{title} → {marks[title]}' for title in headings)}"
    )


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


def linked_module(tmp_path, path, target):
    outside_files(tmp_path)
    config = module(tmp_path)
    link(config, path, target if target.startswith("..") else tmp_path / target)
    return config
