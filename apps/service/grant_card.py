"""The assistant's card for a voucher granted (``service.grant.create``): the voucher, whose it is and the sale that
charged it (then its line), first: a normal card's line shows only its first three data."""

from base.assistant import card_order

summary = card_order.said_first("package_id", "package", "customer_id", "customer", "sale_id", "sale_line_id")
