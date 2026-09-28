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
use std::collections::{HashMap, HashSet};
use std::hash::{Hash, Hasher};
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
    headers
        .get("x-forwarded-for")
        .and_then(|v| v.to_str().ok())
        .and_then(|v| v.rsplit(',').next())
        .map(str::trim)
        .filter(|v| !v.is_empty())
        .map(str::to_owned)
}

/// The stable line every failure leaves (`event=auth_failed reason=… client=… hub=…`). Matched
/// on its fields, never on the prose. `client=-` when no proxy said who it was.
pub fn report(reason: Failure, client: Option<&str>, hub_id: &str) {
    tracing::warn!(
        event = %"auth_failed",
        reason = %reason.code(),
        client = %client.unwrap_or("-"),
        hub = %hub_id,
        "sign-in failed"
    );
}

/// A wrong PIN or badge: counted against the address and logged.
pub fn record_guess(st: &crate::AppState, client: Option<&str>, reason: Failure) {
    if let Some(client) = client {
        st.address_guard.record_guess(client);
    }
    report(reason, client, &st.hub_id());
}

/// A session credential that came back `401`: counted once per distinct token, and logged the
/// first time it is seen, so a till repeating its dead session does not flood the log.
pub fn record_rejected_credential(
    st: &crate::AppState,
    client: Option<&str>,
    reason: Failure,
    token: &str,
) {
    let first_sighting = match client {
        Some(client) => st.address_guard.record_rejected_session(client, token),
        None => true,
    };
    if first_sighting {
        report(reason, client, &st.hub_id());
    }
}

/// What one address did in the current window.
struct Attempts {
    window_start: Instant,
    guesses: u32,
    /// Fingerprints of the session credentials that did not resolve — never the tokens themselves.
    /// Bounded: it stops growing at [`MAX_FORGED_SESSIONS`], which is where the lock starts.
    sessions: HashSet<u64>,
    /// When the current lock expires. `None` = not locked.
    locked_until: Option<Instant>,
}

impl Attempts {
    fn new(now: Instant) -> Self {
        Self {
            window_start: now,
            guesses: 0,
            sessions: HashSet::new(),
            locked_until: None,
        }
    }

    fn is_locked(&self, now: Instant) -> bool {
        self.locked_until.is_some_and(|until| until > now)
    }

    /// Nothing left to remember: the lock is over, or the window closed without one. Either way
    /// the address starts from zero — a lock that forgot only the time would re-lock on the next
    /// single failure, and the window would be permanent in practice.
    fn is_stale(&self, now: Instant) -> bool {
        match self.locked_until {
            Some(until) => until <= now,
            None => now.duration_since(self.window_start) >= WINDOW,
        }
    }

    fn lock(&mut self, now: Instant) {
        self.locked_until = Some(now + LOCK_WINDOW);
    }
}

fn fingerprint(token: &str) -> u64 {
    let mut hasher = std::collections::hash_map::DefaultHasher::new();
    token.hash(&mut hasher);
    hasher.finish()
}

/// Per-address failure counters. Behind one `Mutex`, like [`crate::login_throttle`]: it is touched
/// on failures only, never on the path of a request that is signed in.
pub struct AddressGuard {
    entries: Mutex<HashMap<String, Attempts>>,
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
    ///
    /// Checked BEFORE verifying a PIN or badge, so a locked address stops getting the right/wrong
    /// answer it is fishing for.
    pub fn locked_for(&self, address: &str) -> Option<u64> {
        self.locked_for_at(address, Instant::now())
    }

    /// A wrong PIN or badge from `address`.
    pub fn record_guess(&self, address: &str) {
        self.record_guess_at(address, Instant::now())
    }

    /// A session credential from `address` that did not resolve. Returns `true` the first time
    /// this token is seen in the window, so the caller logs each forged token once and a till
    /// repeating its dead session does not flood the log.
    pub fn record_rejected_session(&self, address: &str, token: &str) -> bool {
        self.record_rejected_session_at(address, token, Instant::now())
    }

    fn locked_for_at(&self, address: &str, now: Instant) -> Option<u64> {
        let mut entries = self.lock();
        let entry = entries.get(address)?;
        if entry.is_locked(now) {
            let until = entry.locked_until?;
            return Some((until - now).as_secs().max(1));
        }
        if entry.is_stale(now) {
            entries.remove(address);
        }
        None
    }

    fn record_guess_at(&self, address: &str, now: Instant) {
        let mut entries = self.lock();
        let entry = Self::current(&mut entries, address, now);
        if entry.is_locked(now) {
            return;
        }
        entry.guesses += 1;
        if entry.guesses >= MAX_GUESSES {
            entry.lock(now);
        }
    }

    fn record_rejected_session_at(&self, address: &str, token: &str, now: Instant) -> bool {
        let mut entries = self.lock();
        let entry = Self::current(&mut entries, address, now);
        let print = fingerprint(token);
        if entry.is_locked(now) || entry.sessions.len() >= MAX_FORGED_SESSIONS {
            return !entry.sessions.contains(&print);
        }
        let first_sighting = entry.sessions.insert(print);
        if entry.sessions.len() >= MAX_FORGED_SESSIONS {
            entry.lock(now);
        }
        first_sighting
    }

    /// The live entry of `address`, started afresh if what it held is stale. A NEW address first
    /// sweeps the stale ones once the map is at [`MAX_TRACKED`].
    fn current<'a>(
        entries: &'a mut HashMap<String, Attempts>,
        address: &str,
        now: Instant,
    ) -> &'a mut Attempts {
        if !entries.contains_key(address) && entries.len() >= MAX_TRACKED {
            entries.retain(|_, attempts| !attempts.is_stale(now));
        }
        let entry = entries
            .entry(address.to_string())
            .or_insert_with(|| Attempts::new(now));
        if entry.is_stale(now) {
            *entry = Attempts::new(now);
        }
        entry
    }

    /// A poisoned mutex must not take the login down: recover the map and carry on.
    fn lock(&self) -> std::sync::MutexGuard<'_, HashMap<String, Attempts>> {
        self.entries.lock().unwrap_or_else(|e| e.into_inner())
    }

    #[cfg(test)]
    fn tracked(&self) -> usize {
        self.lock().len()
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
        assert!(
            g.locked_for_at(SHOP, now).is_none(),
            "one short of the limit"
        );
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
        assert!(
            g.locked_for_at(SHOP, now).is_none(),
            "one short of the limit"
        );
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
        assert!(
            g.tracked() <= 1,
            "every stale address is gone: {}",
            g.tracked()
        );
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
