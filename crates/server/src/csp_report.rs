//! The other end of the hub's `report-uri` (hub#1447).
//!
//! Without this door the hub's CSP is a wall that fires in silence: the browser refuses the
//! resource, writes one line into the console of the device it happened on, and that is the whole
//! record. `ERPlora/infra#73` is what that costs — Cloudflare injected its Web Analytics beacon
//! into the HTML at the edge, `script-src 'self'` refused it on **every page of every hub**, and
//! we found out because a person opened the console by hand.
//!
//! ## Why the report goes to the hub and not to the SaaS
//!
//! An absolute `report-uri` would point the whole fleet at one origin: every hub's violations in
//! one log, the `hub_id` needed inside the report to tell who spoke, and a self-hosted hub
//! reporting to a SaaS it may not have. The hub already knows who it is and already writes logs.
//!
//! ## Two destinations, because they fail in different places
//!
//! - `tracing::warn!` — the trace that always exists. Works on a hub with no Cloud, and it is the
//!   line an alert can watch. The SaaS half of this pair does the same
//!   (`apps/dashboard/core/views.py`).
//! - [`ErrorRegistry`] — the funnel this codebase already has for exactly this class of event
//!   (`/api/error-report` sends the frontend's JS errors down it). It dedups and throttles, which
//!   an unauthenticated door needs, and forwards to the Cloud when the hub is enrolled.
//!
//! ## The door is open, so it assumes nothing
//!
//! Anyone who can open the hub in a browser can post here — that is what `report-uri` means. So
//! the body is parsed leniently and every field is truncated: a report is a `204` whatever it
//! contains, and malformed input is never a `500`. A receiver that panics on bad input is a new
//! way to make noise, not a way to hear it.

use axum::body::Bytes;
use axum::http::StatusCode;
use serde_json::Value;

/// Longest a single field may be once it reaches the log. `script-sample` carries a slice of the
/// offending code and a hostile page decides how long that is.
const FIELD_MAX: usize = 200;

/// How many reports may reach the log per window, and how long the window is.
///
/// The same 60/h the SaaS settled on in `saas#973` §5, where THIS endpoint —the Django twin— was
/// filed as "log injection and free flood": no quota, one `csp_logger.warning` per POST, and the
/// logs go to Loki. It was proved against production. The door is opened by anybody who loads the
/// page, so without a quota it is an unbounded write into the business's own log.
///
/// Sixty is not a measurement of violations; it is the point past which counting stops being
/// useful. A hub with sixty recorded in an hour is already told.
const MAX_PER_WINDOW: u32 = 60;
const WINDOW_SECS: u64 = 3600;

/// A fixed-window counter, GLOBAL to the endpoint.
///
/// Deliberately not per-reporter, which is where the SaaS keys it (`key="ip"`): behind Cloudflare
/// the client address arrives in `X-Forwarded-For`, chosen by whoever posts, so a per-IP quota here
/// is evaded by rotating a header. A global one is not.
///
/// Fixed window and not a token bucket: the worst case is twice the quota across a window boundary,
/// which for a log line is nothing, and this way there is no per-request allocation and no timer.
struct Limiter {
    /// `(window_start_unix, count)`.
    state: std::sync::Mutex<(u64, u32)>,
}

impl Limiter {
    const fn new() -> Self {
        Self {
            state: std::sync::Mutex::new((0, 0)),
        }
    }

    /// `true` if this report may reach the log. Never blocks the response — see [`receive`].
    fn allow(&self, now: u64) -> bool {
        // A poisoned mutex must not turn the report door into a panic loop: a thread that died
        // elsewhere is not a reason to stop hearing what the policy refused.
        let mut guard = match self.state.lock() {
            Ok(guard) => guard,
            Err(poisoned) => poisoned.into_inner(),
        };
        let (window_start, count) = *guard;
        if now.saturating_sub(window_start) >= WINDOW_SECS {
            *guard = (now, 1);
            return true;
        }
        if count >= MAX_PER_WINDOW {
            return false;
        }
        *guard = (window_start, count + 1);
        true
    }
}

