//! Which page may drive this device: the hub the app is LINKED to, and no other (hub#2504).
//!
//! Tauri's ACL decides by PATTERN (`capabilities/default.json` → `https://*.erplora.com/*`), and a
//! pattern cannot name the one business this till belongs to: the hub is chosen at run time, from
//! the SaaS, long after the binary was built. So the ACL lets every page under erplora.com through
//! — another business's hub, the public website, the test SaaS — and this module is the second
//! gate, in front of the app's own commands: the printer, the drawer, the card reader, the way out
//! to the browser and the Downloads folder answer only the page whose ORIGIN is the linked hub.
//!
//! The link itself needs the same care, or the gate is one navigation away from moot: any page
//! the window shows could navigate to its own address with `?shell=1` and become "the hub". So a
//! `?shell=1` navigation links the app only when it LEAVES an entry page (the SaaS, which chooses
//! the hub among the person's own) or lands on the hub already linked. The app links on its own
//! authority too — the hub it remembered, a link the system handed it — through [`HubLink::link`].

use std::sync::Mutex;

use tauri::ipc::Invoke;
use tauri::{Runtime, Url};

/// What a page the ACL lets through may always ask for, linked or not: the device identity and the
/// escape hatch the onboarding needs (`capabilities/onboarding.json`), and the retry of the bundled
/// offline page (`capabilities/degraded.json`). Everything else belongs to the linked hub — a
/// command added tomorrow is closed until someone opens it here on purpose.
const OPEN_COMMANDS: [&str; 3] = ["device_context", "forget_hub", "shell_retry"];

/// The error code a page gets when it asks for a command that belongs to the linked hub.
pub const NOT_THE_LINKED_HUB: &str = "not_the_linked_hub";

/// May any page the ACL lets through call this command?
pub fn is_open_command(command: &str) -> bool {
    OPEN_COMMANDS.contains(&command)
}

/// The ORIGIN of `url`, serialized the way `hub.url` stores it. Opaque origins (`tauri://`, the
/// bundled page) serialize as `null`, which no hub origin ever equals.
fn origin_of(url: &Url) -> String {
    url.origin().ascii_serialization()
}

#[derive(Debug, Default)]
struct LinkState {
    /// The hub this app is linked to — the origin of `hub.url` — if any.
    linked: Option<String>,
    /// The origin of the page the window last went to: the one a `?shell=1` navigation leaves.
    showing: Option<String>,
}

/// The hub this installation is linked to, and the page the window is on.
#[derive(Debug)]
pub struct HubLink {
    /// The pages that choose a hub for the person: the SaaS (and, in development, the page the
    /// override boots at).
    entries: Vec<String>,
    state: Mutex<LinkState>,
}

impl HubLink {
    /// `entries` are the origins a `?shell=1` navigation may leave; `showing` is where the window
    /// starts.
    pub fn new(entries: Vec<String>, showing: Option<&Url>) -> Self {
        Self {
            entries,
            state: Mutex::new(LinkState {
                linked: None,
                showing: showing.map(origin_of),
            }),
        }
    }

