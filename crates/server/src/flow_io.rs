//! **The I/O half of a flow step** (ADR-0283 §4 / K3, hub#662) — the only place in the hub where a
//! flow reaches the network, and the only one that runs **outside the runtime's global lock**.
//!
//! ```text
//!   flows_tick (locked) ──PendingIo──▶ [ this file ] ──IoResult──▶ complete_io (locked)
//!        allow-list, secrets                the call                    output → next step
//! ```
//!
//! Everything about *whether* the call may happen was decided on the other side of that seam
//! (`flows::http::prepare`): the URL was templated, matched against the flow's `http` grants and
//! had its secrets substituted, all under the lock. What is left here is the call itself, plus the
//! one question the runtime cannot answer because it has no network: **where does this name
//! actually point?**
//!
//! ## Anti-SSRF: the address is decided once, and it is the address dialled
//!
//! The classic hole is a check-then-connect: resolve the name, decide the address is fine, and hand
//! the *name* to the HTTP client — which resolves it again. Between those two lookups a DNS record
//! whose TTL is 0 can change (DNS rebinding), and the connection lands on `169.254.169.254` or on
//! the Postgres of the hub next door. The allow-list does not help: `https://api.attacker.com/x` is
//! a perfectly legitimate URL to grant, and the attacker owns the name.
//!
//! So there is **no second lookup**. [`GuardedResolver`] IS the client's resolver
//! (`ClientBuilder::dns_resolver`): it resolves the name once, refuses the answer if ANY address in
//! it is inside a private/loopback/link-local range, and hands back exactly those addresses for
//! hyper to dial. Check and connect use the same list, produced by the same call — there is no
//! window between them to slip through.
//!
//! Two seams that would otherwise go around it, both closed:
//!
//! - **IP literals** (`http://127.0.0.1/`, `http://[::1]/`) never reach a resolver — hyper
//!   short-circuits them — so [`check_url`] validates them before the request is built.
//! - **Redirects** are disabled. A 302 to `http://169.254.169.254/` would be a second request to a
//!   host nobody granted and nobody checked.
//!
//! ## And the URL judged is the URL dialled (hub#728)
//!
//! The literal check above used to be done on the *text* of the URL, with a parser written here,
//! while the request was built from that same text by `reqwest` — which parses it with WHATWG.
//! `http://2130706433/` is «a host name» to a hand-rolled splitter and `http://127.0.0.1/` to
//! WHATWG, so the literal check found nothing to check and hyper short-circuited straight to the
//! loopback. A flow read `/api/hub/context` off the hub running it.
//!
//! There is now **one parse**, in `erplora_runtime::flows::net`, and what crosses the seam is the
//! resulting [`Url`] object. [`check_url`] judges that object and [`wire_request`] hands that same
//! object to `reqwest` — never a string for it to parse again.
//!
//! What this does NOT close, stated plainly: an allow-listed host that is legitimately public today
//! and points somewhere hostile tomorrow is still called (that is what granting a host means), and
//! a *public* address that is nonetheless sensitive — a hub reachable from the internet — is not
//! distinguishable from any other public address here.
use std::net::SocketAddr;
use std::sync::{Arc, OnceLock};
use std::time::Duration;

use erplora_runtime::flows::net::{self, Url};
use erplora_runtime::flows::{HttpRequest, IoResult, PendingIo};
use futures_util::StreamExt;
use reqwest::dns::{Addrs, Name, Resolve, Resolving};
use serde_json::{json, Value};

use crate::state::AppState;

/// The call was refused before it left: a scheme this hub does not speak, or an address inside the
/// network. Distinct from [`ERR_HTTP_FAILED`] on purpose — one is a flow doing something it may
/// not, the other is somebody else's server having a bad day.
pub const ERR_HTTP_BLOCKED: &str = "flow.http_blocked";
pub const ERR_HTTP_FAILED: &str = "flow.http_failed";
pub const ERR_HTTP_TIMEOUT: &str = "flow.http_timeout";
pub const ERR_HTTP_STATUS: &str = "flow.http_status";

/// How much of an answer a step keeps. A megabyte is a generous JSON payload and a small file; past
/// it the response is truncated and the step says so, because the alternative is a run row the size
/// of whatever somebody decided to serve.
const MAX_BODY_BYTES: usize = 1024 * 1024;

