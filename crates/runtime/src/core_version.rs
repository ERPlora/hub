//! What version a build of the hub says it IS, and whether anything backed that number up
//! (hub#1619).
//!
//! This file is compiled TWICE on purpose: once as a module of the crate, and once as the crate's
//! BUILD SCRIPT (`build = "src/core_version.rs"` in `Cargo.toml`), which is what turns the
//! decision below into the `ERPLORA_CORE_VERSION` the crate then reads back with `env!`.
//!
//! It is one file and not a `build.rs` beside it for a reason: `cargo test` never runs the tests
//! of a build script, so logic that lives only there is logic nothing pins. Here every rule below
//! is exercised by `cargo test -p erplora-runtime --lib core_version`, and `main` — the only part
//! cargo runs as a script — is left as thin as it can be: three inputs in, one stamp out.
//!
//! ## Why a build script at all
//!
//! `CORE_VERSION` used to be `env!("CARGO_PKG_VERSION")` and nothing else, which meant a hub
//! compiled from source called itself `1.0.0` — the `[workspace.package]` placeholder that only
//! the release CI ever rewrites (`scripts/stamp-version.sh`). `1.0.0` is BELOW every hub that
//! exists, so a source build refused any module declaring
//! `compatibility.min_erplora_version` (hub#521) and the catalogue sweeps read that refusal as a
//! broken manifest. The cost landed on everyone: the first module to declare the truth would put
//! `local-gate` and `test-hub-modules` red for the whole fleet, so the rational move was to never
//! declare it — 0 of 27 published modules did.
//!
//! ## Why the tags and not `git describe`
//!
//! `scripts/image-tags.sh` derives the `:dev` channel from `git describe --tags --long`, and the
//! obvious move was to copy it. Measured on `develop@1c50d429` (2026-09-07) it does not work
//! here: `main` is an ORPHAN branch (releases are promoted onto it with `commit-tree`), so the
//! release tags are NOT reachable from `develop` and `git describe` answers `v1.1.7-305-g1c50d429`
//! — eight releases stale, and still below a `1.1.15` floor. Reachability is the wrong question;
//! the newest `v*` tag the repository HOLDS is the right one, because `main` is promoted from
//! `develop`, so a `develop` checkout always carries at least what the newest release carries.

/// Reads a version as a comparable triple. A pre-release/build suffix is dropped (`1.2.3-rc1`
/// floors at `1.2.3`) and missing components read as zero (`2` = `2.0.0`): this compares a FLOOR,
/// so being generous about the shape is right, while a fourth component or a non-numeric one is
/// not a version anybody released and returns `None`.
pub fn version_triple(value: &str) -> Option<(u64, u64, u64)> {
    let core = value.trim().split(['-', '+']).next()?;
    let mut parts = core.split('.');
    let major = parts.next()?.parse().ok()?;
    let minor = parts.next().unwrap_or("0").parse().ok()?;
    let patch = parts.next().unwrap_or("0").parse().ok()?;
    parts.next().is_none().then_some((major, minor, patch))
}

/// The number this build reports, and whether a release tag corroborated it.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CoreVersion {
    /// What `CORE_VERSION` becomes: `/readyz`, `/api/hub/context`, the AEAT `SistemaInformatico`
    /// block and the module core floor all read this one string.
    pub version: String,
    /// `false` = this build could not see a single release tag, so it does not actually know
    /// whether its own number is above or below the fleet's. A build in that state must not be
    /// the thing that calls a module's declared floor wrong — see the catalogue sweeps in
    /// `tests/module_manifest_contract.rs`.
    pub corroborated: bool,
}

