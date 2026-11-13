"""What an API test compares: the routes a router binds to its operations and the routes the SPA's op → route map
(``frontend/generated/operations.json``, written by hand) gives them, since the pages call an operation, never an
address. Paths are as the router binds them, without the ``/api`` it is mounted under, unless a name says otherwise."""

import json

from django.conf import settings
from django.urls import resolve


def bound_routes(router) -> set[tuple[str, str, str]]:
    """``(METHOD, path, operation)`` of every route ``router`` binds."""
    return {
        (method, path, route.operation_id)
        for path, view in router.path_operations.items()
        for route in view.operations
        for method in route.methods
    }


def assert_bound(method: str, path: str, operation: str) -> None:
    """``base/api.py`` binds ``path`` to ``operation`` alone and by ``method`` alone, and it resolves under ``/api``."""
    from base.api import router

    [route] = router.path_operations[path].operations
    assert (route.methods, route.operation_id) == ([method], operation)
    assert resolve(f"/api{path}").url_name


def spa_route_map(prefix: str) -> set[tuple[str, str, str]]:
    """``(METHOD, path, operation)`` of each operation named ``<prefix>…`` in the map, the path as the map writes it."""
    spa = json.loads((settings.BASE_DIR / "frontend" / "generated" / "operations.json").read_text())
    return {(route["method"].upper(), route["path"], op) for op, route in spa.items() if op.startswith(prefix)}


def spa_routes(prefix: str) -> set[tuple[str, str, str]]:
    """``spa_route_map`` with each path as the router binds it."""
    return {(method, path.removeprefix("/api"), op) for method, path, op in spa_route_map(prefix)}
