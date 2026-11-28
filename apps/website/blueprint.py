"""What of Website travels in an export of the business (BASE-F35): the page as it is being edited (its template, its
colours and what each section says), read with Website's own read and written with its own save, so that it arrives as
a draft the owner reviews and publishes. Its images travel inside the file as WebP (``base.blueprint.photos.carried``),
each named ``website/img/<its id>.webp``, and are uploaded again into the business that loads it; the categories of its
catalog travel by their name. What visitors see and what Google said of the reviews stay: the page arrives unpublished
and Google is asked again.

A business that never saved its page has none of its own: nothing of it travels or counts. A page the business saved is
its own: a file never overwrites it. The page stays when a load is undone or the app is reset, like the rest of the
business's settings."""

import base64
import copy
import uuid
from collections.abc import Callable

from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import OperationError
from pydantic import ValidationError

from apps.website.choices import SECTION_LABELS
from apps.website.queries.catalog import SOURCES
from apps.website.queries.editor import IMAGE_FIELDS
from base.blueprint.calls import Dataset, Loaded, attempt, call, listed, natural_key, reason, text_of
from base.blueprint.datasets import CATEGORY_MISSING
from base.blueprint.photos import PHOTO_MISSING
from base.images import carried

FOLDER = "website/img/"
#: What a load made: the business's one site, which no id names and nothing removes.
SITE = "site"
LABEL = _("Design, texts and images")

#: What happens to an image the content names, with its section: what takes its place, or ``None`` to leave it out.
Change = Callable[[str, dict], dict | None]


def _each_image(content: dict, change: Change) -> None:
    for section, field in IMAGE_FIELDS:
        part = content.get(section)
        if isinstance(part, dict) and isinstance(part.get(field), dict):
            part[field] = change(section, part[field])
    gallery = content.get("gallery")
    if isinstance(gallery, dict):
        changed = (change("gallery", ref) for ref in listed(gallery, "images", dict))
        gallery["images"] = [ref for ref in changed if ref is not None]


def _files(content: dict) -> list[str]:
    """The name in the file of each image ``content`` names."""
    found = []

    def note(_section: str, ref: dict) -> dict:
        found.append(text_of(ref, "file"))
        return ref

    _each_image(content, note)
    return found


def _saved_site(ctx: OperationContext):
    """The business's page, or ``None`` while nobody saved it (the empty one every business is born with)."""
    site = call(ctx, "website.site.get")
    return site if site.updated_at is not None else None


def _categories(ctx: OperationContext, source: object) -> list:
    return call(ctx, "website.catalog.categories", source=source).categories if source in SOURCES else []


def _as_file(_section: str, ref: dict) -> dict:
    return {"file": f"{FOLDER}{uuid.UUID(ref['id']).hex}.webp", "name": ref["name"]}


def _site_rows(ctx: OperationContext) -> list[dict]:
    site = _saved_site(ctx)
    if site is None:
        return []
    content = site.content.model_dump(mode="json")
    _each_image(content, _as_file)
    catalog = content["catalog"]
    names = {str(row.id): row.name for row in _categories(ctx, catalog["source"])}
    catalog["categories"] = [names[pk] for pk in catalog.pop("category_ids") if pk in names]
    return [{"template": site.template, "theme": site.theme.model_dump(mode="json"), "content": content}]


def _carried_file(ctx: OperationContext, name: str) -> bytes | None:
    """The image ``name`` as the file carries it; one the store no longer has stays out, and its load says so."""
    try:
        image = call(ctx, "website.image.download", id=uuid.UUID(name.removeprefix(FOLDER).removesuffix(".webp")))
    except OperationError:
        return None
    return carried(base64.b64decode(image.data_base64))


def _site_media(ctx: OperationContext, rows: list[dict]) -> dict[str, bytes]:
    names = dict.fromkeys(name for row in rows for name in _files(row["content"]))
    files = {name: _carried_file(ctx, name) for name in names}
    return {name: content for name, content in files.items() if content is not None}


def _uploader(ctx: OperationContext, loaded: Loaded) -> Change:
    """Upload into the business, once, each image the file carries, as the image the content names; one the file does
    not carry, or the business refuses, is left out and told once."""
    uploaded: dict[str, str | None] = {}

    def upload(section: str, ref: dict) -> dict | None:
        name = text_of(ref, "file")
        if name not in uploaded:
            label = " · ".join(part for part in (str(SECTION_LABELS[section]), text_of(ref, "name")) if part)
            uploaded[name] = _upload(ctx, loaded, name, text_of(ref, "name"), label)
        return {"id": uploaded[name]} if uploaded[name] else None

    return upload


def _upload(ctx: OperationContext, loaded: Loaded, name: str, filename: str, label: str) -> str | None:
    if name not in loaded.media:
        loaded.warn(str(PHOTO_MISSING) % {"row": label})
        return None
    data = base64.b64encode(loaded.media[name]).decode("ascii")
    image = attempt(ctx, loaded, label, "website.image.upload", filename=filename or name.rpartition("/")[2],
                    content_type="image/webp", data_base64=data)  # fmt: skip
    return str(image.id) if image is not None else None


def _with_category_ids(ctx: OperationContext, loaded: Loaded, content: dict) -> None:
    """The categories the catalog names, as the ids of the business that loads it; one it does not have is left out and
    told."""
    catalog = content.get("catalog")
    if not isinstance(catalog, dict):
        return
    names = listed(catalog, "categories", str)
    catalog.pop("categories", None)
    ids = {natural_key(row.name): str(row.id) for row in _categories(ctx, catalog.get("source"))} if names else {}
    catalog["category_ids"] = [ids[natural_key(name)] for name in names if natural_key(name) in ids]
    for name in names:
        if natural_key(name) not in ids:
            loaded.warn(str(CATEGORY_MISSING) % {"row": str(SECTION_LABELS["catalog"]), "category": name})


def _site_load(ctx: OperationContext, rows: list[dict], loaded: Loaded) -> None:
    if not rows:
        return
    if _saved_site(ctx) is not None:
        loaded.already += len(rows)
        return
    row = copy.deepcopy(rows[0])
    content = row["content"] if isinstance(row.get("content"), dict) else {}
    _each_image(content, _uploader(ctx, loaded))
    _with_category_ids(ctx, loaded, content)
    try:
        call(ctx, "website.site.save", template=row.get("template"), theme=row.get("theme") or {}, content=content)
    except (OperationError, ValidationError) as exc:
        loaded.refuse(str(LABEL), reason(exc))
        return
    loaded.created.append(SITE)


DATASETS = [
    Dataset(
        key="website.site",
        label=LABEL,
        rows=_site_rows,
        count=lambda ctx: int(_saved_site(ctx) is not None),
        load=_site_load,
        media=_site_media,
        models=("Site", "Image"),
    ),
]
