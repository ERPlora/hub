//! **The photo of a WhatsApp header, uploaded from a flow step** (hub#2335).
//!
//! A template approved with a photo header sends a photo every time: Meta takes it as a link it
//! downloads. The owner of a salon has no public link to her salon's picture — she has the file.
//! So the step's editor (the `flows` module) hands the file to the runtime, the runtime stores it
//! in the hub's own `media/` under `whatsapp/headers/`, and the step keeps that reference; every
//! send signs it afresh (`notify_transport.rs`).
//!
//! What is asserted: the gate (no session → 401; an employee → 403; a module without
//! `manage_flows` → `capability_denied`; the SaaS NEVER called on any refusal), what the file must
//! be (a JPEG or a PNG read from its BYTES, never from its name; at most 5 MB — Meta's own cap for a
//! header image), where it lands (folder `whatsapp/headers`, a name the hub chose, the bytes
//! untouched, the machine credential on the wire) and a store that fails reaching the editor with
//! its own code.
use axum::body::Body;
use axum::extract::Multipart;
use axum::http::{HeaderMap, Request, StatusCode};
use axum::response::IntoResponse;
use axum::routing::post;
use axum::{Json, Router};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use serde_json::{json, Value};
use std::path::{Path as FsPath, PathBuf};
use std::sync::{Arc, Mutex};
use tower::ServiceExt;

const HUB: &str = "hub-flows-header-image";
const MODULE_HEADER: &str = "x-erplora-module";
/// The module the editor of flows runs as (`client.forModule('flows')`): it declares `manage_flows`.
const EDITOR: &str = "flows";
/// An ordinary installed module: it must not get to write into the hub's files through this door.
const INVENTORY: &str = "inventory";
const DOOR: &str = "/api/hub/flows/whatsapp-header-images";
const SAAS_MEDIA: &str = "/api/v1/hub/device/media/";
const BOUNDARY: &str = "----erplora-hub-2335";
/// Meta's cap for a header image (5 MB, `1024 * 1024`).
const MAX_IMAGE: usize = 5 * 1024 * 1024;

const JPEG: &[u8] = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00the salon\xff\xd9";
const PNG: &[u8] = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDRthe salon";
const PDF: &[u8] = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n";
const GIF: &[u8] = b"GIF89a\x01\x00\x01\x00the salon";

/// One upload as the fake SaaS saw it.
#[derive(Debug, Clone)]
struct Stored {
    headers: Vec<(String, String)>,
    folder: String,
    file_name: String,
    content_type: String,
    bytes: Vec<u8>,
}

impl Stored {
    fn header(&self, name: &str) -> Option<&str> {
        self.headers
            .iter()
            .find(|(k, _)| k == name)
            .map(|(_, v)| v.as_str())
    }
}

type Seen = Arc<Mutex<Vec<Stored>>>;

struct Fixture {
    router: Router,
    admin: String,
    employee: String,
    seen: Seen,
}

fn module_dir(root: &FsPath, id: &str, extra: Value) -> PathBuf {
    let dir = root.join(id);
    std::fs::create_dir_all(&dir).unwrap();
    let mut manifest = json!({ "id": id, "name": id, "version": "1.0.0" });
    if let Value::Object(map) = extra {
        for (k, v) in map {
            manifest[k] = v;
        }
    }
    std::fs::write(
        dir.join("module.json"),
        serde_json::to_string_pretty(&manifest).unwrap(),
    )
    .unwrap();
    dir
}

/// The SaaS media manager (`POST …/media/`, multipart `folder` + `files`): `201 {success, saved}`,
/// or `502 {error, saved: 0, failed: 1}` for a file carrying the `refuse-502` marker — the answer
/// of a store that failed.
async fn fake_saas(seen: Seen) -> String {
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    let saas = Router::new().route(
        SAAS_MEDIA,
        post(move |headers: HeaderMap, mut form: Multipart| {
            let seen = seen.clone();
            async move {
                let mut folder = String::new();
                let mut files = Vec::new();
                while let Some(field) = form.next_field().await.unwrap() {
                    match field.name() {
                        Some("folder") => folder = field.text().await.unwrap(),
                        Some("files") => {
                            let file_name = field.file_name().unwrap_or("").to_string();
                            let content_type = field.content_type().unwrap_or("").to_string();
                            let bytes = field.bytes().await.unwrap().to_vec();
                            files.push((file_name, content_type, bytes));
                        }
                        _ => {}
                    }
                }
                let mut refuse = false;
                for (file_name, content_type, bytes) in files {
                    refuse |= bytes.windows(10).any(|w| w == b"refuse-502");
                    seen.lock().unwrap().push(Stored {
                        headers: headers
                            .iter()
                            .map(|(k, v)| {
                                (k.as_str().to_string(), v.to_str().unwrap_or("").to_string())
                            })
                            .collect(),
                        folder: folder.clone(),
                        file_name,
                        content_type,
                        bytes,
                    });
                }
                if refuse {
                    return (
                        StatusCode::BAD_GATEWAY,
                        Json(json!({"error": "could not store the files", "saved": 0, "failed": 1})),
                    )
                        .into_response();
                }
                (
                    StatusCode::CREATED,
                    Json(json!({"success": true, "saved": 1})),
                )
                    .into_response()
            }
        })
        // The real media manager takes files of up to 25 MB; axum's default 2 MB would refuse
        // the 5 MB photo in this fake before the hub's cap is what is being tested.
        .layer(axum::extract::DefaultBodyLimit::disable()),
    );
    tokio::spawn(async move { axum::serve(listener, saas).await.unwrap() });
    format!("http://{address}")
}

