"""What the cut copies and in which order (``base.tenancy.cut``); the cut itself, end to end, is
``base/tests/test_cut_shared_hubs.py``."""

from base.tenancy import cut


def test_the_tables_copied_are_every_hub_table_but_its_identity_and_its_migrations():
    tables = set(cut.tables_to_copy())

    assert {"printing_printer", "printing_printdevice_printers", "base_hubuser", "base_appactivation"} <= tables
    # The outbox goes too, only the business's own events (``cut.copy_rows``).
    assert {"live_outboxevent", "base_eventdelivery"} <= tables
    assert not {"base_hub_identity", "django_migrations"} & tables
    # Nothing of control's: the registry, the accounts, the sessions and who is in which business stay there.
    assert not {"base_hub", "control_cluster", "auth_user", "django_session", "base_membership"} & tables


def test_a_table_comes_after_the_tables_it_points_to_and_tables_in_a_cycle_go_together():
    tables = ["line", "ticket", "customer", "a", "b", "alone"]
    points_to = [("line", "ticket"), ("ticket", "customer"), ("a", "b"), ("b", "a"), ("line", "line")]

    order = cut.copy_order(tables, points_to)

    flat = [table for group in order for table in group]
    assert sorted(flat) == sorted(tables)
    assert flat.index("customer") < flat.index("ticket") < flat.index("line")
    assert ["a", "b"] in [sorted(group) for group in order]
    assert all(len(group) == 1 for group in order if not {"a", "b"} & set(group))


def test_the_order_is_the_same_whatever_order_the_tables_come_in():
    points_to = [("line", "ticket"), ("ticket", "customer")]

    assert cut.copy_order(["line", "ticket", "customer"], points_to) == cut.copy_order(
        ["customer", "line", "ticket"], points_to
    )


def test_only_a_business_s_own_events_and_their_deliveries_are_read_from_control_s_outbox():
    events, deliveries = cut.outbox_tables()

    assert cut.rows_of("printing_printer", "aurora") == ("", [])
    where, params = cut.rows_of(events, "aurora")
    assert "scope_kind" in where and "scope_key" in where and params == ["host", "aurora"]
    where, params = cut.rows_of(deliveries, "aurora")
    assert "event_id" in where and params == ["host", "aurora"]