/// Decides the version a build reports, from the package version and the repository's `v*` tags.
///
/// The package version WINS whenever it was stamped, and there are exactly two shapes of stamped:
/// a plain `X.Y.Z` that matches a tag (`build-hub.yml` on a release, and `main`), and anything
/// carrying a prerelease/build suffix (the `:dev` channel, `1.1.7-dev.305+gabc1234`). Rewriting
/// either would make the image's NAME and the binary's number disagree, which is the drift
/// `crates/server/src/version.rs` exists to prevent.
///
/// Only the third shape is a source build: a plain `X.Y.Z` that no tag matches and that is BELOW
/// a release that exists. That one is the placeholder, and it is replaced by the newest release
/// plus a `-source` marker, so the number satisfies a declared floor without ever passing itself
/// off as the published release of the same name.
///
/// No commit sha in the marker, on purpose: the stamp is baked in with `env!`, so anything in it
/// that moves with HEAD would recompile this crate — and everything downstream of it — on every
/// commit of every worktree of the fleet, and nothing consumes the sha (`git rev-parse HEAD` is
/// right there for whoever wants it).
pub fn decide(package_version: &str, tags: &[String]) -> CoreVersion {
    // `version_triple` refuses a leading `v` on purpose (it reads a module's declared floor, and
    // `v1.2.3` is not what anybody declares there); a git tag always carries one.
    let newest = tags
        .iter()
        .filter_map(|tag| Some((version_triple(tag.trim_start_matches('v'))?, tag)))
        .max_by(|a, b| a.0.cmp(&b.0));
    let Some((newest_triple, newest_tag)) = newest else {
        // No tags in the checkout (a shallow clone, a tarball, a repo without git): the build has
        // nothing to compare itself against and says so, rather than inventing a number.
        return CoreVersion {
            version: package_version.to_string(),
            corroborated: false,
        };
    };

    let stamped_prerelease = package_version.contains('-') || package_version.contains('+');
    let matches_a_tag = tags
        .iter()
        .any(|tag| tag.trim_start_matches('v') == package_version);
    let below_newest = version_triple(package_version).is_some_and(|pkg| pkg < newest_triple);

    if stamped_prerelease || matches_a_tag || !below_newest {
        return CoreVersion {
            version: package_version.to_string(),
            corroborated: true,
        };
    }

    CoreVersion {
        version: format!("{}-source", newest_tag.trim_start_matches('v')),
        corroborated: true,
    }
}

/// Splits `git tag --list` output into tags. A blank checkout yields no tags, not one empty tag.
pub fn tags_from_output(output: &str) -> Vec<String> {
    output
        .lines()
        .map(str::trim)
        .filter(|line| !line.is_empty())
        .map(str::to_string)
        .collect()
}

/// The git files whose change can change the answer — and ONLY the ones that exist.
///
/// 🔴 A `cargo:rerun-if-changed` on a path that does not exist makes cargo treat this build script
/// as stale on EVERY invocation, and a stale build script recompiles this crate and everything
/// downstream of it each time. Measured on a worktree during the hub#1619 review:
/// `<git-dir>/packed-refs` never exists there (only the common dir has one), and an unchanged
/// `cargo test` recompiled `erplora-runtime` every single time.
///
/// `HEAD` is deliberately not among them: the stamp does not depend on it.
pub fn watched_git_inputs(git_dirs: &[String]) -> Vec<String> {
    let mut watched = Vec::new();
    let mut seen: Vec<&String> = Vec::new();
    for dir in git_dirs {
        // A plain checkout answers the same dir for `--git-common-dir` and `--git-dir`.
        if seen.contains(&dir) {
            continue;
        }
        seen.push(dir);
        for input in ["packed-refs", "refs/tags"] {
            let path = format!("{dir}/{input}");
            if std::path::Path::new(&path).exists() {
                watched.push(path);
            }
        }
    }
    watched
}

// ── The build script (`build = "src/core_version.rs"`) ───────────────────────────────────────

