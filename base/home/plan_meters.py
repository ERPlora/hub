"""What the apps say their plan includes and has spent (``plan_meter``), for System and the bell."""

from collections.abc import Iterable, Mapping
from typing import Any

from django.core import checks
from live.context import OperationContext
from live.meta import all_live_app_configs, LiveAppConfig
from live.operations import get, UnknownOperation

from base.home.module_hooks import hook_failed, run_hook

#: Where an app declares what its plan includes and has spent (:func:`plan_meters`).
PLAN_METER_ATTRIBUTE = "plan_meter"


def plan_meters(ctx: OperationContext, configs: Iterable[LiveAppConfig]) -> list[dict]:
    """What the apps of ``configs`` say their plan includes and has spent, for «Usage and plan» of System and the bell
    (BASE-F40), read through each app's own query: base reads no other app's tables. An app declares it on its
    ``LiveAppConfig`` as :data:`PLAN_METER_ATTRIBUTE`: the ``operation``, which of its output's fields are ``used`` and
    ``limit``, its ``label`` and, when its figures may not have come yet, the field that says they did (``measured``).
    Figures not measured yet are ``None``, never a zero; a query that fails is logged and says ``available: False``."""
    meters = []
    for config in configs:
        declared = getattr(config, PLAN_METER_ATTRIBUTE, None)
        if declared is None:
            continue
        meter = {"key": config.label, "label": str(declared["label"]), "used": None, "limit": None, "available": True}
        try:
            row = run_hook(ctx, declared["operation"], {}) or {}
            measured = declared.get("measured")
            if measured is None or row.get(measured) is not None:
                meter.update(used=row[declared["used"]], limit=row[declared["limit"]])
        except Exception:
            hook_failed(f"{config.label}.plan_meter", declared["operation"])
            meter["available"] = False
        meters.append(meter)
    return meters


def plan_meter_errors(configs: Iterable[LiveAppConfig]) -> list[checks.CheckMessage]:
    """``base.E013``: ``plan_meter`` names an operation that exists and fields of its output, with its ``label``."""
    hint = (
        f'Declare {PLAN_METER_ATTRIBUTE} = {{"operation": "<app>.<entity>.<action>", "used": "<field>", "limit": "<field>", '
        '"label": _("…")} on the LiveAppConfig of the module; "measured": "<field>" when its figures may not have come yet.'
    )
    errors = []
    for config in configs:
        declared = getattr(config, PLAN_METER_ATTRIBUTE, None)
        if declared is None:
            continue
        problems = []
        if not isinstance(declared, Mapping):
            problems.append(f"is {declared!r}, not a mapping")
        else:
            if not declared.get("label"):
                problems.append("has no label")
            try:
                fields = get(declared.get("operation")).output.model_fields
            except UnknownOperation:
                problems.append(f"names {declared.get('operation')!r}, which is no operation")
            else:
                names = [declared.get("used"), declared.get("limit")]
                if "measured" in declared:
                    names.append(declared["measured"])
                problems += [f"names {name!r}, which is no field of its output" for name in names if name not in fields]
        errors += [
            checks.Error(f"{config.label}'s {PLAN_METER_ATTRIBUTE} {problem}.", hint=hint, obj=config, id="base.E013")
            for problem in problems
        ]
    return errors


@checks.register("base")
def check_plan_meters(app_configs: Any, **kwargs: Any) -> list[checks.CheckMessage]:
    return plan_meter_errors(all_live_app_configs())
