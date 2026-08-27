//! A hub is somebody's till. It is never, ever indexed (Ioan, 2026-08-26).
//!
//! The landing wants the answer engines in; a hub is the opposite case and had **no defence at
//! all**. Verified on 2026-08-26: this crate serves no `/robots.txt` (so a crawler that asks gets
//! the SPA's 200-with-index.html fallback and reads it as "no rules"), sends no `X-Robots-Tag`,
//! and `apps/web/index.html` carries no `robots` meta. The only `noindex` anywhere in the hub is
//! the one in `public_door.rs`, on a single public form.
//!
//! What a hub would have leaked into a public index is not marketing copy: a per-tenant host name
//! that says who the customer is, the shape of their installed modules, and a login page for a
//! real cash register. And unlike the SaaS there is nothing here to gain — no hub page is ever a
//! search result we want.
//!
//! Three layers, because each covers a hole the others do not:
//!   1. `/robots.txt` — for the crawler that asks first.
//!   2. `X-Robots-Tag` on every response — for the one that does not, and for the URLs a
//!      robots.txt cannot describe (a deep link someone pasted into a public issue).
//!   3. the `robots` meta in the shipped `index.html` — for the copy of the document that is NOT
//!      served by this crate: the degraded shell bundled inside the installed app.
use axum::body::Body;
use axum::http::{Request, StatusCode};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{build_serving_router, default_csp, AppState, AuthMode, HubConfig};
use tower::ServiceExt; // oneshot

const CLOUD: &str = "https://erplora.com";
const INDEX_HTML: &str = "<!doctype html><title>ERPlora SPA</title><div id=app></div>";

/// The `index.html` that actually ships to the browser — read, never copied, so this test
/// cannot pass against a snapshot of what the file used to say.
const SHIPPED_INDEX: &str = include_str!("../../../apps/web/index.html");

/// One `dist/` PER CALL, never a shared path.
///
/// The first draft named the directory after the process id, so every test in this binary got the
/// same one — and `get()` deletes it on the way out. Cargo runs these in parallel, so one test
/// deleted the `index.html` another was mid-request for and `GET /` came back 404. The failure
/// looked like a bug in the code under test; it was a bug in the harness.
fn temp_dist() -> std::path::PathBuf {
    use std::sync::atomic::{AtomicU32, Ordering};
    static SEQ: AtomicU32 = AtomicU32::new(0);
    let dir = std::env::temp_dir().join(format!(
        "erplora_hub_noindex_{}_{}",
        std::process::id(),
        SEQ.fetch_add(1, Ordering::Relaxed)
    ));
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).unwrap();
    std::fs::write(dir.join("index.html"), INDEX_HTML).unwrap();
    dir
}

async fn make_state() -> AppState {
    let db = fresh_db().await;
    let rt = Runtime::new(Box::new(db));
    AppState::with_config(rt, HubConfig::from_env_with_auth(AuthMode::Dev))
}

async fn get(path: &str) -> axum::response::Response {
    let dist = temp_dist();
    let web_dir = dist.to_string_lossy().into_owned();
    let router = build_serving_router(make_state().await, Some(&web_dir), &default_csp(CLOUD));
    let resp = router
        .oneshot(Request::get(path).body(Body::empty()).unwrap())
        .await
        .unwrap();
    let _ = std::fs::remove_dir_all(&dist);
    resp
}

async fn body_of(resp: axum::response::Response) -> String {
    let bytes = axum::body::to_bytes(resp.into_body(), 64 * 1024)
        .await
        .unwrap();
    String::from_utf8(bytes.to_vec()).unwrap()
}

// ── 1. The crawler that asks ────────────────────────────────────────────────────────────────────

#[tokio::test]
async fn a_hub_serves_a_robots_txt_of_its_own() {
    let resp = get("/robots.txt").await;
    assert_eq!(resp.status(), StatusCode::OK);
    assert_eq!(
        resp.headers().get("content-type").map(|v| v
            .to_str()
            .unwrap()
            .split(';')
            .next()
            .unwrap()
            .to_string()),
        Some("text/plain".to_string()),
        "the SPA fallback answered /robots.txt with index.html — a crawler reads that as \
         'this site has no rules', which is the opposite of what it means"
    );
}

#[tokio::test]
async fn the_robots_txt_closes_the_whole_hub_to_everyone() {
    let body = body_of(get("/robots.txt").await).await;
    assert!(
        body.contains("User-agent: *"),
        "no catch-all group in the hub's robots.txt: {body}"
    );
    assert!(
        body.lines().any(|line| line.trim() == "Disallow: /"),
        "the hub's robots.txt does not close the site: {body}"
    );
    assert!(
        !body.contains("Allow:"),
        "a hub has no crawlable corner — an Allow line here is always a mistake: {body}"
    );
    assert!(
        !body.contains("Sitemap:"),
        "advertising a sitemap from a till is handing over the map: {body}"
    );
}

// ── 2. The crawler that does not ask ────────────────────────────────────────────────────────────

const EXPECTED_TAG: &str = "noindex, nofollow, noarchive";

#[tokio::test]
async fn the_app_document_carries_x_robots_tag() {
    let resp = get("/").await;
    assert_eq!(resp.status(), StatusCode::OK);
    assert_eq!(
        resp.headers()
            .get("x-robots-tag")
            .map(|v| v.to_str().unwrap()),
        Some(EXPECTED_TAG),
        "the hub's own document came back indexable"
    );
}

/// Every response, not just the document: a JSON endpoint that ends up in an index leaks the
/// tenant's shape just as well, and `noarchive` is what stops a cached copy outliving the page.
#[tokio::test]
async fn every_response_carries_x_robots_tag() {
    for path in ["/", "/healthz", "/api/hub/context", "/does-not-exist"] {
        let resp = get(path).await;
        assert_eq!(
            resp.headers()
                .get("x-robots-tag")
                .map(|v| v.to_str().unwrap()),
            Some(EXPECTED_TAG),
            "{path} answered {} without X-Robots-Tag",
            resp.status()
        );
    }
}

// ── 3. The copy this crate does not serve ───────────────────────────────────────────────────────

#[tokio::test]
async fn the_shipped_index_html_declares_noindex_in_the_markup() {
    let normalised = SHIPPED_INDEX.replace('\'', "\"");
    assert!(
        normalised.contains(r#"name="robots""#) && normalised.contains("noindex"),
        "apps/web/index.html ships without a robots meta — the header does not reach the copy \
         bundled inside the installed app, and that document is the same one a browser can open"
    );
}