/// Gathers the three inputs and stamps the answer for rustc. Never fails a build: git missing, a
/// tarball with no repository, a shallow clone with no tags — each one falls back to
/// `CARGO_PKG_VERSION` and marks the number as uncorroborated, which is what the catalogue sweeps
/// read before they call a module's declared core floor wrong.
///
/// `ERPLORA_CORE_VERSION` in the environment pins it explicitly and wins over everything: that is
/// how a bench (or a build outside a checkout) STATES a version instead of guessing one.
///
/// Dead when this file is compiled as a module of the crate — cargo only calls it in the other
/// half of its double life.
#[allow(dead_code)]
fn main() {
    println!("cargo:rerun-if-changed=src/core_version.rs");
    println!("cargo:rerun-if-env-changed=ERPLORA_CORE_VERSION");

    let dir = std::env::var("CARGO_MANIFEST_DIR").unwrap_or_else(|_| ".".to_string());
    // A tag arriving changes the answer and nothing in this package does, so the tag refs are the
    // inputs to watch — both dirs, because in a worktree `--git-dir` is the worktree's own and the
    // tags live in the common one. Only the paths that EXIST (see [`watched_git_inputs`]).
    let git_dirs: Vec<String> = ["--git-common-dir", "--git-dir"]
        .iter()
        .filter_map(|reference| git(&dir, &["rev-parse", "--path-format=absolute", reference]))
        .collect();
    for input in watched_git_inputs(&git_dirs) {
        println!("cargo:rerun-if-changed={input}");
    }

    let package = std::env::var("CARGO_PKG_VERSION").unwrap_or_default();
    let decided = match std::env::var("ERPLORA_CORE_VERSION") {
        Ok(pinned) if !pinned.trim().is_empty() => CoreVersion {
            version: pinned.trim().to_string(),
            corroborated: true,
        },
        _ => {
            let tags = git(&dir, &["tag", "--list", "v*"])
                .map(|out| tags_from_output(&out))
                .unwrap_or_default();
            decide(&package, &tags)
        }
    };

    println!("cargo:rustc-env=ERPLORA_CORE_VERSION={}", decided.version);
    println!(
        "cargo:rustc-env=ERPLORA_CORE_VERSION_CORROBORATED={}",
        u8::from(decided.corroborated)
    );
}

