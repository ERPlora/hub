"""Read operations of base, one module per entity: importing each module here registers its operations."""

# blueprints goes first: it imports base.blueprint before base.relay, and the circle base.relay -> base.services ->
# base.blueprint -> base.relay only loads when it starts at base.blueprint.
from . import blueprints as blueprints
from . import (
    access as access,
    api_keys as api_keys,
    app_help as app_help,
    approvals as approvals,
    apps as apps,
    assistant as assistant,
    catalog_images as catalog_images,
    demos as demos,
    devices as devices,
    dumps as dumps,
    files as files,
    home as home,
    hubs as hubs,
    people as people,
    profile as profile,
    sessions as sessions,
    system as system,
    usage as usage,
)
