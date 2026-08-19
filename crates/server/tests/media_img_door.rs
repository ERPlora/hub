//! **A photo is asked for by the BROWSER, not by the app** (hub#791).
//!
//! Every other door of this hub is opened by `X-Hub-Session`, a header the app attaches by hand on
//! each `fetch` (ADR-0003). That works for everything the app *calls*. It does not work for what
//! the browser *fetches on its own*: an `<img src>` — or a `background-image` — is issued by the
//! rendering engine, and there is no place to put a header on it. So every product photo in the
//! till arrived as `401`, and the wall of tiles came up blank.
//!
//! It is the same shape of problem the event channel already solved: `EventSource` cannot set
//! headers either, so `/api/events` takes a **ticket in the query** minted from the session
//! (`event_stream.rs`). Media cannot copy that literally — a till paints 50 tiles at once and the
//! URL it paints comes out of the database (`product.image`), so there is nowhere to thread a
//! per-request ticket without rewriting seeded data and every module that shows a picture.
//!
//! What the browser DOES attach on its own is a cookie. So the hub mints one, and it is deliberately
//! the narrowest thing that works:
//!
//! - **`Path=/api/media/raw`** — it is sent to the read door and to nothing else. Not to `/api/query`,
//!   not to the rest of the media manager.
//! - **read only**: `upload`, `delete`, `folder`, `rename` and `move` keep demanding the header.
//!   That is what makes CSRF a non-issue rather than a mitigation — a forged cross-site request
//!   cannot reach a door that changes anything.
//! - **`HttpOnly`** so script cannot lift it, **`Secure`**, and **`SameSite=Strict`**.
//! - it carries the **session token itself**, so it expires exactly when the session does and there
//!   is no second credential lifetime to reason about (or to forget to revoke).
//!
//! Each negative below is paired with the positive that proves the door is open at all — a hub whose
//! media had simply stopped working would pass every negative here on its own.
use std::sync::{Arc, Mutex};

use axum::body::Body;
use axum::extract::{Query, Request, State};
use axum::http::{Method, StatusCode};
use axum::routing::get;
use axum::{Json, Router};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use serde::Deserialize;
use serde_json::json;
use tower::ServiceExt;

const HUB_ID: &str = "hub-media-img";
/// The bytes the "object storage" hands back, so a 200 can be told apart from an empty relay.
const OBJECT_BYTES: &[u8] = b"RIFF....WEBPfake-photo-bytes";

/// Requests the mini-Cloud saw: (method, path).
type Captured = Arc<Mutex<Vec<(String, String)>>>;

#[derive(Deserialize)]
struct RawQuery {
    path: String,
}

/// Mini-Cloud with the two halves `cloud_raw` needs: the signing call answers `{ url }` pointing
/// back here, and that URL serves the bytes. Without the second half a request that passed the door
/// would still end in 502, and "not 401" would be all this file could ever assert.
async fn spawn_mock_cloud() -> (String, Captured) {
    let captured: Captured = Arc::new(Mutex::new(Vec::new()));
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let addr = listener.local_addr().unwrap();
    let base = format!("http://{addr}");

    let sign_base = base.clone();
    let router = Router::new()
        .route(
            "/api/v1/hub/device/media/raw",
            get(
                move |State(cap): State<Captured>, Query(q): Query<RawQuery>| {
                    let sign_base = sign_base.clone();
                    async move {
                        cap.lock().unwrap().push((
                            "GET".to_string(),
                            format!("/api/v1/hub/device/media/raw?path={}", q.path),
                        ));
                        Json(json!({ "url": format!("{sign_base}/object") }))
                    }
                },
            ),
        )
        .route("/object", get(|| async { OBJECT_BYTES }))
        .fallback(|State(cap): State<Captured>, request: Request| async move {
            cap.lock().unwrap().push((
                request.method().to_string(),
                request.uri().path().to_string(),
            ));
            Json(json!({}))
        })
        .with_state(captured.clone());

    tokio::spawn(async move { axum::serve(listener, router).await.unwrap() });
    (base, captured)
}

