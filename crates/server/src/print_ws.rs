//! **The print host's channel** — `GET /ws/print` (ADR-0196 §6, hub#343).
//!
//! The first client→server channel this hub has ever had. `/ws` is push-only: it fans events out
//! and never listens, which is why hub#342 had to put the print host's heartbeat on an HTTP door
//! "provisionally, until somebody opens the other direction". This is that direction, and the beat
//! moves here — see [the heartbeat note](#the-heartbeat-moves-here).
//!
//! # Who may connect
//!
//! Two layers, and they answer different questions:
//!
//! | Layer | Question | Credential |
//! |-------|----------|------------|
//! | **Authentication** | is there a human logged into this hub on this device? | the hub session (`hello.session`, the same token `X-Hub-Session` carries) |
//! | **Authorisation** | is this device a print host, and of which roles? | the `_print_host` registry (hub#342), re-read on **every** claim |
//!
//! Both are needed, and neither substitutes for the other. A session alone is not enough because
//! the queue carries the **document** — names, lines, totals, the fiscal QR — so a waiter's phone
//! with a perfectly valid session could otherwise drain every ticket the business prints. The
//! registry alone is not enough either: `device_id` is an identifier, never a credential (ADR-0154),
//! and anybody can type one.
//!
//! **The token travels in the first frame, not in the URL.** A browser cannot set headers on a
//! WebSocket handshake, so the only two places left are the query string and the body of a frame.
//! The query string ends up in every access log and proxy trace along the way; the frame does not.
//!
//! ## The refusals, each with its own code
//!
//! | Code | When |
//! |------|------|
//! | `print.not_ready` | any frame before `hello` — an unauthenticated socket cannot claim, confirm, fail or even beat |
//! | `unauthenticated` | `hello` with no session, or with one this hub does not recognise (its *message* tells the two apart) |
//! | `print.device_required` | `hello` that does not say which device is speaking |
//! | `print.host_not_registered` | a device that hosts nothing here (a device of **another hub** included: its rows are not in this hub's registry) |
//! | `print.role_not_hosted` | a real print host reaching for somebody else's role |
//! | `print.frame_too_large` | a peer pushing more than [`MAX_FRAME_BYTES`] at a socket that may not even be authenticated yet |
//!
//! They are deliberately **distinguishable**. If two guards answered the same thing, either one
//! could be deleted and no test would notice.
//!
//! # The heartbeat moves here
//!
//! A connected host beats over this socket (`beat`), and every successful `claim` counts as news
//! too — a device that is taking tickets out is demonstrably there. `POST /api/print/hosts/heartbeat`
//! **stays**, and not as a leftover: registering is still an HTTP gesture with an actor behind it,
//! and a host that has just registered, or is between reconnects, has to be able to say "still
//! here" without a socket. What moves is the beat of a **connected** host.
//!
//! # The protocol
//!
//! ```text
//!  client                                   hub
//!    │  {"type":"hello","session":…,"deviceId":…}  ─▶
//!    ◀─ {"type":"ready","deviceId":…,"roles":[…],"heartbeatSeconds":30}
//!    │  {"type":"claim","role":"kitchen"}          ─▶
//!    ◀─ {"type":"job","jobId":…,"role":…,"documentType":…,"document":{…},"format":…,"attempts":1}
//!    │      … prints via crates/peripherals …
//!    │  {"type":"done","jobId":…}                  ─▶
//!    ◀─ {"type":"ack","jobId":…,"confirmed":true}
//!    ◀─ {"type":"wake","role":"kitchen"}   (a job was just queued for a role you host)
//! ```
//!
//! `wake` is why this is a socket and not polling: the hub tells the host a ticket arrived instead
//! of the host asking every second. It is a **nudge, not a delivery** — the document only ever
//! travels in the answer to a `claim`, which is the frame that goes through the guards.
use axum::extract::ws::{Message, WebSocket, WebSocketUpgrade};
use axum::extract::State;
use axum::http::{HeaderMap, HeaderName, HeaderValue};
use axum::response::Response;
use erplora_runtime::print_hosts;
use serde_json::{json, Value};

use crate::auth;
use crate::state::AppState;

/// Longest client→server frame accepted. These frames carry ids and a role, never a document — the
/// document only ever travels hub→host. Bounded because the socket accepts bytes **before** anybody
/// has proved who they are.
pub const MAX_FRAME_BYTES: usize = 8 * 1024;

/// How long a socket may stay silent before saying `hello`. A connection that never authenticates
/// is not a print host; it is something holding a file descriptor open.
pub const HELLO_TIMEOUT_SECONDS: u64 = 15;

/// Raw event frame the enqueue door broadcasts so connected hosts learn a ticket arrived without
/// polling. Carries the **role only** — never the document.
pub const EVENT_JOB_QUEUED: &str = "print.queued";

