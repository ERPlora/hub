"""The SPA's op → route map (``frontend/generated/operations.json``, hand-written until V3) names every route of the way
in (APP-BASE-3) as ``base/api.py`` binds it: the pages call them by operation, never by address. And each of its
operations tells the assistant what it does, or that it is not the assistant's to run."""

import json

import pytest
from live.operations import get

ROUTES = {
    ("GET", "/access/door", "base.access.door"),
    ("POST", "/me/pin", "base.pin.set"),
    ("GET", "/device", "base.device.current"),
    ("POST", "/device/mode", "base.device.mode_set"),
    ("GET", "/devices", "base.device.list"),
    ("POST", "/devices/rename", "base.device.rename"),
    ("POST", "/devices/remove", "base.device.remove"),
    ("POST", "/devices/prune", "base.device.prune"),
    ("GET", "/access/settings", "base.access.settings"),
    ("POST", "/access/settings/update", "base.access.settings_update"),
    ("GET", "/me/profile", "base.profile.get"),
    ("POST", "/me/profile/update", "base.profile.update"),
    ("POST", "/me/preferences", "base.profile.preferences_set"),
    ("POST", "/me/avatar", "base.profile.avatar_set"),
    ("POST", "/me/avatar/remove", "base.profile.avatar_remove"),
}


def bound_routes() -> set[tuple[str, str, str]]:
    from base.api import router

    bound = set()
    for path, path_view in router.path_operations.items():
        for operation in path_view.operations:
            for method in operation.methods:
                bound.add((method, path, operation.operation_id))
    return bound


def test_base_api_binds_each_route_of_the_way_in_to_its_operation():
    assert ROUTES <= bound_routes()


def test_the_spas_route_map_names_every_route_of_the_way_in(settings):
    spa = json.loads((settings.BASE_DIR / "frontend" / "generated" / "operations.json").read_text())
    mine = {op for _, _, op in ROUTES}
    named = {(route["method"].upper(), route["path"].removeprefix("/api"), op) for op, route in spa.items() if op in mine}
    assert named == ROUTES


# ── What each operation of the way in tells the assistant (PLAN §30: every @operation declares ``ai=``) ─────

WAY_IN_OPERATIONS = sorted({op for _, _, op in ROUTES} | {"base.access.faces"})

# Not the assistant's to run (``ai=INTERNAL`` once ``live`` has it, FIX-LIVE-AI-DECLARATION-E017; until then declared
# as whatsapp_inbox's «System only» ones are): a PIN is typed, never said; a photo is a file; the door is what a till's
# browser shows by itself.
NOT_ASSISTANT_TOOLS = ["base.access.door", "base.access.faces", "base.pin.set", "base.profile.avatar_set"]


@pytest.mark.parametrize("name", WAY_IN_OPERATIONS)
def test_each_operation_of_the_way_in_declares_what_it_does_to_the_assistant(name):
    op = get(name)
    assert isinstance(op.ai, dict) and op.ai["description"].strip()
    if op.kind == "command":
        assert op.ai["risk"] in {"normal", "high"}


@pytest.mark.parametrize("name", NOT_ASSISTANT_TOOLS)
def test_what_the_assistant_must_not_run_says_so_where_it_is_declared(name):
    assert get(name).ai["description"].startswith("Not an assistant tool (")


def test_choosing_ones_pin_is_never_run_without_the_person_in_front():
    # «high»: the assistant would ask first, and an automation never gets it (apps/flow's needs_a_person).
    assert get("base.pin.set").ai["risk"] == "high"
