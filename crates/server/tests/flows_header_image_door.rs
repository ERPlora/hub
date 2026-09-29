//! **The photo, video or PDF of a WhatsApp header, uploaded from a flow step** (hub#2335,
//! hub#2347).
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
//! its own code. For a video and a PDF (hub#2347): the file must be the kind its header is, under
//! Meta's cap for it; the name is the fingerprint of EVERY byte; and a store that stumbles once
//! gets the whole file again.
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
/// An MP4: its first box is `ftyp` (at byte 4) with an ISO brand.
const MP4: &[u8] = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isomthe promo";
/// A QuickTime `.mov` is also an `ftyp` box, but Meta takes only MP4 (and 3GPP) as a header video.
const MOV: &[u8] = b"\x00\x00\x00\x14ftypqt  \x00\x00\x00\x00qt  the promo";
/// An iPhone photo (HEIC) and an MPEG-4 audio (M4A) are `ftyp` files too, and neither is a video.
const HEIC: &[u8] = b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00mif1heicthe salon";
const M4A: &[u8] = b"\x00\x00\x00\x18ftypM4A \x00\x00\x00\x00M4A mp42the jingle";
/// Meta's cap for a header video (16 MB) and for a header document (100 MB).
const MAX_VIDEO: usize = 16 * 1024 * 1024;
const MAX_DOCUMENT: usize = 100 * 1024 * 1024;

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
/// of a store that failed — and `503` the FIRST time it sees a file carrying `retry-503`, the
/// answer of a store that stumbled and is fine a moment later.
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
                let mut stumble = false;
                for (file_name, content_type, bytes) in files {
                    refuse |= bytes.windows(10).any(|w| w == b"refuse-502");
                    stumble |= bytes.windows(9).any(|w| w == b"retry-503")
                        && !seen.lock().unwrap().iter().any(|s| s.bytes == bytes);
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
                if stumble {
                    return (
                        StatusCode::SERVICE_UNAVAILABLE,
                        Json(json!({"error": "try again"})),
                    )
                        .into_response();
                }
                if refuse {
                    return (
                        StatusCode::BAD_GATEWAY,
                        Json(
                            json!({"error": "could not store the files", "saved": 0, "failed": 1}),
                        ),
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

/// A browser's `FormData` with the header's `kind` and its `file`, in either order.
fn media(kind: &str, bytes: &[u8], kind_first: bool) -> Vec<u8> {
    let kind_part = format!(
        "--{BOUNDARY}\r\nContent-Disposition: form-data; name=\"kind\"\r\n\r\n{kind}\r\n"
    );
    let mut file_part = format!(
        "--{BOUNDARY}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"promo\"\r\nContent-Type: application/octet-stream\r\n\r\n"
    )
    .into_bytes();
    file_part.extend_from_slice(bytes);
    file_part.extend_from_slice(b"\r\n");
    let mut body = Vec::new();
    if kind_first {
        body.extend_from_slice(kind_part.as_bytes());
        body.extend_from_slice(&file_part);
    } else {
        body.extend_from_slice(&file_part);
        body.extend_from_slice(kind_part.as_bytes());
    }
    body.extend_from_slice(format!("--{BOUNDARY}--\r\n").as_bytes());
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
    assert_eq!(
        stored.file_name, name,
        "the reference names the file stored"
    );
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
        .oneshot(upload(
            photo("salon.jpg", PNG),
            Some(&f.admin),
            Some(EDITOR),
        ))
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
            .oneshot(upload(
                photo("salon.jpg", JPEG),
                Some(&f.admin),
                Some(EDITOR),
            ))
            .await
            .unwrap();
        refs.push(body_json(response).await["data"]["ref"].clone());
    }
    assert_eq!(refs[0], refs[1]);
    let other = f
        .router
        .clone()
        .oneshot(upload(
            photo("salon.jpg", PNG),
            Some(&f.admin),
            Some(EDITOR),
        ))
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
            .oneshot(upload(
                photo("salon.jpg", bytes),
                Some(&f.admin),
                Some(EDITOR),
            ))
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
        .oneshot(upload(
            photo("salon.jpg", &exactly),
            Some(&f.admin),
            Some(EDITOR),
        ))
        .await
        .unwrap();
    assert_eq!(
        response.status(),
        StatusCode::CREATED,
        "5 MB exactly is taken"
    );
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
        .oneshot(upload(
            photo("salon.jpg", JPEG),
            Some(&f.employee),
            Some(EDITOR),
        ))
        .await
        .unwrap();
    assert_eq!(employee.status(), StatusCode::FORBIDDEN);

    let stranger = f
        .router
        .clone()
        .oneshot(upload(
            photo("salon.jpg", JPEG),
            Some(&f.admin),
            Some(INVENTORY),
        ))
        .await
        .unwrap();
    assert_eq!(stranger.status(), StatusCode::FORBIDDEN);
    assert_eq!(
        body_json(stranger).await["error"]["code"],
        "capability_denied"
    );

    assert!(
        f.seen.lock().unwrap().is_empty(),
        "stored for a refused caller"
    );

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
        .oneshot(upload(
            photo("salon.jpg", &bytes),
            Some(&f.admin),
            Some(EDITOR),
        ))
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

/// **A video or a PDF for the header** (hub#2347): the promotion's video and the restaurant's menu
/// are stored like the photo — in the header folder, under a name the hub chose from the bytes,
/// with the extension and type of what the bytes ARE — whichever order the form sends its fields.
/// Relayed to erplora.com with its length declared: a body that big is streamed from disk, never
/// held whole in a 96 MiB hub, and the store must still see a `Content-Length`, not a chunked body.
#[tokio::test]
async fn a_video_and_a_pdf_land_in_the_header_folder_as_what_their_bytes_are() {
    let f = fixture("video-pdf").await;
    let cases = [
        ("video", MP4, "mp4", "video/mp4", true),
        ("document", PDF, "pdf", "application/pdf", true),
        ("document", PDF, "pdf", "application/pdf", false),
    ];
    for (index, (kind, bytes, ext, mime, kind_first)) in cases.into_iter().enumerate() {
        let response = f
            .router
            .clone()
            .oneshot(upload(
                media(kind, bytes, kind_first),
                Some(&f.admin),
                Some(EDITOR),
            ))
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::CREATED, "{kind}");
        let body = body_json(response).await;
        let reference = body["data"]["ref"].as_str().expect("a ref").to_string();
        let name = stored_name(&reference, ext);
        assert_eq!(body["data"]["mime_type"], mime, "{body}");
        assert_eq!(body["data"]["size"], bytes.len(), "{body}");

        let seen = f.seen.lock().unwrap().clone();
        assert_eq!(seen.len(), index + 1, "{seen:?}");
        let stored = &seen[index];
        assert_eq!(stored.folder, "whatsapp/headers");
        assert_eq!(stored.file_name, name);
        assert_eq!(stored.bytes, bytes, "{kind}: stored untouched");
        assert_eq!(stored.content_type, mime);
        assert_eq!(stored.header("x-hub-token"), Some("machine-secret"));
        assert!(
            stored.header("content-length").is_some() && stored.header("transfer-encoding").is_none(),
            "{kind}: the store gets the length, not a chunked body: {:?}",
            stored.headers
        );
    }
}

/// **The file must be the kind its header is.** A step whose approved header is a video cannot
/// keep a photo, a QuickTime movie or a PDF — Meta would refuse it at every send — and a step with
/// a photo header (no `kind`: the form of hub#2335) still takes only a JPEG or a PNG. Refused
/// before anything is stored, with the code of the header that was asked for, whether the form
/// names its kind before the file or after it.
#[tokio::test]
async fn a_file_that_is_not_the_kind_of_its_header_is_refused_before_it_is_stored() {
    let f = fixture("wrong-kind").await;
    for (kind, bytes, kind_first) in [
        ("video", JPEG, true),
        ("video", MOV, true),
        ("video", HEIC, true),
        ("video", M4A, false),
        ("image", HEIC, true),
        ("video", PDF, true),
        ("video", b"".as_slice(), true),
        ("document", MP4, true),
        ("document", JPEG, true),
        ("document", JPEG, false),
        ("image", MP4, true),
        ("image", PDF, false),
    ] {
        let response = f
            .router
            .clone()
            .oneshot(upload(
                media(kind, bytes, kind_first),
                Some(&f.admin),
                Some(EDITOR),
            ))
            .await
            .unwrap();
        assert_eq!(
            response.status(),
            StatusCode::UNSUPPORTED_MEDIA_TYPE,
            "{kind} {bytes:?}"
        );
        assert_eq!(
            body_json(response).await["error"]["code"],
            format!("whatsapp.header_{kind}_unsupported"),
            "{kind} {bytes:?}"
        );
    }
    let response = f
        .router
        .clone()
        .oneshot(upload(photo("promo.mp4", MP4), Some(&f.admin), Some(EDITOR)))
        .await
        .unwrap();
    assert_eq!(
        body_json(response).await["error"]["code"],
        "whatsapp.header_image_unsupported",
        "no kind is a photo header"
    );
    assert!(f.seen.lock().unwrap().is_empty());
}

/// Meta's caps: a header video weighs 16 MB at most and a header document 100 MB. One byte over is
/// refused with the code of its kind; exactly the cap is taken.
#[tokio::test]
async fn a_video_over_sixteen_and_a_pdf_over_a_hundred_megabytes_are_refused_with_their_code() {
    let f = fixture("media-large").await;
    for (kind, head, cap) in [("video", MP4, MAX_VIDEO), ("document", PDF, MAX_DOCUMENT)] {
        let mut exactly = head.to_vec();
        exactly.resize(cap, 0);
        let mut over = exactly.clone();
        over.push(0);
        let response = f
            .router
            .clone()
            .oneshot(upload(media(kind, &over, true), Some(&f.admin), Some(EDITOR)))
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::PAYLOAD_TOO_LARGE, "{kind}");
        assert_eq!(
            body_json(response).await["error"]["code"],
            format!("whatsapp.header_{kind}_too_large"),
        );
        assert!(f.seen.lock().unwrap().is_empty(), "{kind}");

        let response = f
            .router
            .clone()
            .oneshot(upload(
                media(kind, &exactly, true),
                Some(&f.admin),
                Some(EDITOR),
            ))
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::CREATED, "{kind}: the cap is taken");
        let stored = f.seen.lock().unwrap().pop().expect("stored");
        assert_eq!(stored.bytes.len(), cap, "{kind}");
    }
}

