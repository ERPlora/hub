//! `GET /api/system/usage-series?range=3h|24h|3d` — resource-usage SERIES for the /system screen.
//!
//! The hub keeps no usage history of its own: the SaaS records the fleet's samples and serves
//! them per hub at `GET {cloud}/api/v1/hub/device/metrics/series/` (machine token — ADR-0003:
//! that token never reaches the browser, so the runtime proxies, same pattern as
//! `system::cloud_storage`). The upstream JSON is passed through untouched; a 30 s in-memory
//! cache per range keeps a dashboard left open from hammering the SaaS.
//!
//! When the SaaS cannot be reached (or answers anything but a 2xx JSON) the reply is a **502**
//! whose body says `known: false` for every metric: the UI degrades to «we could not read this»
//! (ADR-0237 — what we did not measure is never painted as a healthy zero). Upstream error
//! bodies are deliberately NOT passed through: they are written for us, can echo request
//! details, and the machine token must never leak into a browser-visible response.

use std::collections::HashMap;
use std::sync::{Mutex, OnceLock};
use std::time::{Duration, Instant};

use axum::extract::{Query, State};
use axum::http::{HeaderMap, StatusCode};
use axum::response::{IntoResponse, Response};
use axum::Json;
use serde::Deserialize;
use serde_json::{json, Value};

use crate::{auth, AppState};

/// How long an upstream answer is served from memory before asking the SaaS again.
pub const CACHE_TTL: Duration = Duration::from_secs(30);

/// The only ranges the SaaS contract offers. 3 days is the maximum on purpose — the screen
/// never offers more, and an arbitrary value must not become a cache key or travel upstream.
const ALLOWED_RANGES: [&str; 3] = ["3h", "24h", "3d"];

#[derive(Deserialize)]
pub struct RangeQuery {
    pub range: Option<String>,
}

/// Per-range in-memory cache of upstream bodies.
#[derive(Default)]
pub struct SeriesCache {
    entries: Mutex<HashMap<String, (Instant, Value)>>,
}

/// Whitelists the requested range. `None` (no param) defaults to `24h`; anything not in the
/// contract is rejected — never forwarded upstream, never a cache key.
fn normalize_range(range: Option<&str>) -> Option<&'static str> {
    match range {
        None => Some("24h"),
        Some(r) => ALLOWED_RANGES
            .iter()
            .find(|allowed| **allowed == r)
            .copied(),
    }
}

/// Body served when the SaaS could not answer: every metric is *unknown*, never a healthy zero
/// (ADR-0237). The UI reads `known: false` and paints its own «we could not read this» state.
fn unknown_body() -> Value {
    json!({
        "metrics": {
            "cpu": { "known": false },
            "ram": { "known": false },
            "db_connections": { "known": false }
        }
    })
}

/// Fetches the series for `range` from the SaaS, serving a fresh-enough cached body first.
///
/// The machine token only travels in the upstream request headers: the returned body is either
/// the upstream 2xx JSON verbatim or [`unknown_body`] — never anything built from the request
/// we signed, so the token cannot leak into what the browser sees.
async fn fetch_series(
    http: &reqwest::Client,
    cloud_base_url: &str,
    hub_id: &str,
    token: &str,
    range: &str,
    cache: &SeriesCache,
    ttl: Duration,
) -> (StatusCode, Value) {
    if let Ok(entries) = cache.entries.lock() {
        if let Some((at, body)) = entries.get(range) {
            if at.elapsed() < ttl {
                return (StatusCode::OK, body.clone());
            }
        }
    }

    let url = format!(
        "{}/api/v1/hub/device/metrics/series/?range={range}",
        cloud_base_url.trim_end_matches('/')
    );
    let resp = http
        .get(&url)
        .header("X-Hub-Token", token)
        .header("X-Hub-Id", hub_id)
        .send()
        .await;
    // Any failure — unreachable, timeout, non-2xx, non-JSON — collapses to the same honest
    // degradation. Upstream error bodies never pass through: see the module doc.
    let Ok(resp) = resp else {
        return (StatusCode::BAD_GATEWAY, unknown_body());
    };
    if !resp.status().is_success() {
        return (StatusCode::BAD_GATEWAY, unknown_body());
    }
    let Ok(body) = resp.json::<Value>().await else {
        return (StatusCode::BAD_GATEWAY, unknown_body());
    };

    if let Ok(mut entries) = cache.entries.lock() {
        entries.insert(range.to_string(), (Instant::now(), body.clone()));
    }
    (StatusCode::OK, body)
}

