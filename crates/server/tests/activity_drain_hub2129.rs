//! **The drain has to run faster than the tap** (review of saas#2129).
//!
//! Two things the first version took for granted and that are false, and both end in the one
//! thing this issue exists to prevent — losing data that cannot be rebuilt afterwards:
//!
//! 1. **The hub does NOT beat often: it beats every 24 h.** The beat's tick shares
//!    `HUB_ENTITLEMENT_REVALIDATE_SECS`, whose default is 86 400 and which no deployment sets.
//!    With a bite of 500 the drain was ~500 events **a day**, and a busy till produces more than
//!    that: the buffer climbs to its ceiling and from then on the trim discards the oldest
//!    **every day, for ever**, with an `eprintln!` as the only trace. The drain has to empty
//!    within the SAME tick, not the next one.
//! 2. **A bare 2xx is no proof the Cloud stored anything.** It is equally the answer of a SaaS
//!    whose ingest blew up (the view swallows that on purpose) and of one that does not know
//!    `activity` yet. Only `activity_ack` says "it arrived and was processed", and only that
//!    deletes.

use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Arc;
use std::sync::Mutex as StdMutex;

use axum::http::StatusCode;
use axum::routing::post;
use axum::{Json, Router};
use erplora_db::testutil::fresh_db;
use erplora_runtime::activity_log::{self, Kind, MAX_EVENTS_PER_BEAT};
use erplora_runtime::Runtime;
use erplora_server::daily_usage::{self, ActivityEvent};
use serde_json::{json, Value};
use tokio::sync::RwLock;

const HUB: &str = "hub-drain";

/// What the fake Cloud answers to each beat, in order. `None` = 500.
type Script = Arc<StdMutex<Vec<Option<Value>>>>;

struct Cloud {
    base_url: String,
    /// How many beats it has received.
    beats: Arc<AtomicUsize>,
    /// How many events it has seen in total.
    events: Arc<AtomicUsize>,
}

/// Stands up a fake Cloud answering whatever `script` says (and, once spent, always acks).
async fn cloud(script: Vec<Option<Value>>) -> Cloud {
    let script: Script = Arc::new(StdMutex::new(script));
    let beats = Arc::new(AtomicUsize::new(0));
    let events = Arc::new(AtomicUsize::new(0));

    let state = (script, beats.clone(), events.clone());
    let app = Router::new()
        .route(
            "/api/v1/hub/device/heartbeat/",
            post(
                |axum::extract::State((script, beats, events)): axum::extract::State<(
                    Script,
                    Arc<AtomicUsize>,
                    Arc<AtomicUsize>,
                )>,
                 Json(body): Json<Value>| async move {
                    beats.fetch_add(1, Ordering::SeqCst);
                    let carried = body
                        .get("activity")
                        .and_then(Value::as_array)
                        .map(Vec::len)
                        .unwrap_or(0);
                    events.fetch_add(carried, Ordering::SeqCst);

                    let next = {
                        let mut script = script.lock().unwrap();
                        if script.is_empty() {
                            Some(json!({"ok": true, "activity_ack": true}))
                        } else {
                            script.remove(0)
                        }
                    };
                    match next {
                        Some(body) => (StatusCode::OK, Json(body)),
                        None => (
                            StatusCode::INTERNAL_SERVER_ERROR,
                            Json(json!({"error": "boom"})),
                        ),
                    }
                },
            ),
        )
        .with_state(state);

    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });

    Cloud {
        base_url: format!("http://{address}"),
        beats,
        events,
    }
}

async fn hub_with(events: usize) -> Arc<RwLock<Runtime>> {
    let rt = Runtime::with_hub_id(Box::new(fresh_db().await), HUB);
    rt.ensure_system_tables().await.unwrap();
    for n in 0..events {
        activity_log::record(
            rt.db(),
            HUB,
            Kind::Sale,
            "ana",
            // Distinct, increasing instants: the drain's order is the real one.
            &format!("2026-10-01T00:00:{:02}.{:03}Z", n / 1000, n % 1000),
        )
        .await
        .unwrap();
    }
    Arc::new(RwLock::new(rt))
}

fn auth() -> cloud_client::Auth {
    cloud_client::Auth::HubToken {
        hub_id: HUB.to_string(),
        token: "machine-token".to_string(),
    }
}

