//! Guard on the Android window reserving the top system inset (hub#1719).
//!
//! `MainActivity` opts into edge-to-edge, which on `targetSdk = 36` is not really a choice: from
//! Android 15 the framework lays every window out behind the system bars whether the app asks for
//! it or not. Opting in is half the contract; the other half is reserving the inset, and that half
//! was missing. The WebView therefore started at the physical top of the screen, so **any** page
//! loaded inside it — the sign-in page the SaaS serves, the till, a module — painted over the
//! clock. QA reproduced it twice on 2026-09-09 (emulator `Pixel_10_Pro` / Android 16, APK 1.1.21):
//! the back arrow of the sign-in page landed on top of the system clock, and the search layer of
//! `/m/sales/pos` blacked the status bar out entirely.
//!
//! The reserving itself lives in `SystemBarInsets` (plugin module), where the Kotlin unit tests
//! reach it on every PR. What no unit test can reach is the wiring: `MainActivity` belongs to
//! `:app`, and `:app` cannot even be configured without files that `cargo tauri android build`
//! writes, so nothing compiles it until the release job. Dropping the call would therefore be
//! silent — green PR, green tags, and an APK painting under the clock again — which is exactly the
//! shape of regression this file exists to stop.

use std::path::PathBuf;

fn repo_root() -> PathBuf {
    // `apps/tauri/src-tauri` → up three.
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../..")
        .canonicalize()
        .expect("cannot resolve the repository root")
}

fn read(relative: &str) -> String {
    let path = repo_root().join(relative);
    std::fs::read_to_string(&path).unwrap_or_else(|e| panic!("cannot read {}: {e}", path.display()))
}

/// A file with every comment line removed: a `//` line explaining a rule is not the rule.
fn code_of(source: &str) -> String {
    source
        .lines()
        .filter(|line| {
            let line = line.trim_start();
            !(line.starts_with("//") || line.starts_with("*") || line.starts_with("/*"))
        })
        .collect::<Vec<_>>()
        .join("\n")
}

const MAIN_ACTIVITY: &str =
    "apps/tauri/src-tauri/gen/android/app/src/main/java/com/erplora/app/MainActivity.kt";
const INSETS_HELPER: &str =
    "crates/tauri-plugin-erplora-android/android/src/main/java/com/erplora/android/SystemBarInsets.kt";

/// The activity must actually reserve the strip.
///
/// This is the whole user-visible promise of hub#1719: open the app on a phone and nothing paints
/// over the system clock. It holds for every page because it is applied to the window, not to a
/// template.
#[test]
fn the_activity_reserves_the_top_system_inset() {
    let activity = code_of(&read(MAIN_ACTIVITY));

    assert!(
        activity.contains("SystemBarInsets.applyTopSystemBarPadding"),
        "{MAIN_ACTIVITY} no longer reserves the top system inset: with edge-to-edge on, the \
         WebView goes back to starting at the physical top of the screen and every page it loads \
         paints over the clock (hub#1719)",
    );
}

/// And it must keep opting into edge-to-edge, so exactly ONE party reserves the strip.
///
/// On API 35+ the framework ignores the opt-out, so dropping the call changes nothing there — the
/// padding still applies and the layout is correct. Below API 35 it is not a no-op: the system
/// would inset the window itself, and the padding would then be added on top of an already-inset
/// window, leaving a double margin on every Android 7-14 device. Keeping the call is what makes
/// the two halves of the contract line up across the whole `minSdk = 24` range.
#[test]
fn the_activity_still_opts_into_edge_to_edge() {
    let activity = code_of(&read(MAIN_ACTIVITY));

    assert!(
        activity.contains("enableEdgeToEdge()"),
        "{MAIN_ACTIVITY} stopped calling enableEdgeToEdge(): below API 35 the system would inset \
         the window on its own and the padding would land on top of it, leaving a double margin \
         (hub#1719)",
    );
}

/// The helper must cover the cutout too, and must not swallow the insets.
///
/// Neither is reachable from a JVM unit test — `WindowInsetsCompat` is an `android.jar` stub
/// there — and both fail quietly:
///
/// - asking only for `systemBars()` leaves a notch painting over the content on a cutout device,
///   because the status bar can be hidden while the cutout stays carved into the panel;
/// - returning `CONSUMED` would zero the insets for the WebView below, so the page's own
///   `env(safe-area-inset-*)` rules — the bottom gesture bar, the assistant drawer — would go flat
///   and we would trade a top overlap for a bottom one.
#[test]
fn the_helper_covers_the_cutout_and_passes_the_insets_on() {
    let helper = code_of(&read(INSETS_HELPER));

    assert!(
        helper.contains("systemBars()"),
        "{INSETS_HELPER} must ask for systemBars(): it is the status bar the clock lives in \
         (hub#1719)",
    );
    assert!(
        helper.contains("displayCutout()"),
        "{INSETS_HELPER} must ask for displayCutout() as well: the status bar can be hidden, the \
         notch cannot, and then nothing would reserve the strip (hub#1719)",
    );
    assert!(
        !helper.contains("CONSUMED"),
        "{INSETS_HELPER} must return the insets it received: consuming them zeroes \
         env(safe-area-inset-*) for every page in the WebView, which is how a fixed top overlap \
         becomes a new bottom one (hub#1719)",
    );
}
