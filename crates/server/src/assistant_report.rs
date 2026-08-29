//! `POST /api/assistant/report` — a signed-in hub user reports inappropriate AI-generated
//! content from the assistant (Microsoft Store policy 11.16, hub#946).
//!
//! The report is NOT a new table: it is funneled into the existing global error registry
//! (ADR-0052 single funnel), whose `CloudErrorSink` forwards it to the SaaS
//! (`POST /api/v1/hub/device/error-report/`) where it is persisted and reviewable.
//!
//! Two deliberate choices:
//! - **severity `unexpected`, never `user`**: a content complaint must reach the operator for
//!   review; `user` severity is telemetry-only and would never surface it.
//! - **the `message` embeds the unique `message_id`**: the registry dedups on
//!   `source|module_id|error_code|message` (see `fingerprint()` in
//!   `crates/runtime/src/error_registry.rs`) — a constant message would silently swallow every
//!   report after the first one.
//!
//! Context fields are truncated for data minimization (GDPR, ADR-0149), on char boundaries —
//! never mid-UTF-8.
use axum::extract::State;
use axum::http::HeaderMap;
use axum::response::{IntoResponse, Response};
use axum::Json;
use erplora_runtime::error_registry::{severity, source, ErrorEvent, ErrorRegistry};
use erplora_runtime::RuntimeError;
use serde::Deserialize;
use serde_json::json;

use crate::state::AppState;
use crate::{auth, err_response, tenant_rejected, unauthorized};

/// Data-minimization caps (chars, not bytes — truncation is char-boundary safe).
const ASSISTANT_MESSAGE_MAX_CHARS: usize = 4000;
const USER_MESSAGE_MAX_CHARS: usize = 4000;
const COMMENT_MAX_CHARS: usize = 1000;
const REASON_MAX_CHARS: usize = 100;
/// How much of the reported response travels inside the event `message` (the dedup key).
const SNIPPET_MAX_CHARS: usize = 120;

/// Body of `POST /api/assistant/report`.
#[derive(Deserialize)]
pub struct ReportReq {
    /// Unique id of the reported assistant message (required, non-empty).
    message_id: String,
    /// The reported AI response text (required, non-empty).
    assistant_message: String,
    /// The user prompt that preceded it (optional).
    #[serde(default)]
    user_message: Option<String>,
    /// Free-text reporter comment (optional).
    #[serde(default)]
    comment: Option<String>,
    /// Short reason tag (optional).
    #[serde(default)]
    reason: Option<String>,
}

/// `POST /api/assistant/report` → `{ok: true}`. Any authenticated hub user may report (no admin
/// gate): the person offended by the content is whoever is in front of the screen.
pub async fn report(
    State(st): State<AppState>,
    headers: HeaderMap,
    Json(req): Json<ReportReq>,
) -> Response {
    let arc = match st.runtime_for(&auth::hub_id(&headers, &st.hub_id())).await {
        Ok(rt) => rt,
        Err(e) => return tenant_rejected(e),
    };
    let rt = arc.read().await;
    let ctx = match auth::authenticate(&headers, &st.config, &rt).await {
        Ok(c) => c,
        Err(e) => return unauthorized(e),
    };
    if let Err(e) = validate(&req) {
        return err_response(e);
    }
    ErrorRegistry::global().report(build_event(&req, &ctx.user_id));
    Json(json!({ "ok": true })).into_response()
}

/// Rejects a report with an empty/whitespace `message_id` or `assistant_message`.
fn validate(req: &ReportReq) -> Result<(), RuntimeError> {
    if req.message_id.trim().is_empty() {
        return Err(RuntimeError::InvalidPayload {
            name: "assistant.report".into(),
            detail: "`message_id` is required and must not be empty".into(),
        });
    }
    if req.assistant_message.trim().is_empty() {
        return Err(RuntimeError::InvalidPayload {
            name: "assistant.report".into(),
            detail: "`assistant_message` is required and must not be empty".into(),
        });
    }
    Ok(())
}

/// Builds the registry event for a content report. See the module doc for why the `message`
/// embeds the `message_id` and why the severity is `unexpected`.
fn build_event(req: &ReportReq, reported_by: &str) -> ErrorEvent {
    let snippet = truncate_chars(&req.assistant_message, SNIPPET_MAX_CHARS);
    let message = format!("AI content reported ({}): {}", req.message_id, snippet);
    ErrorEvent::new(
        source::FRONTEND,
        "assistant_content_report",
        message,
        severity::UNEXPECTED,
    )
    .with_context(json!({
        "kind": "assistant_content_report",
        "message_id": req.message_id,
        "reason": req
            .reason
            .as_deref()
            .map(|s| truncate_chars(s, REASON_MAX_CHARS)),
        "comment": req
            .comment
            .as_deref()
            .map(|s| truncate_chars(s, COMMENT_MAX_CHARS)),
        "user_message": req
            .user_message
            .as_deref()
            .map(|s| truncate_chars(s, USER_MESSAGE_MAX_CHARS)),
        "assistant_message": truncate_chars(&req.assistant_message, ASSISTANT_MESSAGE_MAX_CHARS),
        "reported_by": reported_by,
    }))
}

