//! What the release workflow assumes about the machine it runs on (hub#878).
//!
//! `tauri-release.yml` builds four platforms. Windows and macOS run on GitHub-hosted runners
//! because there is nowhere else to run them; Linux and Android moved to `ci-runner-1`, our own
//! box. Every time that move bit us it was the same shape of bug: **a step that only worked
//! because of something the hosted image happened to give it**, and the red it produced never
//! looked like its cause.
//!
//! `v1.1.0` lost both self-hosted jobs at once:
//!
//! * **Linux** — `tauri-action` falls back to `npm install -g @tauri-apps/cli` when the project
//!   does not depend on the CLI. On a hosted runner the user owns `/usr/lib/node_modules`; on
//!   `ci-runner-1` it belongs to root, so the install died with `EACCES` before a single line of
//!   Rust was compiled. The build only ever worked because of a filesystem permission.
//! * **Android** — `android-actions/setup-android` downloads the command line tools from
//!   `dl.google.com`, which answers **404 to this machine over IPv6** (and 200 over IPv4 —
//!   verified from the runner: `curl -6` 404, `curl -4` 206, for every path under that host).
//!   Hosted runners have no IPv6, so the download could never take the broken road there.
//!
//! Both of those are invisible in the YAML: nothing in it says "this needs a writable
//! `/usr/lib`" or "this needs the IPv4 road to Google". These assertions say it, so that removing
//! either guard fails here instead of on the next tag — which is the worst possible place to find
//! out, because a tag is not re-runnable and a release with two platforms missing is already
//! public by the time anyone looks.

use std::path::PathBuf;

/// The npm package that provides the `tauri` binary. It must be a dependency of the project so it
/// is installed *inside the workspace*, never with `npm install -g`.
const TAURI_CLI_PACKAGE: &str = "@tauri-apps/cli";

/// Node resolves AAAA-first by default (`verbatim`). This is the flag that makes it try IPv4
/// first, and it is the whole reason the Android SDK download reaches Google on `ci-runner-1`.
const IPV4_FIRST: &str = "--dns-result-order=ipv4first";

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

fn workflow() -> String {
    read(".github/workflows/tauri-release.yml")
}

/// The workflow with every comment line removed: a `#` line explaining a rule is not the rule.
fn workflow_code() -> String {
    workflow()
        .lines()
        .filter(|line| !line.trim_start().starts_with('#'))
        .collect::<Vec<_>>()
        .join("\n")
}

fn app_package_json() -> serde_json::Value {
    serde_json::from_str(&read("apps/tauri/package.json"))
        .expect("apps/tauri/package.json is not valid JSON")
}

#[test]
fn the_tauri_cli_is_a_project_dependency_not_a_global_install() {
    let dev_dependencies = app_package_json();
    let version = dev_dependencies
        .get("devDependencies")
        .and_then(|d| d.get(TAURI_CLI_PACKAGE))
        .and_then(|v| v.as_str())
        .unwrap_or_else(|| {
            panic!(
                "apps/tauri/package.json must declare `{TAURI_CLI_PACKAGE}` as a devDependency: it \
                 is the only thing that keeps the release from installing the CLI globally, which \
                 needs a writable /usr/lib/node_modules that `ci-runner-1` does not give (hub#878)"
            )
        });

    // A floating range would compile each release with whatever the CLI is that morning — the
    // same class of "it depends on the day" that this file exists to remove.
    assert!(
        version.starts_with(|c: char| c.is_ascii_digit()),
        "`{TAURI_CLI_PACKAGE}` is pinned to `{version}`; an exact version is what makes two \
         releases of the same commit produce the same bundles"
    );
}

#[test]
fn the_release_never_installs_the_tauri_cli_globally() {
    let code = workflow_code();

    // `tauriScript` is the input that stops `tauri-action` from reaching for the global npm
    // package: with it set, the action runs the CLI we installed and never calls `npm install -g`.
    assert!(
        code.contains("tauriScript:"),
        "the Tauri build step no longer passes `tauriScript`, so `tauri-action` falls back to \
         `npm install -g @tauri-apps/cli` — which is exactly what killed the Linux job of v1.1.0 \
         with EACCES on `ci-runner-1` (hub#878)"
    );
    assert!(
        code.contains("pnpm exec tauri"),
        "the CLI must be invoked from the workspace (`pnpm exec tauri`), so the build depends on \
         the lockfile and not on what the machine lets us write to"
    );
    assert!(
        !code.contains("install -g"),
        "a global install is back in the release workflow: it works on a hosted runner and fails \
         on ours, which is the worst way for it to fail — only on the release, only on two of the \
         four platforms (hub#878)"
    );

    // Installing the dependency is what makes `pnpm exec tauri` resolve to a binary at all.
    assert!(
        code.contains("pnpm install --frozen-lockfile"),
        "nothing installs the workspace dependencies before the build, so `pnpm exec tauri` has \
         no CLI to run"
    );
}