/// The knobs a caller may turn. Production uses [`Limits::default`] and nothing else; the only
/// reason this is a parameter rather than a constant is that a test's fake server necessarily lives
/// on `127.0.0.1`, and an environment variable that unlocked the SSRF guard in a shipped binary
/// would be a hole with a switch on it.
#[derive(Debug, Clone)]
pub struct Limits {
    /// Allow addresses inside this network. **Tests only** — nothing in the server ever sets it.
    pub allow_private_addresses: bool,
    pub max_body_bytes: usize,
}

impl Default for Limits {
    fn default() -> Self {
        Self {
            allow_private_addresses: false,
            max_body_bytes: MAX_BODY_BYTES,
        }
    }
}

impl Limits {
    /// The limits a test with a fake server on loopback needs. Everything else stays as it ships.
    pub fn allowing_private_addresses() -> Self {
        Self {
            allow_private_addresses: true,
            ..Self::default()
        }
    }
}

/// Hands every pending I/O of a tick to its own task, **outside the lock**, and completes it when
/// the answer comes back.
///
/// Detached tasks and not a join: the tick that produced these runs every second and must not wait
/// for a 30 s call. The run they belong to is already claimed with a 300 s lease, so a task that
/// dies with its process leaves a run that is reclaimed and re-issued — never one that is lost.
pub fn dispatch(state: &AppState, pending: Vec<PendingIo>) {
    for io in pending {
        let state = state.clone();
        tokio::spawn(async move {
            let run_id = io.run_id().to_string();
            let step_id = io.step_id().to_string();
            let result = match &io {
                PendingIo::Http { request, .. } => execute(request, &Limits::default()).await,
                // The agent turn (hub#665). It answers with the same `IoResult` vocabulary as an
                // HTTP call, plus the two states only an agent has: the write it proposed is
                // waiting for a person, or a person said no.
                PendingIo::Ai { .. } => {
                    crate::agent_runner::run_turn(&state, &run_id, &step_id).await
                }
            };
            let rt = state.runtime.lock().await;
            if let Err(e) = rt.complete_flow_io(&run_id, &step_id, result).await {
                eprintln!("flows: completing run {run_id} step `{step_id}`: {e}");
            }
        });
    }
}

/// Performs one prepared request and turns it into what the next step reads.
///
/// Output on success: `{status, ok, body_json | body_text}` (plus `truncated: true` when the answer
/// was cut). A **non-2xx answer fails the step**: v1 flows are linear with `on_error: "stop"`, so
/// there is nowhere to branch on a 500, and carrying on would be a flow that treats "the API
/// refused" as "the API accepted".
pub async fn execute(request: &HttpRequest, limits: &Limits) -> IoResult {
    let outgoing = match wire_request(request, limits) {
        Ok(outgoing) => outgoing,
        Err(why) => return IoResult::Failed(why),
    };
    let client = client(limits.allow_private_addresses);

    // Belt and braces on the deadline: reqwest's own timeout covers the request, and this covers
    // everything including reading a body that arrives one slow byte at a time. A step that
    // overruns its lease would be re-issued while still in flight.
    let deadline = Duration::from_secs(request.timeout_seconds + 1);
    let sent = match tokio::time::timeout(deadline, client.execute(outgoing)).await {
        Ok(Ok(response)) => response,
        Ok(Err(e)) => return failed(request, &e),
        Err(_) => {
            return IoResult::Failed(format!(
                "{ERR_HTTP_TIMEOUT}: no answer from `{}` in {} s",
                request.redacted_url(),
                request.timeout_seconds
            ))
        }
    };

    let status = sent.status();
    let (body, truncated) = match tokio::time::timeout(deadline, read_body(sent, limits)).await {
        Ok(Ok(pair)) => pair,
        Ok(Err(e)) => return failed(request, &e),
        Err(_) => {
            return IoResult::Failed(format!(
                "{ERR_HTTP_TIMEOUT}: `{}` answered {} but never finished sending it",
                request.redacted_url(),
                status.as_u16()
            ))
        }
    };
    // Whatever came back is scrubbed of the credential that went out: plenty of APIs echo the key
    // they were sent inside their error message, and that echo would land in `_flow_run_steps`.
    let body = request.scrub(&body);

    if !status.is_success() {
        return IoResult::Failed(format!(
            "{ERR_HTTP_STATUS}: `{}` answered {} — {}",
            request.redacted_url(),
            status.as_u16(),
            first_line(&body)
        ));
    }

    let mut output = json!({ "status": status.as_u16(), "ok": true });
    let map = output.as_object_mut().expect("just built an object");
    match serde_json::from_str::<Value>(&body) {
        Ok(parsed) if parsed.is_object() || parsed.is_array() => {
            map.insert("body_json".into(), parsed);
        }
        _ => {
            map.insert("body_text".into(), json!(body));
        }
    }
    if truncated {
        map.insert("truncated".into(), json!(true));
    }
    IoResult::Done(output)
}

