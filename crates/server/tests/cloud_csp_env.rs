//! `HUB_CSP` may REPLACE the policy; it may not remove it (hub#708).
//!
//! **Its own test binary, and one test.** Env vars are process-global, so a test that writes one
//! cannot share a process with tests that read it — same reasoning as `device_trust_env.rs`, and
//! the same shape of bug: a switch nobody set, defaulting to the unsafe side, green everywhere
//! because every other test built the config by hand.
//!
//! The precise seam: `ServeConfig::from_env` used to hand back `Option<String>` straight from the
//! variable, so "nobody set it" and "serve the app naked" were the same state. Now the variable is
//! an override with a floor under it.
use erplora_server::{default_csp, resolve_csp, ServeConfig};

/// `unsafe` since Rust 2024; what makes it sound here is the file, not the call.
fn set_env(value: Option<&str>) {
    match value {
        Some(v) => unsafe { std::env::set_var("HUB_CSP", v) },
        None => unsafe { std::env::remove_var("HUB_CSP") },
    }
}

#[test]
fn the_config_reads_the_variable_and_defaults_to_a_real_policy() {
    // The policy follows `HUB_CLOUD_API_URL`, so the expectation has to be computed the same way
    // the config does — from whatever Cloud this process is pointed at.
    let expected = || default_csp(&erplora_server::HubConfig::from_env().cloud_base_url);

    // No variable: the shape of every hub in the fleet today, and the one that has to be safe.
    set_env(None);
    assert_eq!(
        ServeConfig::from_env().csp,
        expected(),
        "a deployment that never heard of HUB_CSP serves the app with no policy at all — the bug"
    );

    // Empty, and whitespace-only: what a provisioner writes when a template renders a missing
    // value. Fails to the policy, never past it.
    for blank in ["", "   ", "\n"] {
        set_env(Some(blank));
        assert_eq!(
            ServeConfig::from_env().csp,
            expected(),
            "a blank HUB_CSP ({blank:?}) silently disarmed the policy"
        );
    }

    // The deliberate word, honoured — otherwise there is no way to relax the policy for a hub that
    // genuinely needs it, and the escape hatch would be "comment out the layer".
    let custom = "default-src 'self'; img-src 'self' https://cdn.example";
    set_env(Some(custom));
    assert_eq!(
        ServeConfig::from_env().csp,
        custom,
        "an explicit HUB_CSP has to reach the config, or the override is decorative"
    );

    // Surrounding whitespace is the operator's, not the policy's.
    set_env(Some("  default-src 'self'  "));
    assert_eq!(ServeConfig::from_env().csp, "default-src 'self'");

    set_env(None);
}

#[test]
fn a_policy_the_browser_could_never_receive_falls_back_instead_of_disappearing() {
    // A header value cannot carry a control byte. A `HUB_CSP` with a newline in it — a YAML block
    // scalar that wrapped, the usual way this happens — used to be logged and dropped, leaving the
    // hub bare, which is the one outcome this issue is about. Resolution happens before the header
    // is built, so the runtime never has to choose between panicking and serving nothing.
    //
    // Note what is NOT on this list: a stray accent. `HeaderValue` accepts bytes 0x80–0xFF, so
    // `'sélf'` travels to the browser intact and is rejected THERE, as a policy that parses to
    // nothing useful. Guarding it here would be guarding a case that does not exist.
    const CLOUD: &str = "https://erplora.com";
    for malformed in [
        "default-src 'self'\nimg-src *",
        "default-src 'self'\rimg-src *",
        "default-src 'self'\u{0}",
    ] {
        assert_eq!(
            resolve_csp(Some(malformed.to_string()), CLOUD),
            default_csp(CLOUD),
            "a malformed HUB_CSP ({malformed:?}) left the hub with no policy"
        );
    }
}
