//! **"Ask for a PIN: always / per shift / never"** — the business-wide dial, plan step 2b,
//! hub#359.
//!
//! hub#357/#358 put the friction on the **device** (`shared` = the counter till several people take
//! turns at, `personal` = somebody's own laptop). This is the second control, and it exists for a
//! case the device mode cannot express: the one-person minimarket that does not want to type four
//! digits to sell. It is of the **hub**, not of the device — it is a statement about the business
//! ("we do / do not identify who sells"), which is why it lives in [`crate::settings`] under the
//! key [`PIN_POLICY_SETTING`] rather than in the device row.
//!
//! ## How it composes with the device mode — the most restrictive wins
//!
//! Two controls over the same decision is the dangerous part, so the rule is one line:
//! **neither can lengthen what the other shortened** ([`effective_session_ttl_secs`] is a `min`).
//!
//! | device     | dial        | session window      | who won                                 |
//! |------------|-------------|---------------------|-----------------------------------------|
//! | `shared`   | `always`    | the short one       | the dial (it tightened the till)        |
//! | `shared`   | `per_shift` | the shift           | the device — hub#358 unchanged (default)|
//! | `shared`   | `never`     | **still the shift** | **the device: the dial cannot loosen**  |
//! | `personal` | `always`    | **the short one**   | **the dial: the device cannot loosen**  |
//! | `personal` | `per_shift` | the long one        | the device — hub#358 unchanged (default)|
//! | `personal` | `never`     | the long one        | the device — "remember me", as always   |
//!
//! ## What `never` gives up, and what it deliberately does not
//!
//! It stops the hub asking **which** of the staff is at the till ([`PinPolicy::asks_for_pin`] is
//! what the login screen reads): no pinpad, so whoever opened the till in the morning is the name
//! on every sale until the session expires. That is the consequence the owner is shown, in those
//! words.
//!
//! It does **not** unlock anything. The session still dies when the *device* says it does, so
//! somebody with a real account still has to open the till each shift. `never` gives up
//! **attribution**, never the lock — which is the only reason it can be a legitimate option.
//!
//! Two consequences worth naming, because they are what makes `never` a decision and not a
//! preference:
//!
//!  - **Only an administrator can choose it**, through the one write door
//!    ([`set_policy`] → [`crate::settings::set_many`], behind `require_admin_session` in the HTTP
//!    layer). The login screen runs with no session and can only ever *read* it — if the screen in
//!    front of the lock could turn the lock off, there would be no lock.
//!  - **A staff member whose only credential is a PIN cannot sign in while it is `never`**, because
//!    there is no pinpad to sign in with. That is stated in the option's own text, and it is
//!    reversible by the same administrator.
//!
//! ## What "per shift" honestly means
//!
//! **The hub cannot observe a shift.** There is no shift entity in the core, no business hours and
//! no clock-in. The only thing in the product that resembles one is the cash-register session of
//! the `cash_register` *module* — optional, one-per-hub rather than per-till, carrying no device
//! id, and known to be left open for days (ADR-0130); and the core has no mechanism to react to a
//! module event anyway, so hanging the hub's auth policy off an installable module would invert the
//! dependency. So `per_shift` is the shift-length **window** the hub already enforces and already
//! calls a shift ([`crate::device_mode::SHARED_SESSION_TTL_SECS`], 12 h): a clock, not an observed
//! fact. hub#476 tracks binding it to a real close-of-till if that ever becomes visible to the
//! core.
//!
//! Same honesty for `always`: the literal "every sale" needs a lock screen over the running app
//! (hub#456). Until then it is the **shortest window the hub can promise and keep**
//! ([`ALWAYS_SESSION_TTL_SECS`]), and the owner-facing text says the hour out loud instead of
//! promising something the hub does not do.
use erplora_db::{DatabaseAdapter, Params};
use serde_json::json;

use crate::device_mode::DeviceMode;
use crate::errors::{Result, RuntimeError};

/// The key of this dial in `hub_settings`. It is a **contract**: the column stores it, the web
/// reads it back from `GET /api/settings` and from the unauthenticated device door.
pub const PIN_POLICY_SETTING: &str = "pin_policy";

/// `name` of the `InvalidPayload` rejection of an unreadable policy (HTTP 422).
const POLICY_PAYLOAD: &str = "hub.pin_policy";

/// The session window `always` promises: **one hour**.
///
/// Not "every sale" — the hub cannot ask on every sale until there is a lock screen over the
/// running app (hub#456). This is the shortest window it can promise and keep, and the text the
/// owner reads says so rather than promising the thing the hub does not do. Deliberately well
/// under a shift, or the strictest position of the dial would be indistinguishable from the middle
/// one and the owner would be choosing between a difference that does not exist.
pub const ALWAYS_SESSION_TTL_SECS: i64 = 60 * 60;

