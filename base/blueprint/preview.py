"""What a blueprint brings before it loads: a template of the catalogue or an uploaded file, what it holds and
what of it would load here.
"""

from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import InvalidPayload, NotFound
from live.meta import module_configs

from base import activation
from base.apps_on import active_apps
from base.blueprint.archive import PURPOSE_BACKUP, BlueprintInvalid, Bundle, read_base64
from base.blueprint.datasets import app_label, dataset, datasets_of
from base.blueprint.loading import INACTIVE, UNKNOWN, _apps_of
from base.blueprint.seeds import Template, template
from base.entitlement import blocked_apps

# Statuses of an app in a blueprint's summary, before loading it: on here, off and turned on by the load, off and left
# off (only its data names it, or the plan gives no right to it), or not in this hub.
ON, TURNS_ON = "on", "turns_on"

ONE_SOURCE = _("Choose a template or a file, one of them.")
TEMPLATE_NOT_FOUND = _("This template is no longer in the catalogue.")


def open_source(template_key: str, file_base64: str) -> tuple[Bundle, Template | None]:
    """The blueprint of a template of the catalogue or of an uploaded file, exactly one of them."""
    if bool(template_key) == bool(file_base64):
        raise InvalidPayload(str(ONE_SOURCE), code="base.blueprint_source")
    if template_key:
        seed = template(template_key)
        if seed is None:
            raise NotFound(str(TEMPLATE_NOT_FOUND), code="base.template_not_found")
        return seed.bundle, seed
    try:
        return read_base64(file_base64), None
    except BlueprintInvalid as exc:
        raise InvalidPayload(str(exc), code="base.blueprint_invalid", fields={"file_base64": str(exc)}) from None


def contents(bundle: Bundle) -> list[dict]:
    """What a blueprint brings, by dataset: its name and how many rows."""
    return [{"key": key, "label": str(dataset(key).label), "rows": len(rows)} for key, rows in bundle.data.items()]


def template_out(seed: Template) -> dict:
    return {
        "key": seed.key,
        "name": seed.name,
        "description": seed.description,
        "language": seed.language,
        "country": seed.country,
        "vertical": seed.vertical,
        "version": seed.version,
        "apps": [{"id": app, "label": app_label(app)} for app in seed.bundle.manifest["apps"]],
        "contents": contents(seed.bundle),
    }


def summary(ctx: OperationContext, bundle: Bundle, *, seed: Template | None) -> dict:
    """What a blueprint brings and what of it would load here, writing nothing."""
    on = active_apps(ctx.scope)
    blocked = blocked_apps(ctx.scope)
    known = {config.label for config in module_configs()}
    manifest_ = bundle.manifest
    listed = set(manifest_["apps"])
    backup = manifest_["purpose"] == PURPOSE_BACKUP
    # What the load would be told no by (VeriFactu outside Spain, hub#694) is not promised beforehand.
    wont_go_on = activation.refusals(listed - on, ctx=ctx, hook=activation.CAN_ENABLE)
    apps = []
    for app in _apps_of(bundle):
        if app not in known:
            status = UNKNOWN
        elif app in on:
            status = ON
        elif app in listed and app not in blocked and app not in wont_go_on:
            status = TURNS_ON
        else:
            status = INACTIVE
        parts = [
            {
                "key": part.key,
                "label": str(part.label),
                "rows": len(bundle.data[part.key]),
                "personal": part.personal,
                "travels": backup or not part.personal,
            }
            for part in datasets_of(app)
            if part.key in bundle.data
        ]
        apps.append({"id": app, "label": app_label(app), "status": status, "datasets": parts})
    return {
        "name": manifest_["name"],
        "language": manifest_["language"],
        "country": manifest_["country"],
        "purpose": manifest_["purpose"],
        "created_at": manifest_["created_at"],
        "version": seed.version if seed else manifest_["version"],
        "source": "catalog" if seed else "file",
        "apps": apps,
        "dropped": list(bundle.dropped),
    }
