//! Test-only capture of everything that reaches `tracing` — shared by every log assertion in
//! this crate.
//!
//! # Why this is not four copies of eight lines (hub#1796)
//!
//! `tracing` caches one `Interest` per callsite, **globally and once**: the first time a given
//! `warn!`/`info!` runs, `tracing-core` asks the dispatchers it can see whether they care, and
//! stores the answer for the rest of the process. In `tracing-core` 0.1.36 that first
//! registration takes a shortcut when only one dispatcher is registered
//! (`callsite::register` → `rebuild_callsite_interest` → `Rebuilder::JustOne` →
//! `dispatcher::get_default`) and asks **the dispatcher of the calling thread**.
//!
//! `with_default` is thread-local, so a test thread that installs no subscriber answers
//! `NoSubscriber::register_callsite` = `Interest::never()`, and from then on the macro drops
//! that event *before any subscriber sees it* — including the one another test installed
//! around the same callsite. The capture comes back empty and the assertion fails on a commit
//! that broke nothing.
//!
//! That is not hypothetical: `assistant::tests::a_refused_turn_is_not_mute_in_the_hub_log`
//! shares its `warn!` with `assistant::tests::translate_done_and_tokens`, which runs it with no
//! subscriber. Whichever thread got there first decided the colour of the whole suite, so
//! `cargo test --workspace` went red three times in 24 h on healthy commits (hub#1791, #1792,
//! #1795), at 22-44 min of runner per rerun.
//!
//! The fix is one line of leverage: park a **global** dispatcher that answers
//! `Interest::sometimes()` to everything. `Entered::current()` falls back to the global when a
//! thread has no scoped default, so a subscriber-less thread can no longer answer `never` —
//! `sometimes` means "ask me every time", which restores the per-thread decision the capture
//! needs. It writes nothing itself (`enabled` is always `false`), so a test that captures
//! nothing still sees nothing.

use std::sync::{Arc, Mutex, Once};

use tracing::level_filters::LevelFilter;
use tracing::subscriber::Interest;
use tracing::{span, Event, Id, Metadata, Subscriber};

/// Captures everything that reaches `tracing` on this thread.
#[derive(Clone, Default)]
pub(crate) struct CapturedLog(Arc<Mutex<Vec<u8>>>);

impl CapturedLog {
    pub(crate) fn text(&self) -> String {
        String::from_utf8_lossy(&self.0.lock().unwrap()).to_string()
    }
}

impl std::io::Write for CapturedLog {
    fn write(&mut self, buf: &[u8]) -> std::io::Result<usize> {
        self.0.lock().unwrap().extend_from_slice(buf);
        Ok(buf.len())
    }

    fn flush(&mut self) -> std::io::Result<()> {
        Ok(())
    }
}

impl<'a> tracing_subscriber::fmt::MakeWriter<'a> for CapturedLog {
    type Writer = Self;

    fn make_writer(&'a self) -> Self::Writer {
        self.clone()
    }
}

/// The global dispatcher that keeps the interest cache honest. It never records anything: its
/// only job is to answer `sometimes` so no callsite is ever cached as `never`, and to hold the
/// global max level at `TRACE` so the macros do not short-circuit on it either.
struct AlwaysAsk;

impl Subscriber for AlwaysAsk {
    fn register_callsite(&self, _: &'static Metadata<'static>) -> Interest {
        Interest::sometimes()
    }

    fn enabled(&self, _: &Metadata<'_>) -> bool {
        false
    }

    fn max_level_hint(&self) -> Option<LevelFilter> {
        Some(LevelFilter::TRACE)
    }

    fn new_span(&self, _: &span::Attributes<'_>) -> Id {
        Id::from_u64(1)
    }

    fn record(&self, _: &Id, _: &span::Record<'_>) {}

    fn record_follows_from(&self, _: &Id, _: &Id) {}

    fn event(&self, _: &Event<'_>) {}

    fn enter(&self, _: &Id) {}

    fn exit(&self, _: &Id) {}
}

static ANCHOR: Once = Once::new();

/// Parks [`AlwaysAsk`] as the global dispatcher, once per test binary.
///
/// Call this before installing a scoped subscriber you intend to read back. It is a no-op if
/// something else already claimed the global slot (`logging::init`, a test shell): any real
/// subscriber answers by level instead of `never`, which is all this needs.
pub(crate) fn anchor_the_interest_cache() {
    ANCHOR.call_once(|| {
        let _ = tracing::subscriber::set_global_default(AlwaysAsk);
    });
}

/// Runs `run` under a subscriber scoped to this thread and returns what reached the log.
pub(crate) fn captured(run: impl FnOnce()) -> String {
    anchor_the_interest_cache();
    let sink = CapturedLog::default();
    let subscriber = tracing_subscriber::fmt()
        .with_writer(sink.clone())
        .with_ansi(false)
        .with_max_level(tracing::Level::TRACE)
        .finish();
    tracing::subscriber::with_default(subscriber, run);
    sink.text()
}

#[cfg(test)]
mod tests {
    use super::*;

    /// **The flake of hub#1796, pinned to its losing order.**
    ///
    /// A thread with no subscriber reaches the callsite first, from *inside* the capture — the
    /// exact window the scheduler used to hit by accident. Without the global anchor the
    /// capture comes back as `""` every time; the assertion below is what turns that from a
    /// coin flip into a build error.
    #[test]
    fn a_callsite_first_touched_by_a_subscriberless_thread_still_reaches_the_capture() {
        fn canary() {
            tracing::warn!("hub#1796 canary");
        }

        let log = captured(|| {
            // `with_default` is thread-local: the child inherits no subscriber.
            std::thread::spawn(canary).join().unwrap();
            canary();
        });

        assert!(
            log.contains("hub#1796 canary"),
            "a callsite registered by a subscriber-less thread must still reach the capture, \
             or every log assertion in this crate is one scheduler decision away from red: \
             {log:?}"
        );
    }

    /// The anchor must not turn the capture into a firehose: a thread that captures only sees
    /// what ran inside its own scope, and a thread that does not capture still logs nothing.
    #[test]
    fn the_anchor_records_nothing_of_its_own() {
        anchor_the_interest_cache();
        tracing::warn!("hub#1796 outside any capture");

        let log = captured(|| {
            tracing::warn!("hub#1796 inside the capture");
        });

        assert!(log.contains("inside the capture"), "{log:?}");
        assert!(
            !log.contains("outside any capture"),
            "the capture must not pick up events emitted before it started: {log:?}"
        );
    }
}
