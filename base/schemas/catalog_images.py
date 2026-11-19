"""Schemas of the shared image library (``base.catalog_image.*``)."""

from typing import Annotated

from ninja import Schema
from pydantic import Field, StringConstraints


# ── The shared image library (base.image_catalog) ──────────────────────────────────────────────────────────────────

#: A folder of the library (``hospitality``, ``beauty_hair``…).
CatalogFolder = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]*$", max_length=63)]


class CatalogImageSearchIn(Schema):
    query: str = Field(
        "",
        max_length=100,
        description="What the image shows, as the product or the service is called, in Spanish or English "
        "(«café con leche», «women's haircut»); empty: the whole library by title.",
    )
    folder: CatalogFolder | None = Field(
        None,
        description="Only this folder of the library: beauty_body, beauty_hair, fitness, hospitality, retail or "
        "wellness_spa.",
    )
    limit: int = Field(60, ge=1, le=100, description="How many images to return (1 to 100).")
    offset: int = Field(0, ge=0, description="How many images to skip, to read the next pages.")


class CatalogImageRefIn(Schema):
    reference: str = Field(max_length=200, description="The image's reference: catalog:<folder>/<name>.")


class CatalogImageOut(Schema):
    reference: str = Field(description="What a product or a service keeps to show it: catalog:<folder>/<name>.")
    folder: str = Field(description="Its folder of the library.")
    name: str = Field(description="Its file's name in the folder, without the extension.")
    title: str = Field(description="What it shows, in the reader's language.")
    url: str = Field(description="Where the Hub serves it.")


class CatalogImagePage(Schema):
    rows: list[CatalogImageOut] = Field(description="The images of this page, the best match first.")
    total: int = Field(description="How many images match, across every page.")
    limit: int = Field(description="The page size asked for.")
    offset: int = Field(description="The images skipped before this page.")

