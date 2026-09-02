//! `contracts/kernel/routes.snapshot` ≡ the routes `app()` really registers — ERPlora/hub#1235.
//!
//! Regression test for ERPlora/hub#1235: the HTTP/WS surface of the runtime is what every module
//! and every shell talks to, and until now a route could be added, moved or have its gate relaxed
//! inside a 5 000-line file without anybody seeing it in a diff. So the surface lives in a file,
//! this test regenerates it from `crates/server/src/**` and the build breaks when the two
//! disagree — the mechanism of Kotlin's `apiCheck` and .NET's `PublicApiAnalyzers`.
//!
//! One line per (method, path):
//!
//! ```text
//! GET     /api/settings                                auth:session
//! PUT     /api/settings                                auth:admin
//! ```
//!
//! `auth:` is **derived, never declared**: the classes are the authentication primitives of
//! `crate::auth` reached from the handler through its own helpers and macros (see
//! [`PRIMITIVES`]). `none` means literally "no primitive on that path" — the login doors, the
//! liveness probes, the module assets, `/p/:locator` (whose authorisation IS the locator) and
//! whatever else the code leaves open, which is exactly what a reviewer of this file looks for.
//! The hub's outbound machine token is not a class: it authenticates the hub to the Cloud, not
//! the caller to the hub.
//!
//! Update: `UPDATE_KERNEL_CONTRACT=1 cargo test -p erplora-server --test kernel_contract_routes`,
//! and the resulting diff belongs in a `kind:contract` pull request (ADR «El Hub se CIERRA como
//! KERNEL»).

use std::collections::{BTreeMap, BTreeSet};

#[path = "support/kernel_snapshot.rs"]
mod kernel_snapshot;
#[path = "support/rust_source.rs"]
mod rust_source;

use rust_source::{blank_noise, block_end, called_names, crate_sources, item_bodies, paren_end};

/// The authentication primitives of this crate, and the class each one stands for.
///
/// This table IS the vocabulary of the snapshot. A new way of gating a route has to be added here
/// or every route it gates reads `none`, which the review of a `kind:contract` diff makes very
/// hard to miss.
const PRIMITIVES: &[(&str, &str)] = &[
    // A hub user whose local role administers the hub (`owner`/`admin`).
    ("auth::require_admin_session", "admin"),
    // Any signed-in hub user. A session resolved BY HAND is the same gate: see [`SESSION_BY_HAND`].
    ("auth::require_user_session", "session"),
    // A hub API key (`erpl_live_…`), the credential of the public per-module API.
    ("auth::api_key_principal", "api-key"),
    ("auth::api_key_context", "api-key"),
    ("auth::api_key_token", "api-key"),
    // Session OR API key: the dispatcher doors, which serve both planes.
    ("auth::authenticate", "any-credential"),
    // Second gate on top of the session: the calling module needs the capability granted.
    ("require_module_capability", "capability"),
    // NOT here on purpose: `auth::hub_scoped_auth` / `auth::machine_auth`. They hand the runtime
    // its OWN credential to call the Cloud (ADR-0003) and never look at who is calling — an
    // outbound token is not a gate, and listing it painted open routes as `auth:hub-token`.
];

/// A session gate written by hand: the body READS the session credential AND RESOLVES it
/// (`/api/auth/set-pin`, the profile helper). Both halves, on purpose — `auth_logout` reads the
/// token to delete it and answers the same with or without one, so reading alone is not a gate;
/// and `require_*_session` inside `auth.rs` resolve without the qualified read, so this rule does
/// not leak `session` into every route through the call graph.
const SESSION_BY_HAND: (&str, &str) = ("auth::session_token(", ".resolve_session(");

/// How far a gate may sit from the handler. Six is past the fixed point measured on `develop`
/// (handler → local helper → macro → `auth::…` closes at four), so it is a guard against a cycle,
/// not a limit anybody is meant to hit.
const MAX_DEPTH: usize = 6;

#[test]
fn routes_snapshot_matches_the_router_hub1235() {
    kernel_snapshot::assert_snapshot("routes.snapshot", &generate());
}

/// The router has to be readable at all: if the parser silently found nothing, every later
/// assertion would pass on an empty surface.
#[test]
fn the_router_is_readable_and_not_empty_hub1235() {
    let routes = routes_of_app();
    assert!(
        routes.len() > 100,
        "se han leído {} rutas de `app()`; el router del hub tiene más de cien, \
         así que esto es un fallo del lector, no una superficie que encogió",
        routes.len()
    );
    let known: BTreeSet<&str> = PRIMITIVES.iter().map(|(_, class)| *class).collect();
    for (_, _, class) in &routes {
        for part in class.split('+') {
            assert!(
                part == "none" || known.contains(part),
                "clase de auth `{part}` fuera del vocabulario de PRIMITIVES"
            );
        }
    }
}

