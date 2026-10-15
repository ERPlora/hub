"""Events of the payment app (``<app>.<entity>.<fact>``): recorded by services.py, cited by live.py.

Each one is written in the transaction of its change, and only when the change happened: a refused
step leaves no event (the old module emitted them anyway). The payment app reacts to no event of
another app, so this module only names its own.
"""

PAYMENT_CREATED = "payment.payment.created"
PAYMENT_APPROVED = "payment.payment.approved"
PAYMENT_SENT = "payment.payment.sent"
PAYMENT_COMPLETED = "payment.payment.completed"
PAYMENT_CANCELLED = "payment.payment.cancelled"
METHOD_CREATED = "payment.method.created"
METHOD_UPDATED = "payment.method.updated"
METHOD_DEACTIVATED = "payment.method.deactivated"
METHOD_ACTIVATED = "payment.method.activated"

PAYMENT_EVENTS = [
    PAYMENT_CREATED,
    PAYMENT_APPROVED,
    PAYMENT_SENT,
    PAYMENT_COMPLETED,
    PAYMENT_CANCELLED,
]
METHOD_EVENTS = [METHOD_CREATED, METHOD_UPDATED, METHOD_DEACTIVATED, METHOD_ACTIVATED]
ALL = PAYMENT_EVENTS + METHOD_EVENTS