async fn still_pending(runtime: &Arc<RwLock<Runtime>>) -> usize {
    let rt = runtime.read().await;
    activity_log::pending(rt.db(), HUB, MAX_EVENTS_PER_BEAT)
        .await
        .unwrap()
        .len()
}

/// What the first beat took, exactly as `collect_daily_usage` builds it.
async fn first_bite(runtime: &Arc<RwLock<Runtime>>) -> Vec<ActivityEvent> {
    let rt = runtime.read().await;
    activity_log::pending(rt.db(), HUB, MAX_EVENTS_PER_BEAT)
        .await
        .unwrap()
        .into_iter()
        .map(ActivityEvent::from)
        .collect()
}

// ── 1. The drain empties within the same tick ────────────────────────────────────────────────

/// **The case that motivates the fix.** 1200 events waiting and a single tick: with one bite per
/// tick, at 24 h the hub would take THREE DAYS to deliver them — and would keep producing
/// meanwhile. Here it empties completely before the tick is over.
#[tokio::test]
async fn a_backlog_of_more_than_one_bite_empties_in_a_single_tick() {
    let runtime = hub_with(1200).await;
    let cloud = cloud(vec![]).await;
    let sent = first_bite(&runtime).await;
    assert_eq!(sent.len(), MAX_EVENTS_PER_BEAT, "the bite comes full");

    let settled = daily_usage::settle_activity(
        &runtime,
        &reqwest::Client::new(),
        &cloud.base_url,
        &auth(),
        &sent,
        true,
    )
    .await;

    assert_eq!(settled.confirmed, 1200, "every one was delivered");
    assert_eq!(still_pending(&runtime).await, 0, "nothing left waiting");
    assert_eq!(
        cloud.events.load(Ordering::SeqCst),
        700,
        "the 700 that were missing"
    );
    assert_eq!(cloud.beats.load(Ordering::SeqCst), 2, "two drain beats");
}

/// A SHORT bite means the buffer ran out: nothing further is asked. Without this the hub would
/// send one pointless beat per tick, across the whole fleet, every day.
#[tokio::test]
async fn a_short_bite_means_the_buffer_is_empty_and_nothing_else_is_asked() {
    let runtime = hub_with(3).await;
    let cloud = cloud(vec![]).await;
    let sent = first_bite(&runtime).await;

    let settled = daily_usage::settle_activity(
        &runtime,
        &reqwest::Client::new(),
        &cloud.base_url,
        &auth(),
        &sent,
        true,
    )
    .await;

    assert_eq!(settled.confirmed, 3);
    assert_eq!(settled.rounds, 1, "the first beat already said it all");
    assert_eq!(
        cloud.beats.load(Ordering::SeqCst),
        0,
        "no drain beat at all"
    );
    assert_eq!(still_pending(&runtime).await, 0);
}

/// The cap exists so an enormous buffer does not turn a tick into a storm of beats. Whatever
/// does not fit waits for the next tick — which is right: it is no longer LOST, only delayed.
#[tokio::test]
async fn the_drain_stops_at_the_round_cap_and_the_rest_waits_for_the_next_tick() {
    let rounds_worth = MAX_EVENTS_PER_BEAT * (daily_usage::MAX_DRAIN_ROUNDS + 3);
    let runtime = hub_with(rounds_worth).await;
    let cloud = cloud(vec![]).await;
    let sent = first_bite(&runtime).await;

    let settled = daily_usage::settle_activity(
        &runtime,
        &reqwest::Client::new(),
        &cloud.base_url,
        &auth(),
        &sent,
        true,
    )
    .await;

    assert_eq!(
        settled.rounds,
        daily_usage::MAX_DRAIN_ROUNDS,
        "it stops at the cap"
    );
    assert_eq!(
        settled.confirmed,
        MAX_EVENTS_PER_BEAT * daily_usage::MAX_DRAIN_ROUNDS
    );
    assert_eq!(
        still_pending(&runtime).await,
        MAX_EVENTS_PER_BEAT,
        "the surplus is still there, not lost"
    );
}

// ── 2. Only `activity_ack` deletes ───────────────────────────────────────────────────────────

