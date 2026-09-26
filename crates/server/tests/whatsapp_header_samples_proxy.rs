//! The runtime's door for a template's HEADER SAMPLE (hub#2232) — the hub half of saas#2377.
//!
//! Meta registers a template whose header is a photo, a video or a PDF only with an example of that
//! file already uploaded to it, named by a `header_handle`. The upload is made with the business's
//! Meta token, which only the SaaS holds (ADR-0012), and the SaaS door opens with the hub's
//! **machine credential**, a secret of the runtime that never reaches the browser (ADR-0003). So the
//! module's «Plantillas» tab hands the file to the runtime, and the runtime relays it — in
//! streaming, because a PDF sample can weigh 100 MB.
//!
//! What is asserted: the gate (no session → 401; an employee → 403; a module without
//! `notify:whatsapp` → refused, and the SaaS is NEVER called on any refusal), the credential on the
//! wire (machine only), the multipart body arriving byte for byte with its boundary and its length,
//! the body being STREAMED rather than buffered, a body that is not a form or that is bigger than
//! any sample Meta takes refused before the SaaS is called, and every refusal of the SaaS reaching
//! the module with its own `code` in the envelope the SDK reads.
use axum::body::{Body, Bytes};
use axum::http::{HeaderMap, Request, StatusCode};
use axum::response::IntoResponse;
use axum::routing::post;
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

const HUB: &str = "hub-wa-header-samples";
const MODULE_HEADER: &str = "x-erplora-module";
const WHATSAPP: &str = "whatsapp_inbox";
const DOOR: &str = "/api/hub/whatsapp/template-header-samples";
const SAAS_DOOR: &str = "/api/v1/hub/device/whatsapp/template-header-samples/";
const BOUNDARY: &str = "----erplora-hub-2232";
/// The largest sample Meta takes is a 100 MB PDF (saas#2377, `MB = 1024 * 1024`).
const LARGEST_SAMPLE: u64 = 100 * 1024 * 1024;

fn module_dir(root: &FsPath, channels: &[&str]) -> PathBuf {
    let dir = root.join(WHATSAPP);
    std::fs::create_dir_all(&dir).unwrap();
    let manifest = json!({
        "id": WHATSAPP,
        "name": WHATSAPP,
        "version": "2.1.80",
        "capabilities": { "notify": { "channels": channels } },
    });
    std::fs::write(
        dir.join("module.json"),
        serde_json::to_string_pretty(&manifest).unwrap(),
    )
    .unwrap();
    dir
}

/// One call as the fake SaaS saw it: its headers and the whole body it read.
struct Call {
    headers: Vec<(String, String)>,
    body: Vec<u8>,
}

#[derive(Default)]
struct Seen {
    calls: Vec<Call>,
}

impl Call {
    fn header(&self, name: &str) -> Option<&str> {
        self.headers
            .iter()
            .find(|(k, _)| k == name)
            .map(|(_, v)| v.as_str())
    }
}

struct Fixture {
    router: Router,
    admin: String,
    employee: String,
    seen: Arc<Mutex<Seen>>,
}

async fn fixture(granted: bool, channels: &[&str], tag: &str) -> Fixture {
    fixture_with(granted, channels, tag, None).await
}

/// `first_chunk`: when given, the fake SaaS reports on it the moment the FIRST chunk of the body
/// reaches it — the lever the streaming test pulls.
async fn fixture_with(
    granted: bool,
    channels: &[&str],
    tag: &str,
    first_chunk: Option<tokio::sync::mpsc::UnboundedSender<()>>,
) -> Fixture {
    let seen = Arc::new(Mutex::new(Seen::default()));
    let cloud_base_url = fake_saas(seen.clone(), first_chunk).await;

    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), HUB);
    rt.ensure_system_tables().await.unwrap();
    let temp = std::env::temp_dir().join(format!(
        "erplora-wa-header-samples-{tag}-{}-{granted}",
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
        seen,
    }
}