    fn state(&self) -> std::sync::MutexGuard<'_, LinkState> {
        // A poisoned lock only means another thread panicked holding it; the two `Option`s inside
        // are still whole, so the gate keeps answering instead of taking the till down with it.
        self.state.lock().unwrap_or_else(|poisoned| poisoned.into_inner())
    }

    /// The app links this hub on its own authority: the one it remembered, or the one a link the
    /// system handed it points at (HUB_APP-F02, F03).
    pub fn link(&self, origin: &str) {
        self.state().linked = Some(origin.to_string());
    }

    /// No hub any more: «Change business», or the hub is gone (HUB_APP-F04, F05).
    pub fn forget(&self) {
        self.state().linked = None;
    }

    /// The hub this app is linked to, if any.
    pub fn linked(&self) -> Option<String> {
        self.state().linked.clone()
    }

    /// The window follows a navigation to `url`. Returns the origin to remember as `hub.url` when
    /// this navigation links the app (`?shell=1` on a hub of ours, from an entry page or onto the
    /// hub already linked); `None` otherwise.
    pub fn follow(&self, url: &Url) -> Option<String> {
        let captured = crate::shell_capture_origin(url);
        let mut state = self.state();
        let left = state.showing.replace(origin_of(url));
        let origin = captured?;
        let from_an_entry = left.as_ref().is_some_and(|left| self.entries.contains(left));
        let already_linked = state.linked.as_deref() == Some(origin.as_str());
        if !from_an_entry && !already_linked {
            log::warn!(
                "shell: {origin} asks to be the linked hub from {}; only the SaaS chooses it",
                left.as_deref().unwrap_or("nowhere")
            );
            return None;
        }
        state.linked = Some(origin.clone());
        Some(origin)
    }

    /// May the page at `page` call the commands that belong to the linked hub?
    pub fn drives(&self, page: &Url) -> bool {
        self.state().linked.as_deref() == Some(origin_of(page).as_str())
    }
}

/// Puts the gate in front of the app's commands: `run` hands Tauri `guard(app_commands())`.
pub fn guard<R, F>(commands: F) -> impl Fn(Invoke<R>) -> bool + Send + Sync + 'static
where
    R: Runtime,
    F: Fn(Invoke<R>) -> bool + Send + Sync + 'static,
{
    move |invoke: Invoke<R>| {
        if !admits(&invoke) {
            log::warn!(
                "ipc: {} refused to {}: not the linked hub",
                invoke.message.command(),
                invoke
                    .message
                    .webview_ref()
                    .url()
                    .map(|page| origin_of(&page))
                    .unwrap_or_else(|_| "an unreadable page".to_string())
            );
            invoke.resolver.reject(NOT_THE_LINKED_HUB);
            return true;
        }
        commands(invoke)
    }
}

/// Does this invoke come from a page allowed to run its command? Fails closed: no link state, or a
/// page whose address cannot be read, drives nothing.
fn admits<R: Runtime>(invoke: &Invoke<R>) -> bool {
    use tauri::Manager;
    if is_open_command(invoke.message.command()) {
        return true;
    }
    let webview = invoke.message.webview_ref();
    let Some(link) = webview.try_state::<HubLink>() else {
        return false;
    };
    webview.url().is_ok_and(|page| link.drives(&page))
}

#[cfg(test)]
mod tests {
    use super::*;

    const SAAS: &str = "https://erplora.com";
    const HUB: &str = "https://panaderia.a.erplora.com";

    fn url(raw: &str) -> Url {
        raw.parse().expect("test URL")
    }

    /// A fresh install on the SaaS onboarding, as `open_main_window` builds it.
    fn on_the_onboarding() -> HubLink {
        HubLink::new(vec![SAAS.to_string()], Some(&url("https://erplora.com/shell/")))
    }

    fn linked_to_the_hub() -> HubLink {
        let link = on_the_onboarding();
        link.link(HUB);
        link
    }

    // ── The gate: only the linked hub drives the device ────────────────────────────────────────

    #[test]
    fn the_linked_hub_drives_the_device_on_any_of_its_pages() {
        let link = linked_to_the_hub();
        assert!(link.drives(&url("https://panaderia.a.erplora.com/")));
        assert!(link.drives(&url("https://panaderia.a.erplora.com/m/sales?x=1#/pos")));
    }

    #[test]
    fn another_page_under_erplora_com_does_not_drive_the_device() {
        let link = linked_to_the_hub();
        for page in [
            "https://otronegocio.a.erplora.com/", // another business
            "https://www.erplora.com/",           // the public website
            "https://pre.erplora.com/",           // the test SaaS
            "https://erplora.com/shell/",         // the SaaS apex
            "http://panaderia.a.erplora.com/",    // the same host, another scheme
            "https://panaderia.a.erplora.com:8443/", // the same host, another port
            "http://127.0.0.1:5173/",             // a page served from this device
            "tauri://localhost/index.html",       // the bundled page
        ] {
            assert!(!link.drives(&url(page)), "{page} drives a till linked to {HUB}");
        }
    }

