"""Input and output schemas of the website app (OpenAPI, 422 per field).

The content of a site is a closed set of fixed sections (``SECTIONS``), the same for the four templates: changing
the template changes one field and never the content. ``topbar`` (with its «Log in»), ``hero`` and ``footer`` are
always on the page and cannot hide; the other four carry ``hidden``. Every text is bounded, every link is ``https://``
and an image is the id of an upload, whose URL the server writes (``services.save_site``): nothing the owner types
becomes HTML, a script or a link of another scheme.
"""

from datetime import datetime
from typing import Annotated, Literal
from urllib.parse import urlsplit
from uuid import UUID

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from django.utils.translation import gettext_lazy as _
from ninja import Field, Schema
from pydantic import AfterValidator, ConfigDict, StringConstraints, field_validator, model_validator

from apps.website.palettes import own_colours


#: The fixed sections, in the order every template paints them.
SECTIONS = ("topbar", "hero", "about", "catalog", "contact", "location", "footer")
#: The templates, the id the owner picks (``templates/website/templates/<id>.html``).
TEMPLATES = ("classic", "modern", "minimal", "bold")
#: The palettes (``palettes.json``) in the editor's order; the owner may change any one's two colours.
PALETTE_IDS = ("ocean", "forest", "terracotta", "slate", "rose", "sand", "midnight", "olive")
#: The page's colour mode: light, dark, or auto (the visitor's device decides; ``frontend/website.ts``).
MODES = ("light", "dark", "auto")
#: Where the catalog comes from: the products of Inventory or the services of Services.
CATALOG_SOURCES = ("inventory", "service")
#: The days of the opening hours, Monday first.
DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
#: The image types the website takes (Pillow checks the bytes are one of them).
IMAGE_TYPES = ("image/jpeg", "image/png", "image/webp")
#: The largest image, in bytes (before base64).
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_CATEGORIES = 50

Template = Literal["classic", "modern", "minimal", "bold"]
PaletteId = Literal["ocean", "forest", "terracotta", "slate", "rose", "sand", "midnight", "olive"]
Mode = Literal["light", "dark", "auto"]
CatalogSource = Literal["inventory", "service"]
Day = Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
ImageType = Literal["image/jpeg", "image/png", "image/webp"]
PriceKind = Literal["fixed", "from", "hourly", "free", "none"]

NOT_HTTPS = _("Enter a link that starts with https://.")
NOT_A_PHONE = _("Enter a phone number: digits, spaces and an optional + in front.")
NOT_AN_EMAIL = _("Enter a valid email address.")
SAME_TIMES = _("The opening and the closing time cannot be the same.")
DAY_TWICE = _("Each day can only appear once.")


def _text(max_length: int):
    return Annotated[str, StringConstraints(strip_whitespace=True, max_length=max_length)]


def _https(value: str) -> str:
    """``value`` when it is an ``https://`` link with a host and nothing that could break out of an attribute."""
    if not value:
        return value
    parts = urlsplit(value)
    if (
        parts.scheme != "https"
        or not parts.netloc
        or any(char.isspace() or char in "\"'<>`\\" for char in value)
    ):
        raise ValueError(str(NOT_HTTPS))
    return value


def _phone(value: str) -> str:
    """``value`` when it is 6 to 15 digits with spaces, dashes or brackets, and a ``+`` only in front."""
    if not value:
        return value
    digits = sum(char.isdigit() for char in value)
    allowed = all(char.isdigit() or char in " +-()" for char in value)
    if not allowed or not 6 <= digits <= 15 or "+" in value[1:]:
        raise ValueError(str(NOT_A_PHONE))
    return value


def _email(value: str) -> str:
    if value:
        try:
            validate_email(value)
        except DjangoValidationError:
            raise ValueError(str(NOT_AN_EMAIL)) from None
    return value


Text80 = _text(80)
Text120 = _text(120)
Text160 = _text(160)
Text200 = _text(200)
HttpsUrl = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500), AfterValidator(_https)]
Phone = Annotated[str, StringConstraints(strip_whitespace=True, max_length=24), AfterValidator(_phone)]
Email = Annotated[str, StringConstraints(strip_whitespace=True, max_length=254), AfterValidator(_email)]
HexColor = Annotated[str, StringConstraints(strip_whitespace=True, to_lower=True, pattern=r"^#[0-9a-fA-F]{6}$")]
Clock = Annotated[str, StringConstraints(pattern=r"^([01][0-9]|2[0-3]):[0-5][0-9]$")]