async fn session(rt: &Runtime, name: &str, pin: &str, role: &str) -> String {
    let id = rt.create_user(name, pin, role, None).await.unwrap();
    rt.create_session(&id, 3600, None).await.unwrap()
}

/// The SaaS of saas#2377, per its contract: `201 {header_handle, format, mime_type, size}`, and
/// every refusal as `{"error": "<code>", "detail": "…"}`. Which refusal is picked by a marker
/// inside the file, so the request that reaches it is the real one.
async fn fake_saas(
    seen: Arc<Mutex<Seen>>,
    first_chunk: Option<tokio::sync::mpsc::UnboundedSender<()>>,
) -> String {
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    let saas = Router::new().route(
        SAAS_DOOR,
        post(move |headers: HeaderMap, body: Body| {
            let seen = seen.clone();
            let first_chunk = first_chunk.clone();
            async move {
                let mut stream = body.into_data_stream();
                let mut received = Vec::new();
                while let Some(chunk) = stream.next().await {
                    let chunk = chunk.unwrap();
                    if received.is_empty() {
                        if let Some(tx) = first_chunk.as_ref() {
                            let _ = tx.send(());
                        }
                    }
                    received.extend_from_slice(&chunk);
                }
                let refusal = |status: StatusCode, code: &str| {
                    (
                        status,
                        Json(json!({ "error": code, "detail": "for the log only" })),
                    )
                        .into_response()
                };
                let marked = |m: &str| received.windows(m.len()).any(|w| w == m.as_bytes());
                let answer = if marked("refuse-400") {
                    refusal(StatusCode::BAD_REQUEST, "unsupported_header_sample")
                } else if marked("refuse-409") {
                    refusal(StatusCode::CONFLICT, "no_whatsapp_number")
                } else if marked("refuse-429") {
                    refusal(StatusCode::TOO_MANY_REQUESTS, "meta_rate_limited")
                } else if marked("refuse-502") {
                    refusal(StatusCode::BAD_GATEWAY, "meta_template_failed")
                } else if marked("refuse-503") {
                    refusal(StatusCode::SERVICE_UNAVAILABLE, "whatsapp_not_configured")
                } else if marked("crash-500") {
                    (
                        StatusCode::INTERNAL_SERVER_ERROR,
                        "<html>Server Error (500)</html>",
                    )
                        .into_response()
                } else {
                    (
                        StatusCode::CREATED,
                        Json(json!({
                            "header_handle": "4::aW1hZ2UvanBlZw==:ARb-sample",
                            "format": "IMAGE",
                            "mime_type": "image/jpeg",
                            "size": 17,
                        })),
                    )
                        .into_response()
                };
                seen.lock().unwrap().calls.push(Call {
                    headers: headers
                        .iter()
                        .map(|(k, v)| {
                            (k.as_str().to_string(), v.to_str().unwrap_or("").to_string())
                        })
                        .collect(),
                    body: received,
                });
                answer
            }
        }),
    );
    tokio::spawn(async move { axum::serve(listener, saas).await.unwrap() });
    format!("http://{address}")
}

/// A browser's `FormData` with the one field the SaaS reads, `file`. Bytes include NUL and
/// non-UTF-8 so nothing on the way can have treated the body as text.
fn form(file: &[u8]) -> Vec<u8> {
    let mut body = Vec::new();
    body.extend_from_slice(
        format!(
            "--{BOUNDARY}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"cabecera.jpg\"\r\nContent-Type: image/jpeg\r\n\r\n"
        )
        .as_bytes(),
    );
    body.extend_from_slice(file);
    body.extend_from_slice(format!("\r\n--{BOUNDARY}--\r\n").as_bytes());
    body
}

const PHOTO: &[u8] = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00a sample\xff\xd9";