/// A `200 {"ok": true}` is what a SaaS whose ingest blew up answers, and also one that does not
/// know `activity`. Deleting on that is throwing the data away believing it was stored.
#[tokio::test]
async fn a_bare_200_without_the_ack_keeps_every_event() {
    let runtime = hub_with(4).await;
    let cloud = cloud(vec![]).await;
    let sent = first_bite(&runtime).await;

    let settled = daily_usage::settle_activity(
        &runtime,
        &reqwest::Client::new(),
        &cloud.base_url,
        &auth(),
        &sent,
        false, // the beat answered 200, but without `activity_ack`
    )
    .await;

    assert_eq!(settled.confirmed, 0);
    assert_eq!(still_pending(&runtime).await, 4, "they are kept whole");
}

/// And if the Cloud stops acking MID-drain, what it acked is dropped and the rest stays. Neither
/// is delivered work lost, nor is undelivered work taken for delivered.
#[tokio::test]
async fn when_the_cloud_stops_acking_mid_drain_only_what_it_acked_is_dropped() {
    let runtime = hub_with(MAX_EVENTS_PER_BEAT * 2).await;
    // The drain beat answers a bare 200: no ack, no error.
    let cloud = cloud(vec![Some(json!({"ok": true}))]).await;
    let sent = first_bite(&runtime).await;

    let settled = daily_usage::settle_activity(
        &runtime,
        &reqwest::Client::new(),
        &cloud.base_url,
        &auth(),
        &sent,
        true,
    )
    .await;

    assert_eq!(
        settled.confirmed, MAX_EVENTS_PER_BEAT,
        "only the first bite"
    );
    assert_eq!(
        still_pending(&runtime).await,
        MAX_EVENTS_PER_BEAT,
        "the second bite is still waiting for its acknowledgement"
    );
}

/// A drain beat that fails on the network leaves the rest where it was. Networks drop often;
/// losing the data for that would be worse than taking one more day.
#[tokio::test]
async fn a_failed_drain_beat_leaves_the_rest_where_it_was() {
    let runtime = hub_with(MAX_EVENTS_PER_BEAT * 2).await;
    let cloud = cloud(vec![None]).await; // 500 to the drain beat
    let sent = first_bite(&runtime).await;

    let settled = daily_usage::settle_activity(
        &runtime,
        &reqwest::Client::new(),
        &cloud.base_url,
        &auth(),
        &sent,
        true,
    )
    .await;

    assert_eq!(settled.confirmed, MAX_EVENTS_PER_BEAT);
    assert_eq!(still_pending(&runtime).await, MAX_EVENTS_PER_BEAT);
}

/// A drain beat carries the activity and **nothing of the business**: it is not a real beat, it
/// is the rest of the batch. Sending `orders_today` again would rewrite the day's count with the
/// same number once per round, and the daily cadence is exactly what makes that noise visible.
#[tokio::test]
async fn a_drain_beat_carries_the_events_and_no_business_figures() {
    let runtime = hub_with(MAX_EVENTS_PER_BEAT + 1).await;
    let seen: Arc<StdMutex<Vec<Value>>> = Arc::new(StdMutex::new(Vec::new()));

    let captured = seen.clone();
    let app = Router::new()
        .route(
            "/api/v1/hub/device/heartbeat/",
            post(
                |axum::extract::State(seen): axum::extract::State<Arc<StdMutex<Vec<Value>>>>,
                 Json(body): Json<Value>| async move {
                    seen.lock().unwrap().push(body);
                    (
                        StatusCode::OK,
                        Json(json!({"ok": true, "activity_ack": true})),
                    )
                },
            ),
        )
        .with_state(captured);
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });

    let sent = first_bite(&runtime).await;
    daily_usage::settle_activity(
        &runtime,
        &reqwest::Client::new(),
        &format!("http://{address}"),
        &auth(),
        &sent,
        true,
    )
    .await;

    let bodies = seen.lock().unwrap();
    assert_eq!(bodies.len(), 1, "a single drain beat");
    let body = &bodies[0];
    assert_eq!(body["activity"].as_array().unwrap().len(), 1);
    for business in [
        "orders_today",
        "last_sale_at",
        "terminals",
        "active_users",
        "last_user_activity_at",
        "cpu_pct",
        "memory_peak_mb",
        "transmission_route",
    ] {
        assert!(
            body.get(business).is_none(),
            "the drain does not repeat {business}: {body}"
        );
    }
}
