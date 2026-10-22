"""Which database every model lives in (PLAN-DB §2 and §14.1; plan 2026-10-22-fase-2-tenencia §2.1).

An explicit list, read by the ``TenantRouter`` and by ``base/tenancy/tests/test_inventory.py``:

- ``control``: the control database (``default``): the registry (``control``), Django's admin, auth, contenttypes
  and sessions, and phase 1's ``base.Membership``;
- ``hub``: a hub's own database: ``base``, ``live`` and every module of ``apps/``;
- ``contextual``: the database of the context that writes it: the outbox and its deliveries, whose rows a hub's
  command writes in its hub and the registry's operations (``base.hub.*``, the demos) in control
  (plan §1, contradiction 5);
- ``shared``: the SaaS's ``shared`` schema, which ``base.routers.SharedRouter`` sends to its alias.

A model in none of them is refused (``UnclassifiedModel``): it never lands anywhere by default. The labels are
``app_label.model_name`` in lowercase, those of the models that moved included (``base.hub`` became
``control.hub``): ``allow_migrate`` gets the historical ones while it runs the migrations of before.
"""

CONTROL = "control"
HUB = "hub"
CONTEXTUAL = "contextual"
SHARED = "shared"
CLASSES = frozenset({CONTROL, HUB, CONTEXTUAL, SHARED})

#: The class of every model of these apps, by label.
APP_CLASSES: dict[str, str] = {
    "control": CONTROL,
    "admin": CONTROL,
    "auth": CONTROL,
    "contenttypes": CONTROL,
    "sessions": CONTROL,
    "shared": SHARED,
    "base": HUB,
    "live": HUB,
}

#: Every module of ``apps/`` keeps its tables in each hub's database (CLAUDE.md «Apps»).
HUB_MODULES_PACKAGE = "apps."

#: Models whose class is not their app's, each with its reason.
MODEL_CLASSES: dict[str, tuple[str, str]] = {
    "base.membership": (
        CONTROL,
        "phase 1's session seam: the role of a SaaS user on a host stays in control with Django's sessions "
        "until the hub's own staff and sessions come (plan 2026-10-22, decision 3).",
    ),
    "base.hub": (
        CONTROL,
        "the registry before it moved to control.Hub (base/migrations/0004): its table base_hub is control's.",
    ),
    "base.democode": (
        CONTROL,
        "the demos' codes before they moved to control.DemoCode (base/migrations/0005): control's table.",
    ),
    "live.outboxevent": (
        CONTEXTUAL,
        "a hub's commands record their events in the hub's database; the registry's (base.hub.*, the demos), "
        "which belong to no hub, in control's (plan 2026-10-22, contradiction 5).",
    ),
    "base.eventdelivery": (
        CONTEXTUAL,
        "an event's deliveries live next to the event they deliver (a foreign key to live.OutboxEvent).",
    ),
}


class UnclassifiedModel(LookupError):
    """A model in none of the lists: add it to ``APP_CLASSES`` or ``MODEL_CLASSES`` with its reason."""


def classify_label(app_label: str, model_name: str, app_name: str | None = None) -> str:
    """The class of the model ``app_label.model_name`` (``app_name``: its app's module, ``apps.<id>`` for a module)."""
    label = f"{app_label}.{model_name}".lower()
    if label in MODEL_CLASSES:
        return MODEL_CLASSES[label][0]
    if app_label in APP_CLASSES:
        return APP_CLASSES[app_label]
    if app_name is None or not app_name.startswith(HUB_MODULES_PACKAGE):
        # A migration's historical model knows its app only by label (``tax``): the installed app says ``apps.tax``.
        app_name = _app_name(app_label) or app_name
    if app_name is not None and app_name.startswith(HUB_MODULES_PACKAGE):
        return HUB
    raise UnclassifiedModel(
        f"{label} is in no database class: add it to base.tenancy.inventory (APP_CLASSES or MODEL_CLASSES) with its "
        "reason."
    )


def classify(model) -> str:
    """The class of ``model`` (a model class or instance)."""
    meta = model._meta
    app_config = getattr(meta, "app_config", None)
    app_name = getattr(app_config, "name", None)
    return classify_label(meta.app_label, meta.label_lower.split(".", 1)[1], app_name)


def _app_name(app_label: str) -> str | None:
    from django.apps import apps

    try:
        return apps.get_app_config(app_label).name
    except LookupError:
        return None
