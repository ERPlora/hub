"""Live queries of the staff app and the events that re-run them after the COMMIT."""

from live.live_registry import live

from apps.staff.events import (
    MEMBER_ALL,
    MEMBER_DEACTIVATED,
    MEMBER_TERMINATED,
    MEMBER_UPDATED,
    ROLE_ALL,
    ROLE_UPDATED,
    SCHEDULE_ALL,
    SCHEDULE_DELETED,
    SCHEDULE_UPDATED,
    SETTINGS_UPDATED,
    TIME_OFF_ALL,
    TIME_OFF_APPROVED,
    TIME_OFF_CANCELLED,
    TIME_OFF_REJECTED,
)

# The directory and the pay show the role's name: a renamed role re-runs them.
live("staff.member.list", on=[*MEMBER_ALL, ROLE_UPDATED])
live(
    "staff.member.detail",
    on=[MEMBER_UPDATED, MEMBER_DEACTIVATED, MEMBER_TERMINATED, ROLE_UPDATED],
)
live("staff.member.mine", on=[*MEMBER_ALL, ROLE_UPDATED])
live("staff.member.compensation", on=[*MEMBER_ALL, ROLE_UPDATED])
live("staff.member.stats", on=[*MEMBER_ALL, *TIME_OFF_ALL])
live("staff.commission.summary", on=[*MEMBER_ALL, ROLE_UPDATED])
# Sales' events, by name (Sales is no requirement): a charge, a void or a refund changes what was sold.
SALE_FIGURES = ["sale.sale.completed", "sale.sale.voided", "sale.sale.refunded"]
live("staff.commission.report", on=[*MEMBER_ALL, ROLE_UPDATED, *SALE_FIGURES])
# «Members» of a role counts the active people.
live("staff.role.list", on=[*ROLE_ALL, *MEMBER_ALL])
live("staff.schedule.list", on=[*SCHEDULE_ALL, MEMBER_TERMINATED])
live(
    "staff.schedule.detail", on=[SCHEDULE_UPDATED, SCHEDULE_DELETED, MEMBER_TERMINATED]
)
# A pending request changes nothing available: only an approval or its cancellation does.
live(
    "staff.availability.for_member",
    on=[*SCHEDULE_ALL, TIME_OFF_APPROVED, TIME_OFF_CANCELLED, MEMBER_TERMINATED],
)
live("staff.time_off.list", on=[*TIME_OFF_ALL, MEMBER_UPDATED, MEMBER_TERMINATED])
live(
    "staff.time_off.detail",
    on=[
        TIME_OFF_APPROVED,
        TIME_OFF_REJECTED,
        TIME_OFF_CANCELLED,
        MEMBER_UPDATED,
        MEMBER_TERMINATED,
    ],
)
live(
    "staff.time_off.today",
    on=[TIME_OFF_APPROVED, TIME_OFF_CANCELLED, MEMBER_UPDATED, MEMBER_TERMINATED],
)
live("staff.time_off.mine", on=[*TIME_OFF_ALL, *MEMBER_ALL])
live("staff.settings.get", on=[SETTINGS_UPDATED])
