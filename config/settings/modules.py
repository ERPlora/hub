from decouple import config

from config.settings.core import BASE_DIR, DEBUG, VITE_DEV_PORT, VITE_DEV_SERVER
from config.settings.web import SPA_DIST

# The apps' registry in the SaaS. The image's build fixes the release:
# APP_VERSION (the commit's sha) and APP_RELEASED_AT (its time, ISO 8601), which register_apps
# demands in production and which decide that an older release never overwrites a newer one.
APP_VERSION = config("APP_VERSION", default="")
APP_RELEASED_AT = config("APP_RELEASED_AT", default="")
# translate_workbooks (development only: the anthropic client is a dev dependency; ANTHROPIC_API_KEY
# in the local .env) writes each module's WORKBOOK.<language>.md with this model.
WORKBOOK_TRANSLATION_MODEL = config(
    "WORKBOOK_TRANSLATION_MODEL", default="claude-haiku-5-5"
)

# Operations, live queries and the SPA (packages/live).

LIVE = {
    "context_builder": "base.operations.HubContextBuilder",
    "control_alias": "default",
    # Every operation's transaction opens on the alias of its use_hub; the registry's, on control. An
    # operation of an app the business has no right to answers 402 before (base.entitlement).
    "operation_database": "base.entitlement.operation_database",
    # Where live.operations.atomic() opens (a services.py's savepoint): the active use_hub's alias, inside an operation
    # its transaction's; without a context HubContextMissing, never control's by omission.
    "current_database": "base.tenancy.context.current_alias",
    # Inside each command's own transaction, once it ran: what a manager may approve, done by whoever may do it
    # themselves, goes on the record of approvals.
    "after_command": "base.approval_note.note",
    # A cut of the database (a restart, AWS's maintenance, the Blue/Green switchover;
    # BASE-F111): a read, and what was not applied, waits and tries again up to this long in the whole request, far below
    # the 120 s of the load balancer. What tries again on its own gets its 503 at once: the SaaS's /internal, and
    # /readyz, which has to say the database is gone before its probes give up.
    "database_cut": {
        "wait_seconds": config("DB_CUT_WAIT_SECONDS", default=20, cast=int),
        "no_wait_prefixes": ("/internal/", "/readyz"),
    },
    # Hub slugs (live.slugs): 3–63 characters in production; local development also opens the
    # one-letter demo hubs a and b (a.localhost:8000, b.localhost:8000).
    "hub_slug_min_length": 1 if DEBUG else 3,
    "spa": {
        "entry": "frontend/main.ts",
        "manifest": SPA_DIST / ".vite" / "manifest.json",
        "dev_server": VITE_DEV_SERVER if DEBUG else None,
        "palette_default": "erplora",
        # THEME_PALETTES of packages/ui/src/shell/theme.ts: the ep_palette cookie may name any of them.
        "palettes": [
            "erplora",
            "terracotta",
            "corporate",
            "minimal",
            "forest",
            "ocean",
            "violet",
        ],
        # The old hub's tab and home-screen icons (its apps/web/public/icons/), static files of base: without a
        # <link>, the browser asks for /favicon.ico, which names a file and is a plain 404 (base.spa.NOT_A_FILE).
        "icons": [
            {"rel": "icon", "path": "base/icons/favicon.ico", "sizes": "any"},
            {"rel": "apple-touch-icon", "path": "base/icons/apple-touch-icon.png"},
        ],
    },
    # The repo is its own pnpm workspace (packages/ui is a submodule), so Vite runs from here, with the
    # port Django read (environment or .env): vite.config.ts reads VITE_DEV_PORT from the process
    # environment only, and a Vite on another port than the page's leaves a page that never loads.
    "vite": {
        "command": ["env", f"VITE_DEV_PORT={VITE_DEV_PORT}", "pnpm", "run", "dev"],
        "cwd": str(BASE_DIR),
    },
}

# The apps whose assistant tools all say what a person types to ask for them (AI.asks, live.E020): an app joins in the
# pull request that completes its asks, and layer 1 of the assistant's QA (base/tests/test_assistant_asks.py) checks
# each ask reaches its tool, role by role, and that every app whose tools say asks is here. The list is written only
# here, one app per line (hub#1144).
LIVE_ASSISTANT_ASKS_REQUIRED = (
    "appointment",
    "attendance",
    "base",
    "cart_checkout",
    "cash_register",
    "combo",
    "customer",
    "demo",
    "flow",
    "inventory",
    "invoice",
    "kitchen",
    "modifier",
    "online_booking",
    "payment",
    "pricing",
    "printing",
    "reservation",
    "sale",
    "schedule",
    "service",
    "staff",
    "table",
    "task",
    "tax",
    "verifactu",
    "website",
    "whatsapp_inbox",
)