/// System binaries the Linux bundle needs that a bare Ubuntu does NOT bring, each with the
/// package that provides it and what dies without it. All of them are *copied from the machine*
/// into the AppImage or run against it, so no project dependency can replace them — the apt step
/// is the only place they can live, and that is why they are asserted there.
const APPIMAGE_SYSTEM_PACKAGES: [(&str, &str); 2] = [
    // `/usr/bin/xdg-mime` + `/usr/bin/xdg-open`: tauri-bundler copies both INTO the AppDir —
    // xdg-mime because the app declares deep link schemes (`erplora://`), xdg-open because
    // `bundleXdgOpen` defaults on. Missing → "xdg-mime binary not found", after a full compile.
    ("xdg-utils", "xdg-mime / xdg-open, copied into the AppDir"),
    // `gtk-query-immodules-3.0`: linuxdeploy-plugin-gtk writes `immodules.cache` with it and then
    // `sed -i`s that file. The script runs under `set -e`, so when the tool is missing the sed
    // hits a file that was never written and the whole AppImage step dies there.
    ("libgtk-3-bin", "gtk-query-immodules-3.0 for the GTK plugin"),
];

#[test]
fn the_linux_job_installs_what_the_appimage_takes_from_the_machine() {
    let code = workflow_code();
    let deps_step = code
        .split("Install Linux build deps")
        .nth(1)
        .expect("the Linux job installs its system dependencies in a step of that name")
        .split("- name:")
        .next()
        .expect("the step ends where the next one starts")
        .to_string();

    for (package, why) in APPIMAGE_SYSTEM_PACKAGES {
        assert!(
            deps_step.contains(package),
            "`{package}` is no longer installed by the Linux job. It provides {why}: a hosted \
             runner image happens to carry it, a Hetzner Ubuntu does not, and the bundle only \
             fails AFTER a full release compile — on a tag, where re-running is expensive and the \
             release is already public (hub#878)"
        );
    }
}

/// What stops `Swatinem/rust-cache` from deleting `~/.cargo/registry/src` out from under the job
/// running on the OTHER slot of the same machine.
const CACHE_SAVE_GUARD: &str = "save-if: ${{ runner.environment != 'self-hosted' }}";

/// The clause of [`CACHE_SAVE_GUARD`] that does the work. A `save-if` keeps the save off a
/// self-hosted runner when this clause is one of the `&&` operands of its expression: `false && x`
/// is false whatever `x` is (hub#2706 writes `… && matrix.part == 1`, hub#2710).
const NOT_SELF_HOSTED: &str = "runner.environment != 'self-hosted'";

/// Whether a `save-if:` value is false on a self-hosted runner. Deliberately narrow: an `${{ }}`
/// expression with no `||` anywhere whose `&&` operands include [`NOT_SELF_HOSTED`] (outer
/// parentheses aside). Anything else — `||`, a negation, a bare literal — is not a guard.
fn save_if_is_guard(value: &str) -> bool {
    let Some(expression) = value
        .trim()
        .strip_prefix("${{")
        .and_then(|rest| rest.strip_suffix("}}"))
    else {
        return false;
    };
    if expression.contains("||") {
        return false;
    }
    expression.split("&&").any(|operand| {
        let mut operand = operand.trim();
        while let Some(inner) = operand.strip_prefix('(').and_then(|o| o.strip_suffix(')')) {
            operand = inner.trim();
        }
        operand == NOT_SELF_HOSTED
    })
}

/// One entry per `Swatinem/rust-cache` step of `code`, in order: whether that step's `save-if`
/// keeps the save — and the registry pruning that comes with it — off a self-hosted runner.
fn cache_step_guards(code: &str) -> Vec<bool> {
    let lines: Vec<&str> = code.lines().collect();
    let mut guards = Vec::new();
    for (i, line) in lines.iter().enumerate() {
        let Some(column) = line.find("uses: Swatinem/rust-cache") else {
            continue;
        };
        // The step's own keys (`with:`, `if:`…) sit at the column of `uses:`; the step ends at the
        // first line indented less — the `- ` of the next step, or the next job.
        let step = lines[i + 1..]
            .iter()
            .take_while(|l| l.trim().is_empty() || l.len() - l.trim_start().len() >= column);
        let guarded = step
            .filter_map(|l| l.trim_start().strip_prefix("save-if:"))
            .any(save_if_is_guard);
        guards.push(guarded);
    }
    guards
}

