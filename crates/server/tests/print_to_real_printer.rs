//! **The definition of done of hub#501, against a printer that actually exists.**
//!
//! > A ticket queued with `POST /api/print/jobs` comes out of a real thermal printer, with nobody
//! > touching a dialog, and the `jobId` ends `done`.
//!
//! Everything else in this repo tests one link. This tests the **chain**: the till enqueues over
//! HTTP, the hub keeps the job, the print host claims it over `GET /ws/print`, the structured
//! document goes through `escpos::render_document`, the bytes go down a TCP socket to port 9100, and
//! the host confirms. Until hub#501 this could not be written at all — the queue stored HTML and the
//! renderer only speaks structured documents, so there was no way to get from one end to the other.
//!
//! The claim/print/confirm block below is deliberately what `apps/web/src/lib/print-host.ts` and the
//! `erplora_print` command do, in the same order: this file stands in for the device, because the
//! device is a Tauri app and a Tauri app cannot be a `cargo test`. What it therefore does **not**
//! prove is the Tauri boundary itself (the `invoke` call) — everything on either side of it is here.
//!
//! ```bash
//! ERPLORA_SMOKE_PRINT=1 cargo test -p erplora-server --test print_to_real_printer \
//!   -- --ignored --nocapture
//! ```
//!
//! `#[ignore]` **and** an environment variable, both on purpose: the first keeps it out of the gate,
//! the second keeps a stray `--ignored` from spitting paper across somebody's desk. The printer is
//! read from `ERPLORA_SMOKE_PRINTER` (default `192.168.100.196:9100`) and has to be on the same LAN
//! — a hub deployed on Hetzner cannot reach a printer in a shop, which is the entire reason the
//! **device** drains the queue and the hub does not print.
use erplora_db::testutil::fresh_db;
use erplora_peripherals::escpos::{self, DocumentType};
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use futures_util::{SinkExt, StreamExt};
use serde_json::{json, Value};
use std::net::SocketAddr;
use tokio::io::AsyncWriteExt;
use tokio_tungstenite::tungstenite::Message;

const HUB_ID: &str = "hub-real-printer";
const DEFAULT_PRINTER: &str = "192.168.100.196:9100";
const FRAME_TIMEOUT: std::time::Duration = std::time::Duration::from_secs(10);

/// The printer this run should use, and whether the operator asked for paper at all.
fn printer_target() -> Option<String> {
    if std::env::var("ERPLORA_SMOKE_PRINT").ok().as_deref() != Some("1") {
        println!("skipped: export ERPLORA_SMOKE_PRINT=1 to spend real paper");
        return None;
    }
    Some(std::env::var("ERPLORA_SMOKE_PRINTER").unwrap_or_else(|_| DEFAULT_PRINTER.into()))
}

async fn serve() -> (SocketAddr, AppState, String) {
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), HUB_ID);
    rt.ensure_system_tables().await.unwrap();
    let user = rt
        .create_user("Cashier", "1111", "employee", None)
        .await
        .unwrap();
    let session = rt.create_session(&user, 3600, None).await.unwrap();
    rt.register_print_host("till-1", "receipt", "Counter till", &user)
        .await
        .unwrap();

    let temp = std::env::temp_dir().join(format!("erplora-real-printer-{}", std::process::id()));
    let cfg = HubConfig {
        hub_id: HUB_ID.into(),
        cloud_base_url: "https://example.invalid".into(),
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
        bootstrap_blueprint: None,
    };
    let state = AppState::with_config(rt, cfg);
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let addr = listener.local_addr().unwrap();
    let router = app(state.clone());
    tokio::spawn(async move {
        let _ = axum::serve(listener, router.into_make_service()).await;
    });
    (addr, state, session)
}

type Socket =
    tokio_tungstenite::WebSocketStream<tokio_tungstenite::MaybeTlsStream<tokio::net::TcpStream>>;

async fn send(socket: &mut Socket, frame: Value) {
    socket.send(Message::Text(frame.to_string())).await.unwrap();
}

async fn recv(socket: &mut Socket) -> Value {
    loop {
        let next = tokio::time::timeout(FRAME_TIMEOUT, socket.next())
            .await
            .expect("the hub answered within the window");
        match next {
            Some(Ok(Message::Text(t))) => return serde_json::from_str(&t).unwrap(),
            Some(Ok(_)) => continue,
            other => panic!("the channel closed instead of answering: {other:?}"),
        }
    }
}

/// The ESC/POS stream as text, with the control sequences taken out — what the paper says.
///
/// Only the escapes this renderer emits are dropped (`ESC a/E`, `GS !/V`), which is enough because
/// a receipt is text plus formatting. It exists so the manual run prints its own expectation next to
/// the ticket instead of asking whoever is holding the paper to remember what it should have said.
fn readable(bytes: &[u8]) -> String {
    let mut out = String::new();
    let mut i = 0;
    while i < bytes.len() {
        match bytes[i] {
            // ESC a n | ESC E n — alignment / bold.
            0x1b if i + 2 < bytes.len() => i += 3,
            // GS ! n | GS V n — character size / cut.
            0x1d if i + 2 < bytes.len() => i += 3,
            b => {
                out.push(b as char);
                i += 1;
            }
        }
    }
    out.trim_end().to_string()
}

