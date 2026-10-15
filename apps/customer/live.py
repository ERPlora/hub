"""Live queries of the customer app and the events that re-run them after the COMMIT.

The lookup by phone and the export are not live: the till asks by phone once, and the export is a
file, not a screen.
"""

from live.live_registry import live

from apps.customer import events as E

#: A card that leaves the lists: deleted, merged into another or erased.
CARD_GONE = [E.CUSTOMER_DELETED, E.CUSTOMER_MERGED, E.CUSTOMER_ERASED]
PURCHASES = [E.PURCHASE_RECORDED, E.PURCHASE_VOIDED, E.PURCHASE_REFUNDED]
CONSENT = [E.CONSENT_GRANTED, E.CONSENT_WITHDRAWN]
ORDERS = [E.ORDER_LINKED, E.ORDER_UNLINKED]

live(
    "customer.customer.list",
    on=[E.CUSTOMER_CREATED, E.CUSTOMER_UPDATED, *CARD_GONE, *PURCHASES],
)
# A new card changes no other card; the groups, tags and fields a card shows are its own.
live(
    "customer.customer.detail",
    on=[
        E.CUSTOMER_UPDATED,
        E.CUSTOMER_GROUPS_CHANGED,
        E.CUSTOMER_TAGS_CHANGED,
        *CARD_GONE,
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
    on=[E.CUSTOMER_CREATED, E.CUSTOMER_UPDATED, *CARD_GONE, *PURCHASES],
)
live(
    "customer.group.list",
    on=[
        E.GROUP_CREATED,
        E.GROUP_UPDATED,
        E.GROUP_DELETED,
        E.CUSTOMER_GROUPS_CHANGED,
        *CARD_GONE,
    ],
)
live(
    "customer.tag.list",
    on=[
        E.TAG_CREATED,
        E.TAG_UPDATED,
        E.TAG_DELETED,
        E.CUSTOMER_TAGS_CHANGED,
        *CARD_GONE,
    ],
)
live("customer.field.list", on=[E.FIELD_CREATED, E.FIELD_UPDATED, E.FIELD_DELETED])
live(
    "customer.activity.list",
    on=[E.NOTE_ADDED, E.ACTIVITY_RECORDED, *CONSENT, *PURCHASES, *CARD_GONE],
)
live("customer.purchase.list", on=[*PURCHASES, *CARD_GONE])
live("customer.purchase.divergences", on=[*PURCHASES, *CARD_GONE])
live("customer.consent.state", on=[*CONSENT, *CARD_GONE])
live("customer.consent.history", on=[*CONSENT, *CARD_GONE])
live("customer.order.customer", on=[*ORDERS, *CARD_GONE])
live("customer.order.list", on=[*ORDERS, *CARD_GONE])
