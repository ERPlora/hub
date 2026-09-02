//! **Device mode** — `shared` (the counter till) vs `personal` (your own laptop), plan step 2b,
//! hub#357.
//!
//! One business has both at once — the till at the counter, where several people take turns, and
//! the laptop in the back office — and the SAME person uses both. So this cannot be a hub setting:
//! it belongs to the **device**, keyed by the identifier that already exists (`X-Device-Id`,
//! ADR-0154). What hangs from it: the pinpad only makes sense on a `shared` device (hub#358), and
//! "ask for a PIN: always / per shift / never" is the dial on top (hub#359).
//!
//! Not to be confused with `erplora_set_device_role` — that one is about **printers**
//! (`receipt`/`kitchen`/`bar`/`label`).
//!
//! ## Why it is stored the way it is
//!
//! `personal` is the **lax** mode: no pinpad, long session, "remember me". So the whole design has
//! to answer one question — who can obtain it — and the `device_id` is the worst possible basis
//! for that answer on its own: the client sends it in plain text and can send any string it likes.
//! It is an *identifier*, never a credential.
//!
//! Three properties keep that from mattering:
//!
//! 1. **The hub decides, the client never declares.** The mode is written only by
//!    [`set_mode`], which the HTTP layer puts behind an **admin session** — the same door as
//!    settings, API keys and the role catalogue. Nothing a client sends (login body, header,
//!    query string) declares a mode.
//! 2. **Unknown means strict.** [`mode`] answers [`DeviceMode::Shared`] for a device with no row,
//!    for an empty id and for a stored value it cannot parse. There is no path where an absence,
//!    a typo or a restored backup resolves to the lax mode: guessing high would be guessing in the
//!    direction that removes the pinpad.
//! 3. **`personal` cannot exist without device-trust.** The mode lives in the row of
//!    `hub_trusted_device` (§2.9, hub#330), so only a device that already proved identity with an
//!    online (cloud) login can carry one — and revoking the trust of a stolen laptop
//!    ([`crate::identity::untrust_device`] deletes the row) takes its lax mode with it, with no
//!    cascade to remember. That is the reason this lives in that table instead of a new one.
//!
//! Spoofing another device's id therefore buys an attacker nothing new: it is the same id the
//! device-trust gate already keys on, and it still leaves them facing a credential (PIN or
//! account) they do not have. What the mode changes is **friction**, never authorisation.
//!
//! Persistence: columns `mode`/`mode_set_at`/`mode_set_by` of `hub_trusted_device`, **system
//! migration v17** (v15 was reserved by the print queue, hub#341). `mode_set_by` audits who
//! decided, like `activated_by` in the role catalogue: lowering the identity friction of a terminal
//! is a decision that has to leave a trace.
//!
//! Since **v23** (hub#489) that row is keyed `(hub_id, device_id)`, so both doors below take the
//! hub as well: a mode is a decision **one business** made about **its** terminal. Before it, on a
//! database shared by several hubs, an administrator could lower the friction of a device next
//! door — property 1 above ("the hub decides") held for the *client* and not for the *tenant*.
//!
//! What HANGS off the mode (hub#358): the login screen only offers the pinpad on a `shared` device
//! ([`crate::device_mode::DeviceMode::session_ttl_secs`] is the other half) and the session it opens
//! expires within the shift instead of lasting a month.
use erplora_db::{DatabaseAdapter, Params};
use serde_json::json;

use crate::errors::{Result, RuntimeError};
use crate::hub_users::CORE_NAMESPACE;
use crate::registry::now_rfc3339;

