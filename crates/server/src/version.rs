//! The hub's version — read from one place, by everything that reports it (hub#515).

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
