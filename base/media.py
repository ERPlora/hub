"""``/p/media/<hub>/<name>``: the files of the hub file store (``storages["hub_files"]``, ``base.storage``).

The bucket stays private and the Hub serves what it keeps, from each hub's own host: the images of its public
website first (round 2026-10-21), the documents of other modules later (PLAN-HUB block 7). ``<hub>`` is the hub's id
in hex, the one of its prefix (``hub-<hex>/``), and it must be the host's hub (``request.hub``, the host gate): one hub
never serves another's files. ``<name>`` is the key under that prefix; one that could leave it (``..``, ``.``, an
empty segment, a leading ``/``, a backslash) or is longer than :data:`MAX_NAME_LENGTH` is not found, and so is one
outside :data:`PUBLIC_FOLDERS`, the folders a module publishes: the store also keeps the modules' private documents,
which are never served here. A name that is a folder on disk (local development) is not found either.

No session and no permission: a visitor of the website sees its images, and the names are content hashes, written
once and never changed, so the answer is cached for a year (``immutable``) and sets no cookie. A file opened by its
URL on its own is sandboxed by its CSP (no script, no form), whatever it holds.
"""

import mimetypes

from django.core.files.storage import storages
from django.http import FileResponse, Http404, HttpRequest
from django.utils.csp import CSP
from django.views.decorators.http import require_safe

from base.storage import hub_prefix

#: The longest key under a hub's prefix the Hub serves.
MAX_NAME_LENGTH = 200
#: The folders under a hub's prefix whose files anyone may see: a module that publishes files adds its own.
PUBLIC_FOLDERS = ("website/img/",)
#: The people's photos («My profile», APP-BASE-3): served only to a session of this hub, never cached by others.
AVATARS_FOLDER = "avatars/"
MEMBERS_FOLDERS = (AVATARS_FOLDER,)
#: What opening a name that is no file raises on disk: missing, a folder, under a file, or unreadable.
NO_FILE = (FileNotFoundError, IsADirectoryError, NotADirectoryError, PermissionError)
#: A content-hashed name never changes: a year, and no revalidation.
CACHE_CONTROL = "public, max-age=31536000, immutable"
#: A person's photo: only this browser keeps it.
MEMBERS_CACHE_CONTROL = "private, max-age=31536000, immutable"
#: The CSP of a file opened on its own: nothing runs, nothing loads, no form posts.
FILE_CSP = {"default-src": [CSP.NONE], "sandbox": True}


@require_safe
def media(request: HttpRequest, hub: str, name: str) -> FileResponse:
    own = getattr(request, "hub", None)
    members_only = name.startswith(MEMBERS_FOLDERS)
    if own is None or hub != own.id.hex or not _is_safe_name(name) or not name.startswith(PUBLIC_FOLDERS + MEMBERS_FOLDERS):
        raise Http404("No such file.")
    if members_only and not request.user.is_authenticated:
        raise Http404("No such file.")
    try:
        file = storages["hub_files"].open(f"{hub_prefix(own.id)}/{name}", "rb")
    except NO_FILE:
        raise Http404("No such file.") from None
    content_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
    response = FileResponse(file, content_type=content_type)
    response["Cache-Control"] = MEMBERS_CACHE_CONTROL if members_only else CACHE_CONTROL
    response._csp_config = FILE_CSP
    return response


def _is_safe_name(name: str) -> bool:
    """Whether ``name`` stays under its hub's prefix: relative, with no ``.``/``..``/empty segment, no ``\\``."""
    if not name or len(name) > MAX_NAME_LENGTH or "\\" in name or "\x00" in name:
        return False
    return all(segment not in ("", ".", "..") for segment in name.split("/"))
