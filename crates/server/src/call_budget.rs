//! A rolling-window allowance for the calls this hub makes to the control plane.
//!
//! Extracted from `fiscal_certificate.rs` when hub#1435 retired the delegated certificate: the
//! fetch it bounded is gone, the bound is not. [`crate::gateway_enrolment`] uses it for exactly the
//! same reason the certificate refetch did, and any future converge-by-retrying loop will too.
//!
//! # Why a budget at all, and why it is a safety property
//!
//! Every one of these endpoints is quota'd per hub on the SaaS side. A loop that fires unbounded
//! does not merely waste requests: it spends the hub's whole allowance and takes away **the one
//! call that would have fixed the thing it is retrying**. Being throttled is not a slowdown here —
//! it is the hub locking itself out of its own repair. So each caller keeps its own ceiling well
//! under the control plane's, and asserts the relation with a `const` assert so the COMPILER
//! checks it rather than a test somebody can skip.
//!
//! Rolling rather than fixed buckets, on purpose: a fixed hourly bucket lets a hub spend the whole
//! allowance at 10:59 and the whole next one at 11:01, which is exactly the burst the control plane
//! is protecting itself from.

use std::collections::VecDeque;
use std::sync::Mutex;
use std::time::{Duration, Instant};

/// A rolling-window allowance, shared by every trigger of the thing it bounds.
#[derive(Debug)]
pub struct CallBudget {
    max: usize,
    window: Duration,
    /// When each spend happened, oldest first. Bounded by `max`, so it never grows.
    spent: Mutex<VecDeque<Instant>>,
}

impl CallBudget {
    pub fn new(max: usize, window: Duration) -> Self {
        Self {
            max,
            window,
            spent: Mutex::new(VecDeque::new()),
        }
    }

    /// `max` calls per rolling hour.
    pub fn hourly(max: usize) -> Self {
        Self::new(max, Duration::from_secs(3600))
    }

    /// Takes one unit of budget if there is one. `false` = «not now» — never an error and never a
    /// wait: a pass that is skipped is picked up by the next tick.
    ///
    /// `now` is a parameter so the window is testable without sleeping for an hour.
    pub fn try_spend(&self, now: Instant) -> bool {
        let mut spent = match self.spent.lock() {
            Ok(guard) => guard,
            // A panic in another thread must not disable this hub's converge loops; the worst case
            // of continuing is one extra request.
            Err(poisoned) => poisoned.into_inner(),
        };
        while spent
            .front()
            .is_some_and(|t| now.duration_since(*t) >= self.window)
        {
            spent.pop_front();
        }
        if spent.len() >= self.max {
            return false;
        }
        spent.push_back(now);
        true
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The window ROLLS: budget spent an hour ago is budget again. A hub whose converge loop is
    /// needed twice in a day must be able to run twice.
    #[test]
    fn the_budget_window_rolls_instead_of_resetting_on_the_hour() {
        let budget = CallBudget::new(2, Duration::from_secs(60));
        let start = Instant::now();
        assert!(budget.try_spend(start));
        assert!(budget.try_spend(start + Duration::from_secs(1)));
        assert!(!budget.try_spend(start + Duration::from_secs(2)), "agotado");
        // Justo antes de que expire el primero: sigue agotado.
        assert!(!budget.try_spend(start + Duration::from_secs(59)));
        // Cumplida la ventana del PRIMERO vuelve a haber sitio, y solo para uno: el segundo se
        // gastó un segundo más tarde y cumple su ventana un segundo más tarde. Eso es lo que
        // distingue una ventana deslizante de un cubo horario, que los liberaría a la vez.
        assert!(budget.try_spend(start + Duration::from_secs(60)));
        assert!(!budget.try_spend(start + Duration::from_secs(60)));
        // Y al vencer el segundo, otro más.
        assert!(budget.try_spend(start + Duration::from_secs(61)));
    }

    /// A budget of zero refuses everything instead of letting one through — the arm a caller relies
    /// on to prove that «out of budget» skips the pass rather than erroring.
    #[test]
    fn an_exhausted_budget_never_lets_one_through() {
        let budget = CallBudget::new(0, Duration::from_secs(3600));
        assert!(!budget.try_spend(Instant::now()));
    }

    /// The ceiling is the ceiling: a storm of triggers spends `max` and no more.
    #[test]
    fn a_storm_of_triggers_spends_the_ceiling_and_stops() {
        let budget = CallBudget::hourly(6);
        let now = Instant::now();
        let spent = (0..100).filter(|_| budget.try_spend(now)).count();
        assert_eq!(spent, 6, "el presupuesto es el techo, no una sugerencia");
    }
}
