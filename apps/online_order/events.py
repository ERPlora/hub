"""Events of Online orders (``<app>.<entity>.<fact>``): recorded by services.py, cited by live.py.

Online orders reacts to no event of another app, so this module only names its own.
"""

QR_CODE_REGENERATED = "online_order.qr_code.regenerated"

ORDER_SENT = "online_order.order.sent"
