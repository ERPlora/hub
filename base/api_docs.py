"""The documentation of the business's API (APP-BASE-5; BASE-G150, G48, the old hub's ``openapi.rs``): without the ORM.

:func:`public_document` cuts the hub's own OpenAPI document (django-ninja's, of every route) down to what the apps a
business has publish (``expose_api``): their routes, the bearer key that opens them (``erpk_live_…``, ``base.api_keys``)
and only the schemas those routes use. The platform's own routes (keys, approvals, people…) are never in it. The whole
document is built once per process: the routes are fixed from start-up (PLAN §15).
"""

import copy
import json
from functools import cache

from live.operations import registry as operation_registry

SECURITY_SCHEME = "ApiKey"
_REF = "#/components/schemas/"


@cache
def _whole() -> str:
    from config.api import api

    return json.dumps(api.get_openapi_schema())


def _refs(node: object) -> set[str]:
    text = json.dumps(node)
    found, start = set(), 0
    while (at := text.find(_REF, start)) != -1:
        end = text.index('"', at)
        found.add(text[at + len(_REF) : end])
        start = end
    return found


def public_document(apps: set[str]) -> dict:
    """The OpenAPI document of what ``apps`` publish: their published routes only, opened with a bearer key."""
    whole = json.loads(_whole())
    paths: dict[str, dict] = {}
    for path, item in whole.get("paths", {}).items():
        kept = {}
        for method, route in item.items():
            op = operation_registry.get(route.get("operationId", "")) if isinstance(route, dict) else None
            if op is None or not op.expose_api or op.app_label not in apps:
                continue
            route = copy.deepcopy(route)
            route.pop("security", None)
            described = op.ai.get("description") if isinstance(op.ai, dict) else None
            if described and "description" not in route:
                route["description"] = described
            kept[method] = route
        if kept:
            paths[path] = kept
    schemas = whole.get("components", {}).get("schemas", {})
    needed, pending = set(), _refs(paths)
    while pending:
        name = pending.pop()
        if name in needed or name not in schemas:
            continue
        needed.add(name)
        pending |= _refs(schemas[name])
    components: dict = {"securitySchemes": {SECURITY_SCHEME: {"type": "http", "scheme": "bearer"}}}
    if needed:
        components["schemas"] = {name: schemas[name] for name in sorted(needed)}
    return {
        "openapi": whole.get("openapi", "3.1.0"),
        "info": whole.get("info", {}),
        "paths": paths,
        "components": components,
        "security": [{SECURITY_SCHEME: []}],
    }