/// `/api/auth/set-pin` resolves its session by hand (`auth::session_token` +
/// `Runtime::resolve_session`) instead of through `require_user_session`. It is a session gate all
/// the same — and it read `none` until this test existed (review of hub#1252).
#[test]
fn a_session_resolved_by_hand_is_a_session_gate_hub1235() {
    let body = "{ let Some(token) = auth::session_token(&headers) else { return unauthorized(); }; \
                let user = match rt.resolve_session(&token).await { Ok(Some(u)) => u, _ => return unauthorized() }; }";
    assert_eq!(classes_of(body), BTreeSet::from(["session".to_string()]));
    // `auth_logout`: reads the token to delete it, answers the same without one — not a gate.
    let logout = "{ if let Some(token) = auth::session_token(&headers) { let _ = rt.delete_session(&token).await; } ok() }";
    assert!(
        classes_of(logout).is_empty(),
        "leer el token sin resolverlo no es una puerta: {:?}",
        classes_of(logout)
    );
}

/// `auth::hub_scoped_auth` / `auth::machine_auth` hand the runtime ITS OWN credential to talk to
/// the Cloud (ADR-0003). They never check who is calling: a handler that only uses them is open to
/// anybody who reaches the hub, and the snapshot has to say `none` rather than mint a gate out of
/// an outbound token (review of hub#1252: `/api/assistant/checkout` read `auth:hub-token`).
#[test]
fn the_hub_machine_token_is_an_outbound_credential_not_a_gate_hub1235() {
    let body =
        "{ let Some(auth) = auth::hub_scoped_auth(&headers, &st) else { return unauthorized(); }; \
                let machine = auth::machine_auth(&st); cloud.call(&machine, &auth) }";
    let classes = classes_of(body);
    assert!(
        classes.is_empty(),
        "un token de salida se ha leído como puerta: {classes:?}"
    );
}

/// Classes of one synthetic handler body, through the same fixed point the snapshot uses.
fn classes_of(body: &str) -> BTreeSet<String> {
    let key = ("lib".to_string(), "handler".to_string());
    let mut bodies = BTreeMap::new();
    bodies.insert(key.clone(), body.to_string());
    class_map(&bodies).remove(&key).unwrap_or_default()
}

fn generate() -> String {
    let mut out = String::from(
        "# Rutas HTTP/WS del runtime — generado desde `crates/server/src/**`, NO editar a mano.\n\
         # `UPDATE_KERNEL_CONTRACT=1 cargo test -p erplora-server --test kernel_contract_routes`\n\
         # Contrato del kernel: ADR «El Hub se CIERRA como KERNEL».\n",
    );
    for (method, path, class) in routes_of_app() {
        out.push_str(&format!("{method:<7} {path:<46} auth:{class}\n"));
    }
    out
}

/// `(method, path, auth class)` for every route of `app()`, ordered by path then method.
fn routes_of_app() -> Vec<(String, String, String)> {
    let sources = crate_sources();
    // hub#1404 split `lib.rs`: `pub fn app(` lives in its own module now, so the router
    // source is WHICHEVER file declares it, not `lib.rs` by name.
    let router_src = sources
        .values()
        .find(|src| blank_noise(src).contains("pub fn app("))
        .expect("crates/server/src/** declara `pub fn app(`");
    let blanked = blank_noise(router_src);
    let bodies = item_bodies(&sources);

    let classes = class_map(&bodies);

    let body = app_body(&blanked);
    let mut rows: BTreeMap<(String, String), String> = BTreeMap::new();
    for (path, expr) in route_calls(&blanked, router_src, body) {
        for (method, handler) in method_handlers(&expr) {
            let mut key = split_handler(&handler);
            if !classes.contains_key(&key) {
                if let Some(resolved) = resolve_unqualified(&key.1, &bodies) {
                    key = resolved;
                }
            }
            let found = classes.get(&key).cloned().unwrap_or_default();
            let class = if found.is_empty() {
                "none".to_string()
            } else {
                found.into_iter().collect::<Vec<_>>().join("+")
            };
            rows.insert((path.clone(), method), class);
        }
    }
    rows.into_iter()
        .map(|((path, method), class)| (method, path, class))
        .collect::<Vec<_>>()
}

/// Byte range of the body of `pub fn app(…) -> Router { … }` inside the blanked `lib.rs`.
fn app_body(blanked: &str) -> (usize, usize) {
    let at = blanked
        .find("pub fn app(")
        .expect("`crates/server/src/lib.rs` declara `pub fn app(`");
    let after_args = paren_end(blanked, at + "pub fn app".len());
    let open = after_args + blanked[after_args..].find('{').expect("cuerpo de `app()`");
    (open, block_end(blanked, open))
}

/// `(path, argument expression)` for every `.route(…)` of the given range.
fn route_calls(blanked: &str, original: &str, (from, to): (usize, usize)) -> Vec<(String, String)> {
    let mut out = Vec::new();
    let mut i = from;
    while let Some(rel) = blanked[i..to].find(".route(") {
        let at = i + rel;
        let mut p = at + ".route(".len();
        while blanked.as_bytes()[p].is_ascii_whitespace() {
            p += 1;
        }
        assert_eq!(
            blanked.as_bytes()[p],
            b'"',
            "`.route(` sin literal de ruta en el offset {p}: el lector no entiende esta forma"
        );
        let close = p
            + 1
            + blanked[p + 1..]
                .find('"')
                .expect("cierre del literal de ruta");
        let path = original[p + 1..close].to_string();
        let mut m = close + 1;
        while blanked.as_bytes()[m].is_ascii_whitespace() || blanked.as_bytes()[m] == b',' {
            m += 1;
        }
        let end = paren_end(blanked, at + ".route".len());
        out.push((path, blanked[m..end.saturating_sub(1)].to_string()));
        i = end;
    }
    out
}

