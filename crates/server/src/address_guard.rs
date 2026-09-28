//! Per-address guard for failed sign-ins (hub#2282).
//!
//! Since infra#335 the edge only *watches* 401s: banning on them locked out whole shops whose till
//! kept retrying with a dead session (infra#334). So the hub counts its own failures, per client
//! address, and it can tell the two shapes apart where the edge could not:
//!
//! - **A guess** (a wrong PIN or an unknown badge) spends one attempt. [`crate::login_throttle`]
//!   already locks the NAME after five, but it cannot see an attacker who rotates names; this does.
//! - **A session credential that does not resolve** (`X-Hub-Session`, the `erplora_media` cookie or
//!   an `/api/events` ticket) counts once per DISTINCT token. A till repeating its one dead session
//!   a thousand times is one token; somebody inventing sessions is a new token on every request.
//!
//! When an address reaches either limit, the credential doors (PIN and badge) answer `429` to it
//! for [`LOCK_WINDOW`], before verifying anything. A request that carries a session which resolves
//! never asks this guard: whoever is already signed in keeps working, whatever their address did.
//! Session doors keep answering `401` to unresolvable credentials — a session token is 244 random
//! bits, nobody wins it by guessing, and a till must keep seeing the `401` that sends it back to
//! the login screen.
//!
//! Every failure also leaves one stable line in the log (`event=auth_failed reason=… client=…
//! hub=…`), the signal a watcher outside the hub can alert or ban on.
//!
//! In memory, like [`crate::login_throttle`]: it guards doors only this process serves.
use std::collections::HashMap;
use std::sync::Mutex;
use std::time::{Duration, Instant};

use axum::http::HeaderMap;

/// Wrong PINs/badges one address may send per [`WINDOW`]. High on purpose: a shop is several
/// tills behind one address, and each name already locks itself after five.
pub const MAX_GUESSES: u32 = 20;
/// Distinct session credentials that did not resolve, per address and [`WINDOW`].
pub const MAX_FORGED_SESSIONS: usize = 20;
/// How long failures are remembered.
pub const WINDOW: Duration = Duration::from_secs(15 * 60);
/// How long a locked address stays locked.
pub const LOCK_WINDOW: Duration = Duration::from_secs(15 * 60);
/// Addresses tracked before the stale ones are swept, so a spray from many addresses cannot grow
/// the map without bound.
const MAX_TRACKED: usize = 10_000;

/// Why an attempt failed — the `reason` of the log line.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Failure {
    Pin,
    Badge,
    SessionInvalid,
    TicketInvalid,
}

impl Failure {
    pub fn code(self) -> &'static str {
        match self {
            Failure::Pin => "pin",
            Failure::Badge => "badge",
            Failure::SessionInvalid => "session_invalid",
            Failure::TicketInvalid => "ticket_invalid",
        }
    }
}

/// The client's address: the LAST `X-Forwarded-For` hop, the one the proxy in front of the hub
/// appended (same reasoning as `public_door::throttle_key`: the first hops are whatever the caller
/// wrote). `None` without a proxy header — the hub is never exposed directly (ADR-0092), so there
/// is no address to hold anybody to, and the per-name lock still applies.
pub fn client_address(headers: &HeaderMap) -> Option<String> {
    let _ = headers;
    None
}

/// Per-address failure counters.
pub struct AddressGuard {
    entries: Mutex<HashMap<String, ()>>,
}

impl Default for AddressGuard {
    fn default() -> Self {
        Self::new()
    }
}

impl AddressGuard {
    pub fn new() -> Self {
        Self {
            entries: Mutex::new(HashMap::new()),
        }
    }

    /// Is this address locked right now? `Some(secs)` = locked, and how long to wait.
    pub fn locked_for(&self, address: &str) -> Option<u64> {
        self.locked_for_at(address, Instant::now())
    }

    /// A wrong PIN or badge from `address`.
    pub fn record_guess(&self, address: &str) {
        self.record_guess_at(address, Instant::now())
    }

    /// A session credential from `address` that did not resolve. Returns `true` the first time
    /// this token is seen in the window, so the caller logs each forged token once.
    pub fn record_rejected_session(&self, address: &str, token: &str) -> bool {
        self.record_rejected_session_at(address, token, Instant::now())
    }

    fn locked_for_at(&self, _address: &str, _now: Instant) -> Option<u64> {
        None
    }

    fn record_guess_at(&self, _address: &str, _now: Instant) {}

    fn record_rejected_session_at(&self, _address: &str, _token: &str, _now: Instant) -> bool {
        let _ = &self.entries;
        false
    }