/// **The request as it really goes on the wire.** The one place it is built, and the whole of
/// hub#728/#729 in five lines: [`check_url`] judges `request.url`, and it is *that very object* —
/// not its text — that `reqwest` is handed. A `&str` here would be parsed a second time, and a
/// second parse is a second URL nobody approved.
///
/// Public so that a test can ask what would be dialled without dialling it, of the same code path
/// that dials it; a test that rebuilt the request itself would pin nothing.
pub fn wire_request(request: &HttpRequest, limits: &Limits) -> Result<reqwest::Request, String> {
    check_url(&request.url, limits).map_err(|why| format!("{ERR_HTTP_BLOCKED}: {why}"))?;
    let method = reqwest::Method::from_bytes(request.method.as_bytes()).map_err(|_| {
        format!(
            "{ERR_HTTP_BLOCKED}: `{}` is not an HTTP method",
            request.method
        )
    })?;

    let mut builder = client(limits.allow_private_addresses)
        .request(method, request.url.clone())
        .timeout(Duration::from_secs(request.timeout_seconds));
    for (name, value) in &request.headers {
        builder = builder.header(name, value);
    }
    if let Some(body) = &request.body {
        builder = builder.body(body.clone());
    }
    builder
        .build()
        .map_err(|e| format!("{ERR_HTTP_FAILED}: {}", request.scrub(&error_chain(&e))))
}

/// Reads at most [`Limits::max_body_bytes`], streaming — a `Content-Length` of 4 GB must cost this
/// hub one megabyte of memory, not four gigabytes.
async fn read_body(
    response: reqwest::Response,
    limits: &Limits,
) -> Result<(String, bool), reqwest::Error> {
    let mut stream = response.bytes_stream();
    let mut buffer: Vec<u8> = Vec::new();
    let mut truncated = false;
    while let Some(chunk) = stream.next().await {
        let chunk = chunk?;
        let room = limits.max_body_bytes.saturating_sub(buffer.len());
        if chunk.len() >= room {
            buffer.extend_from_slice(&chunk[..room]);
            truncated = true;
            break;
        }
        buffer.extend_from_slice(&chunk);
    }
    Ok((String::from_utf8_lossy(&buffer).to_string(), truncated))
}

/// A transport failure, told with the whole error chain — the reason a call did not happen lives in
/// the innermost source (`GuardedResolver`'s refusal, a TLS error, a refused connection), and
/// reqwest's own `Display` says only "error sending request".
fn failed(request: &HttpRequest, error: &reqwest::Error) -> IoResult {
    let chain = error_chain(error);
    let code = if error.is_timeout() {
        ERR_HTTP_TIMEOUT
    } else if chain.contains(BLOCKED_MARKER) {
        ERR_HTTP_BLOCKED
    } else {
        ERR_HTTP_FAILED
    };
    IoResult::Failed(format!("{code}: {}", request.scrub(&chain)))
}

fn error_chain(error: &dyn std::error::Error) -> String {
    let mut parts = vec![error.to_string()];
    let mut source = error.source();
    while let Some(e) = source {
        parts.push(e.to_string());
        source = e.source();
    }
    parts.join(": ")
}

fn first_line(body: &str) -> String {
    let line: String = body.lines().next().unwrap_or_default().chars().take(200).collect();
    if line.is_empty() {
        "(empty body)".to_string()
    } else {
        line
    }
}

