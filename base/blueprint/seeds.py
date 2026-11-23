"""The catalogue: the seeds of ``base/seeds/<vertical>.<language>.json``, one per vertical and language."""

import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from base.blueprint.archive import PURPOSE_TEMPLATE, Bundle, _in_order, _rows, manifest
from base.catalog import template_apps

SEEDS_DIR = Path(__file__).resolve().parent.parent / "seeds"


@dataclass(frozen=True)
class Template:
    """A seed of the catalogue: one vertical in one language (``<vertical>.<language>``)."""

    key: str
    name: str
    description: str
    language: str
    country: str
    vertical: str
    version: str
    bundle: Bundle


@cache
def _seeds() -> tuple[Template, ...]:
    templates = []
    for path in sorted(SEEDS_DIR.glob("*.json")):
        seed = json.loads(path.read_text(encoding="utf-8"))
        key = path.stem
        if key != f"{seed['vertical']}.{seed['language']}":
            raise ValueError(f"The seed {path.name} must be named <vertical>.<language>.json.")
        bundle = Bundle(
            manifest=manifest(
                name=seed["name"],
                language=seed["language"],
                country=seed["country"],
                purpose=PURPOSE_TEMPLATE,
                created_at="",
                vertical=seed["vertical"],
                version=seed["version"],
                apps=template_apps(seed["vertical"]),
            ),
            data=_in_order({name: _rows(rows) for name, rows in seed["data"].items()}),
        )
        templates.append(
            Template(
                key=key,
                name=seed["name"],
                description=seed["description"],
                language=seed["language"],
                country=seed["country"],
                vertical=seed["vertical"],
                version=seed["version"],
                bundle=bundle,
            )
        )
    return tuple(templates)


def catalog() -> list[Template]:
    """Every seed of the catalogue, by key."""
    return list(_seeds())


def template(key: str) -> Template | None:
    """The seed ``key`` (``<vertical>.<language>``), or ``None``."""
    return next((seed for seed in _seeds() if seed.key == key), None)
