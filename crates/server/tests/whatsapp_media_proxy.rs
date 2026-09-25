//! The runtime's door for a WhatsApp ATTACHMENT (hub#2114) — the hub half of saas#2285.
//!
//! A customer sends a photo, a voice note or a document. Meta hands the business an asset id, never
//! the file, and the only party that can swap that id for the bytes is the SaaS, which holds the
//! business's Meta token (ADR-0012). The module cannot call the SaaS itself — that door opens with
//! the hub's **machine credential**, a secret of the runtime that never reaches the browser
//! (ADR-0003) — so the runtime proxies it, in streaming: a document can weigh 100 MB.
//!
//! What is asserted: the gate (no session → 401; a role that cannot read the inbox → 403; a module
//! without `notify:whatsapp` → refused, and the SaaS is NEVER called on any refusal), the credential
//! on the wire (machine only), the bytes and their `Content-Type` arriving untouched, the answer
//! being STREAMED rather than buffered, a media id that cannot climb out of its route, and every
//! refusal of the SaaS reaching the module with its own `code` in the envelope the SDK reads.
use axum::body::Body;
use axum::extract::Path;
use axum::http::{HeaderMap, Request, StatusCode};
use axum::response::IntoResponse;
use axum::routing::get;
use axum::{Json, Router};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use futures_util::StreamExt;
use serde_json::{json, Value};
use std::path::{Path as FsPath, PathBuf};
use std::sync::{Arc, Mutex};
use std::time::Duration;
use tower::ServiceExt;

const HUB: &str = "hub-wa-media";
const MODULE_HEADER: &str = "x-erplora-module";
/// The module that owns the inbox and therefore the one that calls this door.
const WHATSAPP: &str = "whatsapp_inbox";
/// What the SaaS serves for the id `42`: arbitrary bytes, NUL included, so nothing on the way can
/// have treated them as text.
const PHOTO: &[u8] = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00a customer's photo\xff\xd9";

/// The inbox module as the hub sees it: it declares `notify` on the given channels, and its roles
/// are the real ones (`employee` reads conversations; `kitchen` is a role that does not).
fn module_dir(root: &FsPath, channels: &[&str]) -> PathBuf {
    let dir = root.join(WHATSAPP);
    std::fs::create_dir_all(&dir).unwrap();
    let manifest = json!({
        "id": WHATSAPP,
        "name": WHATSAPP,
        "version": "2.1.80",
        "capabilities": { "notify": { "channels": channels } },
        "permissions": ["whatsapp_inbox.view_conversation"],
        "role_permissions": {
            "admin": ["*"],
            "employee": ["whatsapp_inbox.view_conversation"],
            "kitchen": []
        }
    });
    std::fs::write(
        dir.join("module.json"),
        serde_json::to_string_pretty(&manifest).unwrap(),
    )
    .unwrap();
    dir
}

/// What the fake SaaS saw: every call, with its path and headers.
#[derive(Default)]
struct Seen {
    calls: Vec<(String, Vec<(String, String)>)>,
}

struct Fixture {
    router: Router,
    admin: String,
    employee: String,
    kitchen: String,
    seen: Arc<Mutex<Seen>>,
}

async fn fixture(granted: bool, channels: &[&str], tag: &str) -> Fixture {
    fixture_with(granted, channels, tag, None).await
}

/// `release`: when given, the SaaS sends the first half of [`PHOTO`] and holds the second half
/// until the sender is dropped or fires — the lever the streaming test pulls.
async fn fixture_with(
    granted: bool,
    channels: &[&str],
    tag: &str,
    release: Option<tokio::sync::watch::Receiver<bool>>,
) -> Fixture {
    let seen = Arc::new(Mutex::new(Seen::default()));
    let cloud_base_url = fake_saas(seen.clone(), release).await;

    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), HUB);
    rt.ensure_system_tables().await.unwrap();
    let temp = std::env::temp_dir().join(format!(
        "erplora-wa-media-{tag}-{}-{granted}",
        std::process::id()
    ));
    rt.install_from_dir(&module_dir(&temp.join("modules"), channels))
        .await
        .unwrap();
    if granted {
        rt.set_module_capability(WHATSAPP, "notify", true, "hub_user:admin")
            .await
            .unwrap();
    }
    let admin = session(&rt, "Ana", "1111", "admin").await;
    let employee = session(&rt, "Luis", "2222", "employee").await;
    let kitchen = session(&rt, "Marta", "3333", "kitchen").await;

    let config = HubConfig {
        demo: false,
        hub_id: HUB.into(),
        cloud_base_url,
        module_cache: temp.join("modules-cache"),
        auth_mode: AuthMode::Session,
        jwt_public_key: None,
        cloud_api_token: Some("machine-secret".into()),
        device_trust_enforce: false,
        media_dir: temp,
        sector: None,
        dev_mode: false,
        dev_modules_dir: None,
        module_trusted_keys: Vec::new(),
    };
    Fixture {
        router: app(AppState::with_config(rt, config)),
        admin,
        employee,
        kitchen,
        seen,
    }
}

