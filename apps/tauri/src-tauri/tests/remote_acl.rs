//! Guard for the shell's REMOTE-origin ACL — the security boundary of the app (ADR-0159/0196).
//!
//! The shell is a thin client: the webview navigates to origins that are NOT the bundled app, and
//! Tauri only lets such an origin call `invoke` when it matches a pattern declared in some
//! `capabilities/*.json` → `remote.urls`. That list hurts in BOTH directions:
//!
//! - too narrow → the hardware is DEAD in production (the till cannot print, the drawer never
//!   opens) and nobody notices until a real hub is in front of you, because dev talks to loopback;
//! - too wide → whatever runs on the allowed origin can drive the till's hardware.
//!
//! So the boundary is split in TWO capabilities on purpose (hub#334):
//!
//! - `default.json` — the hub PWA (`https://*.erplora.com`) plus the dev loopback. This is the
//!   ONLY place that grants the `erplora_*` hardware commands.
//! - `onboarding.json` — the SaaS apex (`https://erplora.com`), where the app BOOTS (ADR-0196).
//!   It gets the device identity and nothing else: the onboarding page never prints.
//!
//! Every assertion below reads the REAL `capabilities/*.json` — the whole directory, not a list
//! hardcoded here, so a capability file added tomorrow is covered the day it lands — and runs the
//! patterns through the SAME engine Tauri uses at runtime (`RemoteUrlPattern`, WHATWG URLPattern).

use std::path::PathBuf;
use std::str::FromStr;

use tauri::Url;
use tauri_utils::acl::RemoteUrlPattern;

/// Everything the onboarding origin (the SaaS apex) may ever ask the app for: the device identity
/// the hub login carries as `X-Device-Id` (single session, ADR-0154) and the escape hatch that
/// drops a captured hub. NOT the hardware.
const ONBOARDING_ALLOWLIST: [&str; 2] = ["allow-device-context", "allow-forget-hub"];

/// One `capabilities/*.json`, reduced to what the ACL cares about.
struct DeclaredCapability {
    file: String,
    /// Declared pattern, kept both as written and as Tauri compiles it.
    patterns: Vec<(String, RemoteUrlPattern)>,
    permissions: Vec<String>,
}

impl DeclaredCapability {
    fn parse(file: String, raw: &str) -> Self {
        let json: serde_json::Value =
            serde_json::from_str(raw).unwrap_or_else(|e| panic!("{file} is not valid JSON: {e}"));

        // A capability with no `remote` block is local-only (`tauri://`), which is legitimate and
        // outside this guard: it declares no remote origin, so it grants nothing to the cloud.
        let declared_urls = match json.get("remote") {
            None => Vec::new(),
            Some(remote) => remote["urls"]
                .as_array()
                .unwrap_or_else(|| panic!("{file} must declare remote.urls as an array"))
                .clone(),
        };
        let patterns = declared_urls
            .iter()
            .map(|value| {
                let declared = value
                    .as_str()
                    .unwrap_or_else(|| panic!("{file}: every remote.url must be a string"));
                let compiled = RemoteUrlPattern::from_str(declared)
                    .unwrap_or_else(|e| panic!("{file}: invalid pattern {declared:?}: {e:?}"));
                (declared.to_string(), compiled)
            })
            .collect();

        let permissions = json["permissions"]
            .as_array()
            .unwrap_or_else(|| panic!("{file} must declare permissions as an array"))
            .iter()
            .map(|value| {
                value
                    .as_str()
                    .unwrap_or_else(|| panic!("{file}: every permission must be a string"))
                    .to_string()
            })
            .collect();

        Self {
            file,
            patterns,
            permissions,
        }
    }

    fn authorizes(&self, url: &Url) -> bool {
        self.patterns.iter().any(|(_, pattern)| pattern.test(url))
    }
}

