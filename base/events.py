"""Events of base (``<app>.<entity>.<fact>``): recorded by base.services in the transaction of their operation.

The registry of hubs (plan 2026-10-17, §1.5) and its demos (§1.6, §1.7): no live query of base reacts to them yet;
the outbox keeps them as the record of what the SaaS asked of the registry and of what the reaper purged.
"""

HUB_REGISTERED = "base.hub.registered"
HUB_STATE_APPLIED = "base.hub.state_applied"
HUB_CANCELLED = "base.hub.cancelled"
HUB_RESTORED = "base.hub.restored"
#: A business of phase 1 got its own database (S5, ``cut_shared_hubs``): how (its mode), where, the rows copied into
#: it and the copy of control taken before; recorded in control's outbox, the record of the cut.
HUB_CUT = "base.hub.cut"
DEMO_CREATED = "base.demo.created"
#: A one-time code into a demo was made; the event names the demo, never the code.
DEMO_CODE_CREATED = "base.demo.code_created"
DEMO_EXPIRED = "base.demo.expired"
DEMO_PURGED = "base.demo.purged"
#: Someone chose or changed their PIN (APP-BASE-3): the grid of «Switch user» has another face. Names nobody.
PIN_SET = "base.pin.set"
#: An administrator made a device shared or personal, named it, removed it, or removed the unused ones (APP-BASE-3).
DEVICE_MODE_CHANGED = "base.device.mode_changed"
DEVICE_RENAMED = "base.device.renamed"
DEVICE_REMOVED = "base.device.removed"
DEVICES_PRUNED = "base.device.pruned"
#: How the business asks who is at the till changed (the PIN pad, when it asks again, the PIN's digits).
ACCESS_SETTINGS_CHANGED = "base.access.settings_changed"
#: Someone changed their own profile (name, contact email, photo, preferences). Names nobody else.
PROFILE_UPDATED = "base.profile.updated"

# ── Data: blueprints, imports and reset (APP-BASE-2) ──
#: A blueprint was loaded (BASE-G105): its load's id and how it went. The Home and the loads read themselves again.
BLUEPRINT_IMPORTED = "base.blueprint.imported"
#: A load was undone (BASE-G108): its id.
IMPORT_UNDONE = "base.import.undone"
#: Every row of the apps named was removed (BASE-G109).
HUB_DATA_RESET = "base.hub.data_reset"
#: What Settings › Data does to the business: the Home's queries follow them (BASE-G131).
DATA_EVENTS = (BLUEPRINT_IMPORTED, IMPORT_UNDONE, HUB_DATA_RESET)
#: A reset moved on (asked, copying, emptying, failed) or a copy of the business's data was made (round 2026-10-30 of
#: PLAN-DB, decision 2): told to the hub's live queries after the COMMIT in control, never recorded in the outbox (the
#: worker writes it in control, outside any operation of the hub).
HUB_RESET_PROGRESSED = "base.hub.reset_progressed"
#: The nightly measurement kept the business's use of yesterday (``base.usage``): told after its COMMIT, as above.
HUB_USAGE_MEASURED = "base.hub.usage_measured"

# ── System (APP-BASE-7) ───────────────────────────────────────────────────────────────────────────────────────
#: The relay gave up on a delivery (its last attempt, or past the deepest level): told to the hub's live queries after
#: the COMMIT, never recorded in the outbox (a listener of every event failing on it would feed itself).
FAILED_EVENT_CREATED = "base.failed_event.created"
#: Who runs the business resent one failed event, or all of them (``count``).
FAILED_EVENT_RETRIED = "base.failed_event.retried"
#: Who runs the business discarded a failed event: closed for good, kept for the audit.
FAILED_EVENT_DISCARDED = "base.failed_event.discarded"