fn upload(body: Vec<u8>, session: Option<&str>, module: Option<&str>) -> Request<Body> {
    let mut req = Request::builder()
        .method("POST")
        .uri(DOOR)
        .header(
            "content-type",
            format!("multipart/form-data; boundary={BOUNDARY}"),
        )
        .header("content-length", body.len().to_string())
        .header("accept-language", "es-ES");
    if let Some(s) = session {
        req = req.header("x-hub-session", s);
    }
    if let Some(m) = module {
        req = req.header(MODULE_HEADER, m);
    }
    req.body(Body::from(body)).unwrap()
}

async fn body_json(response: axum::response::Response) -> Value {
    let bytes = axum::body::to_bytes(response.into_body(), usize::MAX)
        .await
        .unwrap();
    serde_json::from_slice(&bytes).unwrap_or(Value::Null)
}

#[tokio::test]
async fn the_sample_reaches_the_saas_byte_for_byte_and_the_handle_comes_back() {
    let f = fixture(true, &["whatsapp"], "happy").await;
    let sent = form(PHOTO);
    let response = f
        .router
        .oneshot(upload(sent.clone(), Some(&f.admin), Some(WHATSAPP)))
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::CREATED);
    let body = body_json(response).await;
    assert_eq!(body["ok"], true, "{body}");
    assert_eq!(
        body["data"]["header_handle"], "4::aW1hZ2UvanBlZw==:ARb-sample",
        "{body}"
    );
    assert_eq!(body["data"]["format"], "IMAGE", "{body}");

    let seen = f.seen.lock().unwrap();
    assert_eq!(seen.calls.len(), 1);
    let call = &seen.calls[0];
    assert_eq!(call.body, sent, "the form must reach the SaaS untouched");
    // The boundary travels with the body: without it the SaaS cannot find the `file` field.
    assert_eq!(
        call.header("content-type"),
        Some(format!("multipart/form-data; boundary={BOUNDARY}").as_str())
    );
    // Sent with its length, not chunked: the SaaS (and the edge in front of it) knows up front
    // how much is coming.
    assert_eq!(
        call.header("content-length"),
        Some(sent.len().to_string().as_str())
    );
    assert!(call.header("transfer-encoding").is_none());
    // The SaaS words its `detail` in the owner's language, like on every other relayed door.
    assert_eq!(call.header("accept-language"), Some("es-ES"));
    assert_eq!(call.header("x-hub-token"), Some("machine-secret"));
    assert_eq!(call.header("x-hub-id"), Some(HUB));
    assert!(call.header("authorization").is_none());
    assert!(
        call.header("x-hub-session").is_none(),
        "the local session never leaves the hub"
    );
    assert!(call.header("cookie").is_none());
}

/// A PDF sample can weigh 100 MB. Reading it whole into the runtime before the first byte leaves
/// means a hub holding it all in memory; relaying it chunk by chunk does not.
#[tokio::test]
async fn the_sample_is_streamed_to_the_saas_not_buffered() {
    let (first_tx, mut first_rx) = tokio::sync::mpsc::unbounded_channel();
    let f = fixture_with(true, &["whatsapp"], "stream", Some(first_tx)).await;
    let sent = form(PHOTO);
    let (head, tail) = sent.split_at(sent.len() / 2);
    let (head, tail) = (Bytes::copy_from_slice(head), Bytes::copy_from_slice(tail));
    let (go, release) = tokio::sync::oneshot::channel::<()>();
    let body = futures_util::stream::unfold(
        (0u8, Some(release), head, tail),
        |(step, release, head, tail)| async move {
            match step {
                0 => Some((
                    Ok::<_, std::io::Error>(head.clone()),
                    (1, release, head, tail),
                )),
                1 => {
                    if let Some(r) = release {
                        let _ = r.await;
                    }
                    Some((Ok(tail.clone()), (2, None, head, tail)))
                }
                _ => None,
            }
        },
    );
    let request = Request::builder()
        .method("POST")
        .uri(DOOR)
        .header(
            "content-type",
            format!("multipart/form-data; boundary={BOUNDARY}"),
        )
        .header("content-length", sent.len().to_string())
        .header("x-hub-session", &f.admin)
        .header(MODULE_HEADER, WHATSAPP)
        .body(Body::from_stream(body))
        .unwrap();
    let router = f.router.clone();
    let pending = tokio::spawn(async move { router.oneshot(request).await.unwrap() });
    tokio::time::timeout(Duration::from_secs(5), first_rx.recv())
        .await
        .expect("the SaaS saw nothing while the rest of the file was still on its way: the hub buffers the upload instead of streaming it");
    go.send(()).unwrap();
    let response = pending.await.unwrap();
    assert_eq!(response.status(), StatusCode::CREATED);
    assert_eq!(f.seen.lock().unwrap().calls[0].body, sent);
}

