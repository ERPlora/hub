//! What the published catalogue still warns about, and nothing more (hub#1243).
//!
//! ADR-0286 (hub#521) put a middle tier between "install" and "refuse": a field this core does not
//! read installs the module and is REPORTED as a [`crate::manifest::ManifestWarning`]. The warning
//! travels in `GET /api/modules` — but nobody was watching the total, so the catalogue could grow
//! a new one at any time and nothing would go red.
//!
//! This list is that watch. It names the `(module_id, dotted_path)` pairs the published catalogue
//! warns about TODAY, seeded by running the sweep in `installer`'s tests against the 27 published
//! manifests at `origin/main`. Every other manifest must warn about nothing at all.
//!
//! 🔴 **The list may only SHRINK.** Two tests hold it there:
//! `every_published_manifest_has_no_unexpected_warnings_hub1243` fails when the catalogue grows a
//! warning that is not listed here, and `every_grandfathered_manifest_warning_still_warns_hub1243`
//! fails when an entry no longer corresponds to a real warning — so fixing a module forces the
//! line to be deleted instead of rotting here.

/// The `(module_id, dotted_path)` pairs the published catalogue is allowed to warn about.
///
/// Each entry carries the issue that owns the debt. Nothing is added here: a warning on a module
/// being published today means the manifest does not fit this core's contract, and the fix is the
/// manifest.
pub const GRANDFATHERED_MANIFEST_WARNINGS: &[(&str, &str)] = &[
    // Seeded by running the sweep against the 27 published manifests at `origin/main`
    // (2026-08-28). Five warnings, not the "cash_register `protects` + 7 `validates`" the issue
    // described: `protects` became a root field the core reads, and `services` dropped its
    // `validates` — the catalogue moved while the issue waited, which is the whole reason for
    // measuring it instead of asserting a remembered number.
    //
    // hub#610 — `validates` is RETIRED (`manifest::RETIRED_FIELDS`): the guard it describes has
    // never run, so the command executes unguarded. Four commands of `inventory` still ship it.
    (
        "inventory",
        "commands.inventory.categories.create.validates",
    ),
    (
        "inventory",
        "commands.inventory.categories.update.validates",
    ),
    ("inventory", "commands.inventory.products.create.validates"),
    ("inventory", "commands.inventory.products.update.validates"),
];

/// Whether this exact `(module, path)` pair is a known, owned debt.
///
/// The pass is per PATH, not per module: a module already on the list gets no cover for a second
/// field it starts declaring later.
pub fn is_grandfathered(module_id: &str, path: &str) -> bool {
    GRANDFATHERED_MANIFEST_WARNINGS
        .iter()
        .any(|(m, p)| *m == module_id && *p == path)
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The pass is per PATH: being on the list for one field is not cover for another.
    #[test]
    fn the_pass_is_per_path_not_per_module() {
        for (module, path) in GRANDFATHERED_MANIFEST_WARNINGS {
            assert!(is_grandfathered(module, path));
            assert!(
                !is_grandfathered(module, "a_field_nobody_declared_hub1243"),
                "`{module}` must not get a blanket pass for every field it may grow"
            );
        }
    }

    /// A list with the same pair twice is a merge accident: it would let one fix leave a stale
    /// line behind that the shrink test can no longer catch.
    #[test]
    fn the_list_has_no_duplicates() {
        let mut seen = std::collections::BTreeSet::new();
        for pair in GRANDFATHERED_MANIFEST_WARNINGS {
            assert!(seen.insert(*pair), "duplicated grandfather entry: {pair:?}");
        }
    }
}