/// Every `capabilities/*.json` that ships with the crate. Read from disk on purpose: a capability
/// file is a security boundary, and a new one must not be able to slip past these guards just
/// because nobody remembered to list it here.
fn declared_capabilities() -> Vec<DeclaredCapability> {
    let dir = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("capabilities");
    let mut files: Vec<PathBuf> = std::fs::read_dir(&dir)
        .unwrap_or_else(|e| panic!("cannot read {}: {e}", dir.display()))
        .map(|entry| entry.expect("cannot read capability entry").path())
        .filter(|path| path.extension().is_some_and(|ext| ext == "json"))
        .collect();
    files.sort();

    assert!(
        !files.is_empty(),
        "no capability declared in {}: the app would have no IPC at all",
        dir.display()
    );

    files
        .into_iter()
        .map(|path| {
            let name = format!(
                "capabilities/{}",
                path.file_name().unwrap_or_default().to_string_lossy()
            );
            let raw = std::fs::read_to_string(&path)
                .unwrap_or_else(|e| panic!("cannot read {}: {e}", path.display()));
            DeclaredCapability::parse(name, &raw)
        })
        .collect()
}

fn url(raw: &str) -> Url {
    Url::parse(raw).unwrap_or_else(|e| panic!("invalid test URL {raw:?}: {e}"))
}

/// `true` when SOME declared capability authorizes that URL — the same semantics the ACL applies
/// at runtime.
fn is_authorized(raw: &str) -> bool {
    let parsed = url(raw);
    declared_capabilities()
        .iter()
        .any(|capability| capability.authorizes(&parsed))
}

/// Every permission any capability grants to that origin, tagged with the file that grants it.
fn permissions_granted_to(raw: &str) -> Vec<(String, String)> {
    let parsed = url(raw);
    declared_capabilities()
        .into_iter()
        .filter(|capability| capability.authorizes(&parsed))
        .flat_map(|capability| {
            let file = capability.file;
            capability
                .permissions
                .into_iter()
                .map(move |permission| (file.clone(), permission))
        })
        .collect()
}

/// Scheme and authority of a declared pattern, read straight from its text
/// (`https://*.erplora.com/*` → `("https", "*.erplora.com")`).
fn scheme_and_host(pattern: &str) -> (&str, &str) {
    let (scheme, rest) = pattern
        .split_once("://")
        .unwrap_or_else(|| panic!("pattern {pattern:?} declares no scheme"));
    (scheme, rest.split('/').next().unwrap_or_default())
}

// ── What MUST be authorized ─────────────────────────────────────────────────────────────────────

#[test]
fn authorizes_the_saas_onboarding_origin() {
    // ADR-0196: the app BOOTS at the SaaS (`{saas}/shell/`) and only reaches a hub from there. If
    // the apex is not declared the boot page cannot even ask for the device identity — and the
    // apex is NOT covered by `*.erplora.com`, which needs at least one label before the dot.
    assert!(
        is_authorized("https://erplora.com/shell/"),
        "the boot origin of the app is in no remote.urls → the onboarding cannot invoke"
    );
    assert!(is_authorized("https://erplora.com/"));
}

#[test]
fn authorizes_a_lettered_aura_hub() {
    // Hetzner auras are lettered (`Server.domain = "a.erplora.com"`) → `{slug}.a.erplora.com`:
    // TWO labels under `erplora.com`, not one. If this fails, `erplora_discover_printers` and
    // friends are dead in the published desktop app.
    assert!(
        is_authorized("https://panaderia.a.erplora.com/"),
        "the ACL does not cover a real cloud hub ({{slug}}.a.erplora.com) → hardware dead in prod"
    );
}

#[test]
fn authorizes_a_numbered_aura_hub() {
    // The AWS fallback provider numbers its auras (`Server.get_hub_url`) → `{slug}.{n}.erplora.com`.
    // Enumerating aura letters in the capability would have left this one out — and then shipping a
    // new aura would mean shipping a new app to every till.
    assert!(is_authorized("https://panaderia.3.erplora.com/"));
}

#[test]
fn authorizes_any_path_query_and_fragment_of_a_hub() {
    assert!(is_authorized("https://panaderia.a.erplora.com/pos/sale"));
    assert!(is_authorized("https://panaderia.a.erplora.com/?shell=1"));
    assert!(is_authorized("https://panaderia.a.erplora.com/#/orders"));
}