/// How much identity friction a device asks for.
///
/// The default is [`Shared`](DeviceMode::Shared) **on purpose**: every unknown, unreadable or
/// absent value resolves to the strict mode.
///
/// **No serde derives, deliberately.** The wire and the column go through [`as_str`](Self::as_str)
/// and [`parse`](Self::parse), and that is the whole point: `parse` is the door that fails closed
/// with a stable rejection. A `Deserialize` impl would be a second, quieter entrance with a
/// different error shape for the exact value this hub must be strict about.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum DeviceMode {
    /// The counter till: several people take turns at it, so it asks who is standing there.
    #[default]
    Shared,
    /// Somebody's own device: email + password, long session, no pinpad.
    Personal,
}

impl DeviceMode {
    /// The wire/storage spelling. It is a **contract**: the web reads it and the column stores it.
    pub fn as_str(self) -> &'static str {
        match self {
            DeviceMode::Shared => "shared",
            DeviceMode::Personal => "personal",
        }
    }

    /// Parse a mode a caller asked for. The set is **closed**: anything else is refused instead of
    /// being guessed. Exact match, no trimming and no case folding — a `"Personal "` that resolved
    /// would mean the wire format has two spellings, and the one that slips through is always the
    /// lax one.
    ///
    /// An unknown spelling is a malformed request (`InvalidPayload` → 422), not a business
    /// conflict: the UI picks from two options, so only a caller that is not the UI can produce
    /// one. The rejection the **administrator** can legitimately hit is a different thing and has
    /// its own stable code — see [`set_mode`].
    pub fn parse(value: &str) -> Result<Self> {
        match value {
            "shared" => Ok(DeviceMode::Shared),
            "personal" => Ok(DeviceMode::Personal),
            other => Err(RuntimeError::InvalidPayload {
                name: MODE_PAYLOAD.into(),
                detail: format!(
                    "`{other}` is not a device mode: this hub knows `shared` (a device several \
                     people take turns at) and `personal` (somebody's own device)"
                ),
            }),
        }
    }

    /// How long a session opened on this kind of device lives, in seconds (hub#358).
    ///
    /// This is the other half of the mode, and the half that makes the first one worth anything: a
    /// pinpad in front of a session that lasts a month asks who is at the till once and then never
    /// again. `shared` therefore expires within the shift it opened; `personal` keeps the long
    /// session the hub has always had — that is what "remember me" means on your own device.
    ///
    /// hub#359 turns this into a setting ("ask for a PIN: always / per shift / never"); until then
    /// the pair is the dial.
    pub fn session_ttl_secs(self) -> i64 {
        match self {
            DeviceMode::Shared => SHARED_SESSION_TTL_SECS,
            DeviceMode::Personal => crate::identity::DEFAULT_SESSION_TTL_SECS,
        }
    }

    /// Read a mode back from storage, **failing closed**: a value this build cannot parse — a
    /// hand-run `UPDATE`, a restored backup, a column written by a newer version — is the strict
    /// mode, never the lax one.
    fn from_stored(value: Option<&str>) -> Self {
        value
            .and_then(|v| DeviceMode::parse(v).ok())
            .unwrap_or_default()
    }
}

/// `name` of the `InvalidPayload` rejections of this door (the malformed-request half).
const MODE_PAYLOAD: &str = "hub.device.mode";

/// How long a session lasts on a **shared** device: twelve hours — one shift.
///
/// Deliberately shorter than a day: a till whose session survived the night would be an unattended
/// open till every morning, which is the exact situation the pinpad exists to prevent. Long enough
/// that nobody is re-typing a PIN mid-service.
pub const SHARED_SESSION_TTL_SECS: i64 = 60 * 60 * 12;

/// Stable rejection of the device-mode door (`hub.device.*`), so the UI can tell the admin **why**
/// instead of showing a generic failure: an unknown device is fixed by signing in online on it
/// once — a message worth showing, unlike a malformed payload.
fn reject(code: &str, message: impl Into<String>) -> RuntimeError {
    RuntimeError::Domain {
        code: format!("{CORE_NAMESPACE}device.{code}"),
        message: message.into(),
    }
}