/// `GET /api/system/usage-series` — same user-session gate as `/api/system` (this is internal
/// hub telemetry; the Vue route guard is not authentication).
pub async fn usage_series(
    State(st): State<AppState>,
    headers: HeaderMap,
    Query(q): Query<RangeQuery>,
) -> Response {
    {
        let rt = st.runtime.read().await;
        if let Err(error) = auth::require_user_session(&headers, &st.config, &rt).await {
            return (
                StatusCode::UNAUTHORIZED,
                Json(json!({ "ok": false, "error": error.message() })),
            )
                .into_response();
        }
    }

    let Some(range) = normalize_range(q.range.as_deref()) else {
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({ "ok": false, "error": "invalid_range" })),
        )
            .into_response();
    };

    // No machine token = we cannot ask the SaaS at all: same honest degradation as unreachable.
    let Some(token) = st.machine_token() else {
        return (StatusCode::BAD_GATEWAY, Json(unknown_body())).into_response();
    };

    static CACHE: OnceLock<SeriesCache> = OnceLock::new();
    let cache = CACHE.get_or_init(SeriesCache::default);
    let (status, body) = fetch_series(
        &st.http,
        &st.config.cloud_base_url,
        &st.hub_id(),
        &token,
        range,
        cache,
        CACHE_TTL,
    )
    .await;
    (status, Json(body)).into_response()
}

#[cfg(test)]
mod tests {
    //! The proxy's whole contract, against a mock SaaS (same pattern as `daily_usage`'s
    //! heartbeat test: a real axum listener on an ephemeral port). No hub DB involved — the
    //! function under test only talks HTTP.
    use super::*;
    use axum::extract::{Query as UpQuery, State as UpState};
    use axum::routing::get;
    use axum::Router;
    use std::sync::atomic::{AtomicUsize, Ordering};
    use std::sync::Arc;
    use tokio::sync::Mutex as AsyncMutex;

    /// A body shaped like the fixed SaaS contract (saas branch feat/hub-usage-series).
    fn contract_body(range: &str) -> Value {
        json!({
            "range": range,
            "step_seconds": 900,
            "generated_at": "2026-08-15T10:00:00Z",
            "thresholds": { "warning": 70, "critical": 80 },
            "metrics": {
                "cpu": {
                    "known": true, "unit": "%", "current": 42.5, "status": "ok",
                    "points": [[1755100800, 38.2], [1755101700, 42.5]], "message": null
                },
                "ram": {
                    "known": true, "unit": "%", "current": 61.0, "status": "warning",
                    "points": [[1755100800, 58.0], [1755101700, 61.0]], "message": null
                },
                "db_connections": {
                    "known": true, "unit": "connections", "current": 3.0, "status": "ok",
                    "points": [[1755100800, 2.0], [1755101700, 3.0]], "message": null
                }
            },
            "upgrade": { "show": false, "reason": null, "message": null, "url": null }
        })
    }

    /// What the mock SaaS saw of one request: the headers and the `range` query param.
    #[derive(Clone)]
    struct Seen {
        token: Option<String>,
        hub_id: Option<String>,
        range: Option<String>,
    }

    struct Upstream {
        hits: Arc<AtomicUsize>,
        seen: Arc<AsyncMutex<Option<Seen>>>,
        /// Upstream reply: `(status, body)`. The leak test makes this echo the token back.
        reply: Arc<dyn Fn(&Seen) -> (StatusCode, Value) + Send + Sync>,
    }

    async fn upstream_handler(
        UpState(up): UpState<Arc<Upstream>>,
        UpQuery(params): UpQuery<HashMap<String, String>>,
        headers: HeaderMap,
    ) -> (StatusCode, Json<Value>) {
        up.hits.fetch_add(1, Ordering::SeqCst);
        let seen = Seen {
            token: headers
                .get("x-hub-token")
                .and_then(|v| v.to_str().ok())
                .map(String::from),
            hub_id: headers
                .get("x-hub-id")
                .and_then(|v| v.to_str().ok())
                .map(String::from),
            range: params.get("range").cloned(),
        };
        let (status, body) = (up.reply)(&seen);
        *up.seen.lock().await = Some(seen);
        (status, Json(body))
    }

    /// Spawns a mock SaaS serving the series endpoint. Returns its base URL and the state.
    async fn spawn_upstream(
        reply: impl Fn(&Seen) -> (StatusCode, Value) + Send + Sync + 'static,
    ) -> (String, Arc<Upstream>) {
        let up = Arc::new(Upstream {
            hits: Arc::new(AtomicUsize::new(0)),
            seen: Arc::new(AsyncMutex::new(None)),
            reply: Arc::new(reply),
        });
        let app = Router::new()
            .route("/api/v1/hub/device/metrics/series/", get(upstream_handler))
            .with_state(up.clone());
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let address = listener.local_addr().unwrap();
        tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
        (format!("http://{address}"), up)
    }

    /// Every metric of the degraded body must say `known: false` — the UI's cue to paint
    /// «we could not read this» instead of a healthy zero (ADR-0237).
    fn assert_unknown(body: &Value) {
        for metric in ["cpu", "ram", "db_connections"] {
            assert_eq!(
                body.pointer(&format!("/metrics/{metric}/known")),
                Some(&Value::Bool(false)),
                "metric {metric} must be unknown, body: {body}"
            );
        }
    }

