//! The hub's version — read from one place, by everything that reports it (hub#515).
//!
//! The number lives in `[workspace.package] version` of the workspace `Cargo.toml`, and every
//! crate inherits it (`version.workspace = true`). `scripts/image-tags.sh` reads that same file to
//! name the image, so the tag on the registry and the number the binary reports cannot drift.
//!
//! Before this the two had nothing to do with each other: the image took its version from the git
//! ref (the tag on a release, the short sha on `main`) while the binary said `0.0.0` — so «which
//! version is this hub running?» had no answer, and «is this jump a security patch or a new
//! version?» could not even be asked. Two digests do not tell you that.
//!
//! What the criterion for MAJOR/MINOR/PATCH is, for this product:
//! `architecture/hub/versioning.md`.

/// The running version, e.g. `1.0.0`. **This is the number that goes on the wire** — the
/// heartbeat, `error_sink`, anything the Cloud will compare.
///
/// Re-exported from the runtime rather than read again from this crate's `CARGO_PKG_VERSION`
/// (hub#521): since the runtime started REFUSING a module whose `compatibility.min_erplora_version`
/// is above the core, the number it refuses with and the number the hub reports must be the same
/// one. Two `env!` calls in two crates happen to agree today because both inherit
/// `[workspace.package]` — "happens to agree" is not a property worth relying on for a refusal.
pub const HUB_VERSION: &str = erplora_runtime::CORE_VERSION;

/// The same number for a human to read, e.g. `v1.0.0`.
///
/// The `v` is a reading aid and stops there: adding it to what travels would mean the Cloud has to
/// strip it before comparing, and something, somewhere, would forget.
pub fn display() -> String {
    format!("v{HUB_VERSION}")
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Reads `X.Y.Z[-prerelease][+build]` — the same shape `scripts/stamp-version.sh` accepts
    /// before it writes a number into the three files, kept deliberately identical so a version
    /// that survives the stamper cannot be one this rejects.
    ///
    /// The suffix is optional but REAL: the `:dev` channel stamps `1.1.7-dev.305+g1c50d429` and a
    /// source build stamps `1.1.15-source+gd7d8d547` (hub#1619). What is refused is anything that
    /// is not three numbers up front — two components, four, a `v` prefix, a letter.
    fn is_a_version_number(value: &str) -> bool {
        let core = value.split(['-', '+']).next().unwrap_or_default();
        // A suffix must not be empty: `1.2.3-` and `1.2.3+` say a channel and then do not name it.
        let suffix = &value[core.len()..];
        if !suffix.is_empty() && (suffix.len() == 1 || suffix.ends_with(['-', '+'])) {
            return false;
        }
        let parts: Vec<&str> = core.split('.').collect();
        parts.len() == 3
            && parts
                .iter()
                .all(|part| !part.is_empty() && part.chars().all(|c| c.is_ascii_digit()))
    }

    /// The number is a real release number, not the placeholder.
    ///
    /// `0.0.0` is what `[workspace.package]` held from the start, and it is why the fleet could
    /// not say whether a jump was a security patch or a new version: two digests do not tell you
    /// that. This test is the thing that keeps it from silently going back — a revert, a merge
    /// resolution, a `cargo new`-shaped edit — because nothing else would notice: the binary
    /// builds fine at `0.0.0` and just lies about itself forever after.
    #[test]
    fn hub_version_is_a_real_release_number() {
        assert_ne!(
            HUB_VERSION, "0.0.0",
            "[workspace.package] version is back to the 0.0.0 placeholder — see architecture/hub/versioning.md"
        );
        assert!(
            is_a_version_number(HUB_VERSION),
            "not semver X.Y.Z[-prerelease][+build]: {HUB_VERSION}"
        );
    }

    /// 🔴 hub#1619 — a version is allowed to say WHICH build it is, and this test used to say it
    /// was not: it split on `.` and demanded exactly three numeric parts, which no channel but a
    /// plain release has ever satisfied.
    ///
    /// It went red the moment a source build started reporting `1.1.15-source+g<sha>` instead of
    /// the `1.0.0` placeholder, but it was already wrong before that — the `:dev` image stamps
    /// `1.1.7-dev.305+g<sha>` (`scripts/image-tags.sh`) and would have failed the same way. The
    /// guard worth keeping is the one above (the placeholder), not the shape being three digits.
    #[test]
    fn a_version_may_name_the_channel_it_was_built_on_hub1619() {
        // A published release, and the two suffixed channels that exist.
        assert!(is_a_version_number("1.1.15"));
        assert!(is_a_version_number("1.1.7-dev.305+g1c50d429"));
        assert!(is_a_version_number("1.1.15-source+gd7d8d547"));
        // Still not versions: the shape has to be three numbers before any suffix.
        assert!(!is_a_version_number("1.1"));
        assert!(!is_a_version_number("1.1.15.2"));
        assert!(!is_a_version_number("v1.1.15"));
        assert!(!is_a_version_number("1.1.x"));
        assert!(!is_a_version_number(""));
        // And a suffix marker with nothing after it names no channel at all.
        assert!(!is_a_version_number("1.1.15-"));
        assert!(!is_a_version_number("1.1.15+"));
    }

    /// The surfaces that show it to a human prefix a `v`; the wire never does.
    ///
    /// They must not diverge: the panel showing `v1.2.3` while the heartbeat reports `1.2.3` is
    /// fine, but two different NUMBERS would send somebody chasing a version nobody released.
    #[test]
    fn the_displayed_version_is_the_same_number_with_a_v() {
        assert_eq!(display(), format!("v{HUB_VERSION}"));
    }
}
