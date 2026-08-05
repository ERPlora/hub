//! Brute-force guard for the PIN login (hub#329).
//!
//! A PIN is 4 digits — 10,000 combinations — and the hub is reachable on the public internet
//! (`{slug}.erplora.com`). `runtime/src/identity.rs` states it outright: the real security of the
//! PIN depends on device-trust **plus rate-limiting on login**; argon2id only makes an offline
//! attack expensive. This module is that second half.
//!
//! Shape of the guard: per identity, N consecutive failures ⇒ locked for a fixed window; a
//! success clears the counter. In-memory on purpose — the lock protects a login that only this
//! process serves, and a restart is not a free pass (an attacker cannot trigger one).
use std::collections::HashMap;
use std::sync::Mutex;
use std::time::{Duration, Instant};

/// Consecutive failures before the identity is locked. Five is enough slack for a mistyped PIN
/// at the counter and still turns 10,000 tries into days of waiting.
pub const MAX_FAILURES: u32 = 5;
/// How long a locked identity stays locked.
pub const LOCK_WINDOW: Duration = Duration::from_secs(300);

#[derive(Default)]
struct Attempts {
    failures: u32,
    /// When the current lock expires. `None` = not locked.
    locked_until: Option<Instant>,
}

/// Per-identity failure counters. Cheap enough to keep behind one `Mutex`: it is touched once per
/// login attempt, never on the hot path of the POS.
pub struct LoginThrottle {
    entries: Mutex<HashMap<String, Attempts>>,
}

impl Default for LoginThrottle {
    fn default() -> Self {
        Self::new()
    }
}

impl LoginThrottle {
    pub fn new() -> Self {
        Self { entries: Mutex::new(HashMap::new()) }
    }

    /// Is this identity locked right now? `Some(secs)` = locked, and how long to wait.
    ///
    /// Checked BEFORE verifying the PIN: otherwise a locked identity would still leak
    /// "right/wrong" through the response, which is the very signal the attacker wants.
    pub fn locked_for(&self, identity: &str) -> Option<u64> {
        self.locked_for_at(identity, Instant::now())
    }

    /// Records a failed attempt; locks the identity once it reaches [`MAX_FAILURES`].
    pub fn record_failure(&self, identity: &str) {
        self.record_failure_at(identity, Instant::now())
    }

    /// Clears the counter after a successful login: an honest user who mistyped twice starts
    /// fresh, so the guard never accumulates against normal use.
    pub fn record_success(&self, identity: &str) {
        let mut entries = self.lock();
        entries.remove(identity);
    }

    // ── Same logic with an explicit clock, so the tests below can prove expiry ──

    fn locked_for_at(&self, identity: &str, now: Instant) -> Option<u64> {
        let mut entries = self.lock();
        let entry = entries.get_mut(identity)?;
        match entry.locked_until {
            Some(until) if until > now => Some((until - now).as_secs().max(1)),
            // Window elapsed: forget the lock AND the counter, or the next single failure would
            // re-lock immediately and the window would be permanent in practice.
            Some(_) => {
                entries.remove(identity);
                None
            }
            None => None,
        }
    }

    fn record_failure_at(&self, identity: &str, now: Instant) {
        let mut entries = self.lock();
        let entry = entries.entry(identity.to_string()).or_default();
        entry.failures += 1;
        if entry.failures >= MAX_FAILURES {
            entry.locked_until = Some(now + LOCK_WINDOW);
        }
    }

    /// A poisoned mutex must not take the login down: recover the map and carry on. Failing
    /// closed here would lock every user out of the shop over a panic in an unrelated attempt.
    fn lock(&self) -> std::sync::MutexGuard<'_, HashMap<String, Attempts>> {
        self.entries.lock().unwrap_or_else(|e| e.into_inner())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn locks_only_after_the_threshold() {
        let t = LoginThrottle::new();
        for _ in 0..MAX_FAILURES - 1 {
            t.record_failure("Admin");
            assert!(t.locked_for("Admin").is_none());
        }
        t.record_failure("Admin");
        assert!(t.locked_for("Admin").is_some());
    }

    #[test]
    fn a_success_clears_the_counter() {
        let t = LoginThrottle::new();
        for _ in 0..MAX_FAILURES - 1 {
            t.record_failure("Admin");
        }
        t.record_success("Admin");
        t.record_failure("Admin");
        assert!(t.locked_for("Admin").is_none(), "the counter restarted from zero");
    }

    #[test]
    fn the_lock_expires_and_forgets_the_counter() {
        let t = LoginThrottle::new();
        let now = Instant::now();
        for _ in 0..MAX_FAILURES {
            t.record_failure_at("Admin", now);
        }
        assert!(t.locked_for_at("Admin", now).is_some());
        let after = now + LOCK_WINDOW + Duration::from_secs(1);
        assert!(t.locked_for_at("Admin", after).is_none(), "window elapsed → unlocked");
        // And a single new failure must not re-lock: the counter was forgotten with the lock.
        t.record_failure_at("Admin", after);
        assert!(t.locked_for_at("Admin", after).is_none());
    }

    #[test]
    fn identities_do_not_share_a_counter() {
        let t = LoginThrottle::new();
        for _ in 0..MAX_FAILURES {
            t.record_failure("Admin");
        }
        assert!(t.locked_for("Admin").is_some());
        assert!(t.locked_for("Cashier").is_none(), "brute-forcing one name cannot DoS the shop");
    }

    #[test]
    fn reports_a_positive_retry_hint() {
        let t = LoginThrottle::new();
        for _ in 0..MAX_FAILURES {
            t.record_failure("Admin");
        }
        let secs = t.locked_for("Admin").expect("locked");
        assert!(secs > 0 && secs <= LOCK_WINDOW.as_secs());
    }
}
