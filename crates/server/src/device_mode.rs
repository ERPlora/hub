//! HTTP door of the **device mode** (plan step 2b, hub#357): `GET`/`PUT /api/device/mode`.
//!
//! `shared` is the till at the counter, `personal` is somebody's own laptop, and the difference is
//! how much identity friction the device asks for (the conditional pinpad of hub#358 hangs from
//! it). The security of the whole thing is decided by these two doors, so they are deliberately
//! asymmetric:
//!
//!  - **`GET` takes no session.** It has to answer the *login screen*, which runs before anybody
//!    signed in. It answers only for the `X-Device-Id` presented and an unknown one gets `shared`
//!    — the strict mode — so there is nothing to gain by enumerating it.
//!  - **`PUT` takes an ADMIN session**, the same gate as `/api/settings`, the API keys and the
//!    role catalogue. Deciding that a terminal stops asking who is standing at it is
//!    administration of the business, not a preference of whoever is holding the device.
//!
//! **The client never declares its own mode.** `X-Device-Id` is an identifier the client sends in
//! plain text, not a credential: here it can only ever NAME a device (which one is being described,
//! or which one is asking), and naming is not claiming. The login endpoints take no mode at all,
//! and the runtime refuses to write one for a device that never proved itself online, so a made-up
//! id buys nothing (`erplora_runtime::device_mode`).
use axum::extract::State;
use axum::http::{HeaderMap, StatusCode};
use axum::response::{IntoResponse, Response};
use axum::Json;
use erplora_runtime::device_mode::DeviceMode;
use erplora_runtime::pin_policy::PinPolicy;
use serde_json::json;

use crate::auth;
use crate::AppState;

/// Header carrying the device identity of the caller (ADR-0154; the web sends it in `loginHeaders`).
const DEVICE_ID_HEADER: &str = "x-device-id";

/// The device the request comes FROM, or `""` when the client identifies none.
///
/// Trimmed on purpose: a header of blanks is a client that did not identify itself, and it must
/// land on the same branch as no header at all (the strict mode), never on a lookup for `"  "`.
fn device_id_of(headers: &HeaderMap) -> &str {
    headers
        .get(DEVICE_ID_HEADER)
        .and_then(|v| v.to_str().ok())
        .unwrap_or_default()
        .trim()
}

/// The answer of the read door: what this device asks of the person in front of it.
///
/// It carries **both** controls (hub#358 + hub#359) because both are needed to decide whether the
/// pinpad is painted, and the login screen has one chance to ask: splitting them across two
/// requests would mean a window in which the screen has half an answer and has to guess the rest.
/// The write doors stay separate — the mode is of the device, the policy is of the hub.
fn ok(mode: DeviceMode, policy: PinPolicy) -> Response {
    Json(json!({
        "ok": true,
        "data": { "mode": mode.as_str(), "pin_policy": policy.as_str() },
    }))
    .into_response()
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

/// GET /api/device/mode — what kind of device is asking (`{ok, data:{mode}}`).
///
/// **No session**: this is what the login screen reads to decide whether to show the pinpad, and
/// at that point there is no session to require. It says nothing about the hub beyond the mode of
/// the id presented, and an id the hub never met is answered `shared`.
pub async fn get_device_mode(State(st): State<AppState>, headers: HeaderMap) -> Response {
    let arc = match runtime(&st).await {
        Ok(arc) => arc,
        Err(response) => return response,
    };
    let rt = arc.lock().await;
    let mode = match rt.device_mode(device_id_of(&headers)).await {
        Ok(mode) => mode,
        Err(e) => return crate::err_response(e),
    };
    // The dial the business chose (hub#359). It travels on THIS door, and not on `/api/settings`,
    // for one reason: the screen that needs it has no session. Nothing is given away by saying it
    // — the login screen would show the same thing by simply not painting a pinpad — and the value
    // that matters is only ever *reported* here; writing it is the admin door of the settings.
    match rt.pin_policy().await {
        Ok(policy) => ok(mode, policy),
        Err(e) => crate::err_response(e),
    }
}

/// Body of `PUT /api/device/mode`.
#[derive(serde::Deserialize)]
pub struct SetDeviceMode {
    /// Which device is being described. Optional: without it, the device making the request
    /// (`X-Device-Id`) — the realistic gesture is «this device is mine», from the device itself.
    #[serde(default)]
    pub device_id: Option<String>,
    /// `shared` | `personal`. Anything else is refused (422), never guessed.
    pub mode: String,
}

/// PUT /api/device/mode — record what kind of device this is. Returns the mode now in force.
///
/// Auth = **admin session**. The header can only NAME the device; what authorises the write is the
/// session. The runtime refuses (409 `hub.device.unknown_device`) a device that never did an
/// online login: this door records a decision about a known device, it does not enrol one.
pub async fn put_device_mode(
    State(st): State<AppState>,
    headers: HeaderMap,
    Json(input): Json<SetDeviceMode>,
) -> Response {
    let arc = match runtime(&st).await {
        Ok(arc) => arc,
        Err(response) => return response,
    };
    let rt = arc.lock().await;
    let admin = match auth::require_admin_session(&headers, &st.config, &rt).await {
        Ok(user) => user,
        Err(e) => return unauthorized(e),
    };
    let mode = match DeviceMode::parse(&input.mode) {
        Ok(mode) => mode,
        Err(e) => return crate::err_response(e),
    };
    let target = input
        .device_id
        .as_deref()
        .map(str::trim)
        .filter(|id| !id.is_empty())
        .unwrap_or_else(|| device_id_of(&headers));
    if let Err(e) = rt.set_device_mode(target, mode, &admin.id).await {
        return crate::err_response(e);
    }
    // The answer describes the device AFTER the write, dial included — this door does not touch the
    // dial, so it is read back rather than assumed.
    match rt.pin_policy().await {
        Ok(policy) => ok(mode, policy),
        Err(e) => crate::err_response(e),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::http::HeaderValue;

    #[test]
    fn a_client_that_identifies_no_device_is_the_same_as_no_header() {
        // All three mean "I am not telling you which device I am", and the runtime answers the
        // strict mode for `""`. A header of blanks must not become a lookup for `"  "`.
        assert_eq!(device_id_of(&HeaderMap::new()), "");

        let mut blank = HeaderMap::new();
        blank.insert(DEVICE_ID_HEADER, HeaderValue::from_static("   "));
        assert_eq!(device_id_of(&blank), "");

        let mut real = HeaderMap::new();
        real.insert(DEVICE_ID_HEADER, HeaderValue::from_static("  laptop-1 "));
        assert_eq!(device_id_of(&real), "laptop-1");
    }
}