#[tokio::test]
async fn without_a_session_nothing_is_uploaded() {
    let f = fixture(true, &["whatsapp"], "anon").await;
    let response = f
        .router
        .oneshot(upload(form(PHOTO), None, Some(WHATSAPP)))
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
    assert!(f.seen.lock().unwrap().calls.is_empty());
}

/// Same gate as registering the template it belongs to: what the business promises Meta is
/// management, not the shift.
#[tokio::test]
async fn an_employee_cannot_upload_a_sample() {
    let f = fixture(true, &["whatsapp"], "employee").await;
    let response = f
        .router
        .oneshot(upload(form(PHOTO), Some(&f.employee), Some(WHATSAPP)))
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::FORBIDDEN);
    assert!(f.seen.lock().unwrap().calls.is_empty());
}

/// The module half of the gate, the same as the templates door: `notify` granted AND the
/// `whatsapp` channel declared.
#[tokio::test]
async fn a_module_without_notify_on_whatsapp_is_refused_before_the_saas_is_called() {
    for (granted, channels, tag) in [
        (false, &["whatsapp"][..], "not-granted"),
        (true, &["email"][..], "email-only"),
    ] {
        let f = fixture(granted, channels, tag).await;
        let response = f
            .router
            .oneshot(upload(form(PHOTO), Some(&f.admin), Some(WHATSAPP)))
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

/// Only a form goes up: the SaaS reads the multipart field `file`, and anything else would reach it
/// only to be refused with a less useful word.
#[tokio::test]
async fn a_body_that_is_not_a_form_is_refused_before_the_saas_is_called() {
    let f = fixture(true, &["whatsapp"], "not-form").await;
    for content_type in [
        Some("application/json"),
        Some("image/jpeg"),
        Some("multipart/form-data"),
        // A form without its boundary: the SaaS could not find the `file` field in it.
        Some("multipart/form-data; charset=utf-8"),
        Some("multipart/form-data; boundary="),
        None,
    ] {
        let mut req = Request::builder()
            .method("POST")
            .uri(DOOR)
            .header("content-length", PHOTO.len().to_string())
            .header("x-hub-session", &f.admin)
            .header(MODULE_HEADER, WHATSAPP);
        if let Some(ct) = content_type {
            req = req.header("content-type", ct);
        }
        let response = f
            .router
            .clone()
            .oneshot(req.body(Body::from(PHOTO.to_vec())).unwrap())
            .await
            .unwrap();
        assert_eq!(
            response.status(),
            StatusCode::BAD_REQUEST,
            "{content_type:?}"
        );
        let body = body_json(response).await;
        assert_eq!(
            body["error"]["code"], "whatsapp.invalid_header_sample_upload",
            "{content_type:?}: {body}"
        );
    }
    assert!(f.seen.lock().unwrap().calls.is_empty());
}

/// A form bigger than the largest sample Meta takes (a 100 MB PDF, plus the few bytes of framing)
/// is refused from its declared length, before a single byte is relayed — with the same code the
/// SaaS answers, so the tab reads one word whichever side refused. A form that does not declare its
/// length is refused too: without it the hub cannot hold the line without reading the body.
#[tokio::test]
async fn a_form_bigger_than_any_sample_meta_takes_never_reaches_the_saas() {
    let f = fixture(true, &["whatsapp"], "too-big").await;
    let too_big = LARGEST_SAMPLE + 1024 * 1024 + 1;
    let response = f
        .router
        .clone()
        .oneshot(
            Request::builder()
                .method("POST")
                .uri(DOOR)
                .header(
                    "content-type",
                    format!("multipart/form-data; boundary={BOUNDARY}"),
                )
                .header("content-length", too_big.to_string())
                .header("x-hub-session", &f.admin)
                .header(MODULE_HEADER, WHATSAPP)
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::PAYLOAD_TOO_LARGE);
    let body = body_json(response).await;
    assert_eq!(body["error"]["code"], "header_sample_too_large", "{body}");

    let response = f
        .router
        .clone()
        .oneshot(
            Request::builder()
                .method("POST")
                .uri(DOOR)
                .header(
                    "content-type",
                    format!("multipart/form-data; boundary={BOUNDARY}"),
                )
                .header("x-hub-session", &f.admin)
                .header(MODULE_HEADER, WHATSAPP)
                .body(Body::from_stream(futures_util::stream::iter([Ok::<
                    _,
                    std::io::Error,
                >(
                    Bytes::from(form(PHOTO)),
                )])))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::LENGTH_REQUIRED);
    let body = body_json(response).await;
    assert_eq!(
        body["error"]["code"], "whatsapp.header_sample_length_required",
        "{body}"
    );
    assert!(f.seen.lock().unwrap().calls.is_empty());
}

/// Every refusal of saas#2377 reaches the module in the envelope `unwrap(env)` reads, with its own
/// `code` — `5xx` included, which cross as `424` (hub#1763) but keep the code the SaaS named, so
/// the tab tells «this file is not a photo» from «reconnect WhatsApp» from «try again».
#[tokio::test]
async fn every_refusal_of_the_saas_reaches_the_module_with_its_code() {
    let f = fixture(true, &["whatsapp"], "refusals").await;
    for (marker, status, code) in [
        (
            "refuse-400",
            StatusCode::BAD_REQUEST,
            "unsupported_header_sample",
        ),
        ("refuse-409", StatusCode::CONFLICT, "no_whatsapp_number"),
        (
            "refuse-429",
            StatusCode::TOO_MANY_REQUESTS,
            "meta_rate_limited",
        ),
        (
            "refuse-502",
            StatusCode::FAILED_DEPENDENCY,
            "meta_template_failed",
        ),
        (
            "refuse-503",
            StatusCode::FAILED_DEPENDENCY,
            "whatsapp_not_configured",
        ),
        ("crash-500", StatusCode::FAILED_DEPENDENCY, "cloud_rejected"),
    ] {
        let response = f
            .router
            .clone()
            .oneshot(upload(
                form(marker.as_bytes()),
                Some(&f.admin),
                Some(WHATSAPP),
            ))
            .await
            .unwrap();
        assert_eq!(response.status(), status, "{marker}");
        let body = body_json(response).await;
        assert_eq!(body["ok"], false, "{marker}: {body}");
        assert_eq!(body["error"]["code"], code, "{marker}: {body}");
    }
}

#[tokio::test]
async fn a_saas_that_does_not_answer_is_a_code_not_a_hang() {
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), HUB);
    rt.ensure_system_tables().await.unwrap();
    let id = rt.create_user("Ana", "1111", "admin", None).await.unwrap();
    let admin = rt.create_session(&id, 3600, None).await.unwrap();
    let temp = std::env::temp_dir().join(format!(
        "erplora-wa-header-samples-down-{}",
        std::process::id()
    ));
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
        .oneshot(upload(form(PHOTO), Some(&admin), None))
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::FAILED_DEPENDENCY);
    let body = body_json(response).await;
    assert_eq!(body["ok"], false);
    assert_eq!(body["error"]["code"], "cloud_unreachable", "{body}");
    assert!(
        !body.to_string().contains("127.0.0.1"),
        "the control plane's address must not reach the module: {body}"
    );
}
