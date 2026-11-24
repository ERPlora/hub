"""Schemas of the business's files (``base.file.*``)."""

import datetime as dt
from typing import Any, Literal

from django.utils.translation import gettext_noop
from ninja import Schema
from pydantic import Field

from base.schemas.assistant import AN_ATTACHED_FILE


# ── Files ──────────────────────────────────────────────────────────────────────────────────────────────────────

#: How the Files screen shows a file: «image», «pdf», «text», «table» (CSV, TSV), «json», «audio», «video», or «»
#: when it does not (it is downloaded).
FilePreview = Literal["image", "pdf", "text", "table", "json", "audio", "video", ""]


def file_path(title: str | None = None) -> Any:
    """A path under the business's files: names joined by «/» («Facturas/2026/marzo.pdf»); empty is the root.
    ``title`` names it on the assistant's card."""
    return Field(
        default="",
        max_length=1000,
        title=title,
        description="A path in the business's files, «Facturas/2026»; empty: the root.",
    )


FILE_PATH = file_path()
#: An upload in base64: 25 MB of file is 34 952 536 characters.
FILE_UPLOAD_BASE64_MAX = 34_952_536


class FileListIn(Schema):
    folder: str = FILE_PATH


class FileFolderOut(Schema):
    path: str
    name: str
    children: list["FileFolderOut"]


FileFolderOut.model_rebuild()


class FileCrumbOut(Schema):
    path: str
    name: str


class FileItemOut(Schema):
    path: str
    name: str
    size: int = Field(description="Bytes.")
    modified: dt.datetime | None
    #: The type the file is read with at ``base.file.read``.
    content_type: str
    preview: FilePreview


class FileSpaceOut(Schema):
    #: What the hub's files and its apps' take in the store.
    used_bytes: int
    #: The space the plan includes (the SaaS's photo); ``None``: no limit.
    limit_bytes: int | None


class FileCanOut(Schema):
    #: Upload, make folders and rename (``base.upload_files``).
    upload: bool
    #: Delete; moving takes both (``base.delete_files``).
    delete: bool


class FileListOut(Schema):
    """``base.file.list``: every folder of the business (a tree), and the files of the folder open."""

    folder: str
    #: From the root to the open folder, the root itself left out.
    crumbs: list[FileCrumbOut]
    folders: list[FileFolderOut]
    files: list[FileItemOut]
    space: FileSpaceOut
    can: FileCanOut


class FileReadIn(Schema):
    path: str = Field(max_length=1000, description="The file's path, «Facturas/marzo.pdf».")
    #: Shown in the page (``inline``) rather than downloaded, when its type is safe to show.
    inline: bool = False


class FileOut(Schema):
    path: str
    name: str
    size: int
    content_type: str
    preview: FilePreview


class FileUploadIn(Schema):
    folder: str = file_path(gettext_noop("Folder"))
    name: str = Field(max_length=1000, description="The file's name, «marzo.pdf»; a taken one becomes «marzo (1).pdf».")
    content_base64: str = Field(
        max_length=FILE_UPLOAD_BASE64_MAX,
        title=gettext_noop("File"),
        description="The file in base64, 25 MB at most; from the chat, the name of the one the person attached.",
        json_schema_extra=AN_ATTACHED_FILE,
    )


class FileSavedOut(Schema):
    path: str
    #: The name it was kept with: the one asked for, or «name (1).ext» when that was taken.
    name: str
    size: int


class FileFolderCreateIn(Schema):
    parent: str = file_path(gettext_noop("In folder"))
    name: str = Field(max_length=1000, description="The new folder's name, «Facturas»; 100 characters at most.")


class FilePathOut(Schema):
    path: str
    name: str


class FileRenameIn(Schema):
    path: str = Field(
        max_length=1000,
        title=gettext_noop("File or folder"),
        description="The file or folder to rename, «Facturas/marzo.pdf».",
    )
    name: str = Field(max_length=1000, description="Its new name (a name, never a path), «abril.pdf».")


class FileMoveIn(Schema):
    path: str = Field(
        max_length=1000, title=gettext_noop("File or folder"), description="The file or folder to move, «marzo.pdf»."
    )
    to: str = file_path(gettext_noop("Move to"))


class FileDeleteIn(Schema):
    path: str = Field(
        max_length=1000,
        title=gettext_noop("File or folder"),
        description="The file or folder to delete, «Facturas/marzo.pdf».",
    )


class FileDeletedOut(Schema):
    path: str
    #: Whether it was a folder, deleted with everything in it.
    folder: bool