# ── People and permissions (APP-BASE-5) ──────────────────────────────────────────────────────────────────────────
#: Whoever runs the business took a person's PIN away (``person``: their id in the hub).
PERSON_PIN_REMOVED = "base.person.pin_removed"
#: Whoever runs the business gave a person a badge, or took it away.
PERSON_BADGE_SET = "base.person.badge_set"
PERSON_BADGE_REMOVED = "base.person.badge_removed"
PERSON_EVENTS = (PERSON_PIN_REMOVED, PERSON_BADGE_SET, PERSON_BADGE_REMOVED)
#: An API key made, rotated (a new token) or revoked; its token never travels in an event.
API_KEY_CREATED = "base.api_key.created"
API_KEY_ROTATED = "base.api_key.rotated"
API_KEY_REVOKED = "base.api_key.revoked"
API_KEY_EVENTS = (API_KEY_CREATED, API_KEY_ROTATED, API_KEY_REVOKED)
#: A manager approved one refused command with their PIN or badge, and the pass was spent on it (``base.approvals``).
APPROVAL_GRANTED = "base.approval.granted"
APPROVAL_USED = "base.approval.used"
APPROVAL_EVENTS = (APPROVAL_GRANTED, APPROVAL_USED)
#: Whoever runs the business showed or hid the documentation of its API.
API_DOC_SETTINGS_CHANGED = "base.api_doc.settings_changed"

# ── Files (APP-BASE-8) ──
#: A file went up to the business's files (BASE-G83): its path.
FILE_UPLOADED = "base.file.uploaded"
#: A new, empty folder (BASE-G83): its path.
FILE_FOLDER_CREATED = "base.file.folder_created"
#: A file or folder got another name (BASE-G85): its new path and the old one.
FILE_RENAMED = "base.file.renamed"
#: A file or folder went to another folder (BASE-G85): its new path and the old one.
FILE_MOVED = "base.file.moved"
#: A file, or a folder and everything in it, was deleted (BASE-G86): its path and whether it was a folder.
FILE_DELETED = "base.file.deleted"
#: What changes the business's files: Files' listing follows them.
FILE_EVENTS = (FILE_UPLOADED, FILE_FOLDER_CREATED, FILE_RENAMED, FILE_MOVED, FILE_DELETED)

# ── Apps turned on and off by the business (PLAN-HUB §9) ──
#: Whoever runs the business turned an app on (``app``) and, with it, what it needs that was off (``along``).
APP_ENABLED = "base.app.enabled"
#: Whoever runs the business turned an app off (``app``) and, with it, what only it needed (``along``).
APP_DISABLED = "base.app.disabled"
#: An app (``app``, with what it needs: ``along``) was turned on in a hub whose own database lacks its tables, or tried
#: again after failing: ``creating`` until the worker makes them (S3; PLAN-DB §7), then ``base.app.enabled``.
APP_ACTIVATION_REQUESTED = "base.app.activation_requested"
#: Making the tables of the apps ``apps`` failed (``error``, its kind): ``failed``, tried again later or by hand.
APP_ACTIVATION_FAILED = "base.app.activation_failed"
#: What changes which apps are on: the Apps screen, the menu and the Home follow them.
APP_EVENTS = (APP_ENABLED, APP_DISABLED, APP_ACTIVATION_REQUESTED, APP_ACTIVATION_FAILED)

ALL = [
    HUB_REGISTERED,
    HUB_STATE_APPLIED,
    HUB_CANCELLED,
    HUB_RESTORED,
    HUB_CUT,
    DEMO_CREATED,
    DEMO_CODE_CREATED,
    DEMO_EXPIRED,
    DEMO_PURGED,
    *DATA_EVENTS,
    FAILED_EVENT_CREATED,
    FAILED_EVENT_RETRIED,
    FAILED_EVENT_DISCARDED,
    *FILE_EVENTS,
    PIN_SET,
    DEVICE_MODE_CHANGED,
    DEVICE_RENAMED,
    DEVICE_REMOVED,
    DEVICES_PRUNED,
    ACCESS_SETTINGS_CHANGED,
    PROFILE_UPDATED,
    *PERSON_EVENTS,
    *API_KEY_EVENTS,
    *APPROVAL_EVENTS,
    API_DOC_SETTINGS_CHANGED,
    *APP_EVENTS,
]