/// The key of the idle window in `hub_settings` (hub#628): how many minutes of inactivity before
/// the shell signs the user out and shows the pinpad again. Same contract shape as
/// [`PIN_POLICY_SETTING`] — the column stores it, `GET /api/settings` returns it.
///
/// It only has an effect while the policy is [`Always`](PinPolicy::Always), and the one who
/// enforces it is the **client** (the shell's idle detector): the hub cannot see a hand leaving
/// the till. The server keeps [`ALWAYS_SESSION_TTL_SECS`] as the backstop for a client that never
/// comes back to enforce anything.
pub const PIN_INACTIVITY_MINUTES_SETTING: &str = "pin_inactivity_minutes";

/// Idle minutes assumed when the row is absent or unreadable: the middle-low stop of the range
/// the owner is shown (1 · 5 · 10 · 15 · 30). Short enough to be a real lock on a counter till,
/// long enough not to punish reading a long menu out loud.
pub const DEFAULT_PIN_INACTIVITY_MINUTES: i64 = 5;

/// Ceiling of the idle window. Above this the "lock" would outlive the longest coffee break and
/// the position stops being distinguishable from "until you sign out".
pub const MAX_PIN_INACTIVITY_MINUTES: i64 = 30;

/// How often this business wants to be asked who is standing at the till.
///
/// The default is [`PerShift`](PinPolicy::PerShift) **on purpose**, and the reasoning is not "it is
/// the strictest" — it is not. It is the value that (a) keeps every sale attributed to a person,
/// which is the property this feature exists to protect, and (b) is **exactly** what hub#358
/// already shipped, so no hub's sessions change length because a setting appeared. The value that
/// gives the property up is `never`, and nothing — an absent row, a corrupt one, a spelling from
/// the future, a failed read — resolves to it.
///
/// **No serde derives, deliberately** (same reasoning as [`DeviceMode`]): the wire and the column
/// go through [`as_str`](Self::as_str) and [`parse`](Self::parse), and `parse` is the one door that
/// fails closed with a stable rejection. A `Deserialize` impl would be a second, quieter entrance
/// for the exact value this hub must be strict about.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum PinPolicy {
    /// Ask again as soon as the window is up: the shortest session the hub keeps.
    Always,
    /// Ask once and remember for the shift — the window hub#358 already enforces.
    #[default]
    PerShift,
    /// Do not ask who is at the till. Sales stop carrying the name of whoever made them.
    Never,
}

impl PinPolicy {
    /// The wire/storage spelling. It is a **contract**: the column stores it and the web reads it.
    pub fn as_str(self) -> &'static str {
        match self {
            PinPolicy::Always => "always",
            PinPolicy::PerShift => "per_shift",
            PinPolicy::Never => "never",
        }
    }

    /// Parse a policy a caller asked for. The set is **closed**: anything else is refused instead
    /// of guessed. Exact match, no trimming and no case folding — a `"Never "` that resolved would
    /// mean the wire format has two spellings for the position that gives up the name on every
    /// sale, and the one that slips through is always the lax one.
    pub fn parse(value: &str) -> Result<Self> {
        match value {
            "always" => Ok(PinPolicy::Always),
            "per_shift" => Ok(PinPolicy::PerShift),
            "never" => Ok(PinPolicy::Never),
            other => Err(RuntimeError::InvalidPayload {
                name: POLICY_PAYLOAD.into(),
                detail: format!(
                    "`{other}` is not a PIN policy: this hub knows `always`, `per_shift` and \
                     `never`"
                ),
            }),
        }
    }

    /// Read a policy back from storage, **failing closed**: a value this build cannot parse — a
    /// hand-run `UPDATE`, a restored backup, a column written by a newer version — is the default,
    /// never `never`. Guessing high here would be guessing in the direction that stops the hub
    /// asking who is selling.
    pub fn from_stored(value: Option<&str>) -> Self {
        value
            .and_then(|v| PinPolicy::parse(v).ok())
            .unwrap_or_default()
    }

    /// Is the PIN offered as a way in at all? Only `never` says no.
    ///
    /// The login screen reads this **together with** the device mode: the pinpad needs `shared`
    /// (several people take turns, so four digits are the right question), device-trust (a PIN only
    /// works where an online login already happened, §2.9) **and** a dial that still asks. Any one
    /// of the three saying no means the account route instead — which is stricter, not looser.
    pub fn asks_for_pin(self) -> bool {
        !matches!(self, PinPolicy::Never)
    }

    /// The longest session **this dial** allows, or `None` when it imposes no window of its own.
    ///
    /// Only `always` caps, and that asymmetry is the whole point:
    ///
    ///  - **`always`** is the position an owner moves to on purpose, so it applies to *every*
    ///    device. A business that says "always identify yourself" is not carving out an exception
    ///    for the laptop in the back office, and tightening is the direction that is always safe.
    ///  - **`per_shift`** is the **default**, and a default may not change anything. Capping here
    ///    would have shortened every device somebody marked as their own from a month to twelve
    ///    hours — a behaviour change nobody chose, arriving with a setting they never touched. It
    ///    says "keep asking"; how long the session then lives is the device's business (hub#358),
    ///    which on a shared till already *is* a shift.
    ///  - **`never`** says "do not ask", and what remains is whatever the device requires. That is
    ///    why it can never be used to *lengthen* anything.
    ///
    /// The invariant that pins this down is in `crates/runtime/tests/pin_policy.rs`: under the
    /// default, every device gets exactly the window hub#358 gave it.
    pub fn max_session_ttl_secs(self) -> Option<i64> {
        match self {
            PinPolicy::Always => Some(ALWAYS_SESSION_TTL_SECS),
            PinPolicy::PerShift | PinPolicy::Never => None,
        }
    }
}

