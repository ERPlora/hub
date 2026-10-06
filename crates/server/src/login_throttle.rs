//! Brute-force guard for the PIN login (hub#329).
//!
//! A PIN is 4 digits — 10,000 combinations — and the hub is reachable on the public internet
//! (`{slug}.erplora.com`). `runtime/src/identity.rs` states it outright: the real security of the
//! PIN depends on device-trust **plus rate-limiting on login**; argon2id only makes an offline
//! attack expensive. This module is that second half.
//!
//! Shape of the guard: per identity, N consecutive failures ⇒ locked for a fixed window; a
//! success clears the counter. A door where even an accepted try tells the caller something (the
//! own-PIN change, hub#2499) counts **attempts** instead: every one spends the budget, and since no
//! success ever clears it, they are forgotten once [`LOCK_WINDOW`] has passed since the first one.
//! In-memory on purpose — the lock protects a login that only this
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
    /// First attempt of the current window, for the identities counted with
    /// [`LoginThrottle::record_attempt`]. `None` for the login doors, whose counter a success clears.
    window_start: Option<Instant>,
}

impl Attempts {
    /// The attempt window closed without a lock: nothing left to hold against the identity.
    fn window_elapsed(&self, now: Instant) -> bool {
        self.window_start
            .is_some_and(|start| now.duration_since(start) >= LOCK_WINDOW)
    }
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
        Self {
            entries: Mutex::new(HashMap::new()),
        }
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

    /// Records an attempt that spends the budget **whatever its outcome** (hub#2499): the own-PIN
    /// change, where an accepted number is as informative as a refused one. Same threshold and lock
    /// as [`Self::record_failure`]; never cleared by a success, only by the window running out.
    pub fn record_attempt(&self, identity: &str) {
        self.record_attempt_at(identity, Instant::now())
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

    fn record_attempt_at(&self, identity: &str, now: Instant) {
        let mut entries = self.lock();
        let entry = entries.entry(identity.to_string()).or_default();
        if entry.window_elapsed(now) {
            *entry = Attempts::default();
        }
        entry.window_start.get_or_insert(now);
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
        assert!(
            t.locked_for("Admin").is_none(),
            "the counter restarted from zero"
        );
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
        assert!(
            t.locked_for_at("Admin", after).is_none(),
            "window elapsed → unlocked"
        );
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
        assert!(
            t.locked_for("Cashier").is_none(),
            "brute-forcing one name cannot DoS the shop"
        );
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

    #[test]
    fn attempts_lock_at_the_same_threshold() {
        let t = LoginThrottle::new();
        let now = Instant::now();
        for _ in 0..MAX_FAILURES - 1 {
            t.record_attempt_at("pin_change:u-1", now);
            assert!(t.locked_for_at("pin_change:u-1", now).is_none());
        }
        t.record_attempt_at("pin_change:u-1", now);
        assert!(t.locked_for_at("pin_change:u-1", now).is_some());
    }

    /// hub#2499: an attempt counts whatever its outcome, so nothing clears the counter but time.
    /// Without a window, somebody changing their PIN once a month would hit the lock on the fifth.
    #[test]
    fn attempts_older_than_the_window_are_forgotten() {
        let t = LoginThrottle::new();
        let start = Instant::now();
        for _ in 0..MAX_FAILURES - 1 {
            t.record_attempt_at("pin_change:u-1", start);
        }
        let later = start + LOCK_WINDOW + Duration::from_secs(1);
        t.record_attempt_at("pin_change:u-1", later);
        assert!(
            t.locked_for_at("pin_change:u-1", later).is_none(),
            "the four old attempts fell out of the window"
        );
    }

    /// The window starts at the first attempt: spacing them out inside it does not reset it.
    #[test]
    fn attempts_inside_the_window_add_up() {
        let t = LoginThrottle::new();
        let start = Instant::now();
        let step = LOCK_WINDOW / (MAX_FAILURES + 1);
        for i in 0..MAX_FAILURES {
            t.record_attempt_at("pin_change:u-1", start + step * i);
        }
        let last = start + step * (MAX_FAILURES - 1);
        assert!(t.locked_for_at("pin_change:u-1", last).is_some());
    }

    /// The window runs from the FIRST attempt, not from the latest: a later attempt does not push
    /// the old ones forward. Here two attempts open the window, and the rest arrive just after it
    /// closed — a fresh window that holds three, not five.
    #[test]
    fn the_window_runs_from_the_first_attempt() {
        let t = LoginThrottle::new();
        let start = Instant::now();
        t.record_attempt_at("pin_change:u-1", start);
        t.record_attempt_at("pin_change:u-1", start + LOCK_WINDOW / 2);
        let next = start + LOCK_WINDOW + Duration::from_secs(1);
        for _ in 0..MAX_FAILURES - 2 {
            t.record_attempt_at("pin_change:u-1", next);
        }
        assert!(
            t.locked_for_at("pin_change:u-1", next).is_none(),
            "the first two attempts fell out of the window that started with them"
        );
    }
}