/// A cache step as `test-hub.yml` writes it, with `save_if` as its `save-if` line (or none).
fn cache_step_yaml(save_if: Option<&str>) -> String {
    let mut yaml = String::from(
        "    steps:\n      - name: Cache cargo\n        uses: Swatinem/rust-cache@v2\n        with:\n          cache-bin: false\n",
    );
    if let Some(value) = save_if {
        yaml.push_str(&format!("          save-if: {value}\n"));
    }
    yaml.push_str("\n      - name: cargo test\n        run: cargo test\n");
    yaml
}

#[test]
fn hub2710_a_guard_anded_with_another_condition_still_guards() {
    // Regression test for hub#2710. hub#2706 split the Rust suite into a matrix and saves the cache from part 1 only. The save
    // is still off on `ci-runner-1`: `false && x` is false whatever `x` is.
    let yaml = cache_step_yaml(Some(
        "${{ runner.environment != 'self-hosted' && matrix.part == 1 }}",
    ));
    assert_eq!(cache_step_guards(&yaml), vec![true]);

    let yaml = cache_step_yaml(Some(
        "${{ matrix.part == 1 && (runner.environment != 'self-hosted') }}",
    ));
    assert_eq!(cache_step_guards(&yaml), vec![true]);
}

#[test]
fn hub2710_the_plain_guard_still_guards() {
    let yaml = cache_step_yaml(Some("${{ runner.environment != 'self-hosted' }}"));
    assert_eq!(cache_step_guards(&yaml), vec![true]);
}

#[test]
fn hub2710_a_cache_step_without_save_if_is_unguarded() {
    assert_eq!(cache_step_guards(&cache_step_yaml(None)), vec![false]);
}

#[test]
fn hub2710_a_condition_that_can_save_on_the_shared_runner_is_unguarded() {
    for value in [
        // `||`: part 1 saves — and prunes — on `ci-runner-1` too.
        "${{ runner.environment != 'self-hosted' || matrix.part == 1 }}",
        // `&&` binds tighter than `||`: a push saves on `ci-runner-1` whatever the first operand.
        "${{ runner.environment != 'self-hosted' && matrix.part == 1 || github.event_name == 'push' }}",
        "${{ matrix.part == 1 }}",
        "${{ !(runner.environment != 'self-hosted') }}",
        "${{ runner.environment == 'self-hosted' }}",
        "true",
    ] {
        assert_eq!(
            cache_step_guards(&cache_step_yaml(Some(value))),
            vec![false],
            "`save-if: {value}` saves on a self-hosted runner and must not count as a guard"
        );
    }
}

#[test]
fn hub2710_a_guard_on_another_step_does_not_cover_an_unguarded_cache_step() {
    // The old count matched the guard string anywhere in the file: a guard written on some other
    // step would have balanced an unguarded cache step.
    let yaml = format!(
        "{}      - name: Other\n        uses: some/action@v1\n        with:\n          save-if: ${{{{ runner.environment != 'self-hosted' }}}}\n",
        cache_step_yaml(None)
    );
    assert_eq!(cache_step_guards(&yaml), vec![false]);
}

#[test]
fn the_cargo_cache_does_not_prune_the_registry_a_concurrent_job_is_reading() {
    let code = workflow_code();

    // Both Linux jobs of a release run AT THE SAME TIME on `ci-runner-1`: two runner slots, two
    // `_work` trees — and ONE `$HOME`, so one `~/.cargo`. The `Post` of rust-cache `rmRF`s every
    // non-`-sys` directory under `registry/src` before saving (`cleanRegistry`), and the Android
    // build resolves `:tauri-android`, `:tauri-plugin-deep-link`, `:tauri-plugin-notification` and
    // `:tauri-plugin-opener` as Gradle projects living in exactly those directories.
    //
    // Measured, not deduced: `Post Cache cargo` of the desktop job logged
    // "... Cleaning cargo registry ..." at 13:29:24, and 41 s later the Android build died in
    // Gradle's configuration phase with "No matching variant ... No variants exist" for those four
    // projects — a red that names Gradle variants and says nothing about a cache on another job.
    //
    // `save-if: false` returns before any cleaning (rust-cache `save.ts`), so the restore still
    // works and the hosted runners still save: it is only the destructive half that goes away, and
    // only where the machine outlives the job.
    let guards = cache_step_guards(&code);
    let cache_steps = guards.len();
    assert!(
        cache_steps >= 2,
        "expected the desktop and Android jobs to both cache cargo; found {cache_steps}"
    );
    assert_eq!(
        guards.iter().filter(|&&guarded| guarded).count(),
        cache_steps,
        "every `Swatinem/rust-cache` step must carry `{CACHE_SAVE_GUARD}`. Without it the `Post` \
         of whichever job finishes first deletes the registry sources the other one is building \
         from, and a release loses a platform to a failure that looks like a Gradle problem \
         (hub#878)"
    );
}