/// Ephemeral Postgres + mock Cloud. Returns the router and a live admin session token.
async fn fixture() -> (Router, String, Captured) {
    let (cloud_base_url, captured) = spawn_mock_cloud().await;

    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), HUB_ID);
    rt.ensure_system_tables().await.unwrap();
    let admin_id = rt
        .create_user("Admin", "1111", "admin", None)
        .await
        .unwrap();
    let session = rt.create_session(&admin_id, 3600, None).await.unwrap();

    let cfg = HubConfig {
        demo: false,
        hub_id: HUB_ID.into(),
        cloud_base_url,
        module_cache: std::env::temp_dir().join("erplora-media-img-cache"),
        auth_mode: AuthMode::Session,
        jwt_public_key: None,
        cloud_api_token: Some("test-machine-token".into()),
        device_trust_enforce: false,
        media_dir: std::env::temp_dir().join("erplora-media-img-scratch"),
        sector: None,
        dev_mode: false,
        dev_modules_dir: None,
        module_trusted_keys: Vec::new(),
    };
    (app(AppState::with_config(rt, cfg)), session, captured)
}

/// `POST /api/media/session` with the header, returning the whole `Set-Cookie` line.
async fn mint_cookie(router: &Router, session: &str) -> (StatusCode, String) {
    let response = router
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/media/session")
                .header("X-Hub-Session", session)
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    let status = response.status();
    let cookie = response
        .headers()
        .get("set-cookie")
        .map(|v| v.to_str().unwrap().to_string())
        .unwrap_or_default();
    (status, cookie)
}

/// The `name=value` pair of a `Set-Cookie` line — what a browser would send back.
fn cookie_pair(set_cookie: &str) -> String {
    set_cookie.split(';').next().unwrap().to_string()
}

/// A photo request exactly as the rendering engine issues it: no header, only what is in the jar.
async fn fetch_photo(router: &Router, cookie: Option<&str>) -> StatusCode {
    let mut request = Request::builder().uri("/api/media/raw?path=hospitality/pizza.webp");
    if let Some(c) = cookie {
        request = request.header("Cookie", c);
    }
    router
        .clone()
        .oneshot(request.body(Body::empty()).unwrap())
        .await
        .unwrap()
        .status()
}

#[tokio::test]
async fn the_browser_reads_a_photo_with_the_cookie_the_hub_minted() {
    let (router, session, captured) = fixture().await;

    // The negative first, so the positive below cannot be a door that was never shut: an `<img>`
    // with nothing to show for itself is refused.
    assert_eq!(
        fetch_photo(&router, None).await,
        StatusCode::UNAUTHORIZED,
        "an anonymous photo request must stay refused"
    );

    let (status, set_cookie) = mint_cookie(&router, &session).await;
    assert_eq!(status, StatusCode::OK, "minting: {set_cookie}");

    let served = fetch_photo(&router, Some(&cookie_pair(&set_cookie))).await;
    assert_eq!(
        served,
        StatusCode::OK,
        "the same request, with the cookie the hub itself minted, must serve the photo"
    );

    // …and it really went through to storage, rather than being answered by something short of it.
    let seen = captured.lock().unwrap().clone();
    assert!(
        seen.iter()
            .any(|(m, p)| m == "GET" && p.contains("hospitality/pizza.webp")),
        "the Cloud never saw the file request: {seen:?}"
    );
}

#[tokio::test]
async fn the_cookie_is_narrower_than_a_session() {
    let (router, session, _) = fixture().await;
    let (_, set_cookie) = mint_cookie(&router, &session).await;

    for attribute in [
        "HttpOnly",
        "Secure",
        "SameSite=Strict",
        "Path=/api/media/raw",
    ] {
        assert!(
            set_cookie.contains(attribute),
            "the media cookie must carry {attribute}, got: {set_cookie}"
        );
    }
}

