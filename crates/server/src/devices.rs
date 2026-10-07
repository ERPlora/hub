//! HTTP door of **the devices of a business** (hub#455): `GET /api/devices`,
//! `DELETE /api/devices/:device_id`, `PUT /api/devices/:device_id` (hub#494) and
//! `POST /api/devices/prune` (hub#2215).
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

/// The longest name the list column is meant to carry. Not a database limit — the column is TEXT —
/// but the one this door enforces: the name exists to be recognised **at a glance** among three
/// rows, and a paragraph pushed into it would shove the row the owner came for off the screen.
const MAX_DEVICE_NAME: usize = 60;

/// The name as it will be stored, or `None` when it is too long to be one.
///
/// Trimmed in **one** place, so what is stored, what is echoed back and what the list shows are the
/// same string. Blank is allowed and means "take the name back": unlike a blank *id* — which names
/// no device and is a malformed request — it is a real gesture, and it returns the row to unnamed.
///
/// Counted in **characters, not bytes**: "Recepción" is shorter than its UTF-8 length, and a limit
/// that shrank for accented names would be a limit that punishes writing Spanish properly.
fn clean_name(name: &str) -> Option<&str> {
    let name = name.trim();
    (name.chars().count() <= MAX_DEVICE_NAME).then_some(name)
}

/// The name a device is born with the first time this hub sees it (hub#494): the **platform** it
/// announced, never the person who happened to sign in.
///
/// Why the User-Agent and not the id: ADR-0257 made `device_id` 128 opaque bits on purpose, so it
/// says nothing an owner could recognise. Why not the person's name: that is `label`, it changes
/// shift to shift, and a list of three tablets all called "Marta" is the bug this issue exists for.
///
/// What comes out are **proper nouns** ("Chrome · Android", "Safari · iPad") — nothing to translate,
/// which is what keeps a stored default from freezing one language into the database. The date is
/// deliberately NOT part of it: the row already carries `trusted_at`, and the screen can render it
/// in the reader's locale instead of in whichever one the server happened to have.
///
/// An unreadable agent yields `""` — the absence of a name, which the screen turns into "unnamed"
/// and invites the owner to fix. Inventing "Device 1" would be the same lie in a new costume.
pub(crate) fn default_device_name(user_agent: &str) -> String {
    // Order matters: Edge and Opera announce Chrome, and Chrome announces Safari. Most specific
    // first, so the browser reported is the one the owner would name.
    let browser = [
        ("Edg/", "Edge"),
        ("OPR/", "Opera"),
        ("Chrome/", "Chrome"),
        ("Firefox/", "Firefox"),
        ("Safari/", "Safari"),
    ]
    .into_iter()
    .find(|(token, _)| user_agent.contains(token))
    .map(|(_, name)| name);
    // `iPad`/`iPhone` before `Mac OS X`, which they also carry; `Android` before `Linux`, same.
    let platform = [
        ("iPad", "iPad"),
        ("iPhone", "iPhone"),
        ("Android", "Android"),
        ("Windows", "Windows"),
        ("CrOS", "ChromeOS"),
        ("Macintosh", "Mac"),
        ("Mac OS X", "Mac"),
        ("Linux", "Linux"),
    ]
    .into_iter()
    .find(|(token, _)| user_agent.contains(token))
    .map(|(_, name)| name);
    // Half an answer still tells the owner which of the three tablets they are looking at.
    match (browser, platform) {
        (Some(browser), Some(platform)) => format!("{browser} · {platform}"),
        (Some(only), None) | (None, Some(only)) => only.to_string(),
        (None, None) => String::new(),
    }
}

/// The `User-Agent` of a request, or `""` when it declared none.
pub(crate) fn user_agent_of(headers: &HeaderMap) -> &str {
    headers
        .get(axum::http::header::USER_AGENT)
        .and_then(|value| value.to_str().ok())
        .unwrap_or_default()
}

/// Refusal of the admin gate with the stable code every other door of this hub sends (hub#1702,
/// the recipe of hub#1700): `401 unauthorized` when there is no usable session, `403 forbidden` when
/// the session is fine and the role is not. Until then this door flattened both into
/// `401 {"error": "<prose>"}` and Settings → Devices could only say «check the connection».
fn unauthorized(e: auth::AuthError) -> Response {
    crate::auth_rejected(e)
}

