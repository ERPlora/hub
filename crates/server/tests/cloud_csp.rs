//! Guard for the CSP of the page the Hub actually serves to a browser (hub#708).
//!
//! The twin of `apps/tauri/src-tauri/tests/shell_csp.rs`, and the half that was missing. That test
//! pins the policy of `shell-dist/index.html` — the degraded page bundled inside the installed
//! app. It is *not* the app: `app.security.csp` only ever reaches assets served through the Tauri
//! protocol, so the window that navigates to `https://<hub>.erplora.com` carries the policy THAT
//! SERVER sends. This crate is that server.
//!
//! And it sent nothing. `ServeConfig::from_env` read `HUB_CSP`, the provisioner wrote
//! `HUB_CSP_ENFORCE`, and the two names never met — so every hub in the fleet, web and installed
//! app alike, answered with no `Content-Security-Policy` at all while the one page nobody browses
//! was sealed shut. Hence the shape of the fix this file pins: the policy is a CONSTANT IN THE
//! CODE THAT SERVES THE DOCUMENT, `HUB_CSP` may only replace it, and `ServeConfig.csp` is a
//! `String` rather than an `Option<String>` so that "hub with no policy" stops being a state the
//! type can even hold. A variable in another repo, injected by one of two providers and applied
//! only on redeploy, is what failed; a default that ships with the binary cannot drift.
//!
//! Why this policy is load-bearing and not hygiene: every module's Web Component runs in the SAME
//! document and the SAME realm as the shell — no iframe, no sandbox — with the session token in
//! `localStorage`. There is no origin boundary between a module and the till. The CSP is one of
//! the few real walls left on that surface.
use axum::body::Body;
use axum::http::{Request, StatusCode};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{
    build_serving_router, default_csp, AppState, AuthMode, HubConfig, ServeConfig,
};
use std::collections::BTreeMap;
use tower::ServiceExt; // oneshot

/// The shell policy, read from the file that ships it — never copied, or the comparison below
/// would be against a snapshot of what the shell used to say.
const TAURI_CONF: &str = include_str!("../../../apps/tauri/src-tauri/tauri.conf.json");

/// The Cloud a production hub is pointed at. The policy is a function of it, so the tests have to
/// name one; this is what `HUB_CLOUD_API_URL` carries on the fleet.
const CLOUD: &str = "https://erplora.com";

/// The policy a production hub actually serves.
fn served() -> String {
    default_csp(CLOUD)
}

const INDEX_HTML: &str = "<!doctype html><title>ERPlora SPA</title><div id=app></div>";