/// A file of another kind that is ALSO over its own cap — a 17 MB video on a document header — is
/// refused as not being of the header's kind, not as too large: «choose a lighter one» would send
/// her to shrink a file that can never go there. Whether the form names its kind first or last.
#[tokio::test]
async fn a_file_of_another_kind_over_its_own_cap_is_refused_as_the_wrong_kind() {
    let f = fixture("wrong-kind-large").await;
    let mut video = MP4.to_vec();
    video.resize(MAX_VIDEO + 1, 0);
    for kind_first in [false, true] {
        let response = f
            .router
            .clone()
            .oneshot(upload(
                media("document", &video, kind_first),
                Some(&f.admin),
                Some(EDITOR),
            ))
            .await
            .unwrap();
        assert_eq!(
            response.status(),
            StatusCode::UNSUPPORTED_MEDIA_TYPE,
            "kind first: {kind_first}"
        );
        assert_eq!(
            body_json(response).await["error"]["code"],
            "whatsapp.header_document_unsupported",
            "kind first: {kind_first}"
        );
    }
    assert!(f.seen.lock().unwrap().is_empty());
}

/// A `kind` that is not a header Meta takes a file for is refused by name, before a byte is kept.
#[tokio::test]
async fn an_unknown_kind_is_refused_with_its_code() {
    let f = fixture("unknown-kind").await;
    for kind in ["text", "audio", "", "Video"] {
        let response = f
            .router
            .clone()
            .oneshot(upload(media(kind, PDF, true), Some(&f.admin), Some(EDITOR)))
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::BAD_REQUEST, "{kind:?}");
        assert_eq!(
            body_json(response).await["error"]["code"],
            "whatsapp.header_media_kind_unknown",
            "{kind:?}"
        );
    }
    assert!(f.seen.lock().unwrap().is_empty());
}

