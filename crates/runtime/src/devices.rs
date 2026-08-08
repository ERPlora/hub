//! **Devices** (hub#455) — the devices this business has signed in on, and the gesture that cuts a
//! lost one off.
//!
//! `identity::untrust_device` has existed since hub#15 and it held up half the security argument of
//! hub#357/hub#358 — "revoking the trust of a stolen laptop takes its lax mode with it" — while
//! nothing in the product could call it, and nothing could even *list* the devices to name the one
//! that went missing. With hub#358 shipped, that gap has a number on it: a tablet marked `personal`
//! carries a session that lasts **thirty days** and never shows a pinpad.
//!
//! ## What "revoke" means here
//!
//! Two writes, and the second is the one that matters today:
//!
//!  1. the trust row goes — with it the `personal` mode it carried (hub#357: the mode lives in that
//!     row precisely so revocation needs no cascade) and the right to sign in with a PIN (§2.9);
//!  2. **the sessions open on that device are closed.** Without this, revoking would only close the
//!     door the thief already walked through: `resolve_session` reads `hub_session` on every single
//!     request, so deleting those rows is what makes the cut-off take effect on the device's *next*
//!     action rather than in thirty days.
//!
//! It does **not** claim to make the device un-usable forever. Somebody holding it who also has an
//! account can sign in online again and re-trust it — which is correct: what was revoked is the
//! standing permission this hub had granted the *device*, never the credential of a person. The
//! screen says exactly that, because a promise the runtime cannot keep would be worse than none.
//!
//! ## What the list can and cannot be believed about
//!
//! Two of the columns are **chosen by the device**: `device_id` (the `X-Device-Id` header, a string
//! the client picks) and `label` — which is the `name` field of the cloud-login body, overwritten
//! on every online login (`identity::trust_device` upserts it). They are here to be *recognised by
//! eye*, never to be trusted: nothing in this hub decides anything from them. Everything else —
//! `trusted_at`, the mode and its audit trail, and the session counts — the hub wrote itself.
//!
//! The mode is read back **fail-closed**, through the same [`DeviceMode::parse`] the login uses: a
//! value this build cannot read is shown as `shared`, so the list can never tell an owner that a
//! device is stricter or laxer than it will actually behave.
//!
//! ## Blast radius
//!
//! Both statements are keyed on one `device_id` (and, since hub#489, on this hub). Neither has an
//! unbounded form, no `IS NULL` branch and no negation: a session that names **no** device (opened
//! before hub#200 added the column, or by a client that identifies none) is left alone, because
//! "cut off the tablet" is not "sign out everybody I cannot place".
//!
//! Isolation between hubs is the database (ADR-0201, one per hub) **and now also the row**: since
//! hub#489 / system migration v23, `hub_trusted_device` is keyed `(hub_id, device_id)` and both
//! doors here carry the hub. So the list enumerates one business, and a revocation cannot reach the
//! trust of the business next door even where a database is shared.
//!
//! ⚠️ **What is still not scoped: `hub_session`** (and `hub_user` under it) carries no `hub_id`
//! column. On a shared database the *sessions* half of a revocation therefore still crosses — and,
//! worse, a token minted by one hub still resolves in the other. That is a bigger defect than this
//! door and it has its own issue (hub#497); it is named here rather than papered over, and it does
//! not weaken the trust half: privilege is what the trust row grants.
use std::collections::HashMap;

use erplora_db::{DatabaseAdapter, Params};
use serde_json::json;

use crate::device_mode::DeviceMode;
use crate::errors::{Result, RuntimeError};
use crate::registry::now_rfc3339;

/// A device this hub knows, as the owner's list paints it.
///
/// Serialised straight to the wire (`GET /api/devices`), so the field names are a contract.
#[derive(Debug, Clone, PartialEq, Eq, serde::Serialize)]
pub struct TrustedDevice {
    /// The `X-Device-Id` it presents. **Chosen by the device**: an identifier, never a credential.
    pub device_id: String,
    /// The name of the last account that signed in online on it. **Chosen by the device** too (it
    /// travels in the login body), so it is a memory aid and nothing else.
    pub label: String,
    /// When this hub first trusted it (its first online login). Written by the hub.
    pub trusted_at: String,
    /// `shared` | `personal`, read back fail-closed — what the login will *actually* do.
    pub mode: String,
    /// When an administrator last decided the mode, and which `hub_user.id` decided it.
    pub mode_set_at: String,
    pub mode_set_by: String,
    /// How many sessions are open on it **right now** (expired ones do not count).
    pub open_sessions: usize,
    /// When the most recent of those sessions was opened; `""` when nobody is signed in.
    pub last_sign_in: String,
    /// When the longest-lived of those sessions runs out; `""` when nobody is signed in. This is
    /// the thirty days a `personal` device is worth, spelled out.
    pub signed_in_until: String,
}