    #[test]
    fn nothing_drives_the_device_before_a_hub_is_linked() {
        let link = on_the_onboarding();
        assert!(!link.drives(&url("https://panaderia.a.erplora.com/")));
    }

    #[test]
    fn forgetting_the_hub_takes_the_device_away_from_it() {
        let link = linked_to_the_hub();
        link.forget();
        assert_eq!(link.linked(), None);
        assert!(!link.drives(&url("https://panaderia.a.erplora.com/")));
    }

    #[test]
    fn only_identity_escape_and_retry_are_open_to_any_page() {
        for open in ["device_context", "forget_hub", "shell_retry"] {
            assert!(is_open_command(open), "{open} must stay reachable from the onboarding");
        }
        for owned in [
            "erplora_print",
            "erplora_test_print",
            "erplora_open_drawer",
            "erplora_discover_printers",
            "erplora_add_network_printer",
            "erplora_nfc_read",
            "open_external_url",
            "save_download",
            "print_document",
            "erplora_notify",
            "autostart_enable",
            "a_command_added_tomorrow",
        ] {
            assert!(!is_open_command(owned), "{owned} is open to any page under erplora.com");
        }
    }

    // ── The link: who may make a hub "the hub" ─────────────────────────────────────────────────

    #[test]
    fn the_saas_links_the_hub_it_sends_the_window_to() {
        let link = on_the_onboarding();
        // The chooser's /shell/open/<id>/ 302s into the hub with the marker.
        assert_eq!(link.follow(&url("https://erplora.com/shell/open/7/")), None);
        assert_eq!(
            link.follow(&url("https://panaderia.a.erplora.com/?shell=1")),
            Some(HUB.to_string())
        );
        assert_eq!(link.linked().as_deref(), Some(HUB));
        assert!(link.drives(&url("https://panaderia.a.erplora.com/")));
    }

    #[test]
    fn a_page_under_erplora_com_cannot_link_itself() {
        let link = linked_to_the_hub();
        // The hub page links out to the website; the website marks itself.
        assert_eq!(link.follow(&url("https://www.erplora.com/precios")), None);
        assert_eq!(link.follow(&url("https://www.erplora.com/?shell=1")), None);
        assert_eq!(link.linked().as_deref(), Some(HUB), "the website replaced the linked hub");
        assert!(!link.drives(&url("https://www.erplora.com/")));
    }

    #[test]
    fn another_business_cannot_take_the_till_by_marking_its_own_address() {
        let link = linked_to_the_hub();
        assert_eq!(link.follow(&url("https://otronegocio.a.erplora.com/")), None);
        assert_eq!(link.follow(&url("https://otronegocio.a.erplora.com/?shell=1")), None);
        assert_eq!(link.linked().as_deref(), Some(HUB));
    }

    #[test]
    fn the_linked_hub_may_carry_the_marker_again() {
        let link = linked_to_the_hub();
        assert_eq!(link.follow(&url("https://panaderia.a.erplora.com/login")), None);
        assert_eq!(
            link.follow(&url("https://panaderia.a.erplora.com/?shell=1")),
            Some(HUB.to_string())
        );
    }

    #[test]
    fn change_business_goes_back_through_the_saas() {
        let link = linked_to_the_hub();
        link.forget();
        link.follow(&url("https://erplora.com/shell/?choose=1"));
        assert_eq!(
            link.follow(&url("https://otronegocio.a.erplora.com/?shell=1")),
            Some("https://otronegocio.a.erplora.com".to_string())
        );
        assert!(!link.drives(&url("https://panaderia.a.erplora.com/")));
    }

    #[test]
    fn a_marker_on_an_address_that_is_not_ours_links_nothing_even_from_the_saas() {
        let link = on_the_onboarding();
        assert_eq!(link.follow(&url("https://evil.com/?shell=1")), None);
        assert_eq!(link.linked(), None);
    }