/// How long a session opened on `mode`, under `policy`, may live — **the most restrictive wins**.
///
/// A `min`, and it has to be: the two controls are set from different screens by different people
/// at different times, and any rule other than "the shorter one" lets one of them silently undo the
/// other. Concretely, the two rows that matter: `never` cannot buy a shared till the month-long
/// session of a personal device, and marking a device personal cannot opt it out of the strictest
/// policy the business chose.
pub fn effective_session_ttl_secs(mode: DeviceMode, policy: PinPolicy) -> i64 {
    shorter_window(mode.session_ttl_secs(), policy.max_session_ttl_secs())
}

/// The rule itself, over plain seconds: the shorter of the device's window and the dial's cap.
///
/// Split out from [`effective_session_ttl_secs`] **so it can be tested for pairs that do not exist
/// yet**. With today's three positions every cap happens to be shorter than every device window, so
/// "take the shorter" and "take the cap" are indistinguishable through the enum — a mutation
/// campaign found exactly that hole. The day somebody adds a position longer than a shift, the rule
/// has to already be `min`, and here it is pinned regardless of which positions exist.
pub fn shorter_window(device_ttl_secs: i64, dial_cap_secs: Option<i64>) -> i64 {
    match dial_cap_secs {
        Some(cap) => device_ttl_secs.min(cap),
        None => device_ttl_secs,
    }
}

/// The dial of `hub_id`, or the default when the hub never chose (or when what it stored cannot be
/// read).
///
/// Deliberately infallible in the "unknown" direction and tolerant of a hub whose `hub_settings`
/// does not exist yet (same shape as [`crate::settings::country_code_of`]): this is read on **every
/// login**, and a read that could fail would be a read that has to decide what a failure means —
/// the one decision that must never be improvised next to a lock.
pub async fn policy(db: &dyn DatabaseAdapter, hub_id: &str) -> Result<PinPolicy> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    let stored = match db
        .query(
            "SELECT value FROM hub_settings WHERE hub_id = :hub_id AND key = 'pin_policy'",
            &p,
        )
        .await
    {
        Ok(res) => res
            .rows
            .first()
            .and_then(|r| r["value"].as_str().map(str::to_string)),
        Err(_) => None,
    };
    Ok(PinPolicy::from_stored(stored.as_deref()))
}

/// Record how often this hub wants to be asked. `actor` is who decided, for the audit trail.
///
/// Goes through [`crate::settings::set_many`] on purpose: **one write door**, so the validation,
/// the upsert and the `updated_by` stamp are the same whether the change arrives from
/// `PUT /api/settings` or from here. A second path would be a second place to forget the admin
/// gate.
pub async fn set_policy(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    policy: PinPolicy,
    actor: &str,
) -> Result<()> {
    let mut updates = serde_json::Map::new();
    updates.insert(PIN_POLICY_SETTING.to_string(), json!(policy.as_str()));
    // `demo_hub: false` is not a bypass: this door writes ONE key, the pin policy, and a demo hub
    // is only frozen on its fiscal identity (ADR-0197 §4, hub#376) — how often it asks for a PIN
    // is its own business.
    crate::settings::set_many(db, hub_id, &updates, actor, false).await?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_stored_value_this_build_cannot_read_is_the_default_never_never() {
        // The absence of a row, a NULL column and a value from another world all mean the same
        // thing: the hub does not know, so it keeps asking.
        for unreadable in [None, Some(""), Some("Never"), Some("never "), Some("off")] {
            let read = PinPolicy::from_stored(unreadable);
            assert_eq!(read, PinPolicy::default(), "{unreadable:?}");
            assert!(read.asks_for_pin(), "{unreadable:?} stopped the hub asking");
        }
        // The three spellings that ARE the contract still read back.
        assert_eq!(PinPolicy::from_stored(Some("always")), PinPolicy::Always);
        assert_eq!(PinPolicy::from_stored(Some("per_shift")), PinPolicy::PerShift);
        assert_eq!(PinPolicy::from_stored(Some("never")), PinPolicy::Never);
    }

    #[test]
    fn the_default_keeps_every_sale_attributed_to_a_person() {
        assert_eq!(PinPolicy::default(), PinPolicy::PerShift);
        assert!(PinPolicy::default().asks_for_pin());
    }

    #[test]
    fn the_dial_never_lengthens_a_session() {
        for mode in [DeviceMode::Shared, DeviceMode::Personal] {
            for policy in [PinPolicy::Always, PinPolicy::PerShift, PinPolicy::Never] {
                assert!(effective_session_ttl_secs(mode, policy) <= mode.session_ttl_secs());
            }
        }
    }
}