/// Runs git inside the checkout, or `None` for anything that is not a clean answer — a missing
/// binary, a non-zero exit, output that is not UTF-8, or nothing at all.
#[allow(dead_code)]
fn git(dir: &str, args: &[&str]) -> Option<String> {
    let output = std::process::Command::new("git")
        .arg("-C")
        .arg(dir)
        .args(args)
        .output()
        .ok()?;
    if !output.status.success() {
        return None;
    }
    let text = String::from_utf8(output.stdout).ok()?;
    let text = text.trim().to_string();
    (!text.is_empty()).then_some(text)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn tags(list: &[&str]) -> Vec<String> {
        list.iter().map(|t| t.to_string()).collect()
    }

    /// 🔴 hub#1619, the whole reason this module exists: a source build must NOT report the
    /// `[workspace.package]` placeholder, which is below every hub that exists.
    ///
    /// Measured on `develop@1c50d429`: the placeholder is `1.0.0` and the newest release is
    /// `v1.1.15`, so `whatsapp_inbox` declaring `min_erplora_version: 1.1.15` was refused BY THE
    /// DEVELOPER'S OWN BUILD and the catalogue sweep read that refusal as a broken manifest.
    #[test]
    fn a_source_build_reports_the_newest_release_not_the_placeholder_hub1619() {
        let decided = decide("1.0.0", &tags(&["v1.1.14", "v1.1.15", "v1.1.7"]));
        assert_eq!(decided.version, "1.1.15-source");
        assert!(decided.corroborated);
        assert!(
            version_triple(&decided.version) >= version_triple("1.1.15"),
            "a floor of 1.1.15 must be satisfied by {}",
            decided.version
        );
    }

    /// The newest tag is picked NUMERICALLY, not as text: `v1.1.9` sorts after `v1.1.15` in any
    /// lexicographic order, and picking it would put the build back below the fleet.
    #[test]
    fn the_newest_tag_is_the_highest_version_not_the_last_string_hub1619() {
        let decided = decide("1.0.0", &tags(&["v1.1.9", "v1.1.15", "v1.2.0"]));
        assert_eq!(decided.version, "1.2.0-source");
    }

    /// The `-source` marker is not decoration: without it a developer's build would be
    /// indistinguishable from the published release of the same name, on `/readyz`, in the
    /// heartbeat and in the AEAT `SistemaInformatico` block. That is hub#1170 with the sign
    /// flipped — a build claiming a version it is not.
    #[test]
    fn a_source_build_never_passes_itself_off_as_the_release_hub1619() {
        let decided = decide("1.0.0", &tags(&["v1.1.15"]));
        assert_ne!(decided.version, "1.1.15");
        assert_eq!(decided.version, "1.1.15-source");
    }

    /// A release build is stamped from its tag by `scripts/stamp-version.sh` BEFORE compiling, so
    /// the package version is already the truth and must survive untouched — even when a newer
    /// tag exists in the checkout (re-running an older release's build).
    #[test]
    fn a_stamped_release_version_is_never_rewritten_hub1619() {
        let decided = decide("1.1.10", &tags(&["v1.1.10", "v1.1.15"]));
        assert_eq!(decided.version, "1.1.10");
        assert!(decided.corroborated);
    }

    /// The `:dev` channel stamps a prerelease (`image-tags.sh`). The image is NAMED with that
    /// number, so rewriting it here would make the tag on the registry and the number the binary
    /// reports two different things — the exact drift `crates/server/src/version.rs` documents.
    #[test]
    fn a_stamped_prerelease_is_never_rewritten_hub1619() {
        let decided = decide("1.1.7-dev.305+g1c50d429", &tags(&["v1.1.15"]));
        assert_eq!(decided.version, "1.1.7-dev.305+g1c50d429");
        assert!(decided.corroborated);
    }

    /// A workspace version ABOVE every tag is somebody having bumped it on purpose. It is already
    /// the most specific statement available and is left alone.
    #[test]
    fn a_package_version_above_every_tag_is_left_alone_hub1619() {
        let decided = decide("1.2.0", &tags(&["v1.1.15"]));
        assert_eq!(decided.version, "1.2.0");
        assert!(decided.corroborated);
    }

    /// 🔴 The other half, and the one that keeps this from painting the fleet red: with no tags
    /// to compare against (shallow clone, tarball, no git at all) the build keeps the package
    /// version AND says it could not corroborate it. What consumes that flag is the catalogue
    /// sweep, which must not call a module's floor wrong on the word of a build that does not
    /// know its own place in the fleet.
    #[test]
    fn without_tags_the_build_cannot_corroborate_its_version_hub1619() {
        let decided = decide("1.0.0", &[]);
        assert_eq!(decided.version, "1.0.0");
        assert!(!decided.corroborated);
    }

    /// Tags that are not versions do not count as tags.
    #[test]
    fn a_tag_that_is_not_a_version_does_not_corroborate_anything_hub1619() {
        let decided = decide("1.0.0", &tags(&["vnext", "v-broken"]));
        assert_eq!(decided.version, "1.0.0");
        assert!(!decided.corroborated);
    }

    /// 🔴 Only git inputs that EXIST are watched, and `HEAD` never is. A `rerun-if-changed` on a
    /// missing path makes cargo re-run this script — and recompile this crate plus everything
    /// downstream — on every invocation; a worktree has no `packed-refs` of its own, so that was
    /// every `cargo test` of every `hub-wt-*` (measured in the hub#1619 review).
    #[test]
    fn only_git_inputs_that_exist_are_watched_and_head_never_is_hub1619() {
        let root = std::env::temp_dir().join(format!(
            "erplora-core-version-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        let common = root.join("common");
        let worktree = root.join("worktrees").join("wt");
        std::fs::create_dir_all(common.join("refs/tags")).unwrap();
        std::fs::write(common.join("packed-refs"), "").unwrap();
        std::fs::write(common.join("HEAD"), "ref: refs/heads/develop\n").unwrap();
        std::fs::create_dir_all(&worktree).unwrap();
        std::fs::write(worktree.join("HEAD"), "abc\n").unwrap();

        let dirs = [common.display().to_string(), worktree.display().to_string()];
        let watched = watched_git_inputs(&dirs);
        // A plain checkout answers the same dir for `--git-common-dir` and `--git-dir`: each path
        // is watched once.
        let twice = watched_git_inputs(&[dirs[0].clone(), dirs[0].clone()]);
        std::fs::remove_dir_all(&root).unwrap();

        assert_eq!(
            watched,
            vec![
                format!("{}/packed-refs", common.display()),
                format!("{}/refs/tags", common.display()),
            ],
            "the worktree dir has neither file and HEAD is never an input"
        );
        assert_eq!(twice, watched);
        assert_eq!(watched_git_inputs(&[]), Vec::<String>::new());
    }

    /// A checkout with no tags prints NOTHING, and an empty line is not a tag: read as one, it
    /// would reach [`decide`] as a tag that is not a version and change nothing — but a stray
    /// blank line in the middle would silently shorten the list it does read.
    #[test]
    fn tags_are_read_a_line_at_a_time_and_blank_lines_are_not_tags_hub1619() {
        assert_eq!(tags_from_output(""), Vec::<String>::new());
        assert_eq!(tags_from_output("\n \n"), Vec::<String>::new());
        assert_eq!(
            tags_from_output("v1.1.14\nv1.1.15\n"),
            vec!["v1.1.14".to_string(), "v1.1.15".to_string()]
        );
    }
}
