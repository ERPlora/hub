"""Ninja routes of the website app: each route calls exactly one operation and holds no logic.

No path parameters (as ``apps.demo``). Two routes answer something else than JSON: the preview, the draft's HTML that
the editor frames (with the preview's CSP, framed only by the hub itself, never cached), and the QR, the image file to
download (or the operation's JSON to a client that asks for JSON alone, as verifactu's blank model). The image upload
takes its file in base64, more than Django's ceiling for any other view. The public reads have no session
(``auth=None``): their operations check the site is published and count each visitor.
"""

import base64

from django.http import HttpResponse
from live.ninja import bind, run_operation
from ninja import Query, Router
from ninja.decorators import decorate_view

from apps.website import queries, services
from apps.website.csp import preview_policy
from apps.website.schemas import CategoriesIn, ImageUploadIn, QrIn, SaveIn
from base.request_body import accept_body_up_to

router = Router(tags=["website"])

#: The upload's body: 5 MB of image in base64 (6 990 508 characters) and its JSON around it.
MAX_UPLOAD_BODY = 7_100_000


# The editor


@bind(router, "website.site.get", "/website/site")
async def site_get(request):
    return await run_operation(request, queries.get_site)


@bind(router, "website.site.save", "/website/site")
async def site_save(request, data: SaveIn):
    return await run_operation(request, services.save_site, data)


@bind(router, "website.site.publish", "/website/site/publish")
async def site_publish(request):
    return await run_operation(request, services.publish_site)


@bind(router, "website.site.unpublish", "/website/site/unpublish")
async def site_unpublish(request):
    return await run_operation(request, services.unpublish_site)


@bind(
    router,
    "website.site.preview",
    "/website/site/preview",
    openapi_extra={
        "responses": {
            200: {
                "description": "The draft rendered as the public page (text/html), for the editor's frame.",
                "content": {"text/html": {"schema": {"type": "string"}}},
            }
        }
    },
)
async def site_preview(request):
    preview = await run_operation(request, queries.preview_site)
    response = HttpResponse(preview.html, content_type="text/html; charset=utf-8")
    response["Cache-Control"] = "no-store"
    response["X-Frame-Options"] = "SAMEORIGIN"
    response._csp_config = preview_policy()
    return response


@bind(router, "website.image.upload", "/website/images", status=201)
@decorate_view(accept_body_up_to(MAX_UPLOAD_BODY))
async def image_upload(request, data: ImageUploadIn):
    return await run_operation(request, services.upload_image, data)


@bind(
    router,
    "website.qr.get",
    "/website/qr",
    openapi_extra={
        "responses": {
            200: {
                "description": "The QR as the image it is, or the operation's JSON when only JSON is accepted.",
                "content": {
                    "image/png": {"schema": {"type": "string", "format": "binary"}},
                    "image/svg+xml": {"schema": {"type": "string"}},
                },
            }
        }
    },
)
async def qr_get(request, params: Query[QrIn]):
    qr = await run_operation(request, queries.get_qr, params)
    accepts = request.headers.get("Accept", "")
    if "application/json" in accepts and "image/" not in accepts:
        return qr
    return HttpResponse(
        base64.b64decode(qr.content_base64),
        content_type=qr.content_type,
        headers={"Content-Disposition": f'attachment; filename="{qr.filename}"'},
    )


@bind(router, "website.catalog.categories", "/website/catalog/categories")
async def catalog_categories(request, params: Query[CategoriesIn]):
    return await run_operation(request, queries.list_categories, params)


# The public reads (no session)


@bind(router, "website.public.site", "/website/public/site", auth=None)
async def public_site(request):
    return await run_operation(request, queries.public_site)


@bind(router, "website.public.catalog", "/website/public/catalog", auth=None)
async def public_catalog(request):
    return await run_operation(request, queries.public_catalog)


@bind(router, "website.public.reviews", "/website/public/reviews", auth=None)
async def public_reviews(request):
    return await run_operation(request, queries.public_reviews)
