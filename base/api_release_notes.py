"""Ninja route of the release notes: it calls ``base.release_note.list`` and holds no logic. ``config/api.py`` mounts
it."""

from live.ninja import bind, run_operation
from ninja import Query, Router

from base.queries import release_notes
from base.schemas.release_notes import ReleaseNoteListIn

router = Router(tags=["base"])


@bind(router, "base.release_note.list", "/system/release-notes")
async def release_note_list(request, params: Query[ReleaseNoteListIn]):
    return await run_operation(request, release_notes.release_note_list, params)