#[tokio::test]
async fn the_cookie_opens_nothing_that_writes() {
    let (router, session, _) = fixture().await;
    let (_, set_cookie) = mint_cookie(&router, &session).await;
    let cookie = cookie_pair(&set_cookie);

    // `Path` already keeps a browser from sending it here; the door refuses it anyway. Both have to
    // hold: the path is what a browser honours, this is what the hub guarantees.
    //
    // Each request is well-formed for the door it knocks on — `upload` takes a `Multipart`, and a
    // body its extractor rejects would answer 400 without ever reaching the guard, which would make
    // this whole test pass on a hub that had no guard at all.
    const BOUNDARY: &str = "erploratestboundary";
    let multipart = format!(
        "--{BOUNDARY}\r\nContent-Disposition: form-data; name=\"folder\"\r\n\r\n\
         hospitality\r\n--{BOUNDARY}--\r\n"
    );
    let doors = [
        (
            Method::POST,
            "/api/media/upload",
            format!("multipart/form-data; boundary={BOUNDARY}"),
            multipart,
        ),
        (
            Method::DELETE,
            "/api/media?path=hospitality/pizza.webp",
            "application/json".to_string(),
            "{}".to_string(),
        ),
        (
            Method::POST,
            "/api/media/folder",
            "application/json".to_string(),
            json!({ "parent": "", "name": "forged" }).to_string(),
        ),
        (
            Method::POST,
            "/api/media/rename",
            "application/json".to_string(),
            json!({ "path": "hospitality/pizza.webp", "name": "forged.webp" }).to_string(),
        ),
        (
            Method::POST,
            "/api/media/move",
            "application/json".to_string(),
            json!({ "from": "hospitality/pizza.webp", "to": "forged.webp" }).to_string(),
        ),
    ];
    for (method, uri, content_type, body) in doors {
        let status = router
            .clone()
            .oneshot(
                Request::builder()
                    .method(method.clone())
                    .uri(uri)
                    .header("Cookie", &cookie)
                    .header("content-type", content_type)
                    .body(Body::from(body))
                    .unwrap(),
            )
            .await
            .unwrap()
            .status();
        assert_eq!(
            status,
            StatusCode::UNAUTHORIZED,
            "{method} {uri} must not accept the read cookie"
        );
    }
}

#[tokio::test]
async fn a_cookie_the_hub_did_not_mint_opens_nothing() {
    let (router, session, _) = fixture().await;
    let (_, set_cookie) = mint_cookie(&router, &session).await;
    let real = cookie_pair(&set_cookie);
    let name = real.split('=').next().unwrap().to_string();

    // Same cookie name, invented value: the door must resolve the session, not recognise a shape.
    let forged = format!("{name}=erpl_not_a_session_at_all");
    assert_eq!(
        fetch_photo(&router, Some(&forged)).await,
        StatusCode::UNAUTHORIZED,
        "a forged media cookie must not open the read door"
    );

    // Control: the real one still works, so the assertion above is not passing because media broke.
    assert_eq!(fetch_photo(&router, Some(&real)).await, StatusCode::OK);
}

#[tokio::test]
async fn nobody_mints_a_cookie_without_a_session() {
    let (router, _session, _) = fixture().await;

    let anonymous = router
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/media/session")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(anonymous.status(), StatusCode::UNAUTHORIZED);
    assert!(
        anonymous.headers().get("set-cookie").is_none(),
        "a refused mint must not hand out a cookie anyway"
    );

    let invalid = router
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/media/session")
                .header("X-Hub-Session", "not-a-session")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(invalid.status(), StatusCode::UNAUTHORIZED);
    assert!(invalid.headers().get("set-cookie").is_none());
}

#[tokio::test]
async fn the_header_still_opens_the_read_door() {
    // `/files` reads media with `fetch` + the header (`lib/media.ts`). The cookie is an addition,
    // not a replacement: if this breaks, the file manager goes blank.
    let (router, session, _) = fixture().await;

    let status = router
        .clone()
        .oneshot(
            Request::builder()
                .uri("/api/media/raw?path=hospitality/pizza.webp")
                .header("X-Hub-Session", &session)
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap()
        .status();
    assert_eq!(status, StatusCode::OK);
}
