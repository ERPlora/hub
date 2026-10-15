"""Live queries of the service app and the events that re-run them after the COMMIT.

The checks (void_check, adjust_check, redeem_check) are asked at the moment of acting: not followed.
Other apps' events re-run what shows their data: a professional's name and whether they may book
(Staff), a customer's name and whether the card is gone (Customers).
"""

from live.live_registry import live

from apps.service.events import (
    ASSIGNMENT_EVENTS,
    CATEGORY_DELETED,
    CATEGORY_EVENTS,
    CATEGORY_UPDATED,
    CUSTOMER_GONE,
    GRANT_EVENTS,
    GRANT_GRANTED,
    PACKAGE_EVENTS,
    SESSION_EVENTS,
    SERVICE_EVENTS,
    SERVICE_UPDATED,
    SETTINGS_UPDATED,
    STAFF_MEMBER_EVENTS,
)

#: A service row shows its category's name; deleting the category leaves it without one.
CATEGORY_SHOWN = [CATEGORY_UPDATED, CATEGORY_DELETED]
#: A voucher sold shows its customer's name, or the date the card went.
CUSTOMER_NAMED = [*CUSTOMER_GONE, "customer.customer.updated"]

live("service.service.list", on=[*SERVICE_EVENTS, *CATEGORY_SHOWN])
live("service.service.get", on=[*SERVICE_EVENTS, *CATEGORY_SHOWN])
live("service.service.list_for_sale", on=[*SERVICE_EVENTS, *CATEGORY_SHOWN])
live("service.catalog.status", on=SERVICE_EVENTS)
# Each category counts its offered services.
live("service.category.list", on=[*CATEGORY_EVENTS, *SERVICE_EVENTS])
live("service.category.get", on=[*CATEGORY_EVENTS, *SERVICE_EVENTS])
live("service.settings.get", on=[SETTINGS_UPDATED])
live(
    "service.assignment.list",
    on=[*ASSIGNMENT_EVENTS, *SERVICE_EVENTS, *STAFF_MEMBER_EVENTS],
)
live(
    "service.assignment.eligible",
    on=[*ASSIGNMENT_EVENTS, *SERVICE_EVENTS, *STAFF_MEMBER_EVENTS],
)
# A package counts its sales (and a deleted one shows once somebody bought it); its lines show the services.
live("service.package.list", on=[*PACKAGE_EVENTS, GRANT_GRANTED, *SERVICE_EVENTS])
live("service.package.get", on=[*PACKAGE_EVENTS, GRANT_GRANTED, *SERVICE_EVENTS])
live(
    "service.grant.list",
    on=[*GRANT_EVENTS, *SESSION_EVENTS, *PACKAGE_EVENTS, *CUSTOMER_NAMED],
)
live(
    "service.grant.list_orphans",
    on=[*GRANT_EVENTS, *SESSION_EVENTS, *PACKAGE_EVENTS, *CUSTOMER_NAMED],
)
# The till's voucher slot (SERVICE-F22): another till spending a session changes what is left.
live(
    "service.grant.tender_options",
    on=[*GRANT_EVENTS, *SESSION_EVENTS, *PACKAGE_EVENTS, *CUSTOMER_NAMED],
)
live(
    "service.movement.list",
    on=[*GRANT_EVENTS, *SESSION_EVENTS, SERVICE_UPDATED, *CUSTOMER_NAMED],
)
