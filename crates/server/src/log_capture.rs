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
//! The fix is one line of leverage: park a **global** dispatcher and never let it die.
//! `rebuild_callsite_interest` folds the answers of every *live* registrar
//! (`tracing-core-0.1.36/src/callsite.rs:490`) and falls back to `Interest::never()` when there
//! is none (`interest.unwrap_or_else(Interest::never)`); a scoped `set_default` subscriber is
//! dropped at the end of its test, so the losing window is a callsite whose first `register()`
//! finds the registrar list empty or stale. A global dispatcher lives for the whole process, so
//! that list is never empty again.
//!
//! What is load-bearing here was **measured, not assumed** (mutation run, 2026-09-11): only the
//! anchor's *existence* is. Answering `Interest::never()` instead of `sometimes()`, letting
//! `enabled` return `true`, or dropping `max_level_hint` to `OFF` all leave the suite green,
//! because `Dispatch::new` rebuilds the whole cache whenever a capture installs its subscriber
//! and `never.and(sometimes)` is `sometimes`. Those answers stay as written anyway: they are the
//! honest semantics of "ask me every time, I record nothing", and they are what keeps the fix
//! standing if `tracing-core` ever stops rebuilding on a scoped `set_default`.

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
/// Deliberately **private**: [`capture_scope`] is the only caller, so no capture in this crate
/// can be written that forgets to anchor. It is a no-op if something else already claimed the
/// global slot (`logging::init`, a test shell): any real subscriber is alive for the whole
/// process too, which is all this needs.
fn anchor_the_interest_cache() {
    ANCHOR.call_once(|| {
        let _ = tracing::subscriber::set_global_default(AlwaysAsk);
    });
}

/// Installs a capture on this thread and hands back the sink plus the guard that keeps it
/// installed; the capture ends when the guard is dropped.
///
/// Use this when the code under test is `async` and cannot be wrapped in a closure. Everything
/// else should reach for [`captured`], which is this function with the guard handled for you.
pub(crate) fn capture_scope() -> (CapturedLog, tracing::subscriber::DefaultGuard) {
    anchor_the_interest_cache();
    let sink = CapturedLog::default();
    let subscriber = tracing_subscriber::fmt()
        .with_writer(sink.clone())
        .with_ansi(false)
        .with_max_level(tracing::Level::TRACE)
        .finish();
    let guard = tracing::subscriber::set_default(subscriber);
    (sink, guard)
}

/// Runs `run` under a subscriber scoped to this thread and returns what reached the log.
pub(crate) fn captured(run: impl FnOnce()) -> String {
    let (sink, guard) = capture_scope();
    run();
    drop(guard);
    sink.text()
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Set in the child process spawned by [`passes_in_a_fresh_process`], so it runs the
    /// observation instead of spawning a child of its own.
    const IN_CHILD: &str = "ERPLORA_LOG_CAPTURE_ISOLATED";

    /// Re-runs `test_name` alone in a child process and reports whether it passed.
    ///
    /// The interest cache and the global dispatcher are **process-wide and set once**, so an
    /// assertion about them is only honest in a process where nothing else has touched them.
    /// Measured on 2026-09-11: without this, deleting the `anchor_the_interest_cache()` call
    /// left the whole suite green — a sibling test had already parked the anchor, so the guard
    /// below passed while the flake was back. A guard that only fails when it runs alone is not
    /// a guard; CI runs the binary whole.
    fn passes_in_a_fresh_process(test_name: &str) -> bool {
        std::process::Command::new(std::env::current_exe().expect("the path of this test binary"))
            .args([test_name, "--exact", "--test-threads=1", "--nocapture"])
            .env(IN_CHILD, "1")
            .status()
            .expect("re-running this test in a child process")
            .success()
    }

    /// **The flake of hub#1796, pinned to its losing order.**
    ///
    /// A thread with no subscriber reaches the callsite first, from *inside* the capture — the
    /// exact window the scheduler used to hit by accident. Without the global anchor the capture
    /// comes back as `""` every time; the assertion below is what turns that from a coin flip
    /// into a build error.
    #[test]
    fn a_callsite_first_touched_by_a_subscriberless_thread_still_reaches_the_capture() {
        const NAME: &str = concat!(
            "log_capture::tests::",
            "a_callsite_first_touched_by_a_subscriberless_thread_still_reaches_the_capture"
        );

        if std::env::var_os(IN_CHILD).is_none() {
            assert!(
                passes_in_a_fresh_process(NAME),
                "the capture stopped surviving a subscriber-less thread; the child process \
                 above printed the failure"
            );
            return;
        }

        fn canary() {
            tracing::warn!("hub#1796 canary");
        }

        let log = captured(|| {
            // `set_default` is thread-local: the child thread inherits no subscriber.
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
        let before = captured(|| {});
        tracing::warn!("hub#1796 outside any capture");

        let log = captured(|| {
            tracing::warn!("hub#1796 inside the capture");
        });

        assert!(before.is_empty(), "{before:?}");
        assert!(log.contains("inside the capture"), "{log:?}");
        assert!(
            !log.contains("outside any capture"),
            "the capture must not pick up events emitted before it started: {log:?}"
        );
    }

    /// `capture_scope` is the guard-shaped door the async tests use; it has to hand back the
    /// sink that is actually wired to the subscriber it installed.
    #[test]
    fn the_guard_shaped_door_captures_too() {
        let (sink, guard) = capture_scope();
        tracing::warn!("hub#1796 through the guard");
        drop(guard);

        let log = sink.text();
        assert!(log.contains("through the guard"), "{log:?}");
    }
}