    // ── Through the IPC: what a page actually gets back ────────────────────────────────────────
    //
    // A real `on_message` round trip on the mock runtime, with the gate in front of a dispatcher
    // that answers "ran" to any command. The request travels as the bundled page (`tauri://`): the
    // mock context carries no ACL manifest, so Tauri's own pattern check stays out of the way and
    // what is measured is the gate alone — which reads the page the WINDOW shows, as Tauri does.

    use tauri::test::{MockRuntime, INVOKE_KEY};

    struct Till {
        _app: tauri::App<MockRuntime>,
        window: tauri::WebviewWindow<MockRuntime>,
    }

    fn till_showing(page: &str, link: Option<HubLink>) -> Till {
        use tauri::Manager;
        let app = tauri::test::mock_builder()
            .invoke_handler(guard(|invoke: Invoke<MockRuntime>| {
                invoke.resolver.resolve("ran");
                true
            }))
            .build(tauri::test::mock_context(tauri::test::noop_assets()))
            .expect("mock app");
        if let Some(link) = link {
            app.manage(link);
        }
        let window =
            tauri::WebviewWindowBuilder::new(&app, "main", tauri::WebviewUrl::External(url(page)))
                .build()
                .expect("main window");
        Till { _app: app, window }
    }

    fn ask(till: &Till, command: &str) -> Result<serde_json::Value, serde_json::Value> {
        tauri::test::get_ipc_response(
            &till.window,
            tauri::webview::InvokeRequest {
                cmd: command.into(),
                callback: tauri::ipc::CallbackFn(0),
                error: tauri::ipc::CallbackFn(1),
                url: url("tauri://localhost"),
                body: tauri::ipc::InvokeBody::default(),
                headers: Default::default(),
                invoke_key: INVOKE_KEY.to_string(),
            },
        )
        .map(|body| body.deserialize::<serde_json::Value>().expect("json answer"))
    }

    fn refused() -> Result<serde_json::Value, serde_json::Value> {
        Err(serde_json::Value::from(NOT_THE_LINKED_HUB))
    }

    #[test]
    fn the_website_is_refused_the_drawer_of_a_till_linked_to_a_hub() {
        let till = till_showing("https://www.erplora.com/", Some(linked_to_the_hub()));
        for command in ["erplora_open_drawer", "erplora_print", "erplora_test_print", "erplora_nfc_read"] {
            assert_eq!(ask(&till, command), refused(), "{command} ran for the website");
        }
    }

    #[test]
    fn another_business_is_refused_the_printer() {
        let till = till_showing("https://otronegocio.a.erplora.com/m/sales", Some(linked_to_the_hub()));
        assert_eq!(ask(&till, "erplora_print"), refused());
        assert_eq!(ask(&till, "save_download"), refused());
        assert_eq!(ask(&till, "open_external_url"), refused());
    }

    #[test]
    fn the_linked_hub_prints_and_opens_the_drawer() {
        let till = till_showing("https://panaderia.a.erplora.com/m/sales", Some(linked_to_the_hub()));
        assert_eq!(ask(&till, "erplora_print"), Ok("ran".into()));
        assert_eq!(ask(&till, "erplora_open_drawer"), Ok("ran".into()));
    }

    #[test]
    fn the_onboarding_still_gets_the_device_identity_and_the_escape_hatch() {
        let till = till_showing("https://erplora.com/shell/", Some(on_the_onboarding()));
        assert_eq!(ask(&till, "device_context"), Ok("ran".into()));
        assert_eq!(ask(&till, "forget_hub"), Ok("ran".into()));
        assert_eq!(ask(&till, "erplora_print"), refused());
    }

    #[test]
    fn without_a_link_state_the_device_stays_closed() {
        // Fail closed: if the state never got managed, nothing but the open commands answer.
        let till = till_showing("https://panaderia.a.erplora.com/", None);
        assert_eq!(ask(&till, "erplora_open_drawer"), refused());
        assert_eq!(ask(&till, "device_context"), Ok("ran".into()));
    }
}