/// A missing file and a failed store answer with the code of the header that was asked for, so
/// the editor words them as a video or a document, not as a photo.
#[tokio::test]
async fn a_missing_video_and_a_pdf_that_fails_to_store_answer_with_their_own_codes() {
    let f = fixture("media-missing").await;
    let only_kind = format!(
        "--{BOUNDARY}\r\nContent-Disposition: form-data; name=\"kind\"\r\n\r\nvideo\r\n--{BOUNDARY}--\r\n"
    );
    let response = f
        .router
        .clone()
        .oneshot(upload(only_kind.into_bytes(), Some(&f.admin), Some(EDITOR)))
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::BAD_REQUEST);
    assert_eq!(
        body_json(response).await["error"]["code"],
        "whatsapp.header_video_missing"
    );
    assert!(f.seen.lock().unwrap().is_empty());

    let mut bytes = PDF.to_vec();
    bytes.extend_from_slice(b"refuse-502");
    let response = f
        .router
        .clone()
        .oneshot(upload(media("document", &bytes, true), Some(&f.admin), Some(EDITOR)))
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::BAD_GATEWAY);
    let body = body_json(response).await;
    assert_eq!(body["error"]["code"], "whatsapp.header_document_not_saved");
    assert!(body.get("data").is_none(), "{body}");
}

