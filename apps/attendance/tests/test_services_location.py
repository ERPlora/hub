"""Where the device that clocks is: the counter or a personal device, and the workplace radius."""

import dataclasses

import pytest
from django.test import RequestFactory
from django.utils import timezone
from geopy.distance import geodesic

from apps.attendance.models import AttendanceSettings, Record
from base import access
from base.models.access import TrustedDevice

from .conftest import FAR, HUB_DB, NEAR, WORKPLACE, ctx_for, refused, run

pytestmark = HUB_DB


def location_on(
    radius: int = 100, workplace=WORKPLACE, hours: int = 12
) -> AttendanceSettings:
    lat, lng = workplace if workplace else (None, None)
    return AttendanceSettings.objects.create(
        require_location=True,
        geofence_radius_m=radius,
        workplace_lat=lat,
        workplace_lng=lng,
        auto_close_after_hours=hours,
    )


# The workplace radius (ATTENDANCE-F03): only personal devices, never the clock-out. Whether a device is
# personal is the server's to know, never the payload's: it is the mode of
# the session's device, which an administrator chose on it (BASE-F62, «Settings › This device»).


def on_device(ctx, mode: str | None):
    """``ctx`` as it comes from a browser whose ``hub_device`` cookie names a device of this hub in ``mode``
    (``None``: a cookie the hub does not know)."""
    token = access.new_device_token()
    if mode is not None:
        TrustedDevice.objects.create(
            token_digest=access.token_digest(token), mode=mode, last_entry_at=timezone.now()
        )
    request = RequestFactory().post("/api/attendance/clock-in")
    request.COOKIES[access.DEVICE_COOKIE] = token
    return dataclasses.replace(ctx, request=request)


@pytest.fixture
def personal_device(person):
    """Ana's context on her own phone, which an administrator made personal."""

    def make(*args, **kwargs):
        member, ctx = person(*args, **kwargs)
        return member, on_device(ctx, access.PERSONAL)

    return make


def test_a_device_made_personal_clocks_as_personal(person, clock):
    from apps.attendance import services

    clock("2026-10-06T07:00")
    _, ctx = person()
    assert services.location.device_source(on_device(ctx, access.PERSONAL)) == "personal"
    run("attendance.record.clock_in", {}, on_device(ctx, access.PERSONAL))
    assert Record.objects.get().source == "personal"


def test_the_counter_pos_an_unknown_browser_and_a_call_without_one_clock_as_shared(person, clock):
    # The strict fallback (the old module's): a device the hub does not know, or a caller with no browser
    # (an integration's API key, the system), is never asked for a location.
    from apps.attendance import services

    _, ctx = person()
    assert services.location.device_source(on_device(ctx, access.SHARED)) == "shared"
    assert services.location.device_source(on_device(ctx, None)) == "shared"
    assert services.location.device_source(ctx) == "shared"


def test_the_payload_never_says_the_device(person, clock):
    from apps.attendance import services

    clock("2026-10-06T07:00")
    location_on()
    _, ctx = person()
    shared = on_device(ctx, access.SHARED)
    assert services.location.device_source(shared) == "shared"
    run("attendance.record.clock_in", {"source": "personal"}, shared)
    assert (Record.objects.get().source, Record.objects.get().in_within_radius) == ("shared", None)


def test_a_personal_device_must_send_its_position(clock, personal_device):
    clock("2026-10-06T07:00")
    location_on()
    _, ctx = personal_device()
    refused("attendance.location_required", "attendance.record.clock_in", {}, ctx)


def test_without_the_workplace_set_a_personal_device_cannot_clock_in(clock, personal_device):
    clock("2026-10-06T07:00")
    location_on(workplace=None)
    _, ctx = personal_device()
    data = {"lat": NEAR[0], "lng": NEAR[1]}
    refused("attendance.workplace_not_set", "attendance.record.clock_in", data, ctx)


def test_outside_the_radius_it_says_how_far(clock, personal_device):
    clock("2026-10-06T07:00")
    location_on(radius=100)
    _, ctx = personal_device()
    data = {"lat": FAR[0], "lng": FAR[1], "accuracy_m": 9.5}
    error = refused("attendance.outside_radius", "attendance.record.clock_in", data, ctx)
    assert error.message == (
        "You are 855 m from the workplace, outside the allowed 100 m. Move closer to clock in, or clock in at the counter."
    )


def test_inside_the_radius_the_day_keeps_where_it_was_clocked(clock, personal_device):
    clock("2026-10-06T07:00")
    location_on(radius=100)
    _, ctx = personal_device()
    run("attendance.record.clock_in", {"lat": NEAR[0], "lng": NEAR[1], "accuracy_m": 9.5}, ctx)
    day = Record.objects.get()
    assert (day.source, day.in_lat, day.in_lng, day.in_accuracy_m, day.in_within_radius) == (
        "personal",
        NEAR[0],
        NEAR[1],
        9.5,
        True,
    )
    # The Hub measures the distance itself (WGS-84 geodesic), never the device.
    assert day.in_distance_m == pytest.approx(geodesic(WORKPLACE, NEAR).meters, abs=0.5)