/// Marker that a job is scheduled on `ci-runner-1` instead of a GitHub-hosted image.
const SELF_HOSTED_MARKER: &str = "CI_RUNNER_LABEL";

/// Every workflow file in the repository, as `(file name, contents with comments stripped)`.
fn all_workflows_code() -> Vec<(String, String)> {
    let dir = repo_root().join(".github/workflows");
    let mut out = Vec::new();
    for entry in std::fs::read_dir(&dir).expect("cannot list .github/workflows") {
        let path = entry.expect("cannot read a workflow entry").path();
        if path.extension().and_then(|e| e.to_str()) != Some("yml") {
            continue;
        }
        let name = path
            .file_name()
            .and_then(|n| n.to_str())
            .expect("workflow file name is not valid UTF-8")
            .to_string();
        let code = std::fs::read_to_string(&path)
            .unwrap_or_else(|e| panic!("cannot read {}: {e}", path.display()))
            .lines()
            .filter(|line| !line.trim_start().starts_with('#'))
            .collect::<Vec<_>>()
            .join("\n");
        out.push((name, code));
    }
    out.sort();
    out
}

/// The release workflow was fixed on its own (hub#886), which left the hole only half shut: the
/// registry it stopped pruning is the SAME `~/.cargo` that every other Rust workflow of this repo
/// prunes from the other runner slot. `test-hub.yml` and `test-shell.yml` both run on
/// `ci-runner-1` and both save a cargo cache, so either of them finishing while a release builds
/// Android reproduces hub#886 exactly — and the red still lands on the release, still shaped like
/// a Gradle problem, still on a tag that cannot be re-run.
///
/// This is the whole-machine version of the assertion above: the guard is a property of *sharing
/// one `$HOME` between two runner slots*, not a property of the release workflow, so it is checked
/// everywhere the machine is shared rather than in the one file where it happened to hurt first.
#[test]
fn no_workflow_on_the_shared_runner_prunes_the_cargo_registry() {
    let mut unguarded = Vec::new();

    for (name, code) in all_workflows_code() {
        let step_guards = cache_step_guards(&code);
        let cache_steps = step_guards.len();
        if cache_steps == 0 || !code.contains(SELF_HOSTED_MARKER) {
            continue;
        }
        let guards = step_guards.iter().filter(|&&guarded| guarded).count();
        if guards != cache_steps {
            unguarded.push(format!("{name}: {guards} guard(s) for {cache_steps} cache step(s)"));
        }
    }

    assert!(
        unguarded.is_empty(),
        "these workflows run on `ci-runner-1` and save a cargo cache without \
         `{CACHE_SAVE_GUARD}`: {unguarded:?}. The two runner slots share one `$HOME`, so the \
         `Post` of rust-cache `rmRF`s `~/.cargo/registry/src` while the job on the other slot is \
         still compiling from it — measured on v1.1.1: `Cleaning cargo registry` at 00:54:22 and \
         the Android build dead at 00:54:30 with `could not parse/generate dep info ... No such \
         file or directory` (hub#886)"
    );
}

#[test]
fn google_downloads_do_not_take_the_ipv6_road_that_answers_404() {
    let code = workflow_code();
    assert!(
        code.contains(IPV4_FIRST),
        "the workflow no longer forces `{IPV4_FIRST}`. `dl.google.com` answers 404 to \
         `ci-runner-1` over IPv6, and Node — which is what every JS action downloads with — \
         prefers IPv6: `Setup Android SDK` dies with `HTTPError: Unexpected HTTP response: 404` \
         for a file that exists and that `curl -4` fetches fine (hub#878)"
    );
    assert!(
        code.contains("NODE_OPTIONS:"),
        "the IPv4 preference has to reach the actions themselves, and `NODE_OPTIONS` is how a \
         flag reaches a Node process we do not launch"
    );
}
