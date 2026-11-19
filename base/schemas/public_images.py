"""What an upload of an image anyone sees on the business's own pages takes (``base.public_images``)."""

from typing import Annotated, Literal

from ninja import Field, Schema
from pydantic import ConfigDict, StringConstraints

ImageType = Literal["image/jpeg", "image/png", "image/webp"]


class ImageUploadIn(Schema):
    model_config = ConfigDict(extra="forbid")

    filename: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    content_type: ImageType = Field(description="image/jpeg, image/png or image/webp.")
    # 5 MB of bytes is 6 990 508 characters of base64.
    data_base64: str = Field(max_length=7_000_000, description="The file, in base64 (5 MB at most).")