async fn session(rt: &Runtime, name: &str, pin: &str, role: &str) -> String {
    let id = rt.create_user(name, pin, role, None).await.unwrap();
    rt.create_session(&id, 3600, None).await.unwrap()
}

/// The SaaS of saas#2289, per its contract: bytes with Meta's MIME on `200`, and every refusal as
/// `{"error": "<code>", "detail": "…"}` decided before the first byte.
async fn fake_saas(
    seen: Arc<Mutex<Seen>>,
    release: Option<tokio::sync::watch::Receiver<bool>>,
) -> String {
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    let saas = Router::new().route(
        "/api/v1/hub/device/whatsapp/media/:media_id/",
        get(move |Path(media_id): Path<String>, headers: HeaderMap| {
            let seen = seen.clone();
            let release = release.clone();
            async move {
                seen.lock().unwrap().calls.push((
                    media_id.clone(),
                    headers
                        .iter()
                        .map(|(k, v)| {
                            (k.as_str().to_string(), v.to_str().unwrap_or("").to_string())
                        })
                        .collect(),
                ));
                let refusal = |status: StatusCode, code: &str| {
                    (
                        status,
                        Json(json!({ "error": code, "detail": "for the log only" })),
                    )
                        .into_response()
                };
                match media_id.as_str() {
                    "404" => refusal(StatusCode::NOT_FOUND, "media_not_found"),
                    "403" => refusal(StatusCode::FORBIDDEN, "meta_permission_denied"),
                    "409" => refusal(StatusCode::CONFLICT, "no_whatsapp_number"),
                    "502" => refusal(StatusCode::BAD_GATEWAY, "media_unavailable"),
                    "500" => (
                        StatusCode::INTERNAL_SERVER_ERROR,
                        "<html>Server Error (500)</html>",
                    )
                        .into_response(),
                    _ => {
                        let (first, second) = PHOTO.split_at(PHOTO.len() / 2);
                        let (first, second) = (first.to_vec(), second.to_vec());
                        let body = futures_util::stream::unfold(0u8, move |step| {
                            let (first, second) = (first.clone(), second.clone());
                            let mut release = release.clone();
                            async move {
                                match step {
                                    0 => Some((Ok::<_, std::io::Error>(first), 1)),
                                    1 => {
                                        if let Some(r) = release.as_mut() {
                                            let _ = r.wait_for(|go| *go).await;
                                        }
                                        Some((Ok(second), 2))
                                    }
                                    _ => None,
                                }
                            }
                        });
                        (
                            StatusCode::OK,
                            [
                                ("content-type", "audio/ogg; codecs=opus"),
                                ("cache-control", "private, no-store"),
                            ],
                            Body::from_stream(body),
                        )
                            .into_response()
                    }
                }
            }
        }),
    );
    tokio::spawn(async move { axum::serve(listener, saas).await.unwrap() });
    format!("http://{address}")
}

fn request(uri: &str, session: Option<&str>, module: Option<&str>) -> Request<Body> {
    let mut req = Request::builder().method("GET").uri(uri);
    if let Some(s) = session {
        req = req.header("x-hub-session", s);
    }
    if let Some(m) = module {
        req = req.header(MODULE_HEADER, m);
    }
    req.body(Body::empty()).unwrap()
}

async fn body_bytes(response: axum::response::Response) -> Vec<u8> {
    axum::body::to_bytes(response.into_body(), usize::MAX)
        .await
        .unwrap()
        .to_vec()
}

async fn body_json(response: axum::response::Response) -> Value {
    serde_json::from_slice(&body_bytes(response).await).unwrap_or(Value::Null)
}

fn header(response: &axum::response::Response, name: &str) -> Option<String> {
    response
        .headers()
        .get(name)
        .and_then(|v| v.to_str().ok())
        .map(str::to_string)
}