/// The refusal for an id that names no device this hub knows — the one an **administrator** can
/// legitimately hit, so it says what to do about it. Shared with the guard that refuses the hub's
/// own id (hub#454): from the outside both are the same fact, «that is not a device of mine», and
/// two different messages for it would only tell an attacker which of the two they hit.
pub(crate) fn unknown_device(device_id: &str) -> RuntimeError {
    reject(
        "unknown_device",
        format!(
            "this hub does not know the device `{device_id}`: sign in online on it once \
             before choosing how it identifies people"
        ),
    )
}

/// The mode of `device_id`, or [`DeviceMode::Shared`] when the hub has no idea what that is.
///
/// Deliberately infallible in the "unknown" direction: this is read by the **login screen**, with
/// no session, from whatever id the client presents.
pub async fn mode(db: &dyn DatabaseAdapter, hub_id: &str, device_id: &str) -> Result<DeviceMode> {
    if device_id.is_empty() {
        return Ok(DeviceMode::Shared);
    }
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("device_id".into(), json!(device_id));
    let res = db
        .query(
            "SELECT mode FROM hub_trusted_device \
              WHERE hub_id = :hub_id AND device_id = :device_id",
            &p,
        )
        .await?;
    Ok(DeviceMode::from_stored(
        res.rows.first().and_then(|r| r["mode"].as_str()),
    ))
}

/// Record what kind of device `device_id` is. `actor` is the `hub_user.id` that decided.
///
/// Refuses a device the hub has never met (`hub.device.unknown_device`): this door records a
/// decision **about a known device**, it does not enrol one. Without that guard, marking a device
/// personal would double as a way to write rows into the device-trust table from the outside —
/// and the id in question is a string the caller chose.
pub async fn set_mode(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    device_id: &str,
    mode: DeviceMode,
    actor: &str,
) -> Result<()> {
    if device_id.is_empty() {
        return Err(RuntimeError::InvalidPayload {
            name: MODE_PAYLOAD.into(),
            detail: "the device id is required: name the device whose mode is being set".into(),
        });
    }
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("device_id".into(), json!(device_id));
    p.insert("mode".into(), json!(mode.as_str()));
    p.insert("now".into(), json!(now_rfc3339()));
    p.insert("actor".into(), json!(actor));
    // UPDATE, never UPSERT: the row has to exist already, and letting the write door create it
    // would turn "this device is mine" into a way to trust an arbitrary id.
    //
    // Scoped by `hub_id` too (hub#489): a device the hub NEXT DOOR knows is, from here, a device
    // nobody knows — same `unknown_device` refusal as any other stranger, deliberately, so the
    // answer cannot be read as "that id exists, just not for you".
    let res = db
        .execute(
            "UPDATE hub_trusted_device \
                SET mode = :mode, mode_set_at = :now, mode_set_by = :actor \
              WHERE hub_id = :hub_id AND device_id = :device_id",
            &p,
        )
        .await?;
    if res.affected == 0 {
        return Err(unknown_device(device_id));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_stored_value_this_build_cannot_read_is_the_strict_mode() {
        // The absence of a row, a NULL column and a value from another world all mean the same
        // thing: the hub does not know, so it asks who is standing at the device.
        assert_eq!(DeviceMode::from_stored(None), DeviceMode::Shared);
        assert_eq!(DeviceMode::from_stored(Some("")), DeviceMode::Shared);
        assert_eq!(
            DeviceMode::from_stored(Some("trusted-forever")),
            DeviceMode::Shared
        );
        assert_eq!(
            DeviceMode::from_stored(Some("Personal")),
            DeviceMode::Shared
        );
        assert_eq!(DeviceMode::from_stored(Some("shared")), DeviceMode::Shared);
        assert_eq!(
            DeviceMode::from_stored(Some("personal")),
            DeviceMode::Personal,
            "the one spelling that IS the contract still reads back"
        );
    }

    #[test]
    fn the_default_mode_is_the_strict_one() {
        assert_eq!(DeviceMode::default(), DeviceMode::Shared);
    }
}