/// First `max` **chars** of `s` — never slices mid-UTF-8.
fn truncate_chars(s: &str, max: usize) -> &str {
    match s.char_indices().nth(max) {
        Some((byte_idx, _)) => &s[..byte_idx],
        None => s,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn req(message_id: &str, assistant_message: &str) -> ReportReq {
        ReportReq {
            message_id: message_id.to_string(),
            assistant_message: assistant_message.to_string(),
            user_message: Some("what happened?".to_string()),
            comment: Some("this is offensive".to_string()),
            reason: Some("offensive".to_string()),
        }
    }

    #[test]
    fn event_has_stable_code_source_and_severity() {
        let event = build_event(&req("m-1", "bad answer"), "u1");
        assert_eq!(event.error_code, "assistant_content_report");
        assert_eq!(event.source, source::FRONTEND);
        assert_eq!(event.severity, severity::UNEXPECTED);
    }

    #[test]
    fn message_embeds_the_message_id() {
        let event = build_event(&req("m-unique-42", "bad answer"), "u1");
        assert!(
            event.message.contains("m-unique-42"),
            "message must embed the message_id (dedup key): {}",
            event.message
        );
    }

    #[test]
    fn distinct_message_ids_produce_distinct_messages() {
        // The registry dedups on `source|module_id|error_code|message`: if two reports about two
        // different assistant messages shared one event message, the second would be swallowed.
        let a = build_event(&req("m-1", "same text"), "u1");
        let b = build_event(&req("m-2", "same text"), "u1");
        assert_ne!(a.message, b.message);
    }

    #[test]
    fn context_carries_report_fields_and_reporter() {
        let event = build_event(&req("m-1", "bad answer"), "u-77");
        let ctx = &event.context;
        assert_eq!(ctx["kind"], "assistant_content_report");
        assert_eq!(ctx["message_id"], "m-1");
        assert_eq!(ctx["assistant_message"], "bad answer");
        assert_eq!(ctx["user_message"], "what happened?");
        assert_eq!(ctx["comment"], "this is offensive");
        assert_eq!(ctx["reason"], "offensive");
        assert_eq!(ctx["reported_by"], "u-77");
    }

    #[test]
    fn long_fields_are_truncated_in_context() {
        let mut r = req("m-1", &"a".repeat(5000));
        r.user_message = Some("u".repeat(5000));
        r.comment = Some("c".repeat(2000));
        r.reason = Some("r".repeat(500));
        let ctx = build_event(&r, "u1").context;
        assert_eq!(
            ctx["assistant_message"].as_str().unwrap().chars().count(),
            ASSISTANT_MESSAGE_MAX_CHARS
        );
        assert_eq!(
            ctx["user_message"].as_str().unwrap().chars().count(),
            USER_MESSAGE_MAX_CHARS
        );
        assert_eq!(
            ctx["comment"].as_str().unwrap().chars().count(),
            COMMENT_MAX_CHARS
        );
        assert_eq!(
            ctx["reason"].as_str().unwrap().chars().count(),
            REASON_MAX_CHARS
        );
    }

    #[test]
    fn truncate_chars_is_multibyte_safe() {
        // Each char below is multi-byte in UTF-8; a byte-index slice at 3 would panic.
        let s = "ñáéíóú€漢字";
        assert_eq!(truncate_chars(s, 3), "ñáé");
        assert_eq!(truncate_chars(s, 0), "");
        // Emoji with a multi-byte width of 4.
        assert_eq!(truncate_chars("💚💚💚", 2), "💚💚");
    }

    #[test]
    fn truncate_chars_returns_short_strings_untouched() {
        assert_eq!(truncate_chars("short", 100), "short");
        assert_eq!(truncate_chars("", 5), "");
        assert_eq!(truncate_chars("exact", 5), "exact");
    }

    #[test]
    fn empty_assistant_message_is_rejected() {
        assert!(validate(&req("m-1", "")).is_err());
        assert!(validate(&req("m-1", "   ")).is_err());
    }

    #[test]
    fn empty_message_id_is_rejected() {
        assert!(validate(&req("", "bad answer")).is_err());
        assert!(validate(&req("   ", "bad answer")).is_err());
    }

    #[test]
    fn valid_request_passes_validation() {
        assert!(validate(&req("m-1", "bad answer")).is_ok());
    }
}
