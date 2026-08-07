//! The «something is wrong with our certificate» signal (ADR-0202 §2 point 4 — hub#318).
//!
//! Third of the three refetch triggers. The other two live where the answer already is: boot and
//! the heartbeat both run in `erplora-server`, which is the crate that talks to the control plane.
//! This one does not: mTLS against the AEAT fails **inside the `verifactu` native engine**, four
//! layers below, in a crate that has no cloud credential and must never grow one.
//!
//! So the engine does not fetch anything. It **asks**, through this signal, and the server's
//! refetch service is what decides whether to spend a request. That is the whole point of the
//! split: the layer that discovers the problem is not the layer that holds the machine token.
//!
//! # Why a flag and not a queue
//!
//! **Requests coalesce, on purpose.** A TLS failure does not arrive alone: the contingency queue
//! drains many records per pass, and every one of them fails the same handshake against the same
//! authority. A queue would turn one broken certificate into one refetch per stranded invoice, and
//! the control plane budgets that endpoint at **20/h per hub** (`architecture/saas/verifactu-gateway.md`
//! §2.4 point 6). Burning the budget is not a slowdown: it is the hub losing the one call that
//! could have fixed the certificate. N requests between two reads therefore mean exactly ONE
//! refetch — they are all asking for the same thing.
//!
//! Same shape as [`crate::error_registry`] and for the same reason: the runtime raises the fact,
//! the host decides what to do about it, and nothing below the host knows the Cloud exists.

use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::OnceLock;

use tokio::sync::Notify;

/// A pending «refetch the delegated certificate» request.
///
/// One per process in production ([`RefetchSignal::global`]); constructible so tests own theirs.
#[derive(Debug, Default)]
pub struct RefetchSignal {
    /// Whether somebody asked since the last read. A BOOL, not a counter: see the module docs.
    pending: AtomicBool,
    /// Wakes the reader so a failure converges now instead of at the next heartbeat.
    notify: Notify,
}

impl RefetchSignal {
    pub fn new() -> Self {
        Self::default()
    }

    /// The process-wide signal: what `verifactu` raises and what the server's refetch service
    /// reads. Lazy, so a binary that never touches certificates never allocates it.
    pub fn global() -> &'static RefetchSignal {
        static SIGNAL: OnceLock<RefetchSignal> = OnceLock::new();
        SIGNAL.get_or_init(RefetchSignal::new)
    }

    /// Ask for a refetch.
    ///
    /// **Never blocks and never panics**: it is called from the error path of a fiscal
    /// transmission, where the only thing that matters is that the invoice keeps its place in the
    /// contingency queue. Asking twice is asking once (see the module docs).
    pub fn request(&self) {
        self.pending.store(true, Ordering::Release);
        self.notify.notify_one();
    }

    /// Consumes the pending request, if there is one. `true` means «somebody asked, and you are
    /// the one serving it» — the next call answers `false` until somebody asks again.
    pub fn take(&self) -> bool {
        self.pending.swap(false, Ordering::AcqRel)
    }

    /// Waits until there is a request and consumes it.
    ///
    /// Checks the flag BEFORE waiting: a request that arrived while the reader was busy installing
    /// the previous one must not be lost. That is the failure that would hurt most — the one
    /// refetch nobody asks for again, because the queue already gave up on those records.
    ///
    /// ⚠️ **That first check is a belt, not the braces, and no test can tell.** `notify_one` stores
    /// a permit when nobody is waiting, so the loop would also be correct with the check after the
    /// `await` — mutation testing flags moving it as an equivalent mutant. It stays because
    /// correctness here should not rest on one detail of `Notify`'s permit semantics: it is
    /// deliberate defence, not dead code, and it is not to be «simplified» away.
    pub async fn wait(&self) {
        loop {
            if self.take() {
                return;
            }
            self.notify.notified().await;
        }
    }
}

/// Asks the process-wide signal for a refetch — what the `verifactu` engine calls when the AEAT
/// refuses our TLS client certificate.
pub fn request() {
    RefetchSignal::global().request();
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn nothing_is_pending_until_somebody_asks() {
        let signal = RefetchSignal::new();
        assert!(!signal.take());
    }

    #[test]
    fn one_request_is_served_once() {
        let signal = RefetchSignal::new();
        signal.request();
        assert!(signal.take(), "el que sirve tiene que verla");
        assert!(!signal.take(), "y no puede servir dos veces la misma");
    }

    /// 🔒 **The budget guard, at its source.** A broken certificate fails the handshake for every
    /// record the contingency queue drains, so the requests arrive by the hundred. If each one
    /// became a refetch, the hub would burn the control plane's 20/h budget in one pass and lose
    /// the very call that fixes the certificate. They are all asking for the same thing, so they
    /// collapse into one.
    #[test]
    fn a_storm_of_requests_collapses_into_a_single_refetch() {
        let signal = RefetchSignal::new();
        for _ in 0..1_000 {
            signal.request();
        }
        assert!(signal.take());
        assert!(!signal.take(), "mil fallos del mismo certificado piden UN refetch");
    }

    /// A request raised while the reader was busy must still be there when it comes back. The lost
    /// wakeup is the dangerous one: those records already failed, so nobody will ask again.
    #[tokio::test]
    async fn a_request_raised_before_the_reader_waits_is_not_lost() {
        let signal = RefetchSignal::new();
        signal.request();
        // Bounded: a `wait` that did not look at the flag first would park forever, and a test
        // that hangs is a test that never reports the bug.
        tokio::time::timeout(std::time::Duration::from_secs(5), signal.wait())
            .await
            .expect("wait() debe volver con una petición ya levantada");
        assert!(!signal.take(), "wait() consume la petición que sirvió");
    }

    #[tokio::test]
    async fn the_reader_wakes_up_when_a_request_arrives_later() {
        let signal = std::sync::Arc::new(RefetchSignal::new());
        let waiter = {
            let signal = signal.clone();
            tokio::spawn(async move { signal.wait().await })
        };
        // Yield so the waiter really parks before the request arrives.
        tokio::task::yield_now().await;
        signal.request();
        tokio::time::timeout(std::time::Duration::from_secs(5), waiter)
            .await
            .expect("el lector debe despertar")
            .unwrap();
    }

    /// The global is the one `verifactu` reaches for, so the free function has to hit it.
    #[test]
    fn the_free_function_raises_the_process_wide_signal() {
        request();
        assert!(RefetchSignal::global().take());
    }
}