async fn session(rt: &Runtime, name: &str, pin: &str, role: &str) -> String {
    let id = rt.create_user(name, pin, role, None).await.unwrap();
    rt.create_session(&id, 3600, None).await.unwrap()
}

async fn fixture(tag: &str) -> Fixture {
    let seen: Seen = Arc::new(Mutex::new(Vec::new()));
    let cloud_base_url = fake_saas(seen.clone()).await;

    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), HUB);
    rt.ensure_system_tables().await.unwrap();
    let temp = std::env::temp_dir().join(format!(
        "erplora-flows-header-image-{tag}-{}",
        std::process::id()
    ));
    let modules = temp.join("modules");
    rt.install_from_dir(&module_dir(
        &modules,
        EDITOR,
        json!({ "capabilities": { "manage_flows": {} } }),
    ))
    .await
    .unwrap();
    rt.install_from_dir(&module_dir(&modules, INVENTORY, json!({})))
        .await
        .unwrap();
    rt.set_module_capability(EDITOR, "manage_flows", true, "hub_user:admin")
        .await
        .unwrap();
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

/// A browser's `FormData` with one field.
fn form(field: &str, file_name: &str, content_type: &str, bytes: &[u8]) -> Vec<u8> {
    let mut body = Vec::new();
    body.extend_from_slice(
        format!(
            "--{BOUNDARY}\r\nContent-Disposition: form-data; name=\"{field}\"; filename=\"{file_name}\"\r\nContent-Type: {content_type}\r\n\r\n"
        )
        .as_bytes(),
    );
    body.extend_from_slice(bytes);
    body.extend_from_slice(format!("\r\n--{BOUNDARY}--\r\n").as_bytes());
    body
}

fn photo(file_name: &str, bytes: &[u8]) -> Vec<u8> {
    form("file", file_name, "image/jpeg", bytes)
}

fn upload(body: Vec<u8>, session: Option<&str>, module: Option<&str>) -> Request<Body> {
    let mut req = Request::builder()
        .method("POST")
        .uri(DOOR)
        .header(
            "content-type",
            format!("multipart/form-data; boundary={BOUNDARY}"),
        )
        .header("content-length", body.len().to_string());
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

/// The reference the step keeps: `whatsapp/headers/<name>.<ext>`, a name the hub chose — never the
/// one she uploaded, which can carry anything.
fn stored_name(reference: &str, ext: &str) -> String {
    let name = reference
        .strip_prefix("whatsapp/headers/")
        .unwrap_or_else(|| panic!("not in the header folder: {reference}"));
    let stem = name
        .strip_suffix(&format!(".{ext}"))
        .unwrap_or_else(|| panic!("not a .{ext}: {reference}"));
    assert!(
        stem.len() >= 32 && stem.chars().all(|c| c.is_ascii_hexdigit()),
        "the hub names the file, not the upload: {reference}"
    );
    name.to_string()
}

#[tokio::test]
async fn a_jpeg_lands_in_the_header_folder_and_its_reference_comes_back() {
    let f = fixture("jpeg").await;
    let response = f
        .router
        .clone()
        .oneshot(upload(
            photo("../../_logs/salón & co.jpg", JPEG),
            Some(&f.admin),
            Some(EDITOR),
        ))
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::CREATED);
    let body = body_json(response).await;
    assert_eq!(body["ok"], true, "{body}");
    let reference = body["data"]["ref"].as_str().expect("a ref").to_string();
    let name = stored_name(&reference, "jpg");
    assert_eq!(body["data"]["mime_type"], "image/jpeg", "{body}");
    assert_eq!(body["data"]["size"], JPEG.len(), "{body}");

    let seen = f.seen.lock().unwrap().clone();
    assert_eq!(seen.len(), 1, "{seen:?}");
    let stored = &seen[0];
    assert_eq!(stored.folder, "whatsapp/headers");
    assert_eq!(stored.file_name, name, "the reference names the file stored");
    assert_eq!(stored.bytes, JPEG, "the photo is stored untouched");
    assert_eq!(stored.content_type, "image/jpeg");
    assert_eq!(stored.header("x-hub-token"), Some("machine-secret"));
    assert_eq!(stored.header("x-hub-id"), Some(HUB));
    assert!(
        stored.header("x-hub-session").is_none(),
        "the local session never leaves the hub"
    );
}