/// A `dist/` with an index, so the request under test is for a DOCUMENT — the response whose
/// policy the browser actually applies to the app.
fn temp_dist() -> std::path::PathBuf {
    let dir = std::env::temp_dir().join(format!("erplora_hub708_csp_{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).unwrap();
    std::fs::write(dir.join("index.html"), INDEX_HTML).unwrap();
    dir
}

async fn make_state() -> AppState {
    let db = fresh_db().await;
    let rt = Runtime::new(Box::new(db));
    AppState::with_config(rt, HubConfig::from_env_with_auth(AuthMode::Dev))
}

/// A policy string split into `directive -> sources`.
fn directives(policy: &str) -> BTreeMap<String, Vec<String>> {
    policy
        .split(';')
        .filter_map(|directive| {
            let mut parts = directive.split_whitespace();
            let name = parts.next()?;
            Some((
                name.to_string(),
                parts.map(str::to_string).collect::<Vec<_>>(),
            ))
        })
        .collect()
}

/// Sources of a fetch directive, falling back to `default-src` exactly like a browser does.
fn effective(policy: &str, directive: &str) -> Vec<String> {
    let parsed = directives(policy);
    parsed
        .get(directive)
        .or_else(|| parsed.get("default-src"))
        .cloned()
        .unwrap_or_default()
}

fn shell_policy() -> String {
    let conf: serde_json::Value =
        serde_json::from_str(TAURI_CONF).expect("tauri.conf.json is not valid JSON");
    conf["app"]["security"]["csp"]
        .as_str()
        .expect("tauri.conf.json must declare app.security.csp as a string")
        .to_string()
}

// ── The header is there at all — the actual bug ─────────────────────────────────────────────────

#[tokio::test]
async fn the_document_a_hub_serves_carries_a_content_security_policy() {
    // The regression in one assertion: `GET /` is the app's document, and it came back bare.
    let dist = temp_dist();
    let web_dir = dist.to_string_lossy().into_owned();
    let policy = served();
    let router = build_serving_router(make_state().await, Some(&web_dir), &policy);

    let resp = router
        .oneshot(Request::get("/").body(Body::empty()).unwrap())
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    assert_eq!(
        resp.headers()
            .get("content-security-policy")
            .map(|v| v.to_str().unwrap()),
        Some(policy.as_str()),
        "the hub served the app's document with no policy — which is how it shipped: the \
         provisioner set HUB_CSP_ENFORCE and the runtime read HUB_CSP"
    );

    let _ = std::fs::remove_dir_all(&dist);
}

#[tokio::test]
async fn a_hub_that_was_told_nothing_still_gets_the_policy() {
    // The state of every hub in the fleet: no `HUB_CSP` anywhere in its env. It has to be the
    // protected case, not the bare one — the default is the whole fix.
    let hub = HubConfig::from_env_with_auth(AuthMode::Dev);
    let cfg = ServeConfig {
        database_url: String::new(),
        bind: "127.0.0.1:0".into(),
        modules_dir: None,
        csp: default_csp(&hub.cloud_base_url),
        hub,
        machine_token_cell: None,
        hub_id_cell: None,
        web_dir: None,
    };
    let router = build_serving_router(make_state().await, cfg.web_dir.as_deref(), &cfg.csp);
    let resp = router
        .oneshot(Request::get("/healthz").body(Body::empty()).unwrap())
        .await
        .unwrap();
    assert!(
        resp.headers().contains_key("content-security-policy"),
        "a hub built straight from its config answers without a policy"
    );
}

// ── …and the policy stays worth having ──────────────────────────────────────────────────────────

#[test]
fn the_app_can_neither_inline_nor_evaluate_script() {
    let script = effective(&served(), "script-src");
    for forbidden in ["'unsafe-inline'", "'unsafe-eval'"] {
        assert!(
            !script.iter().any(|source| source == forbidden),
            "script-src allows {forbidden}: with every module's Web Component sharing this realm \
             and the session token in localStorage, that is the wall coming down"
        );
    }
    // Verified against the shipped bundle rather than assumed: the one `new Function(` left in
    // `apps/web/dist` is core-js's `globalThis` probe, dead behind a `typeof globalThis` check, and
    // pdf.js 5 dropped its `eval` path (hence no `isEvalSupported` option any more).
    assert!(
        !script.iter().any(|source| source == "'wasm-unsafe-eval'"),
        "nothing in the app instantiates WebAssembly in the browser — the modules' `handler.wasm` \
         runs server-side in the runtime, never in the page"
    );
}

#[test]
fn the_app_frames_nothing_and_rebases_nowhere() {
    let parsed = directives(&served());
    assert_eq!(parsed.get("object-src"), Some(&vec!["'none'".to_string()]));
    assert_eq!(parsed.get("frame-src"), Some(&vec!["'none'".to_string()]));
    assert_eq!(parsed.get("base-uri"), Some(&vec!["'self'".to_string()]));
}

#[test]
fn the_app_may_still_adopt_its_own_styles() {
    // Not hygiene to be tidied away later: Lit adopts component styles through the CSSOM and Ionic
    // writes inline style, so dropping this is a blank, unstyled till. Pinned so the removal is a
    // decision somebody has to argue with, not a passing tidy-up.
    assert!(
        effective(&served(), "style-src").contains(&"'unsafe-inline'".to_string()),
        "style-src lost 'unsafe-inline': Lit and Ionic both need it, and the app renders unstyled"
    );
}

#[test]
fn the_policy_does_not_pin_form_action() {
    // `form-action` does NOT fall back to `default-src`, so its absence is a decision and must stay
    // one. Pinning it breaks the Google login: `googleLoginUrl` sends the browser to the SaaS,
    // allauth bounces it through `/auth/hub-bridge/` and back to the hub with a one-shot code, and
    // `form-action 'self'` cuts that chain with no error the user can act on. Already learned the
    // hard way on the SaaS side.
    assert!(
        !directives(&served()).contains_key("form-action"),
        "form-action is pinned: that is the directive that kills the Google login redirect chain"
    );
}

#[test]
fn the_only_origins_besides_the_hub_are_its_cloud_and_the_tauri_ipc_channel() {
    // The app fetches the SaaS DIRECTLY from the browser — token refresh, `/auth/me/`, invoice
    // downloads (`apps/web/src/lib/cloud.ts`) — so `connect-src 'self'` alone logs everybody out
    // of the cloud half of the hub. Media and module bundles are NOT here: those the runtime
    // proxies (ADR-0047), which is what keeps this list to two names.
    let allowed = ["http://ipc.localhost", CLOUD];
    for (directive, sources) in directives(&served()) {
        for source in sources.iter().filter(|s| s.contains("://")) {
            assert!(
                directive == "connect-src" && allowed.contains(&source.as_str()),
                "{directive} reaches out to `{source}`; the browser talks to this hub, to its own \
                 Cloud and to the Tauri IPC channel, and to nothing else"
            );
        }
    }
}

#[test]
fn the_installed_app_can_still_reach_the_hardware() {
    // The trap this policy walks straight into if nobody looks: the installed app does NOT run a
    // bundled `dist`. Its window navigates to `https://<hub>.erplora.com` (ADR-0159 — see
    // `apps/tauri/src-tauri/capabilities/default.json`), so the document it runs is the one THIS
    // server sends, under THIS policy. Tauri's `invoke` is a `fetch` to `ipc://localhost/<cmd>`
    // (`tauri/src/ipc/protocol.rs`), rewritten to `http://ipc.localhost/<cmd>` on Windows and
    // Android. Drop these two and every till loses printing, the cash drawer and printer
    // discovery — silently, and only in the packaged app, where no test looks.
    let connect = effective(&served(), "connect-src");
    for channel in ["ipc:", "http://ipc.localhost"] {
        assert!(
            connect.iter().any(|source| source == channel),
            "connect-src dropped `{channel}`: the till stops printing in the installed app"
        );
    }
}

#[test]
fn the_cloud_origin_follows_the_configuration_instead_of_being_hardcoded() {
    // ADR-0050 pending (c), closed here: the old `LOOPBACK_CSP` baked `https://erplora.com` in, so
    // a self-host or a staging aura pointed elsewhere was blocked by its own policy — silently,
    // because a CSP violation is a console line nobody is reading on a till.
    assert!(default_csp("https://saas.example.test").contains("https://saas.example.test"));

    // A path is not an origin: left on, the browser path-matches and `/api/v1/auth/refresh/` stops
    // matching the source. Trailing slashes are how a base URL is usually written, so this is the
    // likely input, not the exotic one.
    for written_as in [
        "https://erplora.com/",
        "  https://erplora.com  ",
        "HTTPS://erplora.com",
        "https://erplora.com/api/v1/",
    ] {
        assert_eq!(
            default_csp(written_as),
            served(),
            "{written_as:?} did not reduce to the bare origin; a source with a path attached \
             stops matching every endpoint the app actually calls"
        );
    }

    // No Cloud configured (dev, a bare binary): no cloud origin is allowed. The IPC channel stays —
    // it is not an origin anybody can reach, and the packaged app needs it either way.
    let without_cloud = default_csp("");
    assert!(!without_cloud.contains("erplora.com"));

    // A value that is not an absolute http(s) URL cannot become a source. It would either break
    // the header or, with a `;` in it, append a directive of the attacker's choosing.
    for junk in [
        "erplora.com",
        "javascript:alert(1)",
        "https://a b.com",
        "https://x.com;script-src *",
    ] {
        assert_eq!(
            default_csp(junk),
            without_cloud,
            "{junk:?} reached the policy: a bad HUB_CLOUD_API_URL must not be able to write CSP"
        );
    }
}

// ── Cloud vs shell: every difference is enumerated ──────────────────────────────────────────────

/// Sources the SERVED policy adds on top of the SHELL policy, each with the reason it exists.
/// A widening that is not on this list fails the test — which is what "equivalent, or justified in
/// writing" means once it is executable. The two policies cannot simply be identical: the shell
/// policy governs one bundled page that renders with no network at all, this one governs the whole
/// app.
const JUSTIFIED_WIDENINGS: &[(&str, &str, &str)] = &[
    (
        "img-src",
        "blob:",
        "the file viewer and the avatar paint bytes the runtime already fetched, via \
         URL.createObjectURL — the browser never reaches the storage itself (ADR-0047)",
    ),
    (
        "media-src",
        "blob:",
        "same bytes, same route, for the <video>/<audio> previews; media-src falls back to \
         default-src, so without this line the preview is a dead player",
    ),
    (
        "connect-src",
        CLOUD,
        "the app calls the SaaS straight from the browser for token refresh, /auth/me/ and \
         invoice downloads (apps/web/src/lib/cloud.ts). The shell page needs no such thing: it \
         renders with no network at all, which is the whole point of it",
    ),
    (
        "connect-src",
        "ipc:",
        "Tauri's invoke is a fetch to ipc://localhost/<cmd>, and the installed app runs THIS \
         document, not a bundled one (ADR-0159). The shell page invokes nothing",
    ),
    (
        "connect-src",
        "http://ipc.localhost",
        "the same channel as seen on Windows and Android, where the custom scheme is rewritten \
         to a http://<scheme>.localhost origin",
    ),
];

/// Directives whose values are NOT sources, so "the shell does not allow this" is a category
/// error rather than a widening: they authorise nothing, and the comparison below cannot mean
/// anything about them.
///
/// Nothing is being waved through here. A value that IS an origin —say a `report-uri` pointing at
/// somebody else's collector, which would hand a third party the URL of every page a till
/// visits— still fails `the_only_origins_besides_the_hub_are_its_cloud_and_the_tauri_ipc_channel`,
/// which sweeps EVERY directive for `://`. What this list removes is only the source comparison.
const NON_FETCH_DIRECTIVES: &[(&str, &str)] = &[(
    "report-uri",
    "hub#1447: it does not let anything load — it says where the browser posts what the policy \
     REFUSED. The shell has no counterpart because it renders with no network at all and has \
     nowhere to post to; this policy's report goes to the hub's own /csp-report/",
)];

#[test]
fn every_way_the_served_policy_is_looser_than_the_shell_is_written_down() {
    let shell = shell_policy();
    for (directive, sources) in directives(&served()) {
        if NON_FETCH_DIRECTIVES.iter().any(|(d, _)| *d == directive) {
            continue;
        }
        let allowed_by_shell = effective(&shell, &directive);
        for source in sources {
            if allowed_by_shell.contains(&source) {
                continue;
            }
            let justified = JUSTIFIED_WIDENINGS
                .iter()
                .any(|(d, s, _)| *d == directive && *s == source);
            assert!(
                justified,
                "the served policy allows `{source}` in {directive} and the shell policy does \
                 not, with no reason recorded. Add it to JUSTIFIED_WIDENINGS with the reason, or \
                 take it out — an undocumented widening is how a policy rots into decoration"
            );
        }
    }
}

#[test]
fn the_served_policy_keeps_every_lock_the_shell_has() {
    // The other direction: the shell may not be strictly tighter on the directives that decide
    // whether a page is a sealed box. (It is allowed to be tighter where the widenings above say
    // so, and those are checked by name.)
    let shell = shell_policy();
    let served = directives(&served());
    for directive in ["default-src", "object-src", "frame-src", "base-uri"] {
        assert_eq!(
            served.get(directive),
            directives(&shell).get(directive),
            "{directive} drifted apart from the shell policy with no widening to justify it"
        );
    }
}