class Strict(Schema):
    """A part of the content: nothing beyond its fields."""

    model_config = ConfigDict(extra="forbid")


# The content


class ImageRef(Strict):
    """An uploaded image (``website.image.upload``): its id; the server writes its URL on every save."""

    id: UUID = Field(description="The image's id, as website.image.upload answered it.")
    url: str = Field("", max_length=300, description="Where the Hub serves it; written by the server.")


class CustomColours(Strict):
    """The owner's two colours over the chosen palette's; the page, the bands and the text are derived from them
    (``palettes``)."""

    primary: HexColor = Field(description="The main colour (#rrggbb): buttons, links and the bold header.")
    accent: HexColor = Field(description="The second colour (#rrggbb): prices and details.")


class Theme(Strict):
    palette: PaletteId = Field(
        "ocean",
        description="One of the curated palettes (ocean, forest, terracotta, slate, rose, sand, midnight, olive), "
        "each with a light and a dark version.",
    )
    custom: CustomColours | None = Field(
        None,
        description="The owner's main and second colour over the palette's own; null = the palette's colours "
        "(«Reset colours»). The palette's own pair is stored as null.",
    )
    mode: Mode = Field("auto", description="light, dark, or auto: the visitor's device decides.")

    @model_validator(mode="after")
    def _own_colours_are_no_override(self) -> "Theme":
        if self.custom is not None and self.custom.model_dump() == own_colours(self.palette):
            self.custom = None
        return self


class TopbarSection(Strict):
    """Always on the page: the logo, the business's name and «Log in» (to /auth/login)."""

    name: Text80 = Field("", description="The business's name, as the page shows it.")
    logo: ImageRef | None = Field(None, description="The logo.")


class HeroSection(Strict):
    """Always on the page: the big title under the top bar."""

    title: Text80 = Field("", description="The page's big title.")
    tagline: Text160 = Field("", description="A line under the title.")
    cover: ImageRef | None = Field(None, description="The cover photo.")


class AboutSection(Strict):
    hidden: bool = Field(False, description="True: not on the page.")
    title: Text80 = Field("", description="The section's heading; empty = «About us».")
    text: Annotated[str, StringConstraints(strip_whitespace=True, max_length=4000)] = Field(
        "", description="A few words about the business, in Markdown (no HTML)."
    )
    image: ImageRef | None = Field(None, description="A photo beside the text.")


class CatalogSection(Strict):
    hidden: bool = Field(False, description="True: not on the page.")
    title: Text80 = Field("", description="The section's heading; empty = «Our products» or «Our services».")
    source: CatalogSource | None = Field(
        None, description="inventory (the products on sale) or service (the offered services); none = no catalog."
    )
    category_ids: list[UUID] = Field(
        default_factory=list,
        max_length=MAX_CATEGORIES,
        description="Only these categories of the source; empty = every category.",
    )
    show_prices: bool = Field(True, description="Whether the page shows the prices.")


class Socials(Strict):
    instagram: HttpsUrl = Field("", description="The Instagram profile (https://…).")
    facebook: HttpsUrl = Field("", description="The Facebook page (https://…).")
    tiktok: HttpsUrl = Field("", description="The TikTok profile (https://…).")
    x: HttpsUrl = Field("", description="The X profile (https://…).")


class Interval(Strict):
    opens: Clock = Field(description="HH:MM.")
    closes: Clock = Field(description="HH:MM; earlier than opens = after midnight.")

    @model_validator(mode="after")
    def _not_empty(self) -> "Interval":
        if self.opens == self.closes:
            raise ValueError(str(SAME_TIMES))
        return self


class DayHours(Strict):
    day: Day = Field(description="mon … sun.")
    intervals: list[Interval] = Field(default_factory=list, max_length=3, description="Empty = closed that day.")


class ContactSection(Strict):
    hidden: bool = Field(False, description="True: not on the page.")
    title: Text80 = Field("", description="The section's heading; empty = «Contact».")
    phone: Phone = Field("", description="Phone number.")
    whatsapp: Phone = Field("", description="WhatsApp number, with its country code.")
    email: Email = Field("", description="Email address.")
    socials: Socials = Field(default_factory=Socials, description="Social profiles.")
    hours: list[DayHours] = Field(
        default_factory=list, max_length=7, description="Opening hours, one row per day; empty = not shown."
    )

    @field_validator("hours")
    @classmethod
    def _one_row_per_day(cls, hours: list[DayHours]) -> list[DayHours]:
        days = [row.day for row in hours]
        if len(days) != len(set(days)):
            raise ValueError(str(DAY_TWICE))
        return sorted(hours, key=lambda row: DAYS.index(row.day))