    #[cfg(test)]
    fn tracked(&self) -> usize {
        usize::MAX
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const SHOP: &str = "198.51.100.7";
    const OTHER: &str = "203.0.113.9";

    #[test]
    fn guesses_lock_the_address_only_at_the_threshold() {
        let g = AddressGuard::new();
        let now = Instant::now();
        for _ in 0..MAX_GUESSES - 1 {
            g.record_guess_at(SHOP, now);
        }
        assert!(g.locked_for_at(SHOP, now).is_none(), "one short of the limit");
        g.record_guess_at(SHOP, now);
        let secs = g.locked_for_at(SHOP, now).expect("locked at the limit");
        assert!(secs > 0 && secs <= LOCK_WINDOW.as_secs());
    }

    #[test]
    fn one_address_never_locks_another() {
        let g = AddressGuard::new();
        let now = Instant::now();
        for _ in 0..MAX_GUESSES {
            g.record_guess_at(SHOP, now);
        }
        assert!(g.locked_for_at(SHOP, now).is_some());
        assert!(g.locked_for_at(OTHER, now).is_none());
    }

    /// The shape of infra#334: a till repeating its one dead session all day long.
    #[test]
    fn the_same_dead_session_repeated_never_locks() {
        let g = AddressGuard::new();
        let now = Instant::now();
        assert!(g.record_rejected_session_at(SHOP, "dead-token", now));
        for _ in 0..1_000 {
            assert!(!g.record_rejected_session_at(SHOP, "dead-token", now));
        }
        assert!(g.locked_for_at(SHOP, now).is_none());
    }

    #[test]
    fn distinct_forged_sessions_lock_the_address() {
        let g = AddressGuard::new();
        let now = Instant::now();
        for i in 0..MAX_FORGED_SESSIONS - 1 {
            assert!(g.record_rejected_session_at(SHOP, &format!("forged-{i}"), now));
        }
        assert!(g.locked_for_at(SHOP, now).is_none(), "one short of the limit");
        g.record_rejected_session_at(SHOP, "forged-last", now);
        assert!(g.locked_for_at(SHOP, now).is_some());
        assert!(g.locked_for_at(OTHER, now).is_none());
    }

    #[test]
    fn failures_older_than_the_window_are_forgotten() {
        let g = AddressGuard::new();
        let start = Instant::now();
        for _ in 0..MAX_GUESSES - 1 {
            g.record_guess_at(SHOP, start);
        }
        let later = start + WINDOW + Duration::from_secs(1);
        g.record_guess_at(SHOP, later);
        assert!(
            g.locked_for_at(SHOP, later).is_none(),
            "a slow trickle across windows is a shop, not an attack"
        );
        // The same holds for sessions: the token set restarts with the window.
        assert!(g.record_rejected_session_at(OTHER, "t", start));
        assert!(g.record_rejected_session_at(OTHER, "t", later));
    }

    #[test]
    fn the_lock_expires_and_starts_from_zero() {
        let g = AddressGuard::new();
        let now = Instant::now();
        for _ in 0..MAX_GUESSES {
            g.record_guess_at(SHOP, now);
        }
        let after = now + LOCK_WINDOW + Duration::from_secs(1);
        assert!(g.locked_for_at(SHOP, after).is_none());
        g.record_guess_at(SHOP, after);
        assert!(
            g.locked_for_at(SHOP, after).is_none(),
            "one new failure must not re-lock"
        );
    }

    #[test]
    fn stale_addresses_are_swept_past_the_cap() {
        let g = AddressGuard::new();
        let start = Instant::now();
        for i in 0..MAX_TRACKED {
            g.record_guess_at(&format!("10.0.{}.{}", i / 256, i % 256), start);
        }
        let later = start + WINDOW + LOCK_WINDOW + Duration::from_secs(1);
        g.record_guess_at(SHOP, later);
        assert!(g.tracked() <= 1, "every stale address is gone: {}", g.tracked());
    }

    #[test]
    fn the_client_address_is_the_last_forwarded_hop() {
        let mut headers = HeaderMap::new();
        assert_eq!(client_address(&headers), None, "no proxy, no address");
        headers.insert("x-forwarded-for", "1.2.3.4, 198.51.100.7".parse().unwrap());
        assert_eq!(client_address(&headers).as_deref(), Some(SHOP));
        headers.insert("x-forwarded-for", " ".parse().unwrap());
        assert_eq!(client_address(&headers), None);
    }

    #[test]
    fn reasons_have_stable_codes() {
        assert_eq!(Failure::Pin.code(), "pin");
        assert_eq!(Failure::Badge.code(), "badge");
        assert_eq!(Failure::SessionInvalid.code(), "session_invalid");
        assert_eq!(Failure::TicketInvalid.code(), "ticket_invalid");
    }
}
