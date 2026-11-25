"""Routes of Files."""

from asgiref.sync import sync_to_async
from django.core.files.storage import storages
from live.ninja import bind, run_operation
from ninja import Query, Router
from ninja.decorators import decorate_view

from base import files, queries, services
from base.request_body import accept_body_up_to
from base.schemas.files import (
    FileDeleteIn,
    FileFolderCreateIn,
    FileListIn,
    FileMoveIn,
    FileReadIn,
    FileRenameIn,
    FileUploadIn,
)

router = Router()


#: An upload's body: 25 MB of file in base64 (34 952 536 characters) and its JSON around it.
MAX_FILE_BODY = 35_100_000


@bind(router, "base.file.list", "/files")
async def file_list(request, params: Query[FileListIn]):
    return await run_operation(request, queries.files.file_list, params)


@bind(
    router,
    "base.file.read",
    "/files/raw",
    openapi_extra={
        "responses": {
            200: {
                "description": "The file's bytes (an attachment unless `inline` and safe to show), or the operation's "
                "JSON when only JSON is accepted.",
                "content": {"application/octet-stream": {"schema": {"type": "string", "format": "binary"}}},
            }
        }
    },
)
async def file_read(request, params: Query[FileReadIn]):
    described = await run_operation(request, queries.files.file_read, params)
    if request.headers.get("Accept", "").strip() == "application/json":
        return described
    return await sync_to_async(files.read.file_response)(
        storages["hub_files"], request.hub.id, described.model_dump(), inline=params.inline
    )


@bind(router, "base.file.upload", "/files/upload")
@decorate_view(accept_body_up_to(MAX_FILE_BODY))
async def file_upload(request, data: FileUploadIn):
    return await run_operation(request, services.files.file_upload, data)


@bind(router, "base.file.create_folder", "/files/folder")
async def file_create_folder(request, data: FileFolderCreateIn):
    return await run_operation(request, services.files.file_create_folder, data)


@bind(router, "base.file.rename", "/files/rename")
async def file_rename(request, data: FileRenameIn):
    return await run_operation(request, services.files.file_rename, data)


@bind(router, "base.file.move", "/files/move")
async def file_move(request, data: FileMoveIn):
    return await run_operation(request, services.files.file_move, data)


@bind(router, "base.file.delete", "/files/delete")
async def file_delete(request, data: FileDeleteIn):
    return await run_operation(request, services.files.file_delete, data)
