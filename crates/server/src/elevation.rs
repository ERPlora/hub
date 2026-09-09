//! `POST /api/elevation/approve` — the door the manager's PIN crosses, once (hub#361).
//!
//! Rule 2 of the design: **the PIN is verified in the runtime, never by the client.** So this
//! module is deliberately thin — it routes to the org's runtime, authenticates the cashier who was
//! refused, applies the brute-force guard and hands everything else to
//! [`Runtime::approve_elevation`], which owns every decision. Nothing here decides who may
//! approve what.
//!
//! What it does own is the **guard on the digits**. A PIN is four numbers typed in front of
//! customers — 10,000 combinations — and this hub answers on the public internet: without a limit
//! on the attempts, approval is decorative. It shares the pinpad's [`LoginThrottle`] on purpose,
//! keyed by the approver's name: it is the same credential, so a lock earned at one door has to
//! hold at the other. Only a **wrong-PIN** refusal counts towards it ([`is_bad_pin`]) — tapping
//! the wrong person in the dialog is a mistake anybody makes, and locking their account for it
//! would teach the shop to stop using the dialog and share a password instead.
//!
//! [`Runtime::approve_elevation`]: erplora_runtime::Runtime::approve_elevation
//! [`LoginThrottle`]: crate::login_throttle::LoginThrottle
use axum::extract::rejection::JsonRejection;
use axum::extract::State;
use axum::http::{HeaderMap, StatusCode};
use axum::response::{IntoResponse, Response};
use axum::Json;
use erplora_db::Params;
use erplora_runtime::elevation::{ApproverCredential, ElevationRequest};
use erplora_runtime::RuntimeError;
use serde::Deserialize;
use serde_json::json;

use crate::state::AppState;
use crate::{auth, err_response, invalid_body, tenant_rejected, unauthorized};

/// The stable code the runtime uses for «those digits do not approve this» — the only refusal that
/// is about the PIN, and therefore the only one that spends an attempt.
const BAD_PIN_CODE: &str = "hub.elevation.rejected";

#[derive(Deserialize)]
pub struct ApproveReq {
    /// The approver's `hub_user.name` — the pinpad resolves people by name, and so does this.
    /// Empty when the approval arrives as a **badge**, which resolves the person on its own.
    #[serde(default)]
    approver: String,
    #[serde(default)]
    pin: String,
    /// The badge swiped in the dialog (hub#658). Present INSTEAD of `approver` + `pin`, never as
    /// well: two credentials in one request is a caller that does not know who is standing there,
    /// and picking one for them is how a screen ends up approving with the wrong identity.
    #[serde(default)]
    badge: String,
    /// The action being approved. Both travel so the runtime can bind the approval to them; it
    /// re-reads the command's permission from the registry rather than trusting anything here.
    command: String,
    #[serde(default)]
    payload: Params,
}

impl ApproveReq {
    /// The key the brute-force guard counts against.
    ///
    /// For a PIN it is the approver's NAME, unchanged since hub#361 — the same key the login
    /// pinpad uses, so a lock earned at one door holds at the other. For a badge there is no name
    /// to type, so it is the badge itself: the guard has to bound the attempts against the CARD
    /// being tried, and a shared key would let anybody lock out a colleague by swiping rubbish.
    fn throttle_key(&self) -> String {
        if self.badge.trim().is_empty() {
            self.approver.clone()
        } else {
            format!("badge:{}", self.badge.trim())
        }
    }

    /// What the approver presented. A badge wins when both travel: it is the more specific claim,
    /// and it cannot be typed by mistake into a dialog that is showing a pinpad.
    fn credential(&self) -> ApproverCredential<'_> {
        if self.badge.trim().is_empty() {
            ApproverCredential::Pin {
                name: &self.approver,
                pin: &self.pin,
            }
        } else {
            ApproverCredential::Badge {
                badge: self.badge.trim(),
            }
        }
    }
}