/// A frame from the print host.
#[derive(Debug, serde::Deserialize)]
#[serde(tag = "type")]
enum ClientFrame {
    /// Authenticate the socket and ask the hub what this device is for.
    #[serde(rename = "hello", rename_all = "camelCase")]
    Hello {
        #[serde(default)]
        session: String,
        #[serde(default)]
        device_id: String,
    },
    /// "Give me the next ticket of this role."
    #[serde(rename = "claim", rename_all = "camelCase")]
    Claim {
        #[serde(default)]
        role: String,
    },
    /// "The paper came out."
    #[serde(rename = "done", rename_all = "camelCase")]
    Done {
        #[serde(default)]
        job_id: String,
    },
    /// "I could not print it."
    #[serde(rename = "failed", rename_all = "camelCase")]
    Failed {
        #[serde(default)]
        job_id: String,
        #[serde(default)]
        error: String,
    },
    /// "Still here." The heartbeat of hub#342, now on the socket.
    #[serde(rename = "beat")]
    Beat,
}

/// What the socket knows about its peer.
///
/// `roles` is a **hint for waking only**, never a permission: authorisation is re-read from the
/// registry on every claim, so a role retired mid-session stops working immediately even though the
/// hint still lists it. Keeping the distinction explicit matters — a cached permission is how a
/// revoked device keeps printing.
#[derive(Debug, Default)]
pub(crate) struct DrainConnection {
    /// Empty until `hello` succeeded; that emptiness IS the "not authenticated" state.
    device_id: String,
    /// Roles this device hosted at `hello`. Only decides whether a `wake` is worth sending.
    roles: Vec<String>,
}

impl DrainConnection {
    fn is_ready(&self) -> bool {
        !self.device_id.is_empty()
    }

    /// Does a job queued for `role` concern this connection?
    fn wants_wake_for(&self, role: &str) -> bool {
        self.is_ready() && self.roles.iter().any(|r| r == role)
    }
}

/// A frame to send back, and whether the socket survives it.
pub(crate) struct Reply {
    pub frame: Value,
    /// `false` = answer and hang up. Reserved for refusals that will not get better by retrying:
    /// a socket that cannot authenticate has nothing else to say.
    pub keep_open: bool,
}

fn reply(frame: Value) -> Reply {
    Reply {
        frame,
        keep_open: true,
    }
}

fn fatal(code: &str, message: impl Into<String>) -> Reply {
    Reply {
        frame: json!({ "type": "error", "code": code, "message": message.into() }),
        keep_open: false,
    }
}

fn refuse(code: &str, message: impl Into<String>) -> Reply {
    reply(json!({ "type": "error", "code": code, "message": message.into() }))
}

/// A runtime refusal as a frame, with **the same stable code** it would carry over HTTP.
fn runtime_error(e: erplora_runtime::RuntimeError) -> Reply {
    let (_, code) = crate::err_status_and_code(&e);
    refuse(&code.into_owned(), e.to_string())
}

/// GET /ws/print — the print host's channel.
pub async fn upgrade(State(st): State<AppState>, ws: WebSocketUpgrade) -> Response {
    ws.on_upgrade(move |socket| drain_loop(socket, st))
}

