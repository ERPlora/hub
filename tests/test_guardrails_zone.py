"""Guardrail of the business's clock (hub#687): ``base.business.business_zone`` is the one reading of a business's time
zone. Django's current zone is the deployment's: nothing activates a hub's (PLAN-HUB), so an hour read on it is an hour
of another clock for a business in another zone, and a second reading drifts from the first (the card said 9:00, the
agenda 10:00). A reading on the deployment's clock can only leave this list, never join it. A screen is the same: it
reads the zone the server gives it (``useBusinessZone``, the ``timezone`` of its app's settings), never one written by
hand, but for what it shows until that answers.

Static and fast, like ``tests/test_guardrails.py``: pure functions over source text, proven by a made-up offender (the
positive control), then run over ``base/``, ``control/``, ``apps/`` and ``frontend/`` outside the tests.
"""

import ast
import re
from pathlib import Path, PurePosixPath

HUB_DIR = Path(__file__).resolve().parent.parent
SOURCE_ROOTS = ("base", "control", "apps")
#: The one reading of the business's clock: its fallback, the deployment's.
OWNER = PurePosixPath("base/business.py")
#: ``django.utils.timezone`` readers that take the zone to read in; without one, it is the deployment's.
TAKE_A_ZONE = frozenset({"localtime", "localdate"})
#: ``django.utils.timezone`` readers of the deployment's zone, always.
ALWAYS_THE_DEPLOYMENTS = frozenset(
    {"get_current_timezone", "get_current_timezone_name", "get_default_timezone", "get_default_timezone_name"}
)

#: What still reads the deployment's clock, per file. An hour told to a person, only in hub#772.
KNOWN_READINGS = {
    # hub#772: an invoice's dates and VeriFactu's records and notices, fiscal: only under Ioan's supervision.
    "apps/invoice/queries.py": 3,
    "apps/invoice/services.py": 4,
    "apps/verifactu/queries.py": 1,
    "apps/verifactu/services.py": 6,
    # hub#772 too, because they reach a record: a sale's day and number, and Taxes' «today», the rate a sale's preview
    # says and Invoicing's form proposes (``tests/test_guardrails_fiscal_clock.py``).
    "apps/sale/services.py": 1,
    "apps/tax/queries.py": 1,
    # ERPlora's own hub has no zone of its own: Settings › Business shows the deployment's (``base.business.get``).
    "base/queries.py": 1,
}


#: An IANA zone written in the code of a screen.
ZONE_BY_HAND = re.compile(r"""['"](?:Africa|America|Asia|Atlantic|Australia|Europe|Indian|Pacific)/[A-Za-z_]+['"]""")
#: Where a screen has a zone by hand, per file.
KNOWN_ZONES_BY_HAND = {
    # What it shows until the settings answer with the business's.
    "apps/appointment/frontend/pages/AgendaPage.vue": 1,
    "apps/kitchen/frontend/pages/DisplayPage.vue": 1,
    "apps/kitchen/frontend/pages/HistoryPage.vue": 1,
    "apps/kitchen/frontend/pages/TicketsPage.vue": 1,
    "apps/reservation/frontend/pages/AvailabilityPage.vue": 1,
    "apps/reservation/frontend/pages/ReservationsPage.vue": 1,
    "apps/reservation/frontend/pages/WaitlistPage.vue": 1,
    "apps/sale/frontend/components/pos/KitchenTickets.vue": 1,
    "apps/table/frontend/pages/FloorPlanPage.vue": 1,
    "apps/table/frontend/pages/SessionsPage.vue": 1,
}


def deployment_readings(source: str) -> list[str]:
    """Each reading of the deployment's clock in ``source``: a reader of ``django.utils.timezone`` with no zone, one
    that only knows the deployment's, ``settings.TIME_ZONE`` or a zone written by hand (``ZoneInfo("Europe/Madrid")``).
    A zone named by itself (UTC, for an instant that is on no clock) is none."""
    tree = ast.parse(source)
    zoned = {
        id(node.func)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and (len(node.args) > 1 or any(keyword.arg == "timezone" for keyword in node.keywords))
    }
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "django.utils.timezone":
            found += [
                f"{node.lineno}: import {alias.name}"
                for alias in node.names
                if alias.name in TAKE_A_ZONE | ALWAYS_THE_DEPLOYMENTS
            ]
        elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "timezone":
            if node.attr in ALWAYS_THE_DEPLOYMENTS or (node.attr in TAKE_A_ZONE and id(node) not in zoned):
                found.append(f"{node.lineno}: timezone.{node.attr}")
        elif isinstance(node, ast.Attribute) and node.attr == "TIME_ZONE":
            found.append(f"{node.lineno}: .TIME_ZONE")
        elif isinstance(node, ast.Call) and getattr(node.func, "id", "") == "ZoneInfo" and node.args:
            named = node.args[0]
            if isinstance(named, ast.Constant) and named.value != "UTC":
                found.append(f"{node.lineno}: ZoneInfo({named.value!r})")
    return found


