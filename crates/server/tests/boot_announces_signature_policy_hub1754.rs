//! hub#1754: the boot says, once and always, whether this hub verifies module signatures.
//!
//! The policy itself was already right (hub#870). What was missing was **visibility**: it got
//! logged as a side effect of `HubConfig::signature_policy()` being called, and that only happens
//! when something installs. A hub that was just provisioned installs nothing at boot, so the one
//! deployment whose trust ring was pasted a minute ago —the one where a typo matters most— was
//! also the one that started up mute. The failure then surfaced later, in someone else, as an
//! install that would not go through.
//!
//! This pins the wiring, which is the half a unit test cannot see: that the announcement is made
//! from the composition root, unconditionally, and **before** anything tries to install — so the
//! reason comes before the consequence in the log rather than after it.

use std::fs;
use std::path::{Path, PathBuf};

/// The composition root **with its line comments dropped**.
///
/// Not a nicety: the first version of this guard scanned the raw text, and commenting the
/// announcement out —`// cfg.hub.announce_signature_policy();`, the single likeliest way for it to
/// disappear during a refactor— left the guard green while the hub went back to booting mute. A
/// check that cannot see the very thing it guards is worse than no check, because nobody looks
/// again. Only whole-line comments are dropped, so a `//` inside a string literal is left alone.
fn boot_source() -> (PathBuf, String) {
    let path = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("src")
        .join("boot.rs");
    let text = fs::read_to_string(&path).expect("read crates/server/src/boot.rs");
    let code = text
        .lines()
        .filter(|line| !line.trim_start().starts_with("//"))
        .collect::<Vec<_>>()
        .join("\n");
    (path, code)
}

#[test]
fn hub1754_boot_announces_the_signature_policy_unconditionally() {
    let (path, boot) = boot_source();

    // Positive control FIRST: if the scan cannot see the announcements boot.rs is known to make,
    // it is reading the wrong file and every assertion below would pass by being blind.
    assert!(
        boot.contains(r#"eprintln!("auth: modo {:?}", cfg.hub.auth_mode)"#),
        "{}: the boot no longer announces its auth mode — is this the composition root?",
        path.display()
    );

    let announcement: Vec<&str> = boot
        .lines()
        .filter(|line| line.contains("announce_signature_policy("))
        .collect();
    assert_eq!(
        announcement.len(),
        1,
        "{}: the signature policy is announced exactly once at boot, found {}",
        path.display(),
        announcement.len()
    );

    // Unconditional: at the top level of `serve()`, not tucked inside an `if` the way the old
    // side-effect logging was (it only ran when `installed_but_unregistered()` was non-empty).
    let line = announcement[0];
    let indent = line.len() - line.trim_start().len();
    assert_eq!(
        indent, 4,
        "{}: the announcement is nested {indent} spaces deep, so it is inside some branch — a hub \
         that takes the other branch goes back to booting mute: {line}",
        path.display()
    );
}

#[test]
fn hub1754_the_announcement_comes_before_anything_installs() {
    let (path, boot) = boot_source();

    let announced_at = boot
        .find("announce_signature_policy(")
        .expect("boot announces the signature policy");
    let first_install_at = boot
        .find("installed_but_unregistered()")
        .expect("boot still re-downloads the modules whose cache is empty");

    assert!(
        announced_at < first_install_at,
        "{}: the boot tries to install ({first_install_at}) before it says which signature policy \
         it is installing under ({announced_at}) — a broken ring would print its consequences \
         above its cause",
        path.display()
    );
}