#[tokio::test]
async fn the_customers_photo_reaches_the_inbox_byte_for_byte_with_its_type() {
    let f = fixture(true, &["whatsapp"], "happy").await;
    let response = f
        .router
        .oneshot(request(
            "/api/hub/whatsapp/media/42",
            Some(&f.employee),
            Some(WHATSAPP),
        ))
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::OK);
    assert_eq!(
        header(&response, "content-type").as_deref(),
        Some("audio/ogg; codecs=opus"),
        "the MIME Meta gave (codec parameter included) is what lets the player play it"
    );
    // A customer's photo is personal data: no shared cache keeps it, no browser sniffs it into
    // something it can run.
    assert_eq!(
        header(&response, "cache-control").as_deref(),
        Some("private, no-store")
    );
    assert_eq!(
        header(&response, "x-content-type-options").as_deref(),
        Some("nosniff")
    );
    // Opened by hand (a link pasted into the address bar), it is a download, never a page on the
    // hub's origin: a «document» Meta labels `text/html` must not run there.
    assert_eq!(
        header(&response, "content-disposition").as_deref(),
        Some("attachment")
    );
    assert_eq!(
        header(&response, "content-security-policy").as_deref(),
        Some("sandbox")
    );
    assert_eq!(body_bytes(response).await, PHOTO);

    let seen = f.seen.lock().unwrap();
    assert_eq!(seen.calls.len(), 1);
    let (media_id, headers) = &seen.calls[0];
    assert_eq!(media_id, "42");
    let get = |k: &str| {
        headers
            .iter()
            .find(|(h, _)| h == k)
            .map(|(_, v)| v.as_str())
    };
    assert_eq!(get("x-hub-token"), Some("machine-secret"));
    assert_eq!(get("x-hub-id"), Some(HUB));
    assert!(
        get("authorization").is_none(),
        "no browser bearer reaches the SaaS"
    );
    assert!(
        get("x-hub-session").is_none(),
        "the local session never leaves the hub"
    );
}

/// A document can weigh 100 MB. Buffering it in the runtime before the first byte leaves means a
/// hub holding it all in memory and an inbox staring at a spinner until the last byte lands.
#[tokio::test]
async fn the_attachment_is_streamed_not_buffered() {
    let (go, release) = tokio::sync::watch::channel(false);
    let f = fixture_with(true, &["whatsapp"], "stream", Some(release)).await;
    let response = tokio::time::timeout(
        Duration::from_secs(5),
        f.router.oneshot(request(
            "/api/hub/whatsapp/media/42",
            Some(&f.admin),
            Some(WHATSAPP),
        )),
    )
    .await
    .expect("the hub waited for the WHOLE file before answering: it buffers instead of streaming")
    .unwrap();
    assert_eq!(response.status(), StatusCode::OK);
    let mut body = response.into_body().into_data_stream();
    let first = tokio::time::timeout(Duration::from_secs(5), body.next())
        .await
        .expect("the first half the SaaS already sent never reached the inbox")
        .unwrap()
        .unwrap();
    assert_eq!(&first[..], &PHOTO[..PHOTO.len() / 2]);
    go.send(true).unwrap();
    let mut rest = Vec::new();
    while let Some(chunk) = body.next().await {
        rest.extend_from_slice(&chunk.unwrap());
    }
    assert_eq!(rest, &PHOTO[PHOTO.len() / 2..]);
}

#[tokio::test]
async fn without_a_session_nobody_downloads_anything() {
    let f = fixture(true, &["whatsapp"], "anon").await;
    let response = f
        .router
        .oneshot(request("/api/hub/whatsapp/media/42", None, Some(WHATSAPP)))
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
    assert!(f.seen.lock().unwrap().calls.is_empty());
}

/// Seeing the photo a customer sent is reading the conversation: a role the owner did not let read
/// the inbox cannot pull its attachments by id either.
#[tokio::test]
async fn a_role_that_cannot_read_the_inbox_cannot_download_its_attachments() {
    let f = fixture(true, &["whatsapp"], "kitchen").await;
    let response = f
        .router
        .oneshot(request(
            "/api/hub/whatsapp/media/42",
            Some(&f.kitchen),
            Some(WHATSAPP),
        ))
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::FORBIDDEN);
    let body = body_json(response).await;
    assert_eq!(body["ok"], false);
    assert_eq!(body["error"]["code"], "permission_denied", "{body}");
    assert!(f.seen.lock().unwrap().calls.is_empty());
}

/// The module half of the gate: the same criterion as the templates door (`notify` granted AND the
/// `whatsapp` channel declared), so a module the owner never pointed at WhatsApp cannot read the
/// business's customers' photos.
#[tokio::test]
async fn a_module_without_notify_on_whatsapp_is_refused_before_the_saas_is_called() {
    for (granted, channels, tag) in [
        (false, &["whatsapp"][..], "not-granted"),
        (true, &["email"][..], "email-only"),
    ] {
        let f = fixture(granted, channels, tag).await;
        let response = f
            .router
            .oneshot(request(
                "/api/hub/whatsapp/media/42",
                Some(&f.admin),
                Some(WHATSAPP),
            ))
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::FORBIDDEN, "{tag}");
        let body = body_json(response).await;
        assert_eq!(body["error"]["code"], "capability_denied", "{tag}: {body}");
        assert!(
            f.seen.lock().unwrap().calls.is_empty(),
            "{tag}: a refused module still reached Meta"
        );
    }
}