/// A PNG is a PNG by its bytes, whatever the browser called it.
#[tokio::test]
async fn a_png_is_stored_as_a_png_even_when_named_jpg() {
    let f = fixture("png").await;
    let response = f
        .router
        .clone()
        .oneshot(upload(photo("salon.jpg", PNG), Some(&f.admin), Some(EDITOR)))
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::CREATED);
    let body = body_json(response).await;
    let reference = body["data"]["ref"].as_str().expect("a ref").to_string();
    let name = stored_name(&reference, "png");
    assert_eq!(body["data"]["mime_type"], "image/png", "{body}");
    let seen = f.seen.lock().unwrap().clone();
    assert_eq!(seen[0].file_name, name);
    assert_eq!(seen[0].content_type, "image/png");
}

/// The same photo uploaded twice is the same file: saving the step again does not pile up copies.
#[tokio::test]
async fn the_same_photo_twice_is_the_same_reference() {
    let f = fixture("twice").await;
    let mut refs = Vec::new();
    for _ in 0..2 {
        let response = f
            .router
            .clone()
            .oneshot(upload(photo("salon.jpg", JPEG), Some(&f.admin), Some(EDITOR)))
            .await
            .unwrap();
        refs.push(body_json(response).await["data"]["ref"].clone());
    }
    assert_eq!(refs[0], refs[1]);
    let other = f
        .router
        .clone()
        .oneshot(upload(photo("salon.jpg", PNG), Some(&f.admin), Some(EDITOR)))
        .await
        .unwrap();
    assert_ne!(body_json(other).await["data"]["ref"], refs[0]);
}

/// Meta takes a JPEG or a PNG as a header image and nothing else: a PDF or a GIF — whatever it is
/// called — would be approved nowhere and fail at every send. Refused before anything is stored.
#[tokio::test]
async fn anything_but_a_jpeg_or_a_png_is_refused_before_it_is_stored() {
    let f = fixture("unsupported").await;
    for (name, bytes) in [
        ("salon.jpg", PDF),
        ("salon.png", GIF),
        ("salon.jpg", b"".as_slice()),
        ("salon.jpg", b"\xff\xd8".as_slice()),
    ] {
        let response = f
            .router
            .clone()
            .oneshot(upload(photo(name, bytes), Some(&f.admin), Some(EDITOR)))
            .await
            .unwrap();
        assert_eq!(
            response.status(),
            StatusCode::UNSUPPORTED_MEDIA_TYPE,
            "{name} {bytes:?}"
        );
        assert_eq!(
            body_json(response).await["error"]["code"],
            "whatsapp.header_image_unsupported"
        );
    }
    assert!(f.seen.lock().unwrap().is_empty());
}

/// 5 MB is Meta's cap for a header image: one byte over it would be refused by Meta at every send.
#[tokio::test]
async fn a_photo_over_five_megabytes_is_refused_with_its_code() {
    let f = fixture("large").await;
    let mut exactly = JPEG.to_vec();
    exactly.resize(MAX_IMAGE, 0);
    let mut over = exactly.clone();
    over.push(0);
    let mut far_over = exactly.clone();
    far_over.resize(3 * MAX_IMAGE, 0);

    for bytes in [&over, &far_over] {
        let response = f
            .router
            .clone()
            .oneshot(upload(photo("salon.jpg", bytes), Some(&f.admin), Some(EDITOR)))
            .await
            .unwrap();
        assert_eq!(
            response.status(),
            StatusCode::PAYLOAD_TOO_LARGE,
            "{}",
            bytes.len()
        );
        assert_eq!(
            body_json(response).await["error"]["code"],
            "whatsapp.header_image_too_large",
            "{}",
            bytes.len()
        );
    }
    assert!(f.seen.lock().unwrap().is_empty());

    let response = f
        .router
        .clone()
        .oneshot(upload(photo("salon.jpg", &exactly), Some(&f.admin), Some(EDITOR)))
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::CREATED, "5 MB exactly is taken");
    assert_eq!(f.seen.lock().unwrap()[0].bytes.len(), MAX_IMAGE);
}

