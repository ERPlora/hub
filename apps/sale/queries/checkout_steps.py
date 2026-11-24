"""The steps the apps on in a business add to its charge, which the charge sheet mounts between the amount and the
tenders without knowing those apps (SALE-F39), and which decide whether a charge takes what is added to a tender."""

from live.context import OperationContext
from live.meta import module_configs
from live.operations import INTERNAL, operation

from apps.sale.schemas.checkout import CheckoutStepsOut
from apps.sale.schemas.fields import EmptyIn
from base.apps_on import active_apps


def steps_at_the_charge(ctx: OperationContext) -> list[dict]:
    """``{key, app, component}`` of each step an app on in ``ctx``'s business declares at the charge and its person may
    see, in the order of the installed apps and of each app's own list."""
    on = active_apps(ctx.scope)
    return [
        {"key": f"{config.label}.{step.key}", "app": config.label, "component": step.component}
        for config in module_configs()
        if config.label in on
        for step in config.checkout
        if ctx.has(step.permission)
    ]


# Not an assistant tool: the steps of the charge sheet, the screen's own layout (each step reads and writes through its
# own app's operations).
@operation(
    "sale.checkout.steps",
    kind="query",
    permission="sale.take_payment",
    input=EmptyIn,
    output=CheckoutStepsOut,
    ai=INTERNAL,
)
def checkout_steps(ctx: OperationContext, data: EmptyIn) -> dict:
    return {"steps": steps_at_the_charge(ctx)}
