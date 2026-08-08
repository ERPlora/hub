//! `HUB_DEVICE_TRUST` actually reaches the config (hub#330).
//!
//! `parse_device_trust` is unit-tested next to itself, but a pure function nobody calls is worth
//! nothing: the seam that matters is `HubConfig::from_env_with_auth` **reading that variable and
//! putting the answer in `device_trust_enforce`**. Wiring it to a constant would leave every other
//! test in the tree green — the door tests build `HubConfig` by hand on purpose — while every
//! deployed hub silently lost the gate. That is exactly the shape of the bug this issue closes.
//!
//! **Its own test binary, and one test.** Env vars are process-global, so a test that writes one
//! cannot share a process with tests that read it. Here there is nothing else to race.
use erplora_server::{AuthMode, HubConfig};

/// Set (or clear) an env var. `unsafe` since Rust 2024 for the reason above; the isolation that
/// makes it sound is the file, not the call.
fn set_env(value: Option<&str>) {
    match value {
        Some(v) => unsafe { std::env::set_var("HUB_DEVICE_TRUST", v) },
        None => unsafe { std::env::remove_var("HUB_DEVICE_TRUST") },
    }
}

#[test]
fn the_config_reads_the_variable_and_defaults_to_armed() {
    // No variable: the shape of every hub in the fleet today, and the one that has to be safe.
    set_env(None);
    assert!(
        HubConfig::from_env_with_auth(AuthMode::Session).device_trust_enforce,
        "a deployment that never heard of HUB_DEVICE_TRUST gets the gate"
    );

    // The deliberate word, honoured — otherwise there is no way back out of the gate.
    set_env(Some("off"));
    assert!(
        !HubConfig::from_env_with_auth(AuthMode::Session).device_trust_enforce,
        "`off` has to reach the config, or the switch is decorative"
    );

    // The spelling that already existed keeps working after the default flipped under it.
    set_env(Some("enforce"));
    assert!(HubConfig::from_env_with_auth(AuthMode::Session).device_trust_enforce);

    // A typo is not a way to open the PIN door.
    set_env(Some("nope"));
    assert!(
        HubConfig::from_env_with_auth(AuthMode::Session).device_trust_enforce,
        "an unknown value must fail closed"
    );

    set_env(None);
}
