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
pub const HUB_VERSION: &str = env!("CARGO_PKG_VERSION");

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

        let parts: Vec<&str> = HUB_VERSION.split('.').collect();
        assert_eq!(parts.len(), 3, "not semver X.Y.Z: {HUB_VERSION}");
        for part in parts {
            assert!(
                !part.is_empty() && part.chars().all(|c| c.is_ascii_digit()),
                "not a numeric semver component in {HUB_VERSION}: {part:?}"
            );
        }
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
