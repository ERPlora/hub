"""Live queries of the attendance app: which events re-run which screen (who is in is live)."""

from live.live_registry import live_registry

from apps.attendance import events

RECORD = [
    "attendance.record.clocked_in",
    "attendance.record.clocked_out",
    "attendance.break.started",
    "attendance.break.ended",
    "attendance.record.corrected",
    "attendance.record.flagged",
]


def attendance_queries():
    return {
        name: on
        for name, on in live_registry.subscribable.items()
        if name.startswith("attendance.")
    }


def test_the_registry_is_valid():
    assert live_registry.check() == []


def test_each_query_and_its_events():
    assert attendance_queries() == {
        # The clock screen: my day; a termination unlinks the record, a rename repaints the greeting.
        # A record newly linked to the account (staff.member.created) lets the clock work at once.
        "attendance.record.current": [
            *RECORD,
            "staff.member.created",
            "staff.member.updated",
            "staff.member.terminated",
        ],
        "attendance.record.list": [*RECORD, "staff.member.updated"],
        "attendance.record.detail": [*RECORD, "staff.member.updated"],
        "attendance.correction.list": ["attendance.record.corrected"],
        # ATTENDANCE-F11: who is in now follows every clocking, break, correction and flag.
        "attendance.presence.list": [*RECORD, "staff.member.updated", "staff.member.terminated"],
        "attendance.person.list": [
            "attendance.record.clocked_in",
            "staff.member.created",
            "staff.member.updated",
            "staff.member.terminated",
        ],
        "attendance.settings.get": ["attendance.settings.updated"],
    }


def test_the_export_is_a_one_shot_read():
    assert "attendance.record.export" not in attendance_queries()


def test_clocking_in_re_runs_the_clock_the_records_and_who_is_in():
    assert live_registry.affected([events.CLOCKED_IN]) >= {
        "attendance.record.current",
        "attendance.record.list",
        "attendance.presence.list",
    }
    assert "attendance.settings.get" not in live_registry.affected([events.CLOCKED_IN])


def test_a_correction_re_runs_its_history():
    assert "attendance.correction.list" in live_registry.affected(
        [events.RECORD_CORRECTED]
    )
