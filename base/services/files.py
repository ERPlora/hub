"""Files (``base.file.*``).

The business's files in the hub file store (``base.files``), on the hub of the request only. Who runs the business
uploads, makes folders and renames (``base.upload_files``) and deletes (``base.delete_files``); moving takes
both, as it deletes where the file was and uploads where it goes. Each write records its event in its transaction;
the store is written first, so a refusal of the store leaves no event (a lost event leaves the file: the listing
reads the store, never the events).
"""

import base64
import binascii

from django.core.files.storage import storages
from django.utils import translation
from django.utils.translation import gettext
from live.context import OperationContext
from live.errors import InvalidPayload, PermissionDenied
from live.operations import AI, operation
from live.outbox import record_event

from base import events, files, queries
from base.operations import hub_id
from base.schemas import (
    FileDeletedOut,
    FileDeleteIn,
    FileFolderCreateIn,
    FileMoveIn,
    FilePathOut,
    FileRenameIn,
    FileSavedOut,
    FileUploadIn,
)

UPLOAD_FILES = "base.upload_files"
DELETE_FILES = "base.delete_files"


def _file_bytes(content_base64: str) -> bytes:
    try:
        return base64.b64decode(content_base64, validate=True)
    except (binascii.Error, ValueError):
        message = gettext("The file did not arrive whole. Upload it again.")
        raise InvalidPayload(message, code="base.file_not_base64", fields={"content_base64": message}) from None


@operation(
    "base.file.upload",
    kind="command",
    permission=UPLOAD_FILES,
    input=FileUploadIn,
    output=FileSavedOut,
    expose_api=True,
    ai=AI(
        description=(
            "Keeps a file the person attached in the business's files, in a folder by its path (the folder «Facturas»; "
            "empty: the top). Never overwrites: a taken name becomes «name (1).ext». 25 MB at most; programs are "
            "refused."
        ),
        asks={
            "en": ("upload the contract I attached", "keep this photo in our files", "save this PDF in our files"),
            "es": (
                "archiva el documento que te adjunto",
                "guarda este PDF en los archivos",
                "sube el archivo que te he adjuntado",
            ),
        },
    ),
)
def file_upload(ctx: OperationContext, data: FileUploadIn) -> dict:
    """Keep the file, numbered when its name is taken, within the plan's space."""
    with translation.override(ctx.language):
        content = _file_bytes(data.content_base64)
        saved = files.upload(
            storages["hub_files"],
            hub_id(ctx.scope),
            data.folder,
            data.name,
            content,
            limit_bytes=queries.files.space_limit(ctx),
        )
    record_event(ctx, events.FILE_UPLOADED, {"path": saved["path"]})
    return saved


@operation(
    "base.file.create_folder",
    kind="command",
    permission=UPLOAD_FILES,
    input=FileFolderCreateIn,
    output=FilePathOut,
    expose_api=True,
    ai=AI(
        description=(
            "Makes a new, empty folder in the business's files, inside another by its path (the folder «Facturas»; "
            "empty: the top). Refused when that name is taken there."
        ),
        asks={
            "en": ("make a folder called Invoices", "create a 2026 folder inside Contracts"),
            "es": ("hazme una carpeta 2026 dentro de Contratos", "crea una carpeta para los contratos"),
        },
    ),
)
def file_create_folder(ctx: OperationContext, data: FileFolderCreateIn) -> dict:
    """A new folder, never over a file or folder of that name."""
    with translation.override(ctx.language):
        made = files.create_folder(storages["hub_files"], hub_id(ctx.scope), data.parent, data.name)
    record_event(ctx, events.FILE_FOLDER_CREATED, {"path": made["path"]})
    return made


@operation(
    "base.file.rename",
    kind="command",
    permission=UPLOAD_FILES,
    input=FileRenameIn,
    output=FilePathOut,
    expose_api=True,
    ai=AI(
        description=(
            "Gives a file or a folder of the business's files another name, where it is (the file «Facturas/marzo.pdf» "
            "becomes «abril.pdf»). Refused when the new name is taken there."
        ),
        asks={
            "en": ("rename march.pdf to april.pdf", "call that folder Suppliers instead"),
            "es": ("renombra marzo.pdf como abril.pdf", "renombra la carpeta Viejos como «Archivo 2024»"),
        },
    ),
)
def file_rename(ctx: OperationContext, data: FileRenameIn) -> dict:
    """A new name in the same folder; a folder takes everything in it along."""
    with translation.override(ctx.language):
        renamed = files.rename(storages["hub_files"], hub_id(ctx.scope), data.path, data.name)
    if renamed["path"] != data.path:
        record_event(ctx, events.FILE_RENAMED, {"path": renamed["path"], "from": data.path})
    return renamed


@operation(
    "base.file.move",
    kind="command",
    permission=DELETE_FILES,
    input=FileMoveIn,
    output=FilePathOut,
    expose_api=True,
    ai=AI(
        description=(
            "Moves a file or a folder of the business's files into another folder, both by their path (the file "
            "«marzo.pdf» into the folder «Facturas»; empty: the top). Never overwrites, and a folder never goes inside "
            "itself."
        ),
        asks={
            "en": ("move march.pdf into Invoices", "put the contracts folder inside Legal"),
            "es": ("mueve marzo.pdf a la carpeta Facturas", "mete la carpeta de contratos dentro de Legal"),
        },
    ),
)
def file_move(ctx: OperationContext, data: FileMoveIn) -> dict:
    """To another folder; deleting where it was and uploading where it goes."""
    with translation.override(ctx.language):
        if not ctx.has(UPLOAD_FILES):
            raise PermissionDenied(gettext("Only who runs the business can change the files."))
        moved = files.move(storages["hub_files"], hub_id(ctx.scope), data.path, data.to)
    record_event(ctx, events.FILE_MOVED, {"path": moved["path"], "from": data.path})
    return moved


@operation(
    "base.file.delete",
    kind="command",
    permission=DELETE_FILES,
    input=FileDeleteIn,
    output=FileDeletedOut,
    expose_api=True,
    ai=AI(
        description=(
            "Deletes a file of the business's files, or a folder and everything in it, by its path (the folder "
            "«Facturas/2025»). There is no bin: it cannot be undone."
        ),
        risk="high",
        asks={
            "en": ("delete the old 2025 folder", "throw away march.pdf from our files"),
            "es": ("borra la carpeta de 2025", "elimina marzo.pdf de los archivos"),
        },
    ),
)
def file_delete(ctx: OperationContext, data: FileDeleteIn) -> dict:
    """The file, or the folder and everything in it; no bin."""
    with translation.override(ctx.language):
        deleted = files.delete(storages["hub_files"], hub_id(ctx.scope), data.path)
    record_event(ctx, events.FILE_DELETED, {"path": deleted["path"], "folder": deleted["folder"]})
    return deleted
