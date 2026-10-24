"""The SPA's op → route map (``frontend/generated/operations.json``, hand-written until V3) names every route of the way
in (APP-BASE-3) as ``base/api.py`` binds it: the pages call them by operation, never by address."""

import json

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