async fn runtime(st: &AppState) -> Result<crate::state::SharedRuntime, Response> {
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
    let rt = arc.read().await;
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
    let rt = arc.read().await;
    if let Err(e) = auth::require_admin_session(&headers, &st.config, &rt).await {
        return unauthorized(e);
    }
    let target = device_id.trim();
    // Read BEFORE the write: afterwards the id is gone from the list and "was it the one I am
    // holding" could no longer be answered.
    let was_current = !target.is_empty() && target == device_id_of(&headers);
    match rt.revoke_device(target).await {
        Ok(revocation) => {
            // hub#2599: after the rows are gone, so a ticket minted from now on cannot see them
            // alive. By session, never by person: the device is cut, not who used it.
            end_live_channels(&st, &revocation.ended_sessions);
            Json(json!({
            "ok": true,
            "data": {
                "device_id": target,
                "was_known": revocation.was_known,
                "sessions_closed": revocation.sessions_closed,
                "was_current": was_current,
            },
            }))
            .into_response()
        }
        // A blank segment (`/api/devices/%20`) is a mis-built URL, not an instruction: the runtime
        // refuses it (422) instead of running a `DELETE` keyed on nothing.
        Err(e) => crate::err_response(e),
    }
}

/// Closes the live channels (`/ws`, `/api/events`) of the sessions a device door just deleted,
/// with `events.credential_ended` (hub#2599) — the same cut signing out does (hub#2522).
fn end_live_channels(st: &AppState, ended_sessions: &[String]) {
    for token in ended_sessions {
        st.stream_limiter
            .cut(&crate::event_stream::session_tag(token));
    }
}

/// POST /api/devices/prune — forget every device nobody has used for thirty days (hub#2215).
///
/// Every browser that loses its storage comes back as a new device, and the row of the old one
/// stayed in the list for good. This is the "remove the ones you no longer use" of the account
/// screens people know (Google, Apple, Microsoft): one gesture, with the rule decided by the
/// runtime (`devices::STALE_AFTER_DAYS`, `stale` on each row of the list) so the count the screen
/// shows is the count that goes.
///
/// Auth = **admin session**, like the revocation it repeats. The device asking (`X-Device-Id`) is
/// **kept** whatever its dates say — here the header decides something, but only in the direction
/// of taking LESS: naming a device can spare it, never add one. No body: the window is not the
/// caller's to choose, because a shorter one is how the counter till that has no session at night
/// would go.
pub async fn prune_devices(State(st): State<AppState>, headers: HeaderMap) -> Response {
    let arc = match runtime(&st).await {
        Ok(arc) => arc,
        Err(response) => return response,
    };
    let rt = arc.read().await;
    if let Err(e) = auth::require_admin_session(&headers, &st.config, &rt).await {
        return unauthorized(e);
    }
    match rt.prune_stale_devices(device_id_of(&headers)).await {
        Ok(pruned) => {
            end_live_channels(&st, &pruned.ended_sessions);
            Json(json!({ "ok": true, "data": { "removed": pruned.removed } })).into_response()
        }
        Err(e) => crate::err_response(e),
    }
}

/// Body of `PUT /api/devices/:device_id`.
#[derive(serde::Deserialize)]
pub struct RenameDeviceReq {
    /// What the business calls this device. Blank takes the name back.
    #[serde(default)]
    pub name: String,
}