#[tokio::test]
async fn a_form_without_the_file_is_refused_with_its_code() {
    let f = fixture("missing").await;
    let response = f
        .router
        .clone()
        .oneshot(upload(
            form("files", "salon.jpg", "image/jpeg", JPEG),
            Some(&f.admin),
            Some(EDITOR),
        ))
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::BAD_REQUEST);
    assert_eq!(
        body_json(response).await["error"]["code"],
        "whatsapp.header_image_missing"
    );
    assert!(f.seen.lock().unwrap().is_empty());
}

/// Same door as the rest of the flows: a human owner/admin, and — when a module is the caller —
/// the module the owner granted `manage_flows`. Nothing is stored for anybody else.
#[tokio::test]
async fn only_an_admin_through_the_flows_editor_can_store_a_header_photo() {
    let f = fixture("gate").await;

    let anonymous = f
        .router
        .clone()
        .oneshot(upload(photo("salon.jpg", JPEG), None, Some(EDITOR)))
        .await
        .unwrap();
    assert_eq!(anonymous.status(), StatusCode::UNAUTHORIZED);

    let employee = f
        .router
        .clone()
        .oneshot(upload(photo("salon.jpg", JPEG), Some(&f.employee), Some(EDITOR)))
        .await
        .unwrap();
    assert_eq!(employee.status(), StatusCode::FORBIDDEN);

    let stranger = f
        .router
        .clone()
        .oneshot(upload(photo("salon.jpg", JPEG), Some(&f.admin), Some(INVENTORY)))
        .await
        .unwrap();
    assert_eq!(stranger.status(), StatusCode::FORBIDDEN);
    assert_eq!(
        body_json(stranger).await["error"]["code"],
        "capability_denied"
    );

    assert!(f.seen.lock().unwrap().is_empty(), "stored for a refused caller");

    // The shell and `curl` with an admin session name no module and are let in.
    let shell = f
        .router
        .clone()
        .oneshot(upload(photo("salon.jpg", JPEG), Some(&f.admin), None))
        .await
        .unwrap();
    assert_eq!(shell.status(), StatusCode::CREATED);
}

/// erplora.com could not store it: the editor learns it with a code it can word, and never gets a
/// reference to a file that is not there.
#[tokio::test]
async fn a_store_that_fails_reaches_the_editor_with_its_code_and_no_reference() {
    let f = fixture("store-fails").await;
    let mut bytes = JPEG.to_vec();
    bytes.extend_from_slice(b"refuse-502");
    let response = f
        .router
        .clone()
        .oneshot(upload(photo("salon.jpg", &bytes), Some(&f.admin), Some(EDITOR)))
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::BAD_GATEWAY);
    let body = body_json(response).await;
    assert_eq!(body["ok"], false, "{body}");
    assert_eq!(body["error"]["code"], "whatsapp.header_image_not_saved");
    assert!(body.get("data").is_none(), "{body}");
    assert!(!f.seen.lock().unwrap().is_empty(), "the store was asked");
}

/// A body that is not a form: the gate still answers first, and then the refusal comes in the
/// envelope the SDK reads, with its code — never axum's plain-text rejection.
#[tokio::test]
async fn a_body_that_is_not_a_form_is_refused_in_the_envelope_after_the_gate() {
    let f = fixture("not-a-form").await;
    let request = |session: Option<&str>| {
        let mut req = Request::builder()
            .method("POST")
            .uri(DOOR)
            .header("content-type", "application/json");
        if let Some(s) = session {
            req = req.header("x-hub-session", s);
        }
        req.body(Body::from(r#"{"file":"salon.jpg"}"#)).unwrap()
    };
    let anonymous = f.router.clone().oneshot(request(None)).await.unwrap();
    assert_eq!(anonymous.status(), StatusCode::UNAUTHORIZED);

    let response = f
        .router
        .clone()
        .oneshot(request(Some(&f.admin)))
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::BAD_REQUEST);
    let body = body_json(response).await;
    assert_eq!(body["ok"], false, "{body}");
    assert_eq!(
        body["error"]["code"], "whatsapp.invalid_header_image_upload",
        "{body}"
    );
    assert!(f.seen.lock().unwrap().is_empty());
}