/// A ticket the way `buildReceiptDocument` composes one from a sale (`receipt-document.ts`): this is
/// the shape the whole chain now carries, and the shape the paper has to show.
fn a_real_ticket() -> Value {
    json!({
        "business_name": "ERPlora hub#501",
        "business_address": "Prueba de punta a punta",
        "vat_number": "B00000000",
        "receipt_id": "T-501",
        "cashier": "hub#501",
        "items": [
            { "name": "Cafe solo", "quantity": 2, "total": 2.40 },
            { "name": "Tostada", "quantity": 1, "total": 3.50, "notes": "sin tomate" },
        ],
        "subtotal": 5.90,
        "tax_amount": 0.59,
        "total": 6.49,
        "payment_method": "Efectivo",
        "paid": 10.00,
        "change": 3.51,
        "receipt_footer": "hub#501 — el documento viaja ESTRUCTURADO",
    })
}

#[tokio::test]
#[ignore = "PRINTS ON PAPER: needs a real thermal printer on the LAN and ERPLORA_SMOKE_PRINT=1"]
async fn a_queued_ticket_comes_out_of_a_real_printer_and_ends_done() {
    let Some(printer) = printer_target() else {
        return;
    };
    let (addr, state, session) = serve().await;

    // ── 1. The till charges and enqueues. It never sees a printer. ────────────────────────────
    {
        use axum::body::Body;
        use axum::http::Request;
        use http_body_util::BodyExt;
        use tower::ServiceExt;

        let body = json!({
            "jobId": "smoke-501",
            "role": "receipt",
            "documentType": "receipt",
            "document": a_real_ticket(),
        });
        let resp = app(state.clone())
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/print/jobs")
                    .header("x-hub-session", &session)
                    .header("content-type", "application/json")
                    .body(Body::from(body.to_string()))
                    .unwrap(),
            )
            .await
            .unwrap();
        let bytes = resp.into_body().collect().await.unwrap().to_bytes();
        let json: Value = serde_json::from_slice(&bytes).unwrap();
        assert_eq!(json["status"], "queued", "the ticket is waiting: {json}");
    }

    // ── 2. The print host connects and claims. ────────────────────────────────────────────────
    let (mut socket, _) = tokio_tungstenite::connect_async(format!("ws://{addr}/ws/print"))
        .await
        .expect("the hub accepts the print host");
    send(
        &mut socket,
        json!({ "type": "hello", "session": session, "deviceId": "till-1" }),
    )
    .await;
    assert_eq!(recv(&mut socket).await["type"], "ready");

    send(&mut socket, json!({ "type": "claim", "role": "receipt" })).await;
    let job = recv(&mut socket).await;
    assert_eq!(job["type"], "job");
    assert_eq!(job["jobId"], "smoke-501");

    // ── 3. Document → ESC/POS → the printer's socket. This is `erplora_print`, inlined. ───────
    let doc = DocumentType::parse(job["documentType"].as_str().unwrap())
        .expect("the hub only ever queues a document type the renderer knows");
    let bytes = escpos::render_document(doc, &job["document"]).expect("the document renders");
    println!("→ {} bytes of ESC/POS to {printer}", bytes.len());
    // What the paper should read, so the person holding it can check rather than guess. A socket
    // that accepted the bytes is not the same claim as a ticket that came out right.
    println!("─── expected on the paper ───\n{}\n─────────────────────────────", readable(&bytes));
    let mut stream = tokio::net::TcpStream::connect(&printer)
        .await
        .unwrap_or_else(|e| panic!("no printer answering at {printer}: {e}"));
    stream.write_all(&bytes).await.expect("the printer takes the bytes");
    stream.flush().await.unwrap();

    // ── 4. The host confirms, and the job is terminal. ────────────────────────────────────────
    send(&mut socket, json!({ "type": "done", "jobId": "smoke-501" })).await;
    let ack = recv(&mut socket).await;
    assert_eq!(ack["confirmed"], true, "the hub took the confirmation");

    send(&mut socket, json!({ "type": "claim", "role": "receipt" })).await;
    assert_eq!(
        recv(&mut socket).await["type"],
        "idle",
        "a confirmed ticket is never handed out again"
    );

    let arc = state.runtime_for(&state.hub_id()).await.unwrap();
    let rt = arc.lock().await;
    let status = rt
        .print_queue(None, None, 10)
        .await
        .unwrap()
        .into_iter()
        .find(|j| j.job_id == "smoke-501")
        .map(|j| j.status)
        .unwrap_or_default();
    assert_eq!(status, "done", "and the queue agrees");
    println!("✅ hub#501: paper out, jobId smoke-501 is `done`");
}