/// Meta's ids are digits. Anything else is refused HERE, before any call: it ends up inside a Cloud
/// path. Same code the SaaS answers for it, so the module reads one word whichever side refused.
#[tokio::test]
async fn a_media_id_that_is_not_a_meta_id_never_reaches_the_saas() {
    let f = fixture(true, &["whatsapp"], "hostile").await;
    for hostile in ["abc", "12a", "%2E%2E", "..%2Ftemplates", &"9".repeat(33)] {
        let response = f
            .router
            .clone()
            .oneshot(request(
                &format!("/api/hub/whatsapp/media/{hostile}"),
                Some(&f.admin),
                Some(WHATSAPP),
            ))
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::BAD_REQUEST, "{hostile}");
        let body = body_json(response).await;
        assert_eq!(
            body["error"]["code"], "invalid_media_id",
            "{hostile}: {body}"
        );
    }
    assert!(f.seen.lock().unwrap().calls.is_empty());
    // The longest id Meta can produce still goes through.
    let response = f
        .router
        .oneshot(request(
            &format!("/api/hub/whatsapp/media/{}", "9".repeat(32)),
            Some(&f.admin),
            Some(WHATSAPP),
        ))
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::OK);
}

/// Every refusal of saas#2289 reaches the module in the envelope `unwrap(env)` reads, with its own
/// `code`: the inbox tells «no longer available» from «try again» from «reconnect WhatsApp».
#[tokio::test]
async fn every_refusal_of_the_saas_reaches_the_module_with_its_code() {
    let f = fixture(true, &["whatsapp"], "refusals").await;
    for (id, status, code) in [
        ("404", StatusCode::NOT_FOUND, "media_not_found"),
        ("403", StatusCode::FORBIDDEN, "meta_permission_denied"),
        ("409", StatusCode::CONFLICT, "no_whatsapp_number"),
        // A `5xx` of erplora.com does not cross the edge with its body (hub#1763): it becomes `424`,
        // but the SaaS NAMED this one and the name is what makes the inbox offer «Retry».
        ("502", StatusCode::FAILED_DEPENDENCY, "media_unavailable"),
        // A crash names nothing: one code for «erplora.com could not attend to this».
        ("500", StatusCode::FAILED_DEPENDENCY, "cloud_rejected"),
    ] {
        let response = f
            .router
            .clone()
            .oneshot(request(
                &format!("/api/hub/whatsapp/media/{id}"),
                Some(&f.admin),
                Some(WHATSAPP),
            ))
            .await
            .unwrap();
        assert_eq!(response.status(), status, "{id}");
        assert!(
            header(&response, "content-type")
                .unwrap_or_default()
                .starts_with("application/json"),
            "{id}: a refusal is JSON, never the SaaS's page"
        );
        let body = body_json(response).await;
        assert_eq!(body["ok"], false, "{id}: {body}");
        assert_eq!(body["error"]["code"], code, "{id}: {body}");
    }
}

#[tokio::test]
async fn a_saas_that_does_not_answer_is_a_code_not_a_hang() {
    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), HUB);
    rt.ensure_system_tables().await.unwrap();
    let id = rt.create_user("Ana", "1111", "admin", None).await.unwrap();
    let admin = rt.create_session(&id, 3600, None).await.unwrap();
    let temp = std::env::temp_dir().join(format!("erplora-wa-media-down-{}", std::process::id()));
    // The inbox is installed, as it is on every hub that has attachments to show: its roles are
    // what give the admin the right to read conversations.
    rt.install_from_dir(&module_dir(&temp.join("modules"), &["whatsapp"]))
        .await
        .unwrap();
    let config = HubConfig {
        demo: false,
        hub_id: HUB.into(),
        // Nothing listens on port 9 of loopback.
        cloud_base_url: "http://127.0.0.1:9".into(),
        module_cache: temp.join("modules-cache"),
        auth_mode: AuthMode::Session,
        jwt_public_key: None,
        cloud_api_token: Some("machine-secret".into()),
        device_trust_enforce: false,
        media_dir: temp,
        sector: None,
        dev_mode: false,
        dev_modules_dir: None,
        module_trusted_keys: Vec::new(),
    };
    let response = app(AppState::with_config(rt, config))
        .oneshot(request("/api/hub/whatsapp/media/42", Some(&admin), None))
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::FAILED_DEPENDENCY);
    let body = body_json(response).await;
    assert_eq!(body["ok"], false);
    assert!(
        body["error"]["code"]
            .as_str()
            .is_some_and(|c| c.starts_with("cloud_unreachable")),
        "{body}"
    );
    assert!(
        !body.to_string().contains("127.0.0.1"),
        "the control plane's address must not reach the module: {body}"
    );
}