/// `POST /api/elevation/approve` → `{ok, data:{token, permission, approved_by, approver_name,
/// expires_in_seconds}}`. The `token` is presented back on **one** retry in `X-Elevation-Token`.
pub async fn approve(
    State(st): State<AppState>,
    headers: HeaderMap,
    body: Result<Json<ApproveReq>, JsonRejection>,
) -> Response {
    // The extractor's refusal is caught rather than left to axum, which answers it as a line of
    // English prose (hub#1691). This door is on the module surface — `@erplora/module-sdk` calls
    // it through `unwrap(env)`, which reads `ok` or throws `ErploraError('error', 'unknown
    // error')` — so a body outside the envelope does not degrade here, it goes blank.
    let Json(req) = match body {
        Ok(json) => json,
        Err(rejection) => return invalid_body(rejection),
    };
    let arc = match st.runtime_for(&auth::hub_id(&headers, &st.hub_id())).await {
        Ok(rt) => rt,
        Err(e) => return tenant_rejected(e),
    };
    let rt = arc.read().await;
    // The CASHIER is authenticated as on any other call: the approval is granted to whoever was
    // refused, and they are identified the same way they always are. The approver proves
    // themselves with the PIN alone — they are not opening a session, they are authorising one act.
    let requester = match auth::authenticate(&headers, &st.config, &rt).await {
        Ok(c) => c,
        Err(e) => return unauthorized(e),
    };

    // Checked BEFORE verifying, like the pinpad (hub#329): a locked identity must stop leaking the
    // right/wrong signal that is exactly what an attacker is fishing for.
    let throttle_key = req.throttle_key();
    if let Some(retry_after_secs) = st.login_throttle.locked_for(&throttle_key) {
        return (
            StatusCode::TOO_MANY_REQUESTS,
            Json(json!({
                "ok": false,
                "error": {
                    "code": "too_many_attempts",
                    "message": "too many failed attempts: wait a few minutes before approving again",
                    "retry_after_secs": retry_after_secs
                }
            })),
        )
            .into_response();
    }

    match rt
        .approve_elevation(
            &requester,
            ElevationRequest {
                credential: req.credential(),
                command: &req.command,
                payload: &req.payload,
            },
        )
        .await
    {
        Ok(approval) => {
            st.login_throttle.record_success(&throttle_key);
            Json(json!({
                "ok": true,
                "data": {
                    "token": approval.token,
                    "permission": approval.permission,
                    "approved_by": approval.approved_by,
                    "approver_name": approval.approver_name,
                    "expires_in_seconds": approval.expires_in_seconds,
                }
            }))
            .into_response()
        }
        Err(e) => {
            if is_bad_pin(&e) {
                st.login_throttle.record_failure(&throttle_key);
            }
            err_response(e)
        }
    }
}

/// Is this refusal about the **digits**? Only then does it spend an attempt.
fn is_bad_pin(e: &RuntimeError) -> bool {
    matches!(e, RuntimeError::Domain { code, .. } if code == BAD_PIN_CODE)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn only_a_wrong_pin_spends_an_attempt() {
        assert!(is_bad_pin(&RuntimeError::Domain {
            code: BAD_PIN_CODE.into(),
            message: String::new()
        }));
    }

    #[test]
    fn every_other_refusal_of_this_door_leaves_the_counter_alone() {
        // These are the ways an approval fails WITHOUT the digits being wrong: the wrong person
        // was tapped, the action needs no approval, it can never be approved, or the caller is an
        // integration. Counting them would lock out honest people for using the dialog.
        for code in [
            "hub.elevation.approver_cannot",
            "hub.elevation.not_required",
            "hub.elevation.not_elevable",
            "hub.elevation.machine_principal",
            // …and a namespace that merely looks like it, from a module's own domain error.
            "till.rejected",
        ] {
            assert!(
                !is_bad_pin(&RuntimeError::Domain {
                    code: code.into(),
                    message: String::new()
                }),
                "`{code}` must not spend an attempt"
            );
        }
        assert!(!is_bad_pin(&RuntimeError::InternalCommand(
            "till._settle".into()
        )));
        assert!(!is_bad_pin(&RuntimeError::CommandNotFound("nope".into())));
        assert!(!is_bad_pin(&RuntimeError::PermissionDenied("x".into())));
    }
}
