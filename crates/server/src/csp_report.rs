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
/// Always `204`. The browser is not asking a question and has nothing to do with an error, and a
/// non-2xx here would only teach it to keep retrying a door that works.
pub(crate) async fn receive(body: Bytes) -> StatusCode {
    use erplora_runtime::error_registry::{severity, source, ErrorEvent, ErrorRegistry};

    let violation = summarise(&body);

    // WARN and not INFO: this fires when a wall the till depends on has just refused something.
    // It is bounded — every field is clipped and the body limit caps the request — so it costs no
    // more than the request line `TraceLayer` already writes for the same POST.
    tracing::warn!(
        blocked_uri = %violation.blocked_uri,
        directive = %violation.directive,
        document_uri = %violation.document_uri,
        disposition = %violation.disposition,
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
}
