"""Live queries of the sale app and the events that re-run them after the COMMIT.

The lookups by attempt key and the business day are not live: they are asked once.
"""

from live.live_registry import live

from apps.sale import events as E
from apps.tax.events import RULE_EVENTS

SALES = E.SALE_EVENTS
FIGURES = [E.SALE_COMPLETED, E.SALE_VOIDED, E.SALE_REFUNDED]

live("sale.sale.list", on=SALES)
live("sale.sale.get", on=SALES)
live("sale.sale.stats", on=FIGURES)
live("sale.sale.today", on=FIGURES)
live("sale.sale.last_7_days", on=FIGURES)
live("sale.sale.by_staff", on=FIGURES)
# A partial charge takes lines off a check without changing anything else of it.
live("sale.order.list", on=E.ORDER_EVENTS)
live("sale.order.get", on=E.ORDER_EVENTS)
# What a charge would be: the check, the settings (VAT included, discounts) and tax's rules.
live("sale.checkout.preview", on=[*E.ORDER_EVENTS, E.SETTINGS_UPDATED, *RULE_EVENTS])
# The settings decide which methods charge today.
live("sale.payment_method.list", on=[E.PAYMENT_METHOD_CREATED, E.SETTINGS_UPDATED])
live("sale.settings.get", on=[E.SETTINGS_UPDATED])
live("sale.pos_settings.get", on=[E.SETTINGS_UPDATED])
# Each department shows the rate its category charges today.
live(
    "sale.department.list",
    on=[E.DEPARTMENT_CREATED, E.DEPARTMENT_UPDATED, E.DEPARTMENT_DELETED, *RULE_EVENTS],
)
live(
    "sale.quick_note.list",
    on=[E.QUICK_NOTE_CREATED, E.QUICK_NOTE_UPDATED, E.QUICK_NOTE_DELETED],
)
live("sale.refund.options", on=[E.SALE_REFUNDED, E.SALE_VOIDED])
live("sale.refund.list", on=[E.SALE_REFUNDED])
