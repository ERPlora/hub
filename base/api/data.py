"""Routes of Settings › Data: the blueprints, the imports, the reset and the copies of the business's data.

Settings › Data's that read or load a file take it in base64 in their body, more than Django's ceiling for
any other view; both are commands (POST): reading what a file brings writes nothing, but no query string carries it.
"""

from live.ninja import bind, run_operation
from ninja import Query, Router
from ninja.decorators import decorate_view

from base import queries, services
from base.request_body import accept_body_up_to
from base.schemas.blueprints import BlueprintExportIn, BlueprintImportIn, BlueprintSourceIn, ImportIdIn, ImportUndoIn
from base.schemas.dumps import HubDumpLinkIn
from base.schemas.reset import HubResetIn

router = Router()


#: The upload's body: 20 MB of zip in base64 (27 962 028 characters) and its JSON around it.
MAX_BLUEPRINT_BODY = 28_100_000


@bind(router, "base.blueprint.list", "/settings/data/blueprints")
async def blueprint_list(request):
    return await run_operation(request, queries.blueprints.blueprint_list)


@bind(router, "base.blueprint.inspect", "/settings/data/blueprints/inspect")
@decorate_view(accept_body_up_to(MAX_BLUEPRINT_BODY))
async def blueprint_inspect(request, data: BlueprintSourceIn):
    return await run_operation(request, services.blueprints.blueprint_inspect, data)


@bind(router, "base.blueprint.import", "/settings/data/blueprints/import")
@decorate_view(accept_body_up_to(MAX_BLUEPRINT_BODY))
async def blueprint_import(request, data: BlueprintImportIn):
    return await run_operation(request, services.blueprints.blueprint_import, data)


@bind(router, "base.blueprint.export", "/settings/data/export")
async def blueprint_export(request, data: Query[BlueprintExportIn]):
    return await run_operation(request, queries.blueprints.blueprint_export, data)


@bind(router, "base.import.list", "/settings/data/imports")
async def import_list(request):
    return await run_operation(request, queries.blueprints.import_list)


@bind(router, "base.import.detail", "/settings/data/imports/detail")
async def import_detail(request, data: Query[ImportIdIn]):
    return await run_operation(request, queries.blueprints.import_detail, data)


@bind(router, "base.import.undo", "/settings/data/imports/undo")
async def import_undo(request, data: ImportUndoIn):
    return await run_operation(request, services.blueprints.import_undo, data)


@bind(router, "base.dataset.list", "/settings/data/datasets")
async def dataset_list(request):
    return await run_operation(request, queries.blueprints.dataset_list)


@bind(router, "base.hub.reset", "/settings/data/reset")
async def hub_reset(request, data: HubResetIn):
    return await run_operation(request, services.reset.hub_reset, data)


@bind(router, "base.hub.dumps", "/settings/data/dumps")
async def hub_dumps(request):
    return await run_operation(request, queries.dumps.hub_dumps)


@bind(router, "base.hub.dump_link", "/settings/data/dumps/link")
async def hub_dump_link(request, data: Query[HubDumpLinkIn]):
    return await run_operation(request, queries.dumps.hub_dump_link, data)
