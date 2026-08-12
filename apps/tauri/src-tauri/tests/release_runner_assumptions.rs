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
