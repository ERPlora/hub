//! hub#1406: the daily-usage heartbeat is a WIRE CONTRACT with the SaaS
//! (`saas` stores `verifactu_pending_depth` / `verifactu_oldest_pending_at`,
//! and distinguishes an honest `0` from an absent «I don't know»).
//!
//! These literals are the frozen payload. They were written — and green —
//! BEFORE the decoupling of `daily_usage` from `erplora_verifactu`
//! (PendingObligation, hub#1406), and they must stay green after it: same
//! state in, same bytes out.
//!
//! **`cert_version`/`cert_not_after` left the payload in hub#1435.** They reported which delegated
//! certificate this hub held, and there is no delegated certificate: the SaaS dropped the four
//! `reported_cert_*` columns in saas#1435 phase 2 and IGNORES the fields when an un-updated hub
//! still sends them. Dropping them here is therefore safe in both directions — a new hub against an
//! old SaaS writes two columns fewer, an old hub against the new SaaS is ignored.

use erplora_server::daily_usage::{ActivityEvent, DailyUsageHeartbeat, PendingObligationFields};

fn base() -> DailyUsageHeartbeat {
    DailyUsageHeartbeat {
        orders_today: Some(7),
        last_sale_at: Some("2026-09-01T10:00:00Z".to_string()),
        terminals: Some(2),
        active_users: Some(3),
        last_user_activity_at: Some("2026-09-01T09:00:00Z".to_string()),
        activity: vec![ActivityEvent {
            id: "e-1".to_string(),
            kind: "cash_open".to_string(),
            occurred_at: "2026-09-01T09:00:00.250Z".to_string(),
            actor: "pin-42".to_string(),
        }],
        core_version: "1.2.3".to_string(),
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
        r#""active_users":3,"#,
        r#""last_user_activity_at":"2026-09-01T09:00:00Z","#,
        r#""activity":[{"id":"e-1","type":"cash_open","at":"2026-09-01T09:00:00.250Z","actor":"pin-42"}],"#,
        r#""core_version":"1.2.3","#,
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
        active_users: None,
        last_user_activity_at: None,
        activity: Vec::new(),
        core_version: "1.2.3".to_string(),
        pending: PendingObligationFields(vec![("verifactu".to_string(), 0, None)]),
        cpu_pct: None,
        memory_used_mb: None,
        memory_limit_mb: None,
        memory_peak_mb: None,
        transmission_route: None,
    };
    assert_eq!(
        serde_json::to_string(&hb).unwrap(),
        r#"{"core_version":"1.2.3","verifactu_pending_depth":0}"#
    );
}