def test_the_counter_pos_is_never_asked_for_a_location(person, clock):
    clock("2026-10-06T07:00")
    location_on()
    _, ctx = person()
    run("attendance.record.clock_in", {}, ctx)
    assert Record.objects.get().in_within_radius is None


def test_a_position_nobody_asked_for_keeps_only_how_far_never_where(person, clock):
    # The exact coordinates are kept only when the business requires
    # the location and the device is personal; otherwise only the distance, inside/outside and accuracy.
    clock("2026-10-06T07:00")
    AttendanceSettings.objects.create(workplace_lat=WORKPLACE[0], workplace_lng=WORKPLACE[1])
    _, ctx = person()
    run("attendance.record.clock_in", {"lat": FAR[0], "lng": FAR[1], "accuracy_m": 7}, ctx)
    day = Record.objects.get()
    assert (day.in_lat, day.in_lng) == (None, None)
    assert (round(day.in_distance_m), day.in_within_radius, day.in_accuracy_m) == (855, False, 7)


def test_not_required_a_personal_device_keeps_no_coordinates_either(clock, personal_device):
    clock("2026-10-06T07:00")
    AttendanceSettings.objects.create(workplace_lat=WORKPLACE[0], workplace_lng=WORKPLACE[1])
    _, ctx = personal_device()
    run("attendance.record.clock_in", {"lat": NEAR[0], "lng": NEAR[1]}, ctx)
    day = Record.objects.get()
    assert (day.in_lat, day.in_lng, day.in_within_radius) == (None, None, True)


def test_clocking_out_is_never_blocked_by_the_location(person, clock):
    clock("2026-10-06T07:00")
    _, ctx = person()
    run("attendance.record.clock_in", {}, ctx)
    location_on(radius=50)
    clock("2026-10-06T15:00")
    run("attendance.record.clock_out", {"lat": FAR[0], "lng": FAR[1], "accuracy_m": 12}, ctx)
    day = Record.objects.get()
    assert (day.status, round(day.out_distance_m), day.out_within_radius, day.out_accuracy_m) == ("closed", 855, False, 12)
    # The shared device: no coordinates kept.
    assert (day.out_lat, day.out_lng) == (None, None)
    # And without a position at all.
    clock("2026-10-07T07:00")
    run("attendance.record.clock_in", {}, ctx)
    clock("2026-10-07T15:00")
    run("attendance.record.clock_out", {}, ctx)
    assert Record.objects.filter(status="closed").count() == 2


def test_a_personal_device_out_of_the_radius_still_clocks_out_and_keeps_where(clock, personal_device):
    clock("2026-10-06T07:00")
    location_on(radius=100)
    _, ctx = personal_device()
    run("attendance.record.clock_in", {"lat": NEAR[0], "lng": NEAR[1]}, ctx)
    clock("2026-10-06T15:00")
    run("attendance.record.clock_out", {"lat": FAR[0], "lng": FAR[1]}, ctx)
    day = Record.objects.get()
    assert (day.status, day.out_lat, day.out_lng, day.out_within_radius) == ("closed", FAR[0], FAR[1], False)


def test_the_clock_out_keeps_where_from_the_device_that_clocks_out(person, clock):
    # In at the counter, out from her own phone: the position is the phone's, which the business asked for.
    clock("2026-10-06T07:00")
    location_on(radius=100)
    _, ctx = person()
    run("attendance.record.clock_in", {}, on_device(ctx, access.SHARED))
    clock("2026-10-06T15:00")
    run("attendance.record.clock_out", {"lat": NEAR[0], "lng": NEAR[1]}, on_device(ctx, access.PERSONAL))
    day = Record.objects.get()
    assert (day.source, day.out_lat, day.out_lng, day.out_within_radius) == ("shared", NEAR[0], NEAR[1], True)


def test_clocking_someone_else_from_a_personal_device_asks_for_no_location(person, clock, make_user):
    # ATTENDANCE-F12: the manager vouches for the person (Homebase, Deputy: the radius checks an employee's own
    # clock-in on their phone). Never refused for where the manager is, and nobody keeps the manager's position.
    clock("2026-10-06T07:00")
    location_on(radius=100)
    ana, _ = person()
    boss = make_user("boss", role="hub_manager")
    manager = on_device(ctx_for("hub_manager", actor=boss), access.PERSONAL)
    run("attendance.record.clock_in", {"member": "ana"}, manager)
    run("attendance.record.clock_out", {"member": "ana", "lat": FAR[0], "lng": FAR[1]}, manager)
    run("attendance.record.clock_in", {"member": "ana", "lat": FAR[0], "lng": FAR[1]}, manager)
    first, second = Record.objects.order_by("clock_in_at", "id")
    assert (first.status, first.in_lat, first.out_lat, second.status, second.in_lat) == ("closed", None, None, "open", None)
    assert (second.in_within_radius, first.out_within_radius) == (False, False)