/// The endpoint's quota, for the life of the process.
static LIMITER: Limiter = Limiter::new();

/// Seconds since the epoch, or `0` if the clock is before it — a clock that broken is somebody
/// else's incident, and it must not cost the report.
fn now_unix() -> u64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0)
}

/// What is worth keeping out of a violation report. Everything else the browser sends
/// (`referrer`, `status-code`, `original-policy`, the full `script-sample`) is either noise or a
/// copy of what we already know.
#[derive(Debug, PartialEq, Eq)]
pub(crate) struct Violation {
    /// What the policy refused — the beacon's URL, in the infra#73 case.
    pub blocked_uri: String,
    /// Which directive did the refusing (`script-src-elem`, `style-src`…).
    pub directive: String,
    /// The page it happened on.
    pub document_uri: String,
    /// `enforce` or `report`. A `report` disposition is a policy being tried out, not a wall.
    pub disposition: String,
}

/// Cuts a string to [`FIELD_MAX`] **characters**, never bytes: slicing UTF-8 by byte offset panics
/// mid-codepoint, and a URL with an accent in it is not exotic.
fn clip(value: &str) -> String {
    match value.char_indices().nth(FIELD_MAX) {
        Some((end, _)) => format!("{}…", &value[..end]),
        None => value.to_string(),
    }
}

/// Reads a field as a string, whatever the browser put there. A number or a `null` becomes the
/// empty string rather than a parse failure: the report is still worth having without it.
fn field(report: &Value, key: &str) -> String {
    report
        .get(key)
        .and_then(Value::as_str)
        .map(clip)
        .unwrap_or_default()
}

/// Normalises whatever was posted into a [`Violation`].
///
/// Accepts both envelopes: the classic `{"csp-report": {…}}` that `report-uri` sends, and a bare
/// object, which is what arrives if the payload is ever produced by hand or by the Reporting API's
/// shape. Anything unparseable yields an empty violation — the `204` and the log line still
/// happen, because "somebody posted junk at the report door" is itself worth seeing.
pub(crate) fn summarise(raw: &[u8]) -> Violation {
    let parsed: Value = serde_json::from_slice(raw).unwrap_or(Value::Null);
    let report = match parsed.get("csp-report") {
        Some(inner) if inner.is_object() => inner,
        _ => &parsed,
    };
    Violation {
        blocked_uri: field(report, "blocked-uri"),
        directive: field(report, "effective-directive"),
        document_uri: field(report, "document-uri"),
        disposition: field(report, "disposition"),
    }
}

/// `POST /csp-report/` — where the browser posts what this hub's policy refused.
///
/// Always `204` — including over quota. The browser is not asking a question and has nothing to do
/// with an error, and a non-2xx here would only teach it to keep retrying a door that works; some
/// clients retry the report itself, so a `429` would defend the quota by generating more traffic
/// than it turns away. The quota shortens what is WRITTEN, never what is ANSWERED.
pub(crate) async fn receive(body: Bytes) -> StatusCode {
    use erplora_runtime::error_registry::{severity, source, ErrorEvent, ErrorRegistry};

    // The quota decides what gets WRITTEN, never what gets answered. Over it, the report is
    // dropped here and the browser still gets its `204` — see the doc comment.
    if !LIMITER.allow(now_unix()) {
        return StatusCode::NO_CONTENT;
    }

    let violation = summarise(&body);

    // WARN and not INFO: this fires when a wall the till depends on has just refused something.
    // It is bounded — every field is clipped, the body limit caps the request and the quota caps
    // the rate — so it cannot outgrow the request line `TraceLayer` already writes for this POST.
    //
    // `?` and never `%` (hub#2294): these four values are written by whoever posts, and tracing
    // escapes ESC but not `\n` nor spaces. With `%` a report could end this line and start one that
    // reads as `event=auth_failed … client=<another shop>`, which the edge ban and the alerts
    // count. `Debug` quotes the value and escapes every control character, so it stays one field.
    tracing::warn!(
        blocked_uri = ?violation.blocked_uri,
        directive = ?violation.directive,
        document_uri = ?violation.document_uri,
        disposition = ?violation.disposition,
        "CSP violation reported by the browser"
    );

    // The same funnel `/api/error-report` uses for the frontend's JS errors: it dedups and
    // throttles (a violation that fires on every page load arrives on every page load) and
    // forwards to the Cloud when this hub is enrolled.
    ErrorRegistry::global().report(
        ErrorEvent::new(
            source::FRONTEND,
            "csp_violation",
            format!("{} refused {}", violation.directive, violation.blocked_uri),
            severity::UNEXPECTED,
        )
        .with_context(serde_json::json!({
            "document_uri": violation.document_uri,
            "blocked_uri": violation.blocked_uri,
            "directive": violation.directive,
            "disposition": violation.disposition,
        })),
    );

    StatusCode::NO_CONTENT
}

