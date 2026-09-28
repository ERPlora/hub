//! A tap on a system notice opens the screen it is about (hub#2305) — and both ends of that are
//! strings nothing compiles against, so both can go missing in silence.
//!
//! * The page subscribes to the notification plugin's `actionPerformed` through
//!   `plugin:notification|register_listener`. Without `notification:allow-register-listener` in the
//!   hub PWA's capability the ACL refuses it from the remote origin, the shell logs one warning and
//!   every tap goes back to opening the app wherever it was — which is also what an older app does,
//!   so nothing would look broken.
//! * The page sends the notice with an `id` (the only handle the tap comes back with on Android and
//!   iOS alike). A shell whose `erplora_notify` stops reading it shows the notice under a random id,
//!   and the tap no longer matches any destination.

use std::path::PathBuf;

const REGISTER_LISTENER: &str = "notification:allow-register-listener";

fn read(relative_to_manifest: &str) -> String {
    let path = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join(relative_to_manifest);
    std::fs::read_to_string(&path).unwrap_or_else(|e| panic!("cannot read {}: {e}", path.display()))
}

fn permissions_of(capability: &str) -> Vec<String> {
    let json: serde_json::Value =
        serde_json::from_str(&read(capability)).expect("the capability is not valid JSON");
    json["permissions"]
        .as_array()
        .expect("permissions must be an array")
        .iter()
        .map(|value| value.as_str().expect("every permission is a string").to_owned())
        .collect()
}

#[test]
fn the_hub_pwa_may_hear_a_notice_being_tapped() {
    let permissions = permissions_of("capabilities/default.json");
    assert!(
        permissions.iter().any(|p| p == REGISTER_LISTENER),
        "capabilities/default.json does not grant {REGISTER_LISTENER}: the hub PWA cannot hear a \
         tap on a notice, and tapping «New booking» opens the app wherever it was (hub#2305)"
    );
}

#[test]
fn only_the_hub_pwa_gets_to_listen() {
    // The SaaS apex and the degraded page never send a notice; nothing there has a tap to follow.
    for other in ["capabilities/onboarding.json", "capabilities/degraded.json"] {
        assert!(
            !permissions_of(other).iter().any(|p| p.starts_with("notification:")),
            "{other} grants a notification permission it has no use for"
        );
    }
}

#[test]
fn the_page_and_the_shell_name_the_same_event_and_argument() {
    let page = read("../../web/src/main.ts");
    assert!(
        page.contains("listenTauriPlugin('notification', 'actionPerformed', cb)"),
        "main.ts no longer listens to the notification plugin's `actionPerformed`"
    );
    let sender = read("../../web/src/lib/bridge-transport.ts");
    assert!(
        sender.contains("invokeTauri('erplora_notify', { title, body, id })"),
        "the page no longer sends the notice's `id` to `erplora_notify`"
    );
    let shell = read("src/lib.rs");
    assert!(
        shell.contains("fn erplora_notify(app: tauri::AppHandle, title: String, body: String, id: Option<i64>)"),
        "`erplora_notify` no longer takes the `id` the page sends"
    );
}