/// Handles one client frame. Split from the socket loop so the protocol — and every guard in it —
/// is testable without a transport.
pub(crate) async fn handle_frame(st: &AppState, conn: &mut DrainConnection, raw: &str) -> Reply {
    if raw.len() > MAX_FRAME_BYTES {
        return fatal(
            "print.frame_too_large",
            format!(
                "a frame of {} bytes is over the {MAX_FRAME_BYTES} byte cap for this channel",
                raw.len()
            ),
        );
    }
    let frame: ClientFrame = match serde_json::from_str(raw) {
        Ok(f) => f,
        Err(e) => {
            return refuse(
                "invalid_payload",
                format!("this channel speaks hello/claim/done/failed/beat: {e}"),
            )
        }
    };

    // Everything except `hello` needs an authenticated socket. Checked here, once, rather than in
    // each arm: a guard that has to be remembered four times is a guard that will be forgotten once.
    if !conn.is_ready() && !matches!(frame, ClientFrame::Hello { .. }) {
        return fatal(
            "print.not_ready",
            "say hello with a session and a deviceId before draining",
        );
    }

    let hub_id = st.hub_id();
    let arc = match st.runtime_for(&hub_id).await {
        Ok(rt) => rt,
        Err(e) => return fatal("tenant_rejected", e.to_string()),
    };
    let rt = arc.lock().await;

    match frame {
        ClientFrame::Hello { session, device_id } => {
            // The session is the SAME credential the HTTP doors take; it just arrives in a frame
            // because a browser cannot put a header on a WebSocket handshake.
            let mut headers = HeaderMap::new();
            if let Ok(value) = HeaderValue::from_str(session.trim()) {
                if !session.trim().is_empty() {
                    headers.insert(HeaderName::from_static("x-hub-session"), value);
                }
            }
            if let Err(e) = auth::require_user_session(&headers, &st.config, &rt).await {
                // The message distinguishes "you sent none" from "yours is not valid here" — which
                // is what a session minted in ANOTHER hub gets, since it resolves against this
                // hub's own session table and nothing else.
                return fatal("unauthenticated", e.message());
            }
            let device_id = device_id.trim().to_string();
            if device_id.is_empty() {
                return fatal(
                    "print.device_required",
                    "this channel drains for one device: send its deviceId",
                );
            }
            let roles = match rt.print_roles_of_device(&device_id).await {
                Ok(roles) => roles,
                Err(e) => return runtime_error(e),
            };
            if roles.is_empty() {
                // Note this is also what a device of another hub gets: its registration lives in
                // that hub's rows, so here it hosts nothing.
                return fatal(
                    erplora_runtime::print_drain::ERR_HOST_NOT_REGISTERED,
                    "this device is not a print host of this hub: register it before draining",
                );
            }
            // Connecting is news: the host is demonstrably there.
            let _ = rt.print_host_heartbeat(&device_id).await;
            conn.device_id = device_id.clone();
            conn.roles = roles.clone();
            reply(json!({
                "type": "ready",
                "deviceId": device_id,
                // The hub tells the host what it is for; the client never guesses its own roles.
                "roles": roles,
                // …and how often to beat, same as `POST /api/print/hosts` (hub#342), so the client
                // cannot drift away from the window this hub uses to decide who is live.
                "heartbeatSeconds": print_hosts::HEARTBEAT_SECONDS,
            }))
        }
        ClientFrame::Claim { role } => {
            let role = role.trim().to_string();
            match rt.claim_print_job(&conn.device_id, &role).await {
                Ok(Some(job)) => reply(json!({
                    "type": "job",
                    "jobId": job.job_id,
                    "role": job.role,
                    // The ONLY frame that carries the document, and only after both guards. It
                    // travels STRUCTURED (hub#501): `documentType` picks the renderer and
                    // `document` is the object it reads, which is what makes the same ticket
                    // printable on 58mm, on 80mm or as a PDF — and re-printable tomorrow.
                    "documentType": job.document_type,
                    "document": job.document,
                    "format": job.format,
                    "attempts": job.attempts,
                })),
                // Nothing waiting is an answer, not an error.
                Ok(None) => reply(json!({ "type": "idle", "role": role })),
                Err(e) => runtime_error(e),
            }
        }
        ClientFrame::Done { job_id } => {
            let job_id = job_id.trim().to_string();
            match rt.confirm_print_job(&conn.device_id, &job_id).await {
                Ok(confirmed) => {
                    reply(json!({ "type": "ack", "jobId": job_id, "confirmed": confirmed }))
                }
                Err(e) => runtime_error(e),
            }
        }
        ClientFrame::Failed { job_id, error } => {
            let job_id = job_id.trim().to_string();
            match rt.fail_print_job(&conn.device_id, &job_id, &error).await {
                Ok(requeued) => {
                    reply(json!({ "type": "ack", "jobId": job_id, "requeued": requeued }))
                }
                Err(e) => runtime_error(e),
            }
        }
        ClientFrame::Beat => match rt.print_host_heartbeat(&conn.device_id).await {
            // `refreshed: 0` is a success, not a 404: it says "you host nothing here any more,
            // register again" — the same contract as the HTTP door (hub#342).
            Ok(refreshed) => reply(json!({
                "type": "beat",
                "refreshed": refreshed,
                "heartbeatSeconds": print_hosts::HEARTBEAT_SECONDS,
            })),
            Err(e) => runtime_error(e),
        },
    }
}

