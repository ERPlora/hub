"""What an API key may do on an app: read, create, update and delete.

A key's permissions are ``{app | "*": [actions]}``, ``"*"`` being every app of the business, also the ones it adds
later. A published query is ``read``; a published command is what the verb that ends its name says, from a closed
table: a command whose verb is not in it opens to no key until its verb is put in one of the three
(``base/tests/test_api_actions.py`` fails on it). No ORM here: the door and the screen of the keys both use it.
"""

from collections.abc import Iterable

READ, CREATE, UPDATE, DELETE = "read", "create", "update", "delete"
ACTIONS = (READ, CREATE, UPDATE, DELETE)
#: Every app of the business, in a key's permissions.
EVERY_APP = "*"

#: Commands that make something new: a record, a line of a list, a file.
CREATE_VERBS = frozenset({"create", "add", "bulk_create", "upload", "create_folder"})
#: Commands that take something away for good.
DELETE_VERBS = frozenset({"delete", "remove", "bulk_delete", "erase"})
#: Commands that change what is already there: its fields, its state, a line of it, or that print or send it.
UPDATE_VERBS = frozenset(
    {
        "activate", "add_combo_line", "add_service_line", "adjust", "apply_voucher", "approve", "archive", "assign",
        "auto_close", "bump", "cancel", "charge", "claim", "cleanup_expired", "clear", "clock_in", "clock_out",
        "close", "complete", "confirm", "convert", "correct", "count", "deactivate", "end", "fail", "flag",
        "initiate", "link", "link_customer", "link_order", "mark_abandoned", "mark_completed", "mark_no_show",
        "mark_paid", "mark_read", "mark_sent", "materialize", "merge", "move", "no_show", "note_bill", "notify", "open",
        "park", "place", "print", "print_bill", "print_label", "publish", "ready", "recall", "receive", "redeem",
        "regenerate", "register", "release", "release_unconfirmed", "remove_voucher", "rename", "reorder", "reprint",
        "reschedule", "restore", "retire", "retry", "save", "seat", "send", "serve", "set", "set_active", "set_guests",
        "set_image", "set_rush", "set_sold_out", "set_status", "split", "start", "test", "transfer", "unpublish",
        "update", "upload_image", "upload_logo", "void", "write_off",
    }
)
_BY_VERB = {
    **dict.fromkeys(CREATE_VERBS, CREATE),
    **dict.fromkeys(UPDATE_VERBS, UPDATE),
    **dict.fromkeys(DELETE_VERBS, DELETE),
}


def action_of(op) -> str | None:
    """What ``op`` asks of a key: ``read`` for a query; for a command, its verb's action, or ``None`` if nobody has
    decided it yet."""
    if op.kind == "query":
        return READ
    return _BY_VERB.get(op.name.rsplit(".", 1)[-1])


def granted(scopes: object, app: str) -> frozenset[str]:
    """The actions ``scopes`` give on ``app``: those of every app and those of ``app`` itself."""
    if not isinstance(scopes, dict):
        return frozenset()
    return frozenset(_listed(scopes.get(EVERY_APP)) | _listed(scopes.get(app)))


def allows(scopes: object, app: str, action: str | None) -> bool:
    """Whether a key of ``scopes`` may do ``action`` on ``app``; an action nobody decided, never."""
    return action in granted(scopes, app)


def normalised(scopes: object) -> dict[str, list[str]]:
    """``scopes`` with each app's actions in their order and only actions; an app left with none is not there."""
    if not isinstance(scopes, dict):
        return {}
    kept = {app: [action for action in ACTIONS if action in _listed(given)] for app, given in scopes.items()}
    return {app: actions for app, actions in kept.items() if actions}


def _listed(actions: object) -> set[str]:
    return set(actions) if isinstance(actions, Iterable) and not isinstance(actions, str) else set()
