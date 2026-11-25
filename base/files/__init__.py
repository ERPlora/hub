"""The business's files.

What the Files screen keeps lives in the hub file store (``storages["hub_files"]``, ``base.storage``: S3 in AWS, the
disk locally) under the hub's prefix, in a folder of its own: ``hub-<hex>/files/<path>``. The modules keep theirs
beside it (``website/img/``, ``avatars/``) and the manager never shows nor touches them; nothing of it is public
(``/p/media/`` serves only the folders the apps declare, ``base.media``): a file is read through ``base.file.read``, with the
session and the permission of who asks.

A *name* is one segment (no ``/``, ``\\``, control character, lone dot, or the folder marker) of 255 UTF-8 bytes at
most; a *path* is a chain of names, ``""`` being the root. Both are checked before the store sees them, so no key
ever leaves its hub's folder (an S3 key folds ``..``). Object stores have no folders: an empty one is kept
by its marker (``<folder>/.keep``), and renaming or moving copies every key and then deletes the old ones. Writing
never overwrites in silence: an upload takes «name (1).ext» when «name.ext» is taken (Google Drive, Dropbox), and a
new folder, a rename or a move onto a taken name is refused. Programs (Gmail's blocked list) are never kept.

A listing reads the open folder alone (``Delimiter``); the tree of folders and what the files take come from the hub's
index, kept in the cache between operations (an upload adds its bytes, any other write forgets it), so a batch of
uploads and the listings after each walk the files once. What the apps keep is counted at every call: the space
stays exact for the plan's limit.

These functions take the store and the hub's id, and raise ``live`` errors in the language that is active: the
operations (``base.queries``, ``base.services``) give them the hub of the request and the plan's space. Two do not:
:func:`delete_hub.delete_hub_files`, which empties the whole prefix of a hub that is gone, for the worker that purges
it, and :func:`delete_hub.hubs_in_store`, the hubs whose prefix holds anything, for ``manage.py
delete_leftover_hub_files``.
"""

from . import (
    create as create,
    delete as delete,
    delete_hub as delete_hub,
    index as index,
    listing as listing,
    names as names,
    read as read,
    relocate as relocate,
    space as space,
    store as store,
)
