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
    used: u32,
}

#[derive(Debug, Default)]
pub struct RateLimiter {
    windows: Mutex<HashMap<String, Window>>,
}

impl RateLimiter {
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
        let window = windows.entry(key).or_insert(Window { started: now, used: 0 });
        if now.duration_since(window.started) >= period {
            window.started = now;
            window.used = 0;
        }
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
}