/// `get(handler)`, `.put(handler)`, `axum::routing::patch(handler)` → `(GET, handler)`, …
fn method_handlers(expr: &str) -> Vec<(String, String)> {
    const METHODS: &[&str] = &[
        "get", "post", "put", "delete", "patch", "head", "options", "trace",
    ];
    let b = expr.as_bytes();
    let mut out = Vec::new();
    for method in METHODS {
        let mut i = 0usize;
        while let Some(rel) = expr[i..].find(method) {
            let at = i + rel;
            i = at + method.len();
            if at > 0 && (b[at - 1].is_ascii_alphanumeric() || b[at - 1] == b'_') {
                continue;
            }
            if b.get(i) != Some(&b'(') {
                continue;
            }
            let close = paren_end(expr, i);
            let arg = expr[i + 1..close - 1].trim();
            if arg.is_empty()
                || !arg
                    .chars()
                    .all(|c| c.is_ascii_alphanumeric() || c == '_' || c == ':')
            {
                continue; // not a bare handler path — a nested builder, not a method
            }
            out.push((method.to_uppercase(), arg.to_string()));
        }
    }
    out
}

/// The files hub#1404 split the old `lib.rs` into. Before the split every one of these
/// items lived in ONE file and an unqualified call between them resolved for free; the
/// flat fallback below reproduces exactly that graph — and nothing more: a caller
/// OUTSIDE this set never gained resolution from the split, so it must not gain it now.
const SPLIT_FILES: [&str; 9] = [
    "assistant_api",
    "auth_api",
    "boot",
    "cloud_proxy",
    "config",
    "dispatch_api",
    "load_shed",
    "module_api",
    "routes",
];

fn is_split_file(file: &str) -> bool {
    SPLIT_FILES.contains(&file)
}

/// The (file, fn) of the ONE split file defining `name`, if exactly one does.
fn resolve_unqualified(
    name: &str,
    bodies: &BTreeMap<(String, String), String>,
) -> Option<(String, String)> {
    let mut hits = bodies.keys().filter(|(f, n)| n == name && is_split_file(f));
    let first = hits.next()?.clone();
    hits.next().is_none().then_some(first)
}

fn split_handler(handler: &str) -> (String, String) {
    match handler.rsplit_once("::") {
        Some((module, name)) => (
            module.rsplit("::").next().unwrap_or(module).to_string(),
            name.to_string(),
        ),
        None => ("lib".to_string(), handler.to_string()),
    }
}

/// Authentication classes of every item of the crate, propagated along its call graph.
///
/// A fixed point instead of a recursive walk: each round adds to an item what its callees know,
/// so after [`MAX_DEPTH`] rounds an item carries every primitive reachable within that many calls.
/// Resolution is deliberately narrow — a call resolves inside the module it was written in, or in
/// the module it names explicitly; a name that resolves nowhere is skipped rather than guessed at.
/// That is what keeps the classification from wandering into an unrelated helper of the same name.
fn class_map(
    bodies: &BTreeMap<(String, String), String>,
) -> BTreeMap<(String, String), BTreeSet<String>> {
    let mut classes: BTreeMap<(String, String), BTreeSet<String>> = BTreeMap::new();
    let mut edges: BTreeMap<(String, String), Vec<(String, String)>> = BTreeMap::new();
    for (key, body) in bodies {
        let mut direct = BTreeSet::new();
        for (marker, class) in PRIMITIVES {
            if body.contains(marker) {
                direct.insert((*class).to_string());
            }
        }
        if body.contains(SESSION_BY_HAND.0) && body.contains(SESSION_BY_HAND.1) {
            direct.insert("session".to_string());
        }
        classes.insert(key.clone(), direct);
        let callees = called_names(body)
            .into_iter()
            .filter_map(|call| {
                let k = match call.split_once("::") {
                    Some((m, n)) => (m.to_string(), n.to_string()),
                    None => {
                        let local = (key.0.clone(), call.clone());
                        if bodies.contains_key(&local) {
                            local
                        } else if is_split_file(&key.0) {
                            resolve_unqualified(&call, bodies)?
                        } else {
                            return None;
                        }
                    }
                };
                (bodies.contains_key(&k) && k != *key).then_some(k)
            })
            .collect();
        edges.insert(key.clone(), callees);
    }
    for _ in 0..MAX_DEPTH {
        let previous = classes.clone();
        for (key, callees) in &edges {
            let inherited: BTreeSet<String> = callees
                .iter()
                .filter_map(|c| previous.get(c))
                .flat_map(|s| s.iter().cloned())
                .collect();
            classes
                .get_mut(key)
                .expect("todo item tiene entrada")
                .extend(inherited);
        }
    }
    classes
}
