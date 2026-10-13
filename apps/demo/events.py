"""Events of the demo app (``<app>.<entity>.<fact>``): recorded by services.py, cited by live.py.

The demo app reacts to no event of another app, so this module only names its own.
"""

ITEM_CREATED = "demo.item.created"
ITEM_UPDATED = "demo.item.updated"
ITEM_DELETED = "demo.item.deleted"
ITEM_LINE_ADDED = "demo.item.line_added"

ALL = [ITEM_CREATED, ITEM_UPDATED, ITEM_DELETED, ITEM_LINE_ADDED]