def _sources():
    for root in SOURCE_ROOTS:
        for path in sorted((HUB_DIR / root).rglob("*.py")):
            relative = PurePosixPath(path.relative_to(HUB_DIR).as_posix())
            if "tests" in relative.parts or relative == OWNER:
                continue
            yield str(relative), path.read_text(encoding="utf-8")


def _screens():
    for root in ("apps", "base/frontend", "frontend"):
        for pattern in ("*.ts", "*.vue"):
            for path in sorted((HUB_DIR / root).rglob(pattern)):
                relative = PurePosixPath(path.relative_to(HUB_DIR).as_posix())
                is_test = "__tests__" in relative.parts or "testing" in relative.parts or path.name.endswith(".test.ts")
                if root == "apps" and "frontend" not in relative.parts or is_test or "node_modules" in relative.parts:
                    continue
                yield str(relative), path.read_text(encoding="utf-8")


def test_the_check_catches_every_way_of_reading_the_deployments_clock():
    assert deployment_readings("from django.utils import timezone\n\nx = timezone.localtime(moment)\n") == [
        "3: timezone.localtime"
    ]
    assert deployment_readings("from django.utils import timezone\n\nx = timezone.localdate()\n") == [
        "3: timezone.localdate"
    ]
    assert deployment_readings("from django.utils import timezone\n\nzone = timezone.get_default_timezone()\n") == [
        "3: timezone.get_default_timezone"
    ]
    assert deployment_readings("from django.utils.timezone import localtime\n\nx = localtime(moment)\n") == [
        "1: import localtime"
    ]
    assert deployment_readings("from django.conf import settings\n\nzone = settings.TIME_ZONE\n") == ["3: .TIME_ZONE"]
    assert deployment_readings("zone = ZoneInfo('Europe/Madrid')\n") == ["1: ZoneInfo('Europe/Madrid')"]


def test_the_check_leaves_what_reads_a_clock_it_was_given():
    assert deployment_readings("x = timezone.localtime(moment, business_zone())\n") == []
    assert deployment_readings("x = timezone.localdate(moment, timezone=zone)\n") == []
    assert deployment_readings("x = timezone.now()\n") == []
    assert deployment_readings("zone = ZoneInfo('UTC')\n") == []
    assert deployment_readings("zone = ZoneInfo(hub.timezone)\n") == []
    assert deployment_readings("name = hub.timezone\n") == []


def test_no_hour_is_read_on_the_deployments_clock_but_the_known_ones():
    found = {path: deployment_readings(source) for path, source in _sources()}
    too_many = {path: readings for path, readings in found.items() if len(readings) > KNOWN_READINGS.get(path, 0)}
    assert too_many == {}, (
        "read the business's clock with base.business.business_zone (hub#687):\n"
        + "\n".join(f"{path}:{reading}" for path, readings in too_many.items() for reading in readings)
    )


def test_the_check_catches_a_zone_written_by_hand_in_a_screen():
    assert ZONE_BY_HAND.findall("new Intl.DateTimeFormat(locale, { timeZone: 'Europe/Madrid' })") == ["'Europe/Madrid'"]
    assert ZONE_BY_HAND.findall('const ZONE = "Atlantic/Canary";') == ['"Atlantic/Canary"']
    assert ZONE_BY_HAND.findall("// phase 1: Europe/Madrid, as the server") == []
    assert ZONE_BY_HAND.findall("new Intl.DateTimeFormat(locale, { timeZone: 'UTC' })") == []
    assert ZONE_BY_HAND.findall("const zone = settings.value?.timezone;") == []


def test_no_screen_writes_a_zone_by_hand_but_the_known_ones():
    too_many = {
        path: len(ZONE_BY_HAND.findall(source))
        for path, source in _screens()
        if len(ZONE_BY_HAND.findall(source)) > KNOWN_ZONES_BY_HAND.get(path, 0)
    }
    assert too_many == {}, "read the business's zone with useBusinessZone or its app's settings (hub#687): " + str(too_many)


def test_the_known_readings_name_only_what_still_reads_the_deployments_clock():
    """A reading that left the list leaves no room behind: an entry older than the code would let a new reading of
    the deployment's clock into that file unseen (review of hub#687)."""
    found = {path: len(deployment_readings(source)) for path, source in _sources()}
    stale = {path: (known, found.get(path, 0)) for path, known in KNOWN_READINGS.items() if known > found.get(path, 0)}
    assert stale == {}, "take these out of KNOWN_READINGS (known, found): " + str(stale)


def test_the_known_zones_by_hand_name_only_what_still_has_one():
    found = {path: len(ZONE_BY_HAND.findall(source)) for path, source in _screens()}
    stale = {path: (known, found.get(path, 0)) for path, known in KNOWN_ZONES_BY_HAND.items() if known > found.get(path, 0)}
    assert stale == {}, "take these out of KNOWN_ZONES_BY_HAND (known, found): " + str(stale)
