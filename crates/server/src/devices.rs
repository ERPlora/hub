//! HTTP door of **the devices of a business** (hub#455): `GET /api/devices` and
//! `DELETE /api/devices/:device_id`.
//!
//! The gesture it exists for is "somebody walked off with the tablet". `untrust_device` had been in
//! the runtime since hub#15 holding up half the security argument of hub#357/hub#358, and no route
//! and no screen could call it — so with hub#358 shipped, a lost device marked `personal` kept a
//! session alive for **thirty days** with no pinpad, and the only remedy was a database prompt.
//!
//! ## Auth: an ADMIN session, on BOTH doors
//!
//! The same gate as `/api/settings`, the API keys, the role catalogue and `PUT /api/device/mode` —
//! which is exactly the set of roles the core grants `hub.administer` to (ADR-0248, hub#435). No
//! new permission is minted here, and a module manifest cannot mint that one either
//! (`identity::permissions_for_role` refuses the `hub.` namespace).
//!
//! Note the **asymmetry with its neighbour**: `GET /api/device/mode` deliberately takes no session,
//! because it answers the login screen before one exists, and it says a single word about the one
//! id presented. This read is nothing like it — it enumerates every device of the business, with
//! when each was last used and how long its session still has — which is a shopping list for
//! whoever is holding a stolen one. hub#454 is the cautionary tale (ADR-0257):
//! `GET /api/hub/context` needed no session and published the value that was, at the time, every
//! browser's device id, and a trusted `personal` row hung off it.
//!
//! ## What the header can do here, and what it cannot
//!
//! `X-Device-Id` only ever **names** a device (ADR-0257): on the read it decides which row is
//! flagged `current` so the screen can warn "this is the one you are holding", and on the write it
//! decides nothing at all — what authorises the write is the session, and the device to revoke is
//! in the path.
use axum::extract::{Path, State};
use axum::http::{HeaderMap, StatusCode};
use axum::response::{IntoResponse, Response};
use axum::Json;
use serde_json::json;

use crate::auth;
use crate::device_mode::device_id_of;
use crate::AppState;

/// One row of the list: what the runtime knows about the device, plus whether it is the one asking.
///
/// `current` is **flattened alongside** the runtime's fields rather than nested, because the client
/// reads one shape: the runtime owns the facts about the device, the HTTP layer owns the only fact
/// that depends on who is calling.
#[derive(serde::Serialize)]
struct ListedDevice {
    #[serde(flatten)]
    device: erplora_runtime::devices::TrustedDevice,
    /// `true` when this is the device the request came from (`X-Device-Id`).
    current: bool,
}

fn unauthorized(e: auth::AuthError) -> Response {
    (
        StatusCode::UNAUTHORIZED,
        Json(json!({ "ok": false, "error": e.message() })),
    )
        .into_response()
}

async fn runtime(
    st: &AppState,
) -> Result<std::sync::Arc<tokio::sync::Mutex<erplora_runtime::Runtime>>, Response> {
    st.runtime_for(&st.hub_id())
        .await
        .map_err(crate::tenant_rejected)
}

/// GET /api/devices — every device this business has signed in on (`{ok, data:{devices}}`).
///
/// Auth = **admin session** (see the module docs for why this one is not public).
pub async fn list_devices(State(st): State<AppState>, headers: HeaderMap) -> Response {
    let arc = match runtime(&st).await {
        Ok(arc) => arc,
        Err(response) => return response,
    };
    let rt = arc.lock().await;
    if let Err(e) = auth::require_admin_session(&headers, &st.config, &rt).await {
        return unauthorized(e);
    }
    let devices = match rt.list_devices().await {
        Ok(devices) => devices,
        Err(e) => return crate::err_response(e),
    };
    let asking = device_id_of(&headers);
    let listed: Vec<ListedDevice> = devices
        .into_iter()
        .map(|device| ListedDevice {
            // A caller that names no device matches nothing: `asking` is `""` there, and an empty
            // id is never a device id, so the flag stays off instead of latching onto a row.
            current: !asking.is_empty() && device.device_id == asking,
            device,
        })
        .collect();
    Json(json!({ "ok": true, "data": { "devices": listed } })).into_response()
}

/// DELETE /api/devices/:device_id — cut that device off: close its open sessions and forget it.
///
/// Auth = **admin session**. Answers what it actually did (`was_known`, `sessions_closed`) plus
/// `was_current`, which is the administrator revoking the device in their own hands: allowed on
/// purpose — handing a tablet back or selling it is a real gesture, and refusing would leave the
/// one device an owner can definitely reach as the one they cannot clean — but the screen has to
/// know, so it can send them to the login instead of leaving them tapping a session that is gone.
///
/// Idempotent: revoking a device that is already off is a `200`, not a failure. Two administrators
/// reacting to the same lost tablet is the normal case.
pub async fn revoke_device(
    State(st): State<AppState>,
    headers: HeaderMap,
    Path(device_id): Path<String>,
) -> Response {
    let arc = match runtime(&st).await {
        Ok(arc) => arc,
        Err(response) => return response,
    };
    let rt = arc.lock().await;
    if let Err(e) = auth::require_admin_session(&headers, &st.config, &rt).await {
        return unauthorized(e);
    }
    let target = device_id.trim();
    // Read BEFORE the write: afterwards the id is gone from the list and "was it the one I am
    // holding" could no longer be answered.
    let was_current = !target.is_empty() && target == device_id_of(&headers);
    match rt.revoke_device(target).await {
        Ok(revocation) => Json(json!({
            "ok": true,
            "data": {
                "device_id": target,
                "was_known": revocation.was_known,
                "sessions_closed": revocation.sessions_closed,
                "was_current": was_current,
            },
        }))
        .into_response(),
        // A blank segment (`/api/devices/%20`) is a mis-built URL, not an instruction: the runtime
        // refuses it (422) instead of running a `DELETE` keyed on nothing.
        Err(e) => crate::err_response(e),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::http::HeaderValue;

    #[test]
    fn the_current_flag_needs_the_caller_to_have_named_a_device() {
        // The one case worth pinning: a client that names none must not match the row whose id
        // happens to be empty-ish, and must not match "the first one". No header = nothing current.
        assert_eq!(device_id_of(&HeaderMap::new()), "");

        let mut named = HeaderMap::new();
        named.insert("x-device-id", HeaderValue::from_static(" laptop-1 "));
        assert_eq!(device_id_of(&named), "laptop-1", "trimmed, like every other door");
    }
}