// ── the guard ─────────────────────────────────────────────────────────────────────────────────

/// Marker the resolver's refusal carries so [`failed`] can tell it apart from a network error deep
/// inside hyper's error chain.
const BLOCKED_MARKER: &str = "[flow-ssrf-guard]";

/// The clients, built once. Two of them because the guard is baked into the resolver, and a client
/// is the smallest thing that can carry a resolver.
fn client(allow_private: bool) -> &'static reqwest::Client {
    static STRICT: OnceLock<reqwest::Client> = OnceLock::new();
    static PERMISSIVE: OnceLock<reqwest::Client> = OnceLock::new();
    let cell = if allow_private { &PERMISSIVE } else { &STRICT };
    cell.get_or_init(|| build_client(allow_private))
}

fn build_client(allow_private: bool) -> reqwest::Client {
    reqwest::Client::builder()
        // No redirects: a 302 is a second request, to a host that was never granted and never
        // checked. The step sees the 3xx and fails, which is the honest answer.
        .redirect(reqwest::redirect::Policy::none())
        .dns_resolver(Arc::new(GuardedResolver { allow_private }))
        .build()
        .unwrap_or_else(|e| panic!("building the flow HTTP client: {e}"))
}

/// **The resolver IS the guard.** See the module docs: because this is what hyper uses to resolve,
/// the addresses it approves are the addresses that get dialled — there is no second lookup for a
/// rebinding to happen in.
struct GuardedResolver {
    allow_private: bool,
}

impl Resolve for GuardedResolver {
    fn resolve(&self, name: Name) -> Resolving {
        let allow_private = self.allow_private;
        Box::pin(async move {
            let host = name.as_str().to_string();
            // Port 0: hyper overwrites it with the port of the URL.
            let addrs: Vec<SocketAddr> = tokio::net::lookup_host((host.as_str(), 0))
                .await
                .map_err(|e| -> Box<dyn std::error::Error + Send + Sync> {
                    format!("{BLOCKED_MARKER} `{host}` does not resolve: {e}").into()
                })?
                .collect();
            if addrs.is_empty() {
                return Err(format!("{BLOCKED_MARKER} `{host}` resolves to nothing").into());
            }
            if !allow_private {
                // If ANY answer is internal the whole answer is refused, rather than the internal
                // ones filtered out: a name that answers with one public and one private address is
                // not a name with a bad entry, it is a name doing exactly what a rebinding attack
                // does, and which address gets dialled first is not ours to decide.
                if let Some(bad) = addrs.iter().find(|a| net::is_internal(&a.ip())) {
                    return Err(format!(
                        "{BLOCKED_MARKER} `{host}` resolves to {}, which is inside this network — \
                         a flow reaches the internet, never the hub's own neighbourhood",
                        bad.ip()
                    )
                    .into());
                }
            }
            Ok(Box::new(addrs.into_iter()) as Addrs)
        })
    }
}