class LocationSection(Strict):
    hidden: bool = Field(False, description="True: not on the page.")
    title: Text80 = Field("", description="The section's heading; empty = «Find us».")
    address_lines: list[Text120] = Field(default_factory=list, max_length=4, description="The address, line by line.")
    map_url: HttpsUrl = Field("", description="A map link (https://…), opened in a new tab.")


class FooterSection(Strict):
    """Always on the page: the name, this text and «Log in»."""

    text: Text200 = Field("", description="A short line at the bottom (e.g. the legal name).")


class Content(Strict):
    topbar: TopbarSection = Field(
        default_factory=TopbarSection, description="The bar on top: the business's name and logo (always shown)."
    )
    hero: HeroSection = Field(
        default_factory=HeroSection, description="The header: the big title, a tagline and a cover photo (always shown)."
    )
    about: AboutSection = Field(default_factory=AboutSection, description="About us: a few words and a photo.")
    catalog: CatalogSection = Field(
        default_factory=CatalogSection, description="The products or services the page lists, with their prices."
    )
    contact: ContactSection = Field(
        default_factory=ContactSection, description="Phone, WhatsApp, email, social profiles and opening hours."
    )
    location: LocationSection = Field(default_factory=LocationSection, description="The address and a map link.")
    footer: FooterSection = Field(default_factory=FooterSection, description="The line at the bottom (always shown).")


# The catalog, as the page paints it


class CatalogItemOut(Schema):
    name: str
    price: int | None = Field(description="In cents; none = no price shown.")
    price_kind: PriceKind = Field(description="fixed, from, hourly, free or none.")
    minutes: int | None = Field(None, description="A service's duration.")
    price_label: str = Field("", description="The price as the page prints it, in the visitor's language.")


class CatalogGroupOut(Schema):
    name: str = Field(description="The category; empty = items without one.")
    items: list[CatalogItemOut]


class CatalogOut(Schema):
    source: CatalogSource | None
    show_prices: bool
    groups: list[CatalogGroupOut]


# Inputs


class NoIn(Schema):
    pass


class SaveIn(Strict):
    template: Template = Field(description="classic, modern, minimal or bold.")
    theme: Theme = Field(default_factory=Theme, description="The page's colours (a palette) and its mode.")
    content: Content = Field(default_factory=Content, description="What each section says; the same in any template.")


class ImageUploadIn(Strict):
    filename: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    content_type: ImageType = Field(description="image/jpeg, image/png or image/webp.")
    # 5 MB of bytes is 6 990 508 characters of base64.
    data_base64: str = Field(max_length=7_000_000, description="The file, in base64 (5 MB at most).")


class CategoriesIn(Schema):
    source: CatalogSource = Field(description="inventory or service.")


class QrIn(Schema):
    format: Literal["png", "svg"] = Field("png", description="png (to print) or svg (to scale).")


# Outputs


class SiteOut(Schema):
    template: Template
    theme: Theme
    content: Content
    published_version: int = Field(description="0 = never published.")
    published_at: datetime | None
    is_live: bool = Field(description="True: visitors see the published version on the hub's address.")
    has_changes: bool = Field(description="True: the draft differs from what is published.")
    updated_at: datetime | None
    public_url: str = Field(description="The hub's public address, where the site is.")


class CategoryOut(Schema):
    id: UUID
    name: str


class CategoriesOut(Schema):
    categories: list[CategoryOut] = Field(description="The source's categories, in their order.")


class PreviewOut(Schema):
    html: str = Field(description="The draft, rendered as visitors would see it.")


class PublicationOut(Schema):
    published_version: int
    published_at: datetime | None
    is_live: bool


class ImageOut(Schema):
    id: UUID
    url: str
    content_type: ImageType
    width: int
    height: int
    size: int


class QrOut(Schema):
    format: Literal["png", "svg"]
    url: str = Field(description="The address the QR opens.")
    content_type: str
    filename: str
    content_base64: str


class PublicSiteOut(Schema):
    version: int
    published_at: datetime | None
    template: Template
    theme: Theme
    content: Content = Field(description="What visitors see; a hidden section comes empty.")