/// **The name is the fingerprint of EVERY byte of the file.** A header file is stored under the
/// SHA-256 of its content: the same file twice is one file, and two files never share a name — the
/// second promotion's video must not overwrite the first because both open with the same frames.
/// Files of megabytes, read in many chunks, and the photo of hub#2335 (no `kind`) the same.
#[tokio::test]
async fn the_reference_is_the_fingerprint_of_every_byte_of_the_file() {
    use sha2::{Digest, Sha256};

    let fingerprint = |bytes: &[u8]| -> String {
        Sha256::digest(bytes)
            .iter()
            .map(|b| format!("{b:02x}"))
            .collect()
    };
    let f = fixture("fingerprint").await;
    let mut first = MP4.to_vec();
    first.resize(3 * 1024 * 1024, 7);
    let mut second = first.clone();
    *second.last_mut().expect("bytes") = 8;
    let mut refs = Vec::new();
    for bytes in [&first, &second, &first] {
        let response = f
            .router
            .clone()
            .oneshot(upload(
                media("video", bytes, true),
                Some(&f.admin),
                Some(EDITOR),
            ))
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::CREATED);
        let body = body_json(response).await;
        assert_eq!(
            body["data"]["ref"],
            format!("whatsapp/headers/{}.mp4", fingerprint(bytes)),
            "{body}"
        );
        refs.push(body["data"]["ref"].clone());
    }
    assert_ne!(refs[0], refs[1], "they differ in their last byte");
    assert_eq!(refs[0], refs[2], "the same video twice is one file");

    let response = f
        .router
        .clone()
        .oneshot(upload(
            photo("salon.jpg", JPEG),
            Some(&f.admin),
            Some(EDITOR),
        ))
        .await
        .unwrap();
    assert_eq!(
        body_json(response).await["data"]["ref"],
        format!("whatsapp/headers/{}.jpg", fingerprint(JPEG))
    );
}

/// **A store that stumbles once is asked again, with the whole file again.** The file goes up as
/// a stream read from disk, and a stream already sent cannot be sent twice: every attempt reads
/// the file from its first byte and declares its length.
#[tokio::test]
async fn a_store_that_stumbles_once_gets_the_whole_file_again() {
    let f = fixture("stumbles").await;
    let mut bytes = PDF.to_vec();
    bytes.extend_from_slice(b"retry-503");
    bytes.resize(200 * 1024, b' ');
    let response = f
        .router
        .clone()
        .oneshot(upload(
            media("document", &bytes, true),
            Some(&f.admin),
            Some(EDITOR),
        ))
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::CREATED);
    let body = body_json(response).await;
    let name = stored_name(body["data"]["ref"].as_str().expect("a ref"), "pdf");

    let seen = f.seen.lock().unwrap().clone();
    assert_eq!(seen.len(), 2, "refused once, stored at the second attempt");
    for attempt in &seen {
        assert_eq!(attempt.file_name, name);
        assert_eq!(attempt.bytes, bytes, "every attempt carries the whole file");
        assert_eq!(
            attempt.header("content-length").is_some(),
            attempt.header("transfer-encoding").is_none(),
            "{:?}",
            attempt.headers
        );
        assert!(attempt.header("content-length").is_some());
    }
}

/// A body bigger than the route takes at all — past the largest cap, the document's — is refused
/// as too large in the envelope the SDK reads, never as a broken form, and nothing is stored.
#[tokio::test]
async fn a_body_bigger_than_the_largest_header_is_refused_as_too_large() {
    let f = fixture("over-the-route").await;
    let mut bytes = PDF.to_vec();
    bytes.resize(MAX_DOCUMENT + 128 * 1024, 0);
    let response = f
        .router
        .clone()
        .oneshot(upload(
            media("document", &bytes, true),
            Some(&f.admin),
            Some(EDITOR),
        ))
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::PAYLOAD_TOO_LARGE);
    let body = body_json(response).await;
    assert_eq!(body["ok"], false, "{body}");
    let code = body["error"]["code"].as_str().expect("a code");
    assert!(
        code.starts_with("whatsapp.header_") && code.ends_with("_too_large"),
        "{code}"
    );
    assert!(f.seen.lock().unwrap().is_empty());
}