/// PUT /api/devices/:device_id — give the device the name the **business** chose (hub#494).
///
/// Auth = **admin session**, the same gate as the read and the revocation (ADR-0248). It has to be:
/// the name is what an owner will decide from when they point at the tablet to cut off, so if
/// whoever holds a device could write it, it would be worth exactly as much as `label` — nothing.
///
/// **A door of its own, not a flag on the revocation.** Renaming is housekeeping and revoking takes
/// a till down; one is undone by typing again and the other signs a shift out. Sharing an endpoint
/// would mean one mis-sent field turns "fix a typo" into "disconnect the counter".
///
/// A device this business does not know is a `404`: rows exist because a login trusted a device,
/// never because somebody typed an id — and a row invented here would be a *trusted* one.
pub async fn rename_device(
    State(st): State<AppState>,
    headers: HeaderMap,
    Path(device_id): Path<String>,
    Json(req): Json<RenameDeviceReq>,
) -> Response {
    let arc = match runtime(&st).await {
        Ok(arc) => arc,
        Err(response) => return response,
    };
    let rt = arc.read().await;
    if let Err(e) = auth::require_admin_session(&headers, &st.config, &rt).await {
        return unauthorized(e);
    }
    let Some(name) = clean_name(&req.name) else {
        return (
            StatusCode::UNPROCESSABLE_ENTITY,
            Json(json!({
                "ok": false,
                "error": format!("the device name is at most {MAX_DEVICE_NAME} characters"),
                "code": "device_name_too_long",
            })),
        )
            .into_response();
    };
    match rt.rename_device(device_id.trim(), name).await {
        Ok(renamed) if renamed.was_known => Json(json!({
            "ok": true,
            "data": { "device_id": device_id.trim(), "name": renamed.name },
        }))
        .into_response(),
        Ok(_) => (
            StatusCode::NOT_FOUND,
            Json(json!({
                "ok": false,
                "error": "this business has no such device",
                "code": "device_not_found",
            })),
        )
            .into_response(),
        // A blank segment (`/api/devices/%20`) names no device: the runtime refuses it (422).
        Err(e) => crate::err_response(e),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::http::HeaderValue;

    #[test]
    fn a_device_is_born_named_after_what_it_announced_never_after_the_person() {
        // The name a device is born with (hub#494). `label` — the person — changes shift to shift
        // and is chosen by the client; the platform is the one thing in the request that says
        // something stable about the *device*. ADR-0257 rules out the id: 128 opaque bits.
        assert_eq!(
            default_device_name(
                "Mozilla/5.0 (Linux; Android 14; SM-X200) AppleWebKit/537.36 (KHTML, like Gecko) \
                 Chrome/126.0.0.0 Safari/537.36"
            ),
            "Chrome · Android"
        );
        assert_eq!(
            default_device_name(
                "Mozilla/5.0 (iPad; CPU OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like \
                 Gecko) Version/17.5 Safari/605.1.15"
            ),
            "Safari · iPad"
        );
        assert_eq!(
            default_device_name(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) \
                 Chrome/126.0.0.0 Safari/537.36 Edg/126.0.0.0"
            ),
            "Edge · Windows",
            "Edge announces Chrome AND Safari: the most specific token wins"
        );
        assert_eq!(
            default_device_name(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like \
                 Gecko) Version/17.5 Safari/605.1.15"
            ),
            "Safari · Mac"
        );
    }

    #[test]
    fn a_device_that_announced_nothing_readable_is_left_unnamed() {
        // Empty is not a poor name, it is the absence of one — which is what the screen turns into
        // "unnamed" and what an owner is invited to fix. Making something up ("Device 1") would be
        // the same lie as the person's name it replaces.
        for silent in ["", "   ", "curl/8.6.0", "PostmanRuntime/7.39.0"] {
            assert_eq!(
                default_device_name(silent),
                "",
                "{silent:?} says nothing about the device"
            );
        }
    }

    #[test]
    fn half_an_answer_is_still_worth_more_than_none() {
        // A platform with no recognisable browser (or the other way round) still tells the owner
        // which of the three tablets they are looking at, so it is not thrown away.
        assert_eq!(
            default_device_name("Mozilla/5.0 (Linux; Android 14)"),
            "Android"
        );
        assert_eq!(default_device_name("Firefox/128.0"), "Firefox");
    }

    #[test]
    fn a_name_is_trimmed_and_a_wall_of_text_is_refused() {
        // Same rule as every other door: trimmed in ONE place, so what is stored, what is echoed
        // back and what the list shows are the same string.
        assert_eq!(clean_name("  Barra  "), Some("Barra"));
        // Blank means "take the name back" — the row returns to unnamed, which is a real gesture
        // and not a malformed request (a blank *id*, by contrast, names no device at all).
        assert_eq!(clean_name("   "), Some(""));
        // A paragraph in the column that exists to be read at a glance would push the row the
        // owner is looking for off the screen.
        assert_eq!(clean_name(&"B".repeat(MAX_DEVICE_NAME + 1)), None);
        assert!(
            clean_name(&"B".repeat(MAX_DEVICE_NAME)).is_some(),
            "the limit itself is allowed"
        );
        // Counted in characters: an accented name must not be refused sooner than a plain one.
        assert!(
            clean_name(&"á".repeat(MAX_DEVICE_NAME)).is_some(),
            "60 accented characters fit"
        );
    }

    #[test]
    fn the_current_flag_needs_the_caller_to_have_named_a_device() {
        // The one case worth pinning: a client that names none must not match the row whose id
        // happens to be empty-ish, and must not match "the first one". No header = nothing current.
        assert_eq!(device_id_of(&HeaderMap::new()), "");

        let mut named = HeaderMap::new();
        named.insert("x-device-id", HeaderValue::from_static(" laptop-1 "));
        assert_eq!(
            device_id_of(&named),
            "laptop-1",
            "trimmed, like every other door"
        );
    }
}