/// And the unreadable queue really is ABSENT (both fields), not a fabricated zero.
#[test]
fn hub1406_an_unreadable_queue_is_absent() {
    let hb = DailyUsageHeartbeat {
        orders_today: None,
        last_sale_at: None,
        terminals: None,
        active_users: None,
        last_user_activity_at: None,
        activity: Vec::new(),
        core_version: "1.2.3".to_string(),
        pending: PendingObligationFields::default(),
        cpu_pct: None,
        memory_used_mb: None,
        memory_limit_mb: None,
        memory_peak_mb: None,
        transmission_route: None,
    };
    assert_eq!(
        serde_json::to_string(&hb).unwrap(),
        r#"{"core_version":"1.2.3"}"#
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

/// hub#1814 — the seat census is the number the SaaS cannot obtain on its own: whoever signs in
/// with a PIN has no ERPlora account, so without this field the invitation gate sees a Free hub
/// of one where three people work. It travels under the exact name the SaaS ingests (saas#2022).
#[test]
fn hub1814_the_seat_census_travels_under_the_name_the_saas_ingests() {
    let body = serde_json::to_string(&base()).unwrap();
    assert!(
        body.contains(r#""active_users":3"#),
        "the SaaS reads this exact key into `Hub.reported_active_users`: {body}"
    );
}

/// And the absence contract, which is the whole reason the field is an `Option`: a hub that could
/// not read its census sends NOTHING. A fabricated `0` would say «nobody works here» and hand a
/// free seat to a hub that is already full — the SaaS keeps the value it had (saas#2022).
#[test]
fn hub1814_an_uncountable_census_is_absent_never_a_fabricated_zero() {
    let mut hb = base();
    hb.active_users = None;

    let body = serde_json::to_string(&hb).unwrap();
    assert!(
        !body.contains("active_users"),
        "«I could not count» is the field not being there at all: {body}"
    );
}

/// The other half: a census that WAS read and is empty sends an honest `0`. If the empty case
/// stayed silent the SaaS could not tell it from a hub whose census would not read, and the two
/// mean opposite things for the gate.
#[test]
fn hub1814_an_empty_census_is_an_honest_zero() {
    let mut hb = base();
    hb.active_users = Some(0);

    assert!(
        serde_json::to_string(&hb)
            .unwrap()
            .contains(r#""active_users":0"#),
        "an explicit zero is «I counted and nobody is here», and it has to travel"
    );
}

// ── saas#2129 — the business activity events ─────────────────────────────────────────────────

/// **Four keys and no more**, under the exact names the SaaS reads.
///
/// This is the contract between the two repos and the privacy guard at once: the receiver reads
/// `id`, `type`, `at` and `actor`, and a fifth field added here would either be ignored there —
/// losing the data silently — or carry something about the **END CUSTOMER** into the control
/// plane. Asserting the exact key set is what turns that into a red test instead of a discovery.
/// Mind `type` and `at`: the Rust fields are called `kind` and `occurred_at`.
#[test]
fn saas2129_an_event_travels_with_exactly_the_four_keys_the_saas_reads() {
    let event = ActivityEvent {
        id: "e-1".to_string(),
        kind: "cash_open".to_string(),
        occurred_at: "2026-09-01T09:00:00.250Z".to_string(),
        actor: "pin-42".to_string(),
    };

    let wire = serde_json::to_value(&event).unwrap();
    let mut keys: Vec<&str> = wire
        .as_object()
        .unwrap()
        .keys()
        .map(String::as_str)
        .collect();
    keys.sort_unstable();
    assert_eq!(keys, ["actor", "at", "id", "type"], "{wire}");
}

/// **With nothing to report the field does NOT travel** — not even as `[]`.
///
/// Deliberately unlike the contract of `active_users` and `verifactu_pending_depth`, where an
/// explicit `0` and an absence mean opposite things. Here there is no such distinction: an empty
/// queue and a queue that could not be read both end in "this beat delivers no events", and in
/// both the receiver writes nothing — the events stay in the hub's buffer and the next beat
/// retries, so nothing is lost by staying quiet. And since this rides the beat, and most beats
/// from most hubs come from an idle hub, sending `"activity":[]` would be noise on nearly all.
#[test]
fn saas2129_nothing_to_report_means_the_field_is_absent_not_an_empty_array() {
    let mut hb = base();
    hb.activity = Vec::new();

    // ⚠️ By KEY, not by substring: `body.contains("activity")` also matches
    // `last_user_activity_at`, which travels right beside it, so the assertion would pass
    // whatever the field did. A real trap, hit while writing this test.
    let wire = serde_json::to_value(&hb).unwrap();
    assert!(
        !wire.as_object().unwrap().contains_key("activity"),
        "«no tengo nada» es que el campo no esté: {wire}"
    );
}

/// And a batch travels WHOLE and in order. The SaaS deduplicates by `id`, so a re-send costs
/// nothing — but dropping one on the way is unrecoverable: what is not collected is not rebuilt.
#[test]
fn saas2129_a_batch_travels_whole_and_in_order() {
    let mut hb = base();
    hb.activity = vec![
        ActivityEvent {
            id: "e-1".to_string(),
            kind: "login".to_string(),
            occurred_at: "2026-09-01T09:00:00.100Z".to_string(),
            actor: "pin-42".to_string(),
        },
        ActivityEvent {
            id: "e-2".to_string(),
            kind: "sale".to_string(),
            occurred_at: "2026-09-01T09:00:00.900Z".to_string(),
            actor: "pin-42".to_string(),
        },
    ];

    let wire = serde_json::to_value(&hb).unwrap();
    let sent = wire["activity"].as_array().unwrap();
    assert_eq!(sent.len(), 2, "{wire}");
    assert_eq!(sent[0]["id"], "e-1", "el más viejo primero");
    assert_eq!(sent[1]["id"], "e-2");
}
