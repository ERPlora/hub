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
//! liveness probes, the module assets and `/p/:locator`, whose authorisation IS the locator.
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
    // Any signed-in hub user.
    ("auth::require_user_session", "session"),
    // A hub API key (`erpl_live_…`), the credential of the public per-module API.
    ("auth::api_key_principal", "api-key"),
    ("auth::api_key_context", "api-key"),
    ("auth::api_key_token", "api-key"),
    // Session OR API key: the dispatcher doors, which serve both planes.
    ("auth::authenticate", "any-credential"),
    // The hub's own machine credential, held by the runtime and never by the browser (ADR-0003).
    ("auth::hub_scoped_auth", "hub-token"),
    ("auth::machine_auth", "hub-token"),
    // Second gate on top of the session: the calling module needs the capability granted.
    ("require_module_capability", "capability"),
];

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
    let lib = sources.get("lib").expect("crates/server/src/lib.rs");
    let blanked = blank_noise(lib);
    let bodies = item_bodies(&sources);

    let classes = class_map(&bodies);

    let body = app_body(&blanked);
    let mut rows: BTreeMap<(String, String), String> = BTreeMap::new();
    for (path, expr) in route_calls(&blanked, lib, body) {
        for (method, handler) in method_handlers(&expr) {
            let key = split_handler(&handler);
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
        classes.insert(key.clone(), direct);
        let callees = called_names(body)
            .into_iter()
            .map(|call| match call.split_once("::") {
                Some((m, n)) => (m.to_string(), n.to_string()),
                None => (key.0.clone(), call),
            })
            .filter(|k| bodies.contains_key(k) && k != key)
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