#[cfg(test)]
mod tests {
    //! hub#1447: the parsing half, which is the half a hostile page controls.
    use super::*;

    /// The envelope Chrome actually sent in infra#73.
    const REAL: &str = r#"{"csp-report":{
      "document-uri":"https://salon-aurora.a.erplora.com/login",
      "violated-directive":"script-src-elem",
      "effective-directive":"script-src-elem",
      "disposition":"enforce",
      "blocked-uri":"https://static.cloudflareinsights.com/beacon.min.js/v4513226cda"}}"#;

    #[test]
    fn hub1447_a_real_report_keeps_what_matters() {
        let v = summarise(REAL.as_bytes());
        assert_eq!(v.directive, "script-src-elem");
        assert_eq!(v.disposition, "enforce");
        assert_eq!(
            v.blocked_uri,
            "https://static.cloudflareinsights.com/beacon.min.js/v4513226cda"
        );
        assert_eq!(v.document_uri, "https://salon-aurora.a.erplora.com/login");
    }

    #[test]
    fn hub1447_a_bare_object_is_read_too() {
        // No `csp-report` wrapper: read the top level rather than returning nothing.
        let v = summarise(
            br#"{"blocked-uri":"https://evil.example/x","effective-directive":"img-src"}"#,
        );
        assert_eq!(v.blocked_uri, "https://evil.example/x");
        assert_eq!(v.directive, "img-src");
    }

    #[test]
    fn hub1447_junk_does_not_panic_and_still_reports_something() {
        for raw in [
            &b"not json at all"[..],
            b"",
            b"{}",
            br#"{"csp-report":null}"#,
            br#"{"csp-report":{"blocked-uri":12345}}"#,
            br#"[1,2,3]"#,
        ] {
            let v = summarise(raw);
            assert_eq!(v, summarise(raw), "summarise is not deterministic");
            assert!(v.blocked_uri.len() <= FIELD_MAX + 1);
        }
    }

    #[test]
    fn hub1447_a_flood_cannot_write_the_log_without_end() {
        // saas#973 §5, recreado aquí y arreglado antes de mergear: el mismo endpoint en el SaaS
        // era «inyección en logs y flood» — sin cuota, `csp_logger.warning` por cada POST, y los
        // logs van a Loki. Probado entonces contra producción. La puerta del hub la abre cualquiera
        // que cargue la página, así que sin cuota es una escritura ilimitada en el log del negocio.
        let limiter = Limiter::new();
        let t0 = 1_000_000;
        for i in 0..MAX_PER_WINDOW {
            assert!(limiter.allow(t0), "el informe {i} debería pasar");
        }
        assert!(
            !limiter.allow(t0),
            "el informe {} entró: la cuota no corta",
            MAX_PER_WINDOW + 1
        );
        // Y no es un cierre permanente: la ventana siguiente vuelve a abrir, o una violación real
        // que empiece mañana no se vería nunca.
        assert!(
            limiter.allow(t0 + WINDOW_SECS),
            "la ventana no se renueva: la puerta queda cerrada para siempre"
        );
    }

    #[test]
    fn hub1447_the_quota_is_global_and_not_per_reporter() {
        // A propósito distinto del SaaS, que acota por IP: detrás de Cloudflare la IP del cliente
        // llega en `X-Forwarded-For`, que quien postea elige. Una cuota por IP en el hub se evade
        // rotando la cabecera; una global no. Un negocio con 60 violaciones registradas en una
        // hora ya está avisado — el objetivo es enterarse, no contar.
        let limiter = Limiter::new();
        let t0 = 2_000_000;
        for _ in 0..MAX_PER_WINDOW {
            limiter.allow(t0);
        }
        assert!(
            !limiter.allow(t0),
            "la cuota se agotó y aún deja pasar: no es global"
        );
    }

    #[test]
    fn hub1447_a_long_field_is_clipped_without_splitting_a_character() {
        // Byte-slicing this would panic: `é` is two bytes and the cut lands inside it.
        let long = "é".repeat(FIELD_MAX * 3);
        let raw = format!(r#"{{"csp-report":{{"blocked-uri":"{long}"}}}}"#);
        let v = summarise(raw.as_bytes());
        assert_eq!(
            v.blocked_uri.chars().count(),
            FIELD_MAX + 1,
            "clipped to N chars plus the ellipsis"
        );
        assert!(v.blocked_uri.ends_with('…'));
    }

    /// The four report keys a stranger fills in, next to the field each one lands in on the log.
    const LOGGED_FIELDS: [(&str, &str); 4] = [
        ("blocked-uri", "blocked_uri"),
        ("effective-directive", "directive"),
        ("document-uri", "document_uri"),
        ("disposition", "disposition"),
    ];

    /// What infra#338 feared: the line the address guard writes when a PIN fails, the one the
    /// edge ban and the `erp-hub-auth-failed-burst` alert count — pointing at somebody else's
    /// shop.
    const FORGED: &str =
        "WARN erplora_server::address_guard: event=auth_failed reason=pin client=203.0.113.7 hub=h";

    /// Posts `value` under `key` through the real handler and returns what reached the log.
    async fn logged_for(key: &str, value: &str) -> String {
        let raw = serde_json::json!({ "csp-report": { key: value } }).to_string();
        let (sink, guard) = crate::log_capture::capture_scope();
        receive(Bytes::from(raw)).await;
        drop(guard);
        sink.text()
    }

    #[tokio::test]
    async fn hub2294_a_newline_in_a_report_cannot_forge_a_log_line() {
        // The door is open to anybody and tracing escapes ESC but not `\n`: a raw value used to
        // end the CSP line and start a second one that read exactly like a failed PIN.
        for (key, _) in LOGGED_FIELDS {
            let log = logged_for(key, &format!("x\n{FORGED}")).await;
            let lines: Vec<&str> = log.lines().collect();
            assert_eq!(lines.len(), 1, "{key}: one report must be one line, got {log:?}");
            assert!(
                lines[0].contains("CSP violation reported by the browser"),
                "{key}: the only line is not the report's: {log:?}"
            );
        }
    }

    #[tokio::test]
    async fn hub2294_a_forged_event_stays_quoted_inside_its_field() {
        // Without a newline the fake text rode inside the CSP line as bare `event=… client=…`
        // pairs, which a key=value reader cannot tell from the hub's own. Quoted, it is one value.
        for (key, field) in LOGGED_FIELDS {
            let log = logged_for(key, &format!("x {FORGED}")).await;
            assert!(
                log.contains(&format!("{field}=\"x {FORGED}\"")),
                "{key}: the value is not enclosed in its own field: {log:?}"
            );
        }
    }
}
