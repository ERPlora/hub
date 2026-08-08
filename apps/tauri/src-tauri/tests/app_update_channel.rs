//! The two ends of the update channel of the installed app (hub#400), each of which fails MUTELY.
//!
//! The web app asks the shell "which build are you?" with `plugin:app|version`, and compares it
//! with what the Cloud publishes. Neither half of that is code in this crate — the question is one
//! line of TypeScript and the answer comes from Tauri's own `core:app` plugin — which is exactly
//! why they need a guard here: **both ends can be removed without anything failing to compile.**
//!
//! * Trim `core:default` out of `capabilities/default.json` (a plausible tightening: "the till does
//!   not need windows or menus") and the ACL starts refusing `app|version` **only from a remote
//!   origin**. Dev, which loads loopback and `tauri://`, keeps working. Every till in the field goes
//!   quiet, forever, with no error anywhere.
//! * Stop publishing the version manifest from the release workflow and the Cloud has nothing to
//!   report. Same silence, other end.
//!
//! Neither is hypothetical bookkeeping: silence is the *correct* behaviour of the feature when it
//! cannot check, so a broken update channel is indistinguishable from a healthy one that has
//! nothing to say. Nothing but these assertions would ever notice.

use std::path::PathBuf;

/// What the page invokes. Kept as a literal on both sides: the TypeScript writes the same string,
/// and there is no shared symbol between a webview bundle and this crate to bind them.
const VERSION_COMMAND: &str = "plugin:app|version";

/// The permission set that carries it. `core:default` is `["core:path:default", …,
/// "core:app:default", …]`, and `core:app:default` enables `version` (tauri `build.rs`, PLUGINS).
const CORE_DEFAULT: &str = "core:default";

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

fn hub_pwa_capability() -> serde_json::Value {
    let raw = std::fs::read_to_string(
        PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("capabilities/default.json"),
    )
    .expect("cannot read capabilities/default.json");
    serde_json::from_str(&raw).expect("capabilities/default.json is not valid JSON")
}

#[test]
fn the_hub_pwa_may_ask_the_shell_which_build_it_is() {
    let capability = hub_pwa_capability();
    let permissions: Vec<&str> = capability["permissions"]
        .as_array()
        .expect("permissions must be an array")
        .iter()
        .map(|value| value.as_str().expect("every permission is a string"))
        .collect();

    assert!(
        permissions.contains(&CORE_DEFAULT),
        "capabilities/default.json no longer grants {CORE_DEFAULT}, so `{VERSION_COMMAND}` is \
         refused to the hub PWA. Nothing breaks in dev and every installed till stops being able \
         to tell whether it is out of date — in silence, which is also what a healthy till does \
         when there is no news (hub#400)."
    );
}

#[test]
fn the_page_and_the_shell_name_the_same_command() {
    let source = read("apps/web/src/lib/app-update.ts");
    assert!(
        source.contains(VERSION_COMMAND),
        "the web app no longer invokes `{VERSION_COMMAND}`; whatever it invokes now must be a \
         command some capability grants, or the check is dead on every installed app"
    );
}

#[test]
fn the_release_publishes_the_version_the_cloud_reports() {
    // Without this file there is nothing to compare against: the bucket holds installers, and an
    // installer does not say which version it is. The Cloud reads exactly this key.
    let workflow = read(".github/workflows/tauri-release.yml");
    assert!(
        workflow.contains("latest.json"),
        "the release workflow no longer publishes the version manifest, so the Cloud has nothing \
         to report and every till reads `unknown` forever (hub#400)"
    );
    assert!(
        workflow.contains("downloads/app/latest/latest.json"),
        "the version manifest must land on the key the SaaS reads — `downloads/app/latest/latest.json`"
    );
}

#[test]
fn the_manifest_is_refreshed_for_every_channel_the_bucket_serves() {
    // `latest/` is the folder the Cloud serves from, on a tag push AND on a manual dispatch. A
    // manifest written only on tags would leave a hand-refreshed `latest/` announcing the previous
    // version — an update that never stops being offered, and an installer that is already there.
    let workflow = read(".github/workflows/tauri-release.yml");
    let manifest_step = workflow
        .split("Upload to Hetzner Object Storage")
        .nth(1)
        .expect("the upload step is where the manifest is written");
    assert!(
        manifest_step.contains("latest.json"),
        "the manifest must be written by the same step that uploads the installers, so the two \
         can never disagree about what `latest/` holds"
    );
}
