"""Events of the customer app (``customer.<entity>.<fact>``): recorded by services.py, cited by live.py.

They carry ids only, never personal data: whoever needs the card asks ``customer.customer.detail``.

Reactions to other apps' events (WORKBOOK «A qué reacciona»): ``sale.sale.completed`` will run
``customer.purchase.record`` and ``sale.sale.voided`` ``customer.purchase.void``. Both operations are
built and tested; the reactions are wired here once the sale app exists and the outbox relay
delivers events between apps (phase 2).
"""

CUSTOMER_CREATED = "customer.customer.created"
CUSTOMER_UPDATED = "customer.customer.updated"
CUSTOMER_GROUPS_CHANGED = "customer.customer.groups_changed"
CUSTOMER_TAGS_CHANGED = "customer.customer.tags_changed"
CUSTOMER_DELETED = "customer.customer.deleted"
CUSTOMER_MERGED = "customer.customer.merged"
CUSTOMER_ERASED = "customer.customer.erased"
NOTE_ADDED = "customer.note.added"
ACTIVITY_RECORDED = "customer.activity.recorded"
CONSENT_GRANTED = "customer.consent.granted"
CONSENT_WITHDRAWN = "customer.consent.withdrawn"
ORDER_LINKED = "customer.order.linked"
ORDER_UNLINKED = "customer.order.unlinked"
PURCHASE_RECORDED = "customer.purchase.recorded"
PURCHASE_VOIDED = "customer.purchase.voided"
GROUP_CREATED = "customer.group.created"
GROUP_UPDATED = "customer.group.updated"
GROUP_DELETED = "customer.group.deleted"
TAG_CREATED = "customer.tag.created"
TAG_UPDATED = "customer.tag.updated"
TAG_DELETED = "customer.tag.deleted"
FIELD_CREATED = "customer.field.created"
FIELD_UPDATED = "customer.field.updated"
FIELD_DELETED = "customer.field.deleted"

ALL = [
    CUSTOMER_CREATED,
    CUSTOMER_UPDATED,
    CUSTOMER_GROUPS_CHANGED,
    CUSTOMER_TAGS_CHANGED,
    CUSTOMER_DELETED,
    CUSTOMER_MERGED,
    CUSTOMER_ERASED,
    NOTE_ADDED,
    ACTIVITY_RECORDED,
    CONSENT_GRANTED,
    CONSENT_WITHDRAWN,
    ORDER_LINKED,
    ORDER_UNLINKED,
    PURCHASE_RECORDED,
    PURCHASE_VOIDED,
    GROUP_CREATED,
    GROUP_UPDATED,
    GROUP_DELETED,
    TAG_CREATED,
    TAG_UPDATED,
    TAG_DELETED,
    FIELD_CREATED,
    FIELD_UPDATED,
    FIELD_DELETED,
]