#[test]
fn authorizes_the_development_loopback_origins() {
    assert!(is_authorized("http://127.0.0.1:5173/"), "Vite PWA in dev");
    assert!(is_authorized("http://127.0.0.1:8787/"), "local runtime in dev");
    assert!(
        is_authorized("http://127.0.0.1:8001/shell/"),
        "local SaaS in dev (`manage.py runserver 8001`) — without it `ERPLORA_SHELL_URL` boots \
         into a page whose invokes are silently refused, and the fix looks like widening the \
         hardware capability"
    );
}

#[test]
fn the_hub_origin_can_drive_the_hardware() {
    let granted: Vec<String> = permissions_granted_to("https://panaderia.a.erplora.com/")
        .into_iter()
        .map(|(_, permission)| permission)
        .collect();

    for needed in ["allow-erplora-print", "allow-erplora-open-drawer"] {
        assert!(
            granted.iter().any(|permission| permission == needed),
            "the hub PWA does not get `{needed}` → the till cannot work"
        );
    }
}

// ── What must NOT be authorized ─────────────────────────────────────────────────────────────────

#[test]
fn rejects_an_undeclared_origin() {
    assert!(!is_authorized("https://example.com/"));
    assert!(!is_authorized("https://erplora.dev/"));
    assert!(!is_authorized("https://hub.erplora.net/"));
}

#[test]
fn rejects_a_domain_that_merely_starts_with_ours() {
    // The classic origin-confusion vector: the attacker registers `erplora.com.attacker.com`.
    assert!(
        !is_authorized("https://erplora.com.attacker.com/"),
        "a domain that STARTS with erplora.com must not pass the ACL"
    );
    assert!(!is_authorized("https://panaderia.a.erplora.com.attacker.com/"));
}

#[test]
fn rejects_a_domain_that_merely_ends_with_our_label() {
    // Registering `myerplora.com` must not buy you the till's printer.
    assert!(!is_authorized("https://myerplora.com/"));
    assert!(!is_authorized("https://x.myerplora.com/"));
}

#[test]
fn rejects_userinfo_confusion() {
    // `https://erplora.com@evil.com/` reads as ours to a human; the host is `evil.com`.
    assert!(!is_authorized("https://erplora.com@evil.com/"));
    assert!(!is_authorized("https://panaderia.a.erplora.com@evil.com/"));
}

#[test]
fn rejects_plain_http_outside_loopback() {
    // https only on remote; plain http is for loopback development.
    assert!(!is_authorized("http://panaderia.a.erplora.com/"));
    assert!(!is_authorized("http://erplora.com/"));
}

#[test]
fn the_saas_origin_cannot_drive_the_hardware() {
    // THE boundary hub#334 draws. `erplora.com` also serves marketing, billing and a third-party
    // checkout; the onboarding is by far the widest attack surface of the origins the app loads.
    // Whatever gets injected there must not be able to open the cash drawer.
    for (file, permission) in permissions_granted_to("https://erplora.com/shell/") {
        assert!(
            ONBOARDING_ALLOWLIST.contains(&permission.as_str()),
            "{file} authorizes the SaaS apex and grants `{permission}`; the onboarding origin may \
             only ever get {ONBOARDING_ALLOWLIST:?}"
        );
    }
}

#[test]
fn no_capability_declares_an_origin_outside_our_domain() {
    // Structural guard: rejecting today's known attackers is not enough, because the next widening
    // is written by someone who has not read this file. Every declared pattern must be https on
    // `erplora.com` (or a subdomain of it), or plain http on loopback for development.
    for capability in declared_capabilities() {
        for (declared, _) in &capability.patterns {
            let (scheme, host) = scheme_and_host(declared);
            let ours = host == "erplora.com" || host.ends_with(".erplora.com");
            let loopback = host.starts_with("127.0.0.1")
                || host.starts_with("localhost")
                || host.starts_with("[::1]");
            match scheme {
                "https" => assert!(
                    ours,
                    "{}: `{declared}` is not an erplora.com origin",
                    capability.file
                ),
                "http" => assert!(
                    loopback,
                    "{}: `{declared}` is plain http outside loopback",
                    capability.file
                ),
                other => panic!("{}: `{declared}` uses scheme `{other}`", capability.file),
            }
        }
    }
}
