"""Read operations of the customer app (``READ ONLY``), and the lookups its commands share.

Every read sees the live cards only (not deleted, merged nor erased). A customer may be named by
its id or by its name, phone or email (``find_customer``); groups, tags and fields, by name.
"""

# Importing a module registers its operations: the modules with operations come first, in the order the registry
# lists them, and the helpers follow.
from . import (
    cards as cards,
    exports as exports,
    groups as groups,
    tags as tags,
    custom_fields as custom_fields,
    records as records,
    activity as activity,
    purchases as purchases,
    consent as consent,
    orders as orders,
    health as health,
    recovery as recovery,
    reads as reads,
    naming as naming,
    contact as contact,
)
