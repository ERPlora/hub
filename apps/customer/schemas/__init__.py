"""Input and output schemas of the customer app's operations (OpenAPI, live params, 422 per field).

Every field has a description: these schemas are also the JSON Schema of the assistant's tools.
A customer can be named by its ``id`` or, when the id is not known (by voice, by text), by its exact
name, phone or email (``customer``); groups, tags and fields, by their name. Money is in cents.
"""

from . import (
    activity as activity,
    cards as cards,
    consent as consent,
    contact as contact,
    custom_fields as custom_fields,
    erasing as erasing,
    exports as exports,
    fields as fields,
    groups as groups,
    health as health,
    importing as importing,
    memberships as memberships,
    merging as merging,
    orders as orders,
    purchases as purchases,
    recovery as recovery,
    tags as tags,
)
