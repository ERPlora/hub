"""Ninja routes of the online booking app: each route calls exactly one operation and holds no logic.

No path parameters (as ``apps.demo``): a booking travels in the input (query string on GET, body on POST), by
its id, its number or the customer and the day. The public operations have session routes too, for the owner's
and the admin's preview (``online_booking.public``); the page without a session (base, ``/p/<slug>/book``)
calls them in-process with the public door's context. The platform's reaction (``customer.erase``) has no
route.
"""

from live.ninja import bind, run_operation
from ninja import Query, Router
from ninja.decorators import decorate_view

from apps.online_booking import queries, services
from apps.online_booking.schemas import (
    BookingListIn,
    BookingRefIn,
    CancelIn,
    PublicBookIn,
    PublicCancelIn,
    PublicServicesIn,
    PublicSlotsIn,
    SettingsIn,
    TokenIn,
)
from base.public_images import MAX_UPLOAD_BODY
from base.request_body import accept_body_up_to
from base.schemas.public_images import ImageUploadIn

router = Router(tags=["online_booking"])


# The inbox


@bind(router, "online_booking.booking.list", "/online_booking/bookings")
async def booking_list(request, params: Query[BookingListIn]):
    return await run_operation(request, queries.bookings.list_bookings, params)


@bind(router, "online_booking.booking.get", "/online_booking/bookings/detail")
async def booking_get(request, params: Query[BookingRefIn]):
    return await run_operation(request, queries.bookings.get_booking, params)


@bind(router, "online_booking.booking.confirm", "/online_booking/bookings/confirm")
async def booking_confirm(request, data: BookingRefIn):
    return await run_operation(request, services.bookings.confirm_booking, data)


@bind(router, "online_booking.booking.complete", "/online_booking/bookings/complete")
async def booking_complete(request, data: BookingRefIn):
    return await run_operation(request, services.bookings.complete_booking, data)


@bind(router, "online_booking.booking.no_show", "/online_booking/bookings/no_show")
async def booking_no_show(request, data: BookingRefIn):
    return await run_operation(request, services.bookings.no_show_booking, data)


@bind(router, "online_booking.booking.cancel", "/online_booking/bookings/cancel")
async def booking_cancel(request, data: CancelIn):
    return await run_operation(request, services.bookings.cancel_booking, data)


@bind(router, "online_booking.booking.delete", "/online_booking/bookings/delete")
async def booking_delete(request, data: BookingRefIn):
    return await run_operation(request, services.bookings.delete_booking, data)


# Settings


@bind(router, "online_booking.settings.get", "/online_booking/settings")
async def settings_get(request):
    return await run_operation(request, queries.settings.get_settings)


@bind(router, "online_booking.settings.update", "/online_booking/settings")
async def settings_update(request, data: SettingsIn):
    return await run_operation(request, services.settings.update_settings, data)


# The logo's file comes in base64, more than Django's ceiling for any other view.
@bind(router, "online_booking.settings.upload_logo", "/online_booking/settings/logo", status=201)
@decorate_view(accept_body_up_to(MAX_UPLOAD_BODY))
async def settings_upload_logo(request, data: ImageUploadIn):
    return await run_operation(request, services.logo.upload_logo, data)


# The public page (session routes: the preview)


@bind(router, "online_booking.public.page", "/online_booking/public/page")
async def public_page(request):
    return await run_operation(request, queries.page.public_page)


@bind(router, "online_booking.public.services", "/online_booking/public/services")
async def public_services(request, params: Query[PublicServicesIn]):
    return await run_operation(request, queries.offer.public_services, params)


@bind(router, "online_booking.public.slots", "/online_booking/public/slots")
async def public_slots(request, params: Query[PublicSlotsIn]):
    return await run_operation(request, queries.offer.public_slots, params)


@bind(router, "online_booking.public.booking", "/online_booking/public/booking")
async def public_booking(request, params: Query[TokenIn]):
    return await run_operation(request, queries.links.public_booking, params)


@bind(router, "online_booking.public.book", "/online_booking/public/book")
async def public_book(request, data: PublicBookIn):
    return await run_operation(request, services.public_booking.public_book, data)


@bind(router, "online_booking.public.cancel", "/online_booking/public/cancel")
async def public_cancel(request, data: PublicCancelIn):
    return await run_operation(request, services.links.public_cancel, data)