/// The scheme and, for a literal address, the address — the half of the guard a resolver never
/// sees, because hyper does not resolve `http://127.0.0.1/`.
///
/// It takes the [`Url`] the runtime already parsed, so «which host is this?» is answered by
/// `Url::host()` — the WHATWG host parser, the same one that will produce the address hyper
/// dials. That identity is hub#728: every spelling of the loopback (`2130706433`, `0x7f000001`,
/// `127.1`, `127.0.0.1.`, `[::ffff:7f00:1]`) arrives here already collapsed into `127.0.0.1`,
/// instead of looking like a host name to a splitter that only understood dotted quads.
fn check_url(url: &Url, limits: &Limits) -> Result<(), String> {
    if !matches!(url.scheme(), "http" | "https") {
        return Err(format!("`{url}` is not an http(s) URL"));
    }
    // A NAME is not judged here — that is the resolver's job, and it is judged there so that the
    // addresses approved are the addresses dialled (no window for a DNS rebinding).
    let Some(ip) = net::literal_address(url) else {
        return Ok(());
    };
    if !limits.allow_private_addresses && net::is_internal(&ip) {
        return Err(format!(
            "`{ip}` is inside this network — a flow reaches the internet, never the hub's own \
             neighbourhood"
        ));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The whole pipeline in one line: **parse once**, then judge THAT. Nothing in the server can
    /// hand the guard a string, so nothing in these tests may either — an URL that does not parse
    /// is a call that never happens, which is the same answer as a refusal.
    ///
    /// The address arithmetic itself (`is_internal`, and which spelling of a literal collapses
    /// into which address) lives with the parser, in `erplora_runtime::flows::net`; what belongs
    /// here is what THIS gate does with the answer. The end-to-end behaviour — a real fake server,
    /// the count of requests that leave, a name that resolves to loopback — is in
    /// `tests/flow_http_step.rs`, which can bind a socket.
    fn refused(url: &str, limits: &Limits) -> bool {
        match net::parse(url) {
            Err(_) => true,
            Ok(parsed) => check_url(&parsed, limits).is_err(),
        }
    }

    #[test]
    fn a_literal_address_inside_the_network_is_refused_before_a_socket_is_opened() {
        let limits = Limits::default();
        for url in [
            "http://127.0.0.1:8080/x",
            "http://[::1]/x",
            "https://169.254.169.254/latest/meta-data/",
            "http://[::ffff:127.0.0.1]/x",
        ] {
            assert!(refused(url, &limits), "{url}");
        }
        assert!(!refused("https://api.example.com/v1/x", &limits));
        // A NAME is not judged here — that is the resolver's job, and it is judged there so that
        // the address checked is the address dialled.
        assert!(!refused("http://localhost/x", &limits));
    }

    /// hub#728 — the corpus a QA walked a live hub through. Every string here is `127.0.0.1` or
    /// `169.254.169.254` **to the parser the HTTP client uses**, so it has to be that to the guard
    /// too. The one that was verified in the wild is the first: a flow read `/api/hub/context` off
    /// the hub that was running it.
    #[test]
    fn an_address_inside_this_network_is_refused_in_every_notation_a_url_can_spell_it() {
        let limits = Limits::default();
        for url in [
            "http://2130706433:8791/api/hub/context", // 127.0.0.1 in decimal
            "http://0x7f000001/x",                    // …in hex
            "http://017700000001/x",                  // …in octal
            "http://127.1/x",                         // …short form
            "http://127.0.0.1./x",                    // …with the root label
            "http://0/x",                             // …0.0.0.0, the other way to say "me"
            "http://2852039166/latest/meta-data/",    // the cloud metadata service in decimal
            "http://0xa9fea9fe/latest/meta-data/",    // …in hex
            "http://[::ffff:169.254.169.254]/x",      // …wearing an IPv6 hat
            "http://[::ffff:a9fe:a9fe]/x",            // …the same hat, written in groups
            "http://[64:ff9b::a9fe:a9fe]/x",          // …through NAT64
            "http://[0:0:0:0:0:0:0:1]/x",             // ::1, uncompressed
            "http://3232235777/x",                    // 192.168.1.1 in decimal
            "http://167772161/x",                     // 10.0.0.1 in decimal
        ] {
            assert!(refused(url, &limits), "{url}");
        }

        // The twin, so that «refused» keeps meaning something: the public internet still goes out,
        // including hosts whose name is all digits and addresses next door to a blocked range.
        for url in [
            "https://api.example.com/v1/x",
            "http://1.1.1.1/x",
            "http://172.32.0.1/x",
            "http://[2606:4700:4700::1111]/x",
        ] {
            assert!(!refused(url, &limits), "{url}");
        }
    }

    #[test]
    fn only_http_and_https_ever_leave() {
        let limits = Limits::default();
        for url in ["file:///etc/passwd", "ftp://example.com/x", "gopher://x/", "/x"] {
            assert!(refused(url, &limits), "{url}");
        }
    }

    #[test]
    fn the_test_only_escape_hatch_is_the_only_way_past_the_guard() {
        // It exists for a fake server on loopback and nothing else — nothing in the server sets it,
        // and there is deliberately no environment variable that would.
        assert!(!Limits::default().allow_private_addresses);
        assert!(refused("http://127.0.0.1:9/x", &Limits::default()));
        assert!(!refused("http://127.0.0.1:9/x", &Limits::allowing_private_addresses()));
    }
}