/// What a revocation actually did — the honest report, not "ok".
///
/// The owner just told the hub a device was lost, so the two facts worth answering are whether the
/// hub knew it at all and how many open sessions were closed by the gesture.
#[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Serialize)]
pub struct Revocation {
    /// `true` if there was a trust row to remove. `false` is not an error — see [`revoke`].
    pub was_known: bool,
    /// Sessions that stopped resolving because of this call.
    pub sessions_closed: usize,
}

/// `name` of the `InvalidPayload` rejection of this door.
const DEVICE_PAYLOAD: &str = "hub.device.id";

/// The device id a caller named, or a rejection when it named none.
///
/// Trimmed and refused when blank, for one reason: every statement below is keyed on this value,
/// and a blank one is a caller that did not say which device — a malformed request. Letting it
/// through would turn a mis-built URL into a `DELETE` nobody asked for.
fn named(device_id: &str) -> Result<&str> {
    let id = device_id.trim();
    if id.is_empty() {
        return Err(RuntimeError::InvalidPayload {
            name: DEVICE_PAYLOAD.into(),
            detail: "the device id is required: name the device being revoked".into(),
        });
    }
    Ok(id)
}

/// The sessions open on one device, folded as the rows arrive.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
struct OpenSessions {
    count: usize,
    /// Latest `created_at` seen.
    last_sign_in: String,
    /// Furthest `expires_at` seen.
    until: String,
}

impl OpenSessions {
    /// Fold in one open session. Both timestamps keep the **maximum**: the owner is asking "is
    /// anybody on it, and for how much longer", so the newest sign-in and the last expiry to run
    /// out are the answers. RFC-3339 strings from `now_rfc3339` compare correctly as text (the same
    /// property `expires_at > :now` already relies on in SQL).
    fn saw(&mut self, created_at: &str, expires_at: &str) {
        self.count += 1;
        if created_at > self.last_sign_in.as_str() {
            self.last_sign_in = created_at.to_string();
        }
        if expires_at > self.until.as_str() {
            self.until = expires_at.to_string();
        }
    }
}

/// The mode to SHOW for a stored value, decided by the same parser the login obeys.
///
/// Fail-closed: an unreadable value (a hand-run `UPDATE`, a restored backup, a column written by a
/// newer build) shows as `shared`, which is what the device will actually do. A list that reported
/// the raw column would be a list that can contradict the hub.
fn listed_mode(stored: Option<&str>) -> &'static str {
    stored
        .and_then(|v| DeviceMode::parse(v).ok())
        .unwrap_or_default()
        .as_str()
}

/// Every device **this hub** knows, newest activity first.
///
/// Two statements instead of one `LEFT JOIN … GROUP BY`: the aggregation is then a pure fold that
/// tests can pin down, and there is no dialect corner where Postgres and SQLite disagree about
/// which columns a `GROUP BY` may carry. A hub has a handful of devices; this is not a hot path.
///
/// The device statement is scoped by `hub_id` (hub#489). The session one cannot be — `hub_session`
/// has no such column — but it only ever *decorates* a device this hub listed, so the enumeration
/// itself never leaks: at most a neighbour's session inflates the count of a device id both
/// businesses happen to trust. Named in the module doc, hub#497.
pub async fn list(db: &dyn DatabaseAdapter, hub_id: &str) -> Result<Vec<TrustedDevice>> {
    let mut p = Params::new();
    p.insert("now".into(), json!(now_rfc3339()));
    // Open sessions only. An expired row is not somebody signed in, and counting it would tell the
    // owner a till is in use in an empty shop — the exact opposite of the signal they came for.
    let sessions = db
        .query(
            "SELECT device_id, created_at, expires_at FROM hub_session \
              WHERE device_id IS NOT NULL AND expires_at > :now",
            &p,
        )
        .await?;
    let mut open: HashMap<String, OpenSessions> = HashMap::new();
    for row in &sessions.rows {
        let Some(device_id) = row["device_id"].as_str() else {
            continue;
        };
        open.entry(device_id.to_string()).or_default().saw(
            row["created_at"].as_str().unwrap_or_default(),
            row["expires_at"].as_str().unwrap_or_default(),
        );
    }

    let mut scope = Params::new();
    scope.insert("hub_id".into(), json!(hub_id));
    let devices = db
        .query(
            "SELECT device_id, label, trusted_at, mode, mode_set_at, mode_set_by \
               FROM hub_trusted_device WHERE hub_id = :hub_id",
            &scope,
        )
        .await?;
    let mut listed: Vec<TrustedDevice> = devices
        .rows
        .iter()
        .map(|r| {
            let device_id = r["device_id"].as_str().unwrap_or_default().to_string();
            let sessions = open.get(&device_id).cloned().unwrap_or_default();
            TrustedDevice {
                label: r["label"].as_str().unwrap_or_default().to_string(),
                trusted_at: r["trusted_at"].as_str().unwrap_or_default().to_string(),
                mode: listed_mode(r["mode"].as_str()).to_string(),
                mode_set_at: r["mode_set_at"].as_str().unwrap_or_default().to_string(),
                mode_set_by: r["mode_set_by"].as_str().unwrap_or_default().to_string(),
                open_sessions: sessions.count,
                last_sign_in: sessions.last_sign_in,
                signed_in_until: sessions.until,
                device_id,
            }
        })
        .collect();
    // The one the owner is looking for is the one that was used last, so that is the top of the
    // list. Ties fall back to the hub's own clock and then to the id, so the order is total and the
    // screen never reshuffles between two reads that saw the same data.
    listed.sort_by(|a, b| {
        b.last_sign_in
            .cmp(&a.last_sign_in)
            .then_with(|| b.trusted_at.cmp(&a.trusted_at))
            .then_with(|| a.device_id.cmp(&b.device_id))
    });
    Ok(listed)
}

