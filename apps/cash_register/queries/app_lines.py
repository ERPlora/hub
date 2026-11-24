"""What another app records in a session as its own (Tips: the tips taken and paid out), apart from the cash brought
in and taken out by hand, as the session's summary and its X/Z report show it.

Each app with a line in the session gets its own: in cash, by card, with other payment methods (only when there were
some) and paid out. What goes out by card or another method is a correction of what came in that way (no drawer pays
by card), so it nets into its line; what goes out in cash is paid out of the drawer. The cash register knows no such
app by name: it names the lines after the app that recorded them."""

from django.utils.translation import pgettext_lazy

from apps.cash_register.models import Movement
from apps.cash_register.queries.lines import CASH, Line
from base.system import app_name

#: The words of its lines: %(app)s is the name of the app that recorded them.
IN_CASH = pgettext_lazy("cash report", "%(app)s in cash")
BY_CARD = pgettext_lazy("cash report", "%(app)s by card")
WITH_OTHER_METHODS = pgettext_lazy("cash report", "%(app)s with other payment methods")
# Translators: %(app)s is the name of the app that records these lines in the drawer: Tips («Propinas pagadas»).
PAID_OUT = pgettext_lazy("cash report", "%(app)s paid out")
OTHER_METHODS = ("transfer", "other")


def app_lines(lines: list[Line]) -> list[dict]:
    """The lines of ``lines`` another app recorded, by app (in the order of their names in the registry), in the
    active language."""
    by_app: dict[str, list[Line]] = {}
    for line in lines:
        if line.app:
            by_app.setdefault(line.app, []).append(line)
    return [row for app in sorted(by_app) for row in _of_app(app, by_app[app])]


def _of_app(app: str, lines: list[Line]) -> list[dict]:
    def cash(kind: str) -> int:
        return sum(line.amount for line in lines if line.method_type == CASH and line.type == kind)

    def net(methods: tuple[str, ...]) -> int:
        return sum(line.signed_amount for line in lines if line.method_type in methods)

    other = net(OTHER_METHODS)
    figures = [
        (IN_CASH, cash(Movement.Type.IN)),
        (BY_CARD, net(("card",))),
        *([(WITH_OTHER_METHODS, other)] if other else []),
        (PAID_OUT, -cash(Movement.Type.OUT)),
    ]
    name = app_name(app)
    return [{"app": app, "label": str(label) % {"app": name}, "amount": amount} for label, amount in figures]
