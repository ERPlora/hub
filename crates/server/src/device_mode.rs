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
///
/// Shared with [`crate::devices`] (hub#455) rather than copied: two definitions of "which device is
/// asking" that could drift is exactly how one door ends up trimming and the other one not.
pub(crate) fn device_id_of(headers: &HeaderMap) -> &str {
    headers
        .get(DEVICE_ID_HEADER)
        .and_then(|v| v.to_str().ok())
        .unwrap_or_default()
        .trim()
}

/// The demo adoption rule (hub#630), in ONE place for the two doors that must agree on it.
///
/// On an ephemeral demo (`HUB_DEMO`, ADR-0197) the FIRST device to present itself is adopted —
/// a visitor has no account, and an online login is the only other thing that earns a device its
/// trust. Two doors apply this rule and they must never drift: `auth_pin` (crate root), which
/// performs the adoption when a PIN is submitted, and [`get_device_mode`], which tells the login
/// screen whether the pinpad it would paint is usable (hub#514).
///
/// The second caller exists because the two rules DID drift (2026-08-12): hub#514 made the pinpad
/// hang from this door's `trusted` bit, which answered from the raw trust rows — so on a virgin
/// demo the pinpad was never offered, and the adoption that fires on submit became unreachable.
/// Every `/demo` visitor saw the account door instead of the keypad.
///
/// `false` for a client that names no device (adoption adopts a device, it does not invent one)
/// and on any hub that is not a demo — leaking this answer to a normal hub would paint a pinpad
/// for whoever knocks first on a public URL.
pub(crate) async fn demo_would_adopt(
    demo: bool,
    rt: &erplora_runtime::Runtime,
    device_id: &str,
) -> erplora_runtime::Result<bool> {
    if !demo || device_id.is_empty() {
        return Ok(false);
    }
    Ok(rt.list_devices().await?.is_empty())
}

/// The answer of the read door: what this device asks of the person in front of it.
///
/// It carries **all three** controls (hub#358 + hub#359 + hub#514) because all three are needed to
/// decide whether the pinpad is painted, and the login screen has one chance to ask: splitting them
/// across two requests would mean a window in which the screen has half an answer and has to guess
/// the rest. The write doors stay separate — the mode is of the device, the policy is of the hub.
///
/// `trusted` (hub#514) says whether **this device** did an online login here before — i.e. whether
/// a PIN is even usable on it. Before #514 the client sourced this bit from `localStorage`, which
/// desynchronised from the server on revoke and on first use of a new device. Now the server — the
/// authority — says it, on the same door that already answers without session.
fn ok(mode: DeviceMode, policy: PinPolicy, trusted: bool) -> Response {
    Json(json!({
        "ok": true,
        "data": { "mode": mode.as_str(), "pin_policy": policy.as_str(), "trusted": trusted },
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

async fn runtime(st: &AppState) -> Result<crate::state::SharedRuntime, Response> {
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
    let rt = arc.read().await;
    let device_id = device_id_of(&headers);
    let mode = match rt.device_mode(device_id).await {
        Ok(mode) => mode,
        Err(e) => return crate::err_response(e),
    };
    // hub#514: whether THIS device can use the PIN. The server is the authority — before, the
    // client guessed from localStorage and offered a pinpad that the runtime would then refuse.
    // `personal` mode already implies trust (the mode lives in the trust row), so this only
    // disambiguates `shared`; but asking unconditionally is cheaper than special-casing and the
    // answer is the same single bit the login screen needs.
    //
    // The question is "would a PIN from this device get in?", NOT "is there a trust row?" — on a
    // virgin demo the two differ: no row exists, yet the PIN door will adopt the first device
    // that submits (hub#630, [`demo_would_adopt`]). Answering from the raw row painted no pinpad
    // and made that adoption unreachable — the regression every `/demo` visitor hit (2026-08-12).
    let trusted = match rt.is_device_trusted(device_id).await {
        Ok(true) => true,
        Ok(false) => demo_would_adopt(st.config.demo, &rt, device_id)
            .await
            // Fail-closed: if the adoption question cannot be answered, the screen falls back to
            // the account door, which is stronger — never the other way.
            .unwrap_or(false),
        // Fail-closed: a device we cannot look up is not trusted.
        Err(_) => false,
    };
    // The dial the business chose (hub#359). It travels on THIS door, and not on `/api/settings`,
    // for one reason: the screen that needs it has no session. Nothing is given away by saying it
    // — the login screen would show the same thing by simply not painting a pinpad — and the value
    // that matters is only ever *reported* here; writing it is the admin door of the settings.
    match rt.pin_policy().await {
        Ok(policy) => ok(mode, policy, trusted),
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
    let rt = arc.read().await;
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
    // dial, so it is read back rather than assumed. `trusted` is read back too: PUT runs on a known
    // device with an admin session, so it is always trusted, but the answer is one shape.
    let trusted = rt.is_device_trusted(target).await.unwrap_or(false);
    match rt.pin_policy().await {
        Ok(policy) => ok(mode, policy, trusted),
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
