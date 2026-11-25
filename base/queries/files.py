"""The business's files in the hub file store (``base.file.*``) and the plan's space for them."""

from django.core.files.storage import Storage, storages
from django.utils import translation
from live.context import OperationContext
from live.operations import AI, operation

from base import files
from base.models import Hub
from base.operations import hub_id
from base.schemas.files import FileListIn, FileListOut, FileOut, FileReadIn


# ── Files ──────────────────────────────────────────────────────────────────────────────────────────────────────
# The business's files in the hub file store (``base.files``), on the hub of the request only. Everyone of the hub
# sees and opens them.
VIEW_FILES = "base.view_files"
UPLOAD_FILES = "base.upload_files"
DELETE_FILES = "base.delete_files"


def space_limit(ctx: OperationContext) -> int | None:
    """The space for files of the plan in the SaaS's last photo of the hub of ``ctx``; ``None``: no limit."""
    return files.space.space_limit(Hub.objects.filter(slug=ctx.scope.key).values_list("state", flat=True).first())


def refuse_past_the_plans_space(ctx: OperationContext, store: Storage, size: int) -> None:
    """Files' 409 ``base.file_no_space`` (``base.files.space.refuse_past_the_space``) when ``size`` more bytes go past the
    space the plan of ``ctx``'s hub includes, said in the caller's language (an API key's or the assistant's call has
    no request). For the apps that keep a file in the hub file store: it takes the plan's space as Files does."""
    with translation.override(ctx.language):
        files.space.refuse_past_the_space(store, hub_id(ctx.scope), size, limit_bytes=space_limit(ctx))


@operation(
    "base.file.list",
    kind="query",
    permission=VIEW_FILES,
    input=FileListIn,
    output=FileListOut,
    expose_api=True,
    ai=AI(
        description=(
            "Lists the business's files: every folder, and the files of one folder by its path (the folder "
            "«Facturas/2026»; empty: the top), each with its name, size and date, and the space they take against what "
            "the plan includes."
        ),
        asks={
            "en": ("show me our files", "how much storage are we using?", "what's in the Contracts folder?"),
            "es": ("enséñame los archivos del negocio", "¿cuánto espacio llevamos ocupado?"),
        },
    ),
)
def file_list(ctx: OperationContext, data: FileListIn) -> dict:
    """The tree, the folder's files, the space used and what this person may do with them."""
    with translation.override(ctx.language):
        listing = files.listing.listing(storages["hub_files"], hub_id(ctx.scope), data.folder)
    used = listing.pop("used_bytes")
    return {
        **listing,
        "space": {"used_bytes": used, "limit_bytes": space_limit(ctx)},
        "can": {"upload": ctx.has(UPLOAD_FILES), "delete": ctx.has(DELETE_FILES)},
    }


@operation(
    "base.file.read",
    kind="query",
    permission=VIEW_FILES,
    input=FileReadIn,
    output=FileOut,
    expose_api=True,
    ai=AI(
        description=(
            "Finds one file of the business by its path (the file «Facturas/marzo.pdf»): its name, size and type. Its "
            "bytes are read at the same address by whoever may see the files."
        ),
        asks={
            "en": (
                "find the file Invoices/march.pdf",
                "how big is the contract PDF?",
                "what kind of document is the quote, and how much space does it take?",
            ),
            "es": (
                "búscame el archivo Facturas/marzo.pdf",
                "¿cuánto pesa ese archivo?",
                "¿de qué tipo es el documento del presupuesto y cuánto ocupa?",
            ),
        },
    ),
)
def file_read(ctx: OperationContext, data: FileReadIn) -> dict:
    """The file, described; ``base.api`` streams its bytes to the person who asked."""
    with translation.override(ctx.language):
        return files.read.describe(storages["hub_files"], hub_id(ctx.scope), data.path)
