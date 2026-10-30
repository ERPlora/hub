"""``/p/media/<hub>/<name>``: the files of the hub file store (``storages["hub_files"]``, ``base.storage``).

The bucket stays private and the Hub serves what it keeps, from each hub's own host: the images of its public
website first (round 2026-10-21), the documents of other modules later (PLAN-HUB block 7). ``<hub>`` is the hub's id
in hex, the one of its prefix (``hub-<hex>/``), and it must be the host's hub (``request.hub``, the host gate): one hub
never serves another's files. ``<name>`` is the key under that prefix; one that could leave it (``..``, ``.``, an
empty segment, a leading ``/``, a backslash) or is longer than :data:`MAX_NAME_LENGTH` is not found, and so is one
outside the folders served (:func:`served_folders`): the store also keeps the modules' private documents, which are
never served here. A name that is a folder on disk (local development) is not found either.

Each app says which folders of its own are served, in its ``LiveAppConfig`` (FIX-HUB-BASE-MEDIA-DOES-NOT-SERVE-
WHATSAPP-INBOX-SAMPLES): ``public_media``, whose files anyone sees (the website's images), and ``members_media``, whose
files only a session of this hub sees (a template's sample in the WhatsApp inbox); base's own are the people's photos
(:data:`AVATARS_FOLDER`, for the hub's sessions). A folder starts with the app's label and a ``/`` and never climbs out
of it, so no app opens another's files: what does not is never served and is said at start (``base.E010``). A visitor
asking for a members' file gets the 404 of a missing one, and an app the business turned off serves none of its own.

No permission: a visitor of the website sees its images, and the names are content hashes, written once and never
changed, so the answer is cached for a year (``immutable``; a members' file only in that browser) and sets no cookie.
A file opened by its URL on its own is sandboxed by its CSP (no script, no form), whatever it holds.
"""

import mimetypes
from dataclasses import dataclass

from django.core import checks
from django.core.files.storage import storages
from django.http import FileResponse, Http404, HttpRequest
from django.utils.csp import CSP
from django.views.decorators.http import require_safe
from live.context import Scope
from live.meta import all_live_app_configs

from base.activation import off_apps
from base.storage import hub_prefix

#: The longest key under a hub's prefix the Hub serves.
MAX_NAME_LENGTH = 200
#: The people's photos («My profile», APP-BASE-3): base's own folder, served only to a session of this hub.
AVATARS_FOLDER = "avatars/"
#: What an app declares in its ``LiveAppConfig``: the folders of its own whose files anyone may see…
PUBLIC_MEDIA = "public_media"
#: …and the ones only a session of this hub may see.
MEMBERS_MEDIA = "members_media"
#: What opening a name that is no file raises on disk: missing, a folder, under a file, or unreadable.
NO_FILE = (FileNotFoundError, IsADirectoryError, NotADirectoryError, PermissionError)
#: A content-hashed name never changes: a year, and no revalidation.
CACHE_CONTROL = "public, max-age=31536000, immutable"
#: A members' file (a person's photo): only this browser keeps it.
MEMBERS_CACHE_CONTROL = "private, max-age=31536000, immutable"
#: The CSP of a file opened on its own: nothing runs, nothing loads, no form posts.
FILE_CSP = {"default-src": [CSP.NONE], "sandbox": True}


@dataclass(frozen=True)
class Folder:
    """A folder under a hub's prefix that ``/p/media/`` serves, the app it is of, and whether only members see it."""

    prefix: str
    app: str
    members: bool


@require_safe
def media(request: HttpRequest, hub: str, name: str) -> FileResponse:
    own = getattr(request, "hub", None)
    if own is None or hub != own.id.hex or not _is_safe_name(name):
        raise Http404("No such file.")
    folder = next((folder for folder in served_folders() if name.startswith(folder.prefix)), None)
    if folder is None or (folder.members and not request.user.is_authenticated):
        raise Http404("No such file.")
    if folder.app != "base" and folder.app in off_apps(Scope("host", own.slug)):
        raise Http404("No such file.")
    try:
        file = storages["hub_files"].open(f"{hub_prefix(own.id)}/{name}", "rb")
    except NO_FILE:
        raise Http404("No such file.") from None
    content_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
    response = FileResponse(file, content_type=content_type)
    response["Cache-Control"] = MEMBERS_CACHE_CONTROL if folder.members else CACHE_CONTROL
    response._csp_config = FILE_CSP
    return response


def served_folders() -> list[Folder]:
    """Every folder served, the members' first (a members' folder inside a public one stays theirs): base's people's
    photos and the sound ones each installed app declares (what ``base.E010`` refuses is never served)."""
    folders = [Folder(AVATARS_FOLDER, "base", members=True)]
    for config in all_live_app_configs():
        for attribute, members in ((MEMBERS_MEDIA, True), (PUBLIC_MEDIA, False)):
            if _problems(config, attribute):
                continue
            folders += [Folder(prefix, config.label, members) for prefix in getattr(config, attribute, ())]
    return sorted(folders, key=lambda folder: not folder.members)


def _is_safe_name(name: str) -> bool:
    """Whether ``name`` stays under its hub's prefix: relative, with no ``.``/``..``/empty segment, no ``\\``."""
    if not name or len(name) > MAX_NAME_LENGTH or "\\" in name or "\x00" in name:
        return False
    return all(segment not in ("", ".", "..") for segment in name.split("/"))


@checks.register("base")
def check_media_folders(app_configs=None, **kwargs) -> list[checks.CheckMessage]:
    """``base.E010``: an app declares in ``public_media`` and ``members_media`` a list of folders of its own: each
    starts with its label and a ``/``, ends in ``/`` and never climbs out (no ``..``, ``.``, empty segment or ``\\``)."""
    return [
        checks.Error(
            problem,
            hint=f'An app serves only folders of its own: {PUBLIC_MEDIA} = ["<label>/<folder>/"] for anyone, '
            f'{MEMBERS_MEDIA} = ["<label>/<folder>/"] for the hub\'s sessions.',
            obj=config,
            id="base.E010",
        )
        for config in all_live_app_configs()
        for attribute in (PUBLIC_MEDIA, MEMBERS_MEDIA)
        for problem in _problems(config, attribute)
    ]


def _problems(config, attribute: str) -> list[str]:
    """What is wrong with the folders ``config`` declares in ``attribute`` (none declared: nothing)."""
    declared = getattr(config, attribute, ())
    if not isinstance(declared, list | tuple) or not all(isinstance(folder, str) for folder in declared):
        return [f"{config.label}.{attribute} is not a list of folders."]
    return [problem for folder in declared if (problem := _problem(config.label, attribute, folder))]


def _problem(label: str, attribute: str, folder: str) -> str | None:
    said = f"{label}.{attribute} names {folder!r}"
    if "\\" in folder or "\x00" in folder:
        return f"{said}, which climbs out of its folder."
    if not folder.startswith(f"{label}/"):
        return f"{said}, not under {label}/: an app serves only its own folders."
    if any(segment in ("", ".", "..") for segment in folder.split("/")[:-1]):
        return f"{said}, which climbs out of its folder."
    if not folder.endswith("/"):
        return f"{said}, which does not end in /."
    return None
