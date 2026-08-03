//! Límite de peticiones por principal, en memoria y por proceso.
//!
//! Es una defensa rápida delante del dispatcher. La autoridad funcional sigue en el Runtime; en un
//! despliegue con varias réplicas el edge puede añadir un límite distribuido más estricto.

use std::collections::HashMap;
use std::sync::Mutex;
use std::time::{Duration, Instant};

#[derive(Debug)]
struct Window {
    started: Instant,
    expires_at: Instant,
    last_seen: Instant,
    used: u32,
}

const DEFAULT_MAX_WINDOWS: usize = 4096;

#[derive(Debug)]
pub struct RateLimiter {
    windows: Mutex<HashMap<String, Window>>,
    max_windows: usize,
}

impl Default for RateLimiter {
    fn default() -> Self {
        Self {
            windows: Mutex::new(HashMap::new()),
            max_windows: DEFAULT_MAX_WINDOWS,
        }
    }
}

impl RateLimiter {
    #[cfg(test)]
    fn with_capacity(max_windows: usize) -> Self {
        Self {
            windows: Mutex::new(HashMap::new()),
            max_windows: max_windows.max(1),
        }
    }

    /// Consume una petición. `Err(retry_after_seconds)` significa límite agotado.
    pub fn check(&self, key: impl Into<String>, limit: u32, period: Duration) -> Result<(), u64> {
        self.check_at(key.into(), limit.max(1), period, Instant::now())
    }

    fn check_at(
        &self,
        key: String,
        limit: u32,
        period: Duration,
        now: Instant,
    ) -> Result<(), u64> {
        let mut windows = self.windows.lock().unwrap_or_else(|poisoned| poisoned.into_inner());
        // TTL: las claves vencidas desaparecen aunque nunca vuelvan a consultarse.
        windows.retain(|_, window| now < window.expires_at);
        if !windows.contains_key(&key) && windows.len() >= self.max_windows {
            // Cap duro + LRU: bajo un barrido de claves únicas el uso de memoria permanece acotado.
            if let Some(oldest) = windows
                .iter()
                .min_by_key(|(_, window)| window.last_seen)
                .map(|(key, _)| key.clone())
            {
                windows.remove(&oldest);
            }
        }
        let window = windows.entry(key).or_insert(Window {
            started: now,
            expires_at: now + period,
            last_seen: now,
            used: 0,
        });
        window.last_seen = now;
        if window.used >= limit {
            let elapsed = now.duration_since(window.started);
            let remaining = period.saturating_sub(elapsed);
            return Err(remaining.as_secs().max(1));
        }
        window.used += 1;
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn limits_each_key_and_resets_after_the_window() {
        let limiter = RateLimiter::default();
        let start = Instant::now();
        assert!(limiter.check_at("a".into(), 2, Duration::from_secs(60), start).is_ok());
        assert!(limiter.check_at("a".into(), 2, Duration::from_secs(60), start).is_ok());
        assert_eq!(
            limiter.check_at("a".into(), 2, Duration::from_secs(60), start),
            Err(60)
        );
        assert!(limiter.check_at("b".into(), 2, Duration::from_secs(60), start).is_ok());
        assert!(limiter
            .check_at("a".into(), 2, Duration::from_secs(60), start + Duration::from_secs(60))
            .is_ok());
    }

    #[test]
    fn expires_old_keys_and_evicts_lru_at_the_hard_cap() {
        let limiter = RateLimiter::with_capacity(2);
        let start = Instant::now();
        assert!(limiter.check_at("a".into(), 1, Duration::from_secs(60), start).is_ok());
        assert!(limiter
            .check_at(
                "b".into(),
                1,
                Duration::from_secs(60),
                start + Duration::from_millis(500),
            )
            .is_ok());
        assert!(limiter
            .check_at("c".into(), 1, Duration::from_secs(60), start + Duration::from_secs(1))
            .is_ok());
        let windows = limiter.windows.lock().unwrap();
        assert_eq!(windows.len(), 2);
        assert!(!windows.contains_key("a"), "la clave LRU sale al alcanzar el cap");
        drop(windows);

        assert!(limiter
            .check_at("d".into(), 1, Duration::from_secs(60), start + Duration::from_secs(61))
            .is_ok());
        let windows = limiter.windows.lock().unwrap();
        assert_eq!(windows.len(), 1, "las ventanas vencidas se purgan por TTL");
        assert!(windows.contains_key("d"));
    }
}