    #[tokio::test]
    async fn usage_series_proxies_saas_response() {
        let (base, up) = spawn_upstream(|seen| {
            (
                StatusCode::OK,
                contract_body(seen.range.as_deref().unwrap_or("?")),
            )
        })
        .await;

        let cache = SeriesCache::default();
        let (status, body) = fetch_series(
            &reqwest::Client::new(),
            &base,
            "hub-a",
            "machine-token",
            "3d",
            &cache,
            CACHE_TTL,
        )
        .await;

        assert_eq!(status, StatusCode::OK);
        assert_eq!(
            body,
            contract_body("3d"),
            "upstream JSON passes through untouched"
        );

        let seen = up.seen.lock().await.clone().expect("upstream was called");
        assert_eq!(seen.token.as_deref(), Some("machine-token"));
        assert_eq!(seen.hub_id.as_deref(), Some("hub-a"));
        assert_eq!(seen.range.as_deref(), Some("3d"));
    }

    #[tokio::test]
    async fn usage_series_returns_unknown_body_when_saas_unreachable() {
        // Port 1 answers nothing: connection refused, immediately.
        let cache = SeriesCache::default();
        let (status, body) = fetch_series(
            &reqwest::Client::new(),
            "http://127.0.0.1:1",
            "hub-a",
            "machine-token",
            "24h",
            &cache,
            CACHE_TTL,
        )
        .await;

        assert_eq!(status, StatusCode::BAD_GATEWAY);
        assert_unknown(&body);
    }

    #[tokio::test]
    async fn usage_series_caches_upstream_for_30s() {
        let (base, up) = spawn_upstream(|seen| {
            (
                StatusCode::OK,
                contract_body(seen.range.as_deref().unwrap_or("?")),
            )
        })
        .await;
        let client = reqwest::Client::new();
        let cache = SeriesCache::default();

        // Two requests for the same range within the TTL: one upstream hit.
        let (s1, b1) = fetch_series(&client, &base, "hub-a", "t", "3h", &cache, CACHE_TTL).await;
        let (s2, b2) = fetch_series(&client, &base, "hub-a", "t", "3h", &cache, CACHE_TTL).await;
        assert_eq!((s1, s2), (StatusCode::OK, StatusCode::OK));
        assert_eq!(b1, b2, "the cached body is the upstream body");
        assert_eq!(
            up.hits.load(Ordering::SeqCst),
            1,
            "second call served from cache"
        );

        // A different range is a different cache entry.
        let _ = fetch_series(&client, &base, "hub-a", "t", "24h", &cache, CACHE_TTL).await;
        assert_eq!(up.hits.load(Ordering::SeqCst), 2);

        // A zero TTL means the entry is always stale: the TTL is what gates re-fetching.
        let _ = fetch_series(&client, &base, "hub-a", "t", "3h", &cache, Duration::ZERO).await;
        assert_eq!(
            up.hits.load(Ordering::SeqCst),
            3,
            "expired entry re-fetches upstream"
        );
    }

    #[tokio::test]
    async fn usage_series_never_leaks_machine_token_in_response() {
        // A hostile/echoing upstream: replies 500 with the token it received in the body. If
        // the proxy passed upstream error bodies through, the browser would read the machine
        // token — so errors must collapse to the unknown body instead.
        let (base, _up) = spawn_upstream(|seen| {
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                json!({ "detail": format!("bad token: {}", seen.token.clone().unwrap_or_default()) }),
            )
        })
        .await;

        let cache = SeriesCache::default();
        let (status, body) = fetch_series(
            &reqwest::Client::new(),
            &base,
            "hub-a",
            "machine-token-SECRET",
            "3h",
            &cache,
            CACHE_TTL,
        )
        .await;

        assert_eq!(status, StatusCode::BAD_GATEWAY);
        assert_unknown(&body);
        assert!(
            !body.to_string().contains("machine-token-SECRET"),
            "the machine token must never appear in the response body"
        );

        // And on the happy path the passthrough body carries no token either.
        let (base_ok, _up_ok) = spawn_upstream(|seen| {
            (
                StatusCode::OK,
                contract_body(seen.range.as_deref().unwrap_or("?")),
            )
        })
        .await;
        let (_, ok_body) = fetch_series(
            &reqwest::Client::new(),
            &base_ok,
            "hub-a",
            "machine-token-SECRET",
            "3h",
            &SeriesCache::default(),
            CACHE_TTL,
        )
        .await;
        assert!(!ok_body.to_string().contains("machine-token-SECRET"));
    }

    #[test]
    fn range_is_whitelisted_and_defaults_to_24h() {
        assert_eq!(normalize_range(None), Some("24h"));
        assert_eq!(normalize_range(Some("3h")), Some("3h"));
        assert_eq!(normalize_range(Some("24h")), Some("24h"));
        assert_eq!(normalize_range(Some("3d")), Some("3d"));
        // The contract stops at 3 days, and junk never travels upstream nor keys the cache.
        assert_eq!(normalize_range(Some("7d")), None);
        assert_eq!(normalize_range(Some("../etc")), None);
        assert_eq!(normalize_range(Some("")), None);
    }
}
