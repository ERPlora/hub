//! hub#1406: the daily-usage heartbeat is a WIRE CONTRACT with the SaaS
//! (`saas` stores `verifactu_pending_depth` / `verifactu_oldest_pending_at`,
//! and distinguishes an honest `0` from an absent «I don't know»).
//!
//! These literals are the frozen payload. They were written — and green —
//! BEFORE the decoupling of `daily_usage` from `erplora_verifactu`
//! (PendingObligation, hub#1406), and they must stay green after it: same
//! state in, same bytes out.

use erplora_server::daily_usage::{DailyUsageHeartbeat, PendingObligationFields};

fn base() -> DailyUsageHeartbeat {
    DailyUsageHeartbeat {
        orders_today: Some(7),
        last_sale_at: Some("2026-09-01T10:00:00Z".to_string()),
        terminals: Some(2),
        last_user_activity_at: Some("2026-09-01T09:00:00Z".to_string()),
        cert_version: Some(3),
        cert_not_after: Some("2027-01-01".to_string()),
        hub_version: "1.2.3".to_string(),
        pending: PendingObligationFields(vec![(
            "verifactu".to_string(),
            2,
            Some("2026-08-30T08:00:00Z".to_string()),
        )]),
        cpu_pct: Some(1.5),
        memory_used_mb: Some(100.0),
        memory_limit_mb: Some(512.0),
        memory_peak_mb: Some(222.0),
        transmission_route: Some("delegated"),
    }
}

#[test]
fn hub1406_full_heartbeat_serializes_byte_identically() {
    let expected = concat!(
        r#"{"orders_today":7,"last_sale_at":"2026-09-01T10:00:00Z","terminals":2,"#,
        r#""last_user_activity_at":"2026-09-01T09:00:00Z","cert_version":3,"#,
        r#""cert_not_after":"2027-01-01","hub_version":"1.2.3","#,
        r#""verifactu_pending_depth":2,"verifactu_oldest_pending_at":"2026-08-30T08:00:00Z","#,
        r#""cpu_pct":1.5,"memory_used_mb":100.0,"memory_limit_mb":512.0,"memory_peak_mb":222.0,"#,
        r#""transmission_route":"delegated"}"#,
    );
    assert_eq!(serde_json::to_string(&base()).unwrap(), expected);
}

/// The honest zero: queue readable and EMPTY sends `0`, never an absent field —
/// absent means «could not read it» and would show in the fleet panel as a hub
/// gone silent (the exact conflation hub#326 forbids).
#[test]
fn hub1406_an_empty_queue_is_a_zero_not_an_absence() {
    let hb = DailyUsageHeartbeat {
        orders_today: None,
        last_sale_at: None,
        terminals: None,
        last_user_activity_at: None,
        cert_version: None,
        cert_not_after: None,
        hub_version: "1.2.3".to_string(),
        pending: PendingObligationFields(vec![("verifactu".to_string(), 0, None)]),
        cpu_pct: None,
        memory_used_mb: None,
        memory_limit_mb: None,
        memory_peak_mb: None,
        transmission_route: None,
    };
    assert_eq!(
        serde_json::to_string(&hb).unwrap(),
        r#"{"hub_version":"1.2.3","verifactu_pending_depth":0}"#
    );
}

/// And the unreadable queue really is ABSENT (both fields), not a fabricated zero.
#[test]
fn hub1406_an_unreadable_queue_is_absent() {
    let hb = DailyUsageHeartbeat {
        orders_today: None,
        last_sale_at: None,
        terminals: None,
        last_user_activity_at: None,
        cert_version: None,
        cert_not_after: None,
        hub_version: "1.2.3".to_string(),
        pending: PendingObligationFields::default(),
        cpu_pct: None,
        memory_used_mb: None,
        memory_limit_mb: None,
        memory_peak_mb: None,
        transmission_route: None,
    };
    assert_eq!(
        serde_json::to_string(&hb).unwrap(),
        r#"{"hub_version":"1.2.3"}"#
    );
}

/// hub#1441 — the transmission route is a CLOSED vocabulary on the wire, and both words have to
/// travel verbatim: the SaaS ignores anything that is not one of the two (saas#1745), so a
/// misspelling here is a hub whose route silently never updates.
#[test]
fn hub1441_both_routes_travel_verbatim() {
    for route in ["own", "delegated"] {
        let mut hb = base();
        hb.transmission_route = Some(route);
        assert!(
            serde_json::to_string(&hb)
                .unwrap()
                .ends_with(&format!(r#","transmission_route":"{route}"}}"#)),
            "the route travels as the word the SaaS programs against"
        );
    }
}

/// And an unknown route is ABSENT, not empty: `""` is read by the SaaS as `delegated`
/// (its own legacy tolerance), so sending it for a hub whose route could not be read would
/// silently claim the delegated route — the exact fabrication this field must never make.
#[test]
fn hub1441_an_unknown_route_is_absent_never_an_empty_string() {
    let mut hb = base();
    hb.transmission_route = None;

    let body = serde_json::to_string(&hb).unwrap();
    assert!(
        !body.contains("transmission_route"),
        "«I could not read it» is the field not being there at all: {body}"
    );
}
