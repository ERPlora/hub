"""Live queries of the customer app and the events that re-run them after the COMMIT.

The lookup by phone and the export are not live: the till asks by phone once, and the export is a
file, not a screen.
"""

from live.live_registry import live

from apps.customer import events as E

#: A card that leaves the lists (deleted, merged into another or erased) or comes back to them (restored, CUSTOMER-F33).
CARD_IN_OR_OUT = [E.CUSTOMER_DELETED, E.CUSTOMER_MERGED, E.CUSTOMER_ERASED, E.CUSTOMER_RESTORED]
PURCHASES = [E.PURCHASE_RECORDED, E.PURCHASE_VOIDED, E.PURCHASE_REFUNDED]
HEALTH_CONSENT = [E.HEALTH_CONSENT_GRANTED, E.HEALTH_CONSENT_WITHDRAWN]
HEALTH = [*HEALTH_CONSENT, E.HEALTH_UPDATED]
CONSENT = [E.CONSENT_GRANTED, E.CONSENT_WITHDRAWN]
ORDERS = [E.ORDER_LINKED, E.ORDER_UNLINKED]

live(
    "customer.customer.list",
    on=[E.CUSTOMER_CREATED, E.CUSTOMER_UPDATED, *CARD_IN_OR_OUT, *PURCHASES],
)
# A new card changes no other card; the groups, tags and fields a card shows are its own.
live(
    "customer.customer.detail",
    on=[
        E.CUSTOMER_UPDATED,
        E.CUSTOMER_GROUPS_CHANGED,
        E.CUSTOMER_TAGS_CHANGED,
        *CARD_IN_OR_OUT,
        *CONSENT,
        *PURCHASES,
        E.GROUP_DELETED,
        E.TAG_DELETED,
        E.FIELD_CREATED,
        E.FIELD_UPDATED,
        E.FIELD_DELETED,
    ],
)
live(
    "customer.customer.stats",
    on=[E.CUSTOMER_CREATED, E.CUSTOMER_UPDATED, *CARD_IN_OR_OUT, *PURCHASES],
)
live(
    "customer.group.list",
    on=[
        E.GROUP_CREATED,
        E.GROUP_UPDATED,
        E.GROUP_DELETED,
        E.CUSTOMER_GROUPS_CHANGED,
        *CARD_IN_OR_OUT,
    ],
)
live(
    "customer.tag.list",
    on=[
        E.TAG_CREATED,
        E.TAG_UPDATED,
        E.TAG_DELETED,
        E.CUSTOMER_TAGS_CHANGED,
        *CARD_IN_OR_OUT,
    ],
)
live("customer.field.list", on=[E.FIELD_CREATED, E.FIELD_UPDATED, E.FIELD_DELETED])
live(
    "customer.activity.list",
    on=[E.NOTE_ADDED, E.ACTIVITY_RECORDED, *CONSENT, *PURCHASES, *HEALTH, *CARD_IN_OR_OUT],
)
live("customer.purchase.list", on=[*PURCHASES, *CARD_IN_OR_OUT])
live("customer.purchase.divergences", on=[*PURCHASES, *CARD_IN_OR_OUT])
live("customer.consent.state", on=[*CONSENT, *HEALTH_CONSENT, *CARD_IN_OR_OUT])
live("customer.consent.history", on=[*CONSENT, *HEALTH_CONSENT, *CARD_IN_OR_OUT])
live("customer.order.customer", on=[*ORDERS, *CARD_IN_OR_OUT])
live("customer.order.list", on=[*ORDERS, *CARD_IN_OR_OUT])
# Health data (CUSTOMER-F32): its own block, re-run by its own events and when the card goes.
live("customer.health.detail", on=[*HEALTH, *CARD_IN_OR_OUT])