/// The socket loop: client frames in one direction, `wake` nudges in the other.
async fn drain_loop(mut socket: WebSocket, st: AppState) {
    let mut conn = DrainConnection::default();
    let mut events = st.events.subscribe();
    let hello_deadline =
        tokio::time::Instant::now() + tokio::time::Duration::from_secs(HELLO_TIMEOUT_SECONDS);

    loop {
        tokio::select! {
            incoming = socket.recv() => {
                let Some(Ok(message)) = incoming else { break };
                let text = match message {
                    Message::Text(t) => t,
                    // Pings/pongs/closes are transport, not protocol. A binary frame is not
                    // something this channel speaks.
                    Message::Close(_) => break,
                    _ => continue,
                };
                let Reply { frame, keep_open } = handle_frame(&st, &mut conn, &text).await;
                let payload = serde_json::to_string(&frame).unwrap_or_else(|_| "{}".into());
                if socket.send(Message::Text(payload)).await.is_err() || !keep_open {
                    break;
                }
            }
            event = events.recv() => {
                match event {
                    Ok(ev) => {
                        if ev.get("type").and_then(Value::as_str) != Some(EVENT_JOB_QUEUED) {
                            continue;
                        }
                        let role = ev.get("role").and_then(Value::as_str).unwrap_or_default();
                        if !conn.wants_wake_for(role) {
                            continue;
                        }
                        let frame = json!({ "type": "wake", "role": role }).to_string();
                        if socket.send(Message::Text(frame)).await.is_err() {
                            break;
                        }
                    }
                    // A host that fell behind the broadcast missed a nudge, not a ticket: the queue
                    // is in the database and the next claim finds it. Dropping the socket over a
                    // lost nudge would be worse than the nudge.
                    Err(tokio::sync::broadcast::error::RecvError::Lagged(_)) => continue,
                    Err(tokio::sync::broadcast::error::RecvError::Closed) => break,
                }
            }
            _ = tokio::time::sleep_until(hello_deadline), if !conn.is_ready() => {
                let frame = json!({
                    "type": "error",
                    "code": "print.not_ready",
                    "message": "no hello within the handshake window",
                }).to_string();
                let _ = socket.send(Message::Text(frame)).await;
                break;
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::state::AuthMode;
    use erplora_db::testutil::fresh_db;
    use erplora_runtime::print_queue::{self, NewPrintJob};
    use erplora_runtime::Runtime;

    const HUB_ID: &str = "hub-drain";

    struct Fixture {
        st: AppState,
        session: String,
    }

    fn config(hub_id: &str) -> crate::HubConfig {
        let temp = std::env::temp_dir().join(format!("erplora-print-ws-{}", std::process::id()));
        crate::HubConfig {
            demo: false,
            hub_id: hub_id.into(),
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
        }
    }

    async fn fixture() -> Fixture {
        let db = fresh_db().await;
        let rt = Runtime::with_hub_id(Box::new(db), HUB_ID);
        rt.ensure_system_tables().await.unwrap();
        let user = rt
            .create_user("Cashier", "1111", "employee", None)
            .await
            .unwrap();
        let session = rt.create_session(&user, 3600, None).await.unwrap();
        Fixture {
            st: AppState::with_config(rt, config(HUB_ID)),
            session,
        }
    }

    /// A second hub, in its own schema, with its own session — the neighbour that has to stay
    /// untouched while this one refuses its credentials.
    async fn other_hub() -> (AppState, String) {
        let db = fresh_db().await;
        let rt = Runtime::with_hub_id(Box::new(db), "hub-next-door");
        rt.ensure_system_tables().await.unwrap();
        let user = rt
            .create_user("Neighbour", "2222", "employee", None)
            .await
            .unwrap();
        let session = rt.create_session(&user, 3600, None).await.unwrap();
        (AppState::with_config(rt, config("hub-next-door")), session)
    }

    async fn register(st: &AppState, device_id: &str, role: &str) {
        let arc = st.runtime_for(&st.hub_id()).await.unwrap();
        let rt = arc.lock().await;
        rt.register_print_host(device_id, role, "Till", "u1")
            .await
            .unwrap();
    }

    async fn enqueue(st: &AppState, job_id: &str, role: &str) {
        let arc = st.runtime_for(&st.hub_id()).await.unwrap();
        let rt = arc.lock().await;
        rt.enqueue_print_job(&NewPrintJob {
            job_id: job_id.into(),
            role: role.into(),
            document_type: "receipt".into(),
            document: json!({ "receipt_id": job_id }),
            format: print_queue::FORMAT_RECEIPT.into(),
        })
        .await
        .unwrap();
    }

    async fn status_of(st: &AppState, job_id: &str) -> String {
        let arc = st.runtime_for(&st.hub_id()).await.unwrap();
        let rt = arc.lock().await;
        rt.print_queue(None, None, 500)
            .await
            .unwrap()
            .into_iter()
            .find(|j| j.job_id == job_id)
            .map(|j| j.status)
            .unwrap_or_default()
    }

    async fn send(st: &AppState, conn: &mut DrainConnection, frame: Value) -> Reply {
        handle_frame(st, conn, &frame.to_string()).await
    }

    fn hello(session: &str, device_id: &str) -> Value {
        json!({ "type": "hello", "session": session, "deviceId": device_id })
    }

    async fn connected(f: &Fixture, device_id: &str) -> DrainConnection {
        let mut conn = DrainConnection::default();
        let r = send(&f.st, &mut conn, hello(&f.session, device_id)).await;
        assert_eq!(r.frame["type"], "ready", "hello failed: {}", r.frame);
        conn
    }

    // ── Who may connect ───────────────────────────────────────────────────────────────────────

    /// **Without a credential you get nothing.** The queue carries the ticket's HTML, so an
    /// anonymous socket that could claim would be a public read of everything the business prints.
    #[tokio::test]
    async fn a_socket_without_a_session_cannot_open_the_channel() {
        let f = fixture().await;
        register(&f.st, "till-1", "receipt").await;
        let mut conn = DrainConnection::default();

        let r = send(&f.st, &mut conn, hello("", "till-1")).await;
        assert_eq!(r.frame["code"], "unauthenticated");
        assert!(!r.keep_open, "a socket that cannot authenticate is hung up");
        assert!(!conn.is_ready());
    }

    /// **A session of another hub is not a session here.** It is refused with the same code as an
    /// absent one but a different *message*, because they are different facts — and because two
    /// guards that answer identically are one guard nobody would miss.
    ///
    /// The neighbouring hub stays open and usable throughout: its own device drains its own queue
    /// after the refusal, which is what proves nothing leaked sideways.
    #[tokio::test]
    async fn a_session_minted_in_another_hub_does_not_open_this_ones_channel() {
        let f = fixture().await;
        register(&f.st, "till-1", "receipt").await;
        let (neighbour, neighbour_session) = other_hub().await;
        register(&neighbour, "till-2", "receipt").await;
        enqueue(&neighbour, "j-next-door", "receipt").await;

        let mut conn = DrainConnection::default();
        let r = send(&f.st, &mut conn, hello(&neighbour_session, "till-1")).await;
        assert_eq!(r.frame["code"], "unauthenticated");
        assert!(!r.keep_open);

        let absent = send(&f.st, &mut DrainConnection::default(), hello("", "till-1")).await;
        assert_ne!(
            r.frame["message"], absent.frame["message"],
            "«you sent no session» and «yours is not valid here» are different facts"
        );

        // The neighbour is untouched: its ticket is still waiting and its own host still drains it.
        assert_eq!(
            status_of(&neighbour, "j-next-door").await,
            print_queue::STATUS_PENDING
        );
        let mut their_conn = DrainConnection::default();
        let ready = send(
            &neighbour,
            &mut their_conn,
            hello(&neighbour_session, "till-2"),
        )
        .await;
        assert_eq!(ready.frame["type"], "ready");
        let job = send(
            &neighbour,
            &mut their_conn,
            json!({"type":"claim","role":"receipt"}),
        )
        .await;
        assert_eq!(job.frame["jobId"], "j-next-door");
    }

    /// A valid session on a device nobody registered as a print host still drains nothing: being
    /// logged in is not being the till by the kitchen printer.
    #[tokio::test]
    async fn a_valid_session_on_an_unregistered_device_cannot_open_the_channel() {
        let f = fixture().await;
        register(&f.st, "till-1", "receipt").await;
        enqueue(&f.st, "j1", "receipt").await;
        let mut conn = DrainConnection::default();

        let r = send(&f.st, &mut conn, hello(&f.session, "waiters-phone")).await;
        assert_eq!(
            r.frame["code"],
            erplora_runtime::print_drain::ERR_HOST_NOT_REGISTERED
        );
        assert!(!r.keep_open);
        assert_eq!(status_of(&f.st, "j1").await, print_queue::STATUS_PENDING);
    }

    /// A device that hosts a role in ANOTHER hub is, here, a device that hosts nothing — and it is
    /// told exactly that, with the neighbour's registration left alone.
    #[tokio::test]
    async fn a_device_registered_in_another_hub_hosts_nothing_here() {
        let f = fixture().await;
        let (neighbour, _) = other_hub().await;
        register(&neighbour, "till-next-door", "receipt").await;

        let mut conn = DrainConnection::default();
        let r = send(&f.st, &mut conn, hello(&f.session, "till-next-door")).await;
        assert_eq!(
            r.frame["code"],
            erplora_runtime::print_drain::ERR_HOST_NOT_REGISTERED
        );

        let arc = neighbour.runtime_for(&neighbour.hub_id()).await.unwrap();
        let rt = arc.lock().await;
        assert_eq!(
            rt.print_hosts().await.unwrap().len(),
            1,
            "the neighbour's registration is still there"
        );
    }

    /// `hello` without a device is refused: this channel drains for one device, and there is no
    /// parameter anywhere that names another.
    #[tokio::test]
    async fn hello_without_a_device_is_refused() {
        let f = fixture().await;
        let mut conn = DrainConnection::default();

        for id in ["", "   "] {
            let r = send(&f.st, &mut conn, hello(&f.session, id)).await;
            assert_eq!(r.frame["code"], "print.device_required");
            assert!(!conn.is_ready());
        }
    }

    /// **Nothing works before `hello`.** Not claiming, not confirming, not even beating — a socket
    /// that has not proved who it is cannot use the channel to find out anything either.
    #[tokio::test]
    async fn no_frame_works_before_hello() {
        let f = fixture().await;
        register(&f.st, "till-1", "receipt").await;
        enqueue(&f.st, "j1", "receipt").await;

        for frame in [
            json!({"type":"claim","role":"receipt"}),
            json!({"type":"done","jobId":"j1"}),
            json!({"type":"failed","jobId":"j1","error":"x"}),
            json!({"type":"beat"}),
        ] {
            let mut conn = DrainConnection::default();
            let r = send(&f.st, &mut conn, frame.clone()).await;
            assert_eq!(
                r.frame["code"], "print.not_ready",
                "{frame} slipped through"
            );
            assert!(!r.keep_open);
        }
        assert_eq!(
            status_of(&f.st, "j1").await,
            print_queue::STATUS_PENDING,
            "not one of them touched the queue"
        );
    }

    /// A peer that pushes a huge frame at a socket it has not authenticated is hung up on. The
    /// document never travels in this direction, so there is nothing legitimate to send that is big.
    #[tokio::test]
    async fn an_oversized_frame_is_refused_before_it_is_even_parsed() {
        let f = fixture().await;
        let mut conn = DrainConnection::default();

        let huge = "x".repeat(MAX_FRAME_BYTES + 1);
        let r = handle_frame(&f.st, &mut conn, &huge).await;
        assert_eq!(r.frame["code"], "print.frame_too_large");
        assert!(!r.keep_open);
    }

    /// The cap is a limit, not an off-by-one: a frame of **exactly** the maximum is a frame, and it
    /// is judged on what it says rather than on its length.
    #[tokio::test]
    async fn a_frame_of_exactly_the_cap_is_not_refused_for_its_size() {
        let f = fixture().await;
        let mut conn = DrainConnection::default();

        // Pad the (bogus) session until the frame weighs exactly the cap.
        let skeleton = hello("", "till-1").to_string().len();
        let exact = hello(&"s".repeat(MAX_FRAME_BYTES - skeleton), "till-1").to_string();
        assert_eq!(exact.len(), MAX_FRAME_BYTES);

        let r = handle_frame(&f.st, &mut conn, &exact).await;
        assert_eq!(
            r.frame["code"], "unauthenticated",
            "judged on its contents, not on its size"
        );
    }

    /// **The cap is pinned from both ends**, because neither number follows from the other:
    ///
    ///  - **big enough for a real handshake**: `hello` carries a session token and a device id, both
    ///    opaque strings this hub does not get to choose the length of. A cap that refused one would
    ///    lock a legitimate till out of printing, which is worse than anything it is defending
    ///    against;
    ///  - **far smaller than a document**: the whole reason it exists is that nothing travelling in
    ///    this direction is ever a ticket. If it grew to `MAX_DOCUMENT_BYTES` it would stop meaning
    ///    anything.
    #[test]
    fn the_frame_cap_fits_a_handshake_and_is_nowhere_near_a_document() {
        assert!(
            MAX_FRAME_BYTES >= 4 * 1024,
            "a session token plus a device id must never be too big to say hello with"
        );
        assert!(
            MAX_FRAME_BYTES < erplora_runtime::print_queue::MAX_DOCUMENT_BYTES,
            "a client frame is not a document: the cap has to be visibly smaller than one"
        );
    }

    /// A frame this channel does not speak is refused without dropping the socket: a client bug is
    /// not a reason to make the till stop printing.
    #[tokio::test]
    async fn an_unknown_frame_is_refused_without_closing_the_socket() {
        let f = fixture().await;
        register(&f.st, "till-1", "receipt").await;
        let mut conn = connected(&f, "till-1").await;

        let r = send(
            &f.st,
            &mut conn,
            json!({ "type": "please-print-everything" }),
        )
        .await;
        assert_eq!(r.frame["code"], "invalid_payload");
        assert!(
            r.keep_open,
            "a bad frame is not a reason to hang up on a till"
        );
    }

    // ── Draining ──────────────────────────────────────────────────────────────────────────────

    /// The whole point, end to end over the protocol: hello → claim → the document → done.
    #[tokio::test]
    async fn a_registered_host_claims_prints_and_confirms() {
        let f = fixture().await;
        register(&f.st, "till-1", "receipt").await;
        enqueue(&f.st, "j1", "receipt").await;
        let mut conn = connected(&f, "till-1").await;

        let job = send(&f.st, &mut conn, json!({"type":"claim","role":"receipt"})).await;
        assert_eq!(job.frame["type"], "job");
        assert_eq!(job.frame["jobId"], "j1");
        // hub#1159: the queue now stamps the hub's language on enqueue, so the device can print
        // the paper in it. The assertion is NOT relaxed to "contains what the producer sent" —
        // that would let a future change smuggle a second field in unnoticed. It stays exact:
        // everything the producer sent, arriving whole, PLUS the one stamp and nothing else.
        let document = &job.frame["document"];
        assert_eq!(
            document["receipt_id"],
            json!("j1"),
            "the STRUCTURED document travels to the host that claimed it, and only there"
        );
        assert_eq!(
            document["locale"],
            json!("es"),
            "the queue stamps the hub's language once, for every producer (hub#1159)"
        );
        assert_eq!(
            document.as_object().map(|d| d.len()),
            Some(2),
            "the stamp is the ONLY thing the queue adds — anything else reaching the host is \
             something the producer never sent: {document:?}"
        );
        assert_eq!(
            job.frame["documentType"], "receipt",
            "…together with which renderer turns it into paper"
        );
        assert!(
            job.frame.get("html").is_none(),
            "the retired HTML field is gone from the wire, not merely empty"
        );
        assert_eq!(job.frame["format"], print_queue::FORMAT_RECEIPT);

        let ack = send(&f.st, &mut conn, json!({"type":"done","jobId":"j1"})).await;
        assert_eq!(ack.frame["confirmed"], true);
        assert_eq!(status_of(&f.st, "j1").await, print_queue::STATUS_DONE);

        let again = send(&f.st, &mut conn, json!({"type":"claim","role":"receipt"})).await;
        assert_eq!(
            again.frame["type"], "idle",
            "a confirmed ticket is terminal"
        );
    }

    /// `hello` answers with what the hub knows, not with what the client asked for: the roles come
    /// from the registry and the beat cadence from the hub.
    #[tokio::test]
    async fn hello_tells_the_host_what_it_is_for_and_how_often_to_beat() {
        let f = fixture().await;
        register(&f.st, "till-1", "receipt").await;
        register(&f.st, "till-1", "kitchen").await;
        let mut conn = DrainConnection::default();

        let r = send(&f.st, &mut conn, hello(&f.session, "till-1")).await;
        assert_eq!(r.frame["type"], "ready");
        assert_eq!(r.frame["deviceId"], "till-1");
        assert_eq!(r.frame["roles"], json!(["kitchen", "receipt"]));
        assert_eq!(
            r.frame["heartbeatSeconds"],
            json!(print_hosts::HEARTBEAT_SECONDS)
        );
    }

    /// An authenticated host reaching for a role it does not hold is refused — and the socket stays
    /// up, because it is still a legitimate print host for its own roles.
    #[tokio::test]
    async fn an_authenticated_host_cannot_claim_a_role_it_does_not_hold() {
        let f = fixture().await;
        register(&f.st, "till-bar", "bar").await;
        enqueue(&f.st, "j-kitchen", "kitchen").await;
        let mut conn = connected(&f, "till-bar").await;

        let r = send(&f.st, &mut conn, json!({"type":"claim","role":"kitchen"})).await;
        assert_eq!(
            r.frame["code"],
            erplora_runtime::print_drain::ERR_ROLE_NOT_HOSTED
        );
        assert!(r.keep_open, "it is still the bar's print host");
        assert_eq!(
            status_of(&f.st, "j-kitchen").await,
            print_queue::STATUS_PENDING
        );
    }

    /// Same on the closing door, where the damage would be a **lost** ticket rather than a read one.
    #[tokio::test]
    async fn an_authenticated_host_cannot_confirm_another_roles_job() {
        let f = fixture().await;
        register(&f.st, "till-bar", "bar").await;
        register(&f.st, "till-k", "kitchen").await;
        enqueue(&f.st, "j-kitchen", "kitchen").await;
        let mut kitchen = connected(&f, "till-k").await;
        send(
            &f.st,
            &mut kitchen,
            json!({"type":"claim","role":"kitchen"}),
        )
        .await;

        let mut bar = connected(&f, "till-bar").await;
        let r = send(&f.st, &mut bar, json!({"type":"done","jobId":"j-kitchen"})).await;
        assert_eq!(
            r.frame["code"],
            erplora_runtime::print_drain::ERR_ROLE_NOT_HOSTED
        );
        assert_eq!(
            status_of(&f.st, "j-kitchen").await,
            print_queue::STATUS_PRINTING,
            "the kitchen's ticket is still on its way out"
        );
    }

    /// Nothing waiting is `idle`, not an error: a host polls its role all day and most of the time
    /// the answer is "nothing for you".
    #[tokio::test]
    async fn an_empty_queue_answers_idle() {
        let f = fixture().await;
        register(&f.st, "till-1", "receipt").await;
        let mut conn = connected(&f, "till-1").await;

        let r = send(&f.st, &mut conn, json!({"type":"claim","role":"receipt"})).await;
        assert_eq!(r.frame["type"], "idle");
        assert_eq!(r.frame["role"], "receipt");
    }

    /// A reported failure puts the ticket back for the next host and says so.
    #[tokio::test]
    async fn a_reported_failure_is_acknowledged_and_requeues_the_ticket() {
        let f = fixture().await;
        register(&f.st, "till-1", "receipt").await;
        enqueue(&f.st, "j1", "receipt").await;
        let mut conn = connected(&f, "till-1").await;
        send(&f.st, &mut conn, json!({"type":"claim","role":"receipt"})).await;

        let r = send(
            &f.st,
            &mut conn,
            json!({"type":"failed","jobId":"j1","error":"out of paper"}),
        )
        .await;
        assert_eq!(r.frame["requeued"], true);
        assert_eq!(status_of(&f.st, "j1").await, print_queue::STATUS_PENDING);
    }

    // ── The heartbeat, now on this socket ─────────────────────────────────────────────────────

    /// **The beat that hub#342 had to put on HTTP now travels here.** It is the same news for the
    /// same rows: every role the device hosts comes back at once.
    #[tokio::test]
    async fn a_beat_over_the_socket_refreshes_every_role_of_the_device() {
        let f = fixture().await;
        register(&f.st, "till-1", "receipt").await;
        register(&f.st, "till-1", "kitchen").await;
        let mut conn = connected(&f, "till-1").await;

        let r = send(&f.st, &mut conn, json!({ "type": "beat" })).await;
        assert_eq!(r.frame["type"], "beat");
        assert_eq!(r.frame["refreshed"], json!(2));
        assert_eq!(
            r.frame["heartbeatSeconds"],
            json!(print_hosts::HEARTBEAT_SECONDS)
        );
    }

    /// **The other half of the migration: the HTTP door still works**, deliberately. Registering is
    /// still HTTP, and a host between reconnects has to be able to say "still here" without a
    /// socket. Only the beat of a *connected* host moved.
    #[tokio::test]
    async fn the_http_heartbeat_still_answers_for_a_host_with_no_socket() {
        use axum::body::Body;
        use axum::http::Request;
        use http_body_util::BodyExt;
        use tower::ServiceExt;

        let f = fixture().await;
        register(&f.st, "till-1", "receipt").await;
        let router = crate::app(f.st.clone());

        let resp = router
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/print/hosts/heartbeat")
                    .header("x-hub-session", &f.session)
                    .header("x-device-id", "till-1")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        let bytes = resp.into_body().collect().await.unwrap().to_bytes();
        let body: Value = serde_json::from_slice(&bytes).unwrap();
        assert_eq!(body["ok"], true);
        assert_eq!(body["refreshed"], json!(1));
    }

    /// A beat from a host whose registration was retired while it was connected answers `0` — the
    /// signal that tells it to register again — instead of silently keeping a dead row warm.
    #[tokio::test]
    async fn a_beat_from_a_host_that_was_retired_reports_that_it_hosts_nothing() {
        let f = fixture().await;
        register(&f.st, "till-1", "receipt").await;
        let mut conn = connected(&f, "till-1").await;
        {
            let arc = f.st.runtime_for(&f.st.hub_id()).await.unwrap();
            let rt = arc.lock().await;
            rt.unregister_print_host("till-1", None).await.unwrap();
        }

        let r = send(&f.st, &mut conn, json!({ "type": "beat" })).await;
        assert_eq!(r.frame["refreshed"], json!(0));
    }

    /// **A role retired mid-session stops working immediately.** The roles reported at `hello` are
    /// a hint for waking, never a permission: authorisation is re-read from the registry on every
    /// claim, or a revoked till would keep printing until it happened to reconnect.
    #[tokio::test]
    async fn a_role_retired_while_connected_can_no_longer_be_claimed() {
        let f = fixture().await;
        register(&f.st, "till-1", "receipt").await;
        enqueue(&f.st, "j1", "receipt").await;
        let mut conn = connected(&f, "till-1").await;
        {
            let arc = f.st.runtime_for(&f.st.hub_id()).await.unwrap();
            let rt = arc.lock().await;
            rt.unregister_print_host("till-1", Some("receipt"))
                .await
                .unwrap();
        }

        let r = send(&f.st, &mut conn, json!({"type":"claim","role":"receipt"})).await;
        assert_eq!(
            r.frame["code"],
            erplora_runtime::print_drain::ERR_HOST_NOT_REGISTERED,
            "the socket is still open but the device hosts nothing any more"
        );
        assert_eq!(status_of(&f.st, "j1").await, print_queue::STATUS_PENDING);
    }

    // ── The nudge ─────────────────────────────────────────────────────────────────────────────

    /// A `wake` only goes to a connection that (a) authenticated and (b) hosts that role. It is a
    /// nudge and never carries the document, but a hub that woke every socket for every role would
    /// still be telling a bar till how busy the kitchen is.
    #[test]
    fn a_wake_is_only_for_an_authenticated_host_of_that_role() {
        let mut conn = DrainConnection::default();
        assert!(
            !conn.wants_wake_for("kitchen"),
            "a socket that never said hello is nudged about nothing"
        );

        conn.device_id = "till-1".into();
        conn.roles = vec!["kitchen".into()];
        assert!(conn.wants_wake_for("kitchen"));
        assert!(!conn.wants_wake_for("bar"));
    }
}