/// Cut `device_id` off: close its open sessions, then forget it.
///
/// **Sessions first.** If the second statement failed, the caller gets an error and retries with a
/// device that is already signed out; the other order would leave a forgotten device still holding
/// a live token, which is the state this whole issue exists to remove.
///
/// **Idempotent, and an unknown device is not an error.** Two administrators reacting to the same
/// lost tablet is the normal case, and the second one must not be told that something went wrong.
/// It still closes sessions for a device with no trust row: the row is why a device is *listed*,
/// never why it is *connected*.
///
/// The trust delete is scoped to `hub_id` (hub#489) so it cannot reach the row of the business next
/// door; the session delete is not, because `hub_session` has no such column (hub#497).
pub async fn revoke(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    device_id: &str,
) -> Result<Revocation> {
    let device_id = named(device_id)?;
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("device_id".into(), json!(device_id));
    let closed = db
        .execute(
            "DELETE FROM hub_session WHERE device_id = :device_id",
            &p,
        )
        .await?;
    let forgotten = db
        .execute(
            "DELETE FROM hub_trusted_device WHERE hub_id = :hub_id AND device_id = :device_id",
            &p,
        )
        .await?;
    Ok(Revocation {
        was_known: forgotten.affected > 0,
        sessions_closed: closed.affected as usize,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_caller_that_names_no_device_is_refused_rather_than_guessed() {
        // Blank, whitespace and a tab all mean "I did not say which device". Every statement in
        // this module is keyed on the value, so guessing here is guessing about a `DELETE`.
        for blank in ["", " ", "\t", "   \n"] {
            assert!(named(blank).is_err(), "{blank:?} names no device");
        }
        assert_eq!(named("  till-1 ").unwrap(), "till-1", "a real id is trimmed, not refused");
    }

    #[test]
    fn the_mode_shown_is_the_mode_the_login_will_obey() {
        // Same closed set as `DeviceMode::parse`, same direction on every doubt: `shared`. A list
        // that showed a raw column could tell the owner a till is lax when the login is strict.
        assert_eq!(listed_mode(Some("personal")), "personal");
        assert_eq!(listed_mode(Some("shared")), "shared");
        assert_eq!(listed_mode(None), "shared");
        assert_eq!(listed_mode(Some("")), "shared");
        assert_eq!(listed_mode(Some("Personal")), "shared", "no case folding, like the parser");
        assert_eq!(listed_mode(Some("trusted-forever")), "shared");
    }

    #[test]
    fn the_session_fold_answers_who_is_on_it_now_and_for_how_long() {
        let mut open = OpenSessions::default();
        assert_eq!(open, OpenSessions { count: 0, last_sign_in: String::new(), until: String::new() });

        open.saw("2026-08-01T08:00:00+00:00", "2026-08-01T20:00:00+00:00");
        open.saw("2026-08-01T09:30:00+00:00", "2026-08-01T18:00:00+00:00");

        assert_eq!(open.count, 2);
        // The NEWEST sign-in and the LAST expiry to run out — deliberately not the same row: "when
        // was it last used" and "how long is it still open" are two different questions, and the
        // second one is the one that says how long a stolen tablet would keep working.
        assert_eq!(open.last_sign_in, "2026-08-01T09:30:00+00:00");
        assert_eq!(open.until, "2026-08-01T20:00:00+00:00");
    }
}
