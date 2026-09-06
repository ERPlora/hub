//! `postman/erplora-hub.postman_collection.json` ≡ `contracts/kernel/routes.snapshot` +
//! `postman/overlay.json` — ERPlora/hub#1613.
//!
//! The hub's OpenAPI (`GET /api/v1/openapi.json`) only describes the `expose_api` operations of
//! the installed modules; the ~150 routes of the core (session, PIN, API keys, `/api/command`,
//! `/api/query`, flows, events, blueprint import/export…) had no description anybody could import.
//! This test GENERATES a Postman collection from the kernel's frozen route surface — which
//! `kernel_contract_routes.rs` already keeps equal to the router — and demands the committed file
//! be byte-identical to a fresh generation: when a route changes and nobody re-exports, the build
//! goes red instead of the collection going stale.
//!
//! What the schema does not carry (request bodies, descriptions, the scripts that save the session
//! and the API key into variables) lives in `postman/overlay.json`, keyed by `METHOD path`. An
//! overlay entry for a route that does not exist fails too: the overlay only ever shrinks with the
//! surface.
//!
//! Update: `UPDATE_POSTMAN_COLLECTION=1 cargo test -p erplora-server --test postman_collection_hub1613`.
//! The collection is NOT part of `contracts/kernel/`: regenerating it is not a contract change.

use std::collections::{BTreeMap, BTreeSet};
use std::path::PathBuf;

use serde_json::{json, Map, Value};

const UPDATE_ENV: &str = "UPDATE_POSTMAN_COLLECTION";
const COLLECTION: &str = "postman/erplora-hub.postman_collection.json";
const OVERLAY: &str = "postman/overlay.json";
const SNAPSHOT: &str = "contracts/kernel/routes.snapshot";
const COLLECTION_NAME: &str = "ERPlora Hub API";
const START_HERE: &str = "00 · Session — start here";
const DEFAULT_HUB_URL: &str = "https://banco-pre.a.erplora.com";
/// One id forever: a fresh one per export would make every regeneration a spurious diff.
const POSTMAN_ID: &str = "8b1e6c3a-2d5f-4a7b-9e0c-1f2a3b4c5d6e";

/// The requests that open the collection, in the order a newcomer needs them.
const START_ORDER: &[(&str, &str)] = &[
    ("GET", "/api/hub/context"),
    ("POST", "/api/auth/cloud"),
    ("POST", "/api/auth/set-pin"),
    ("POST", "/api/auth/pin"),
    ("POST", "/api/keys"),
    ("GET", "/api/v1/openapi.json"),
    ("POST", "/api/auth/logout"),
];

const VARIABLES: &[(&str, &str, &str)] = &[
    ("hub_url", DEFAULT_HUB_URL, "The hub. The permanent PRE bench by default."),
    ("access_token", "", "The SaaS user JWT — what the SaaS collection's Login saves. Only POST /api/auth/cloud reads it."),
    ("hub_session", "", "Saved by POST /api/auth/cloud and POST /api/auth/pin. Sent as `X-Hub-Session`."),
    ("hub_api_key", "", "Saved by POST /api/keys (shown once). Sent as `Authorization: Bearer erpl_live_…` on the module data API."),
    ("hub_pin", "", "The local PIN (six digits) you set with POST /api/auth/set-pin."),
    ("device_id", "postman", "How this client identifies itself to the device-trust gate on PIN/badge logins."),
    ("hub_user_name", "", "The local user's name, for POST /api/auth/pin."),
];

#[derive(Clone, Debug, PartialEq, Eq, PartialOrd, Ord)]
struct Route {
    method: String,
    path: String,
    auth: String,
}

fn repo(rel: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .join(rel)
}

fn routes() -> Vec<Route> {
    let text =
        std::fs::read_to_string(repo(SNAPSHOT)).expect("contracts/kernel/routes.snapshot se lee");
    text.lines()
        .filter(|line| !line.trim().is_empty() && !line.starts_with('#'))
        .map(|line| {
            let mut parts = line.split_whitespace();
            let method = parts.next().expect("método").to_string();
            let path = parts.next().expect("ruta").to_string();
            let auth = parts
                .next()
                .and_then(|a| a.strip_prefix("auth:"))
                .expect("clase auth:<x>")
                .to_string();
            Route { method, path, auth }
        })
        .collect()
}

fn overlay() -> Map<String, Value> {
    let text = std::fs::read_to_string(repo(OVERLAY)).expect("postman/overlay.json se lee");
    serde_json::from_str::<Value>(&text)
        .expect("postman/overlay.json es JSON")
        .as_object()
        .expect("postman/overlay.json es un objeto {\"METHOD path\": {…}}")
        .clone()
}

fn key_of(route: &Route) -> String {
    format!("{} {}", route.method, route.path)
}

/// Folder by route family. `/api/hub/flows/...` → `hub · flows`, `/api/auth/...` → `auth`,
/// `/healthz` → `system`.
fn folder_of(path: &str) -> String {
    let rest = match path.strip_prefix("/api/") {
        Some(rest) => rest,
        None => return "system".to_string(),
    };
    let segments: Vec<&str> = rest.split('/').filter(|s| !s.is_empty()).collect();
    match segments.as_slice() {
        ["hub", second, ..] if !second.starts_with(':') => format!("hub · {second}"),
        ["v1", ..] => "openapi".to_string(),
        [first, ..] => (*first).to_string(),
        [] => "api".to_string(),
    }
}

/// `:id` → `{{id}}`, `*path` → `{{path}}`.
fn templated(path: &str) -> String {
    path.split('/')
        .map(|segment| {
            if let Some(name) = segment
                .strip_prefix(':')
                .or_else(|| segment.strip_prefix('*'))
            {
                format!("{{{{{name}}}}}")
            } else {
                segment.to_string()
            }
        })
        .collect::<Vec<_>>()
        .join("/")
}

enum Credential {
    None,
    Session,
    ApiKey,
}

fn credential(auth: &str) -> Credential {
    match auth {
        "none" => Credential::None,
        "api-key" => Credential::ApiKey,
        // `session`, `admin`, `admin+capability`, `admin+session`, `any-credential`,
        // `admin+any-credential`: a user session opens every one of them.
        _ => Credential::Session,
    }
}

fn header(key: &str, value: &str) -> Value {
    json!({ "key": key, "value": value, "type": "text" })
}

fn item(route: &Route, extra: Option<&Value>) -> Value {
    let key = key_of(route);
    let over = extra.and_then(Value::as_object);
    let get = |field: &str| over.and_then(|o| o.get(field));

    let mut headers: Vec<Value> = match credential(&route.auth) {
        Credential::None => vec![],
        Credential::Session => vec![header("X-Hub-Session", "{{hub_session}}")],
        Credential::ApiKey => vec![header("Authorization", "Bearer {{hub_api_key}}")],
    };
    if let Some(Value::Object(extra_headers)) = get("headers") {
        for (k, v) in extra_headers {
            headers.push(header(k, v.as_str().unwrap_or_default()));
        }
    }

    let mut description = format!("auth: {}", route.auth);
    if let Some(Value::String(text)) = get("description") {
        description = format!("{text}\n\n(auth: {})", route.auth);
    }

    let path = templated(&route.path);
    let mut query: Vec<Value> = vec![];
    if let Some(Value::Array(params)) = get("query") {
        query = params.clone();
    }
    let raw = {
        let enabled: Vec<String> = query
            .iter()
            .filter(|q| !q.get("disabled").and_then(Value::as_bool).unwrap_or(false))
            .map(|q| {
                format!(
                    "{}={}",
                    q.get("key").and_then(Value::as_str).unwrap_or_default(),
                    q.get("value").and_then(Value::as_str).unwrap_or_default()
                )
            })
            .collect();
        if enabled.is_empty() {
            format!("{{{{hub_url}}}}{path}")
        } else {
            format!("{{{{hub_url}}}}{path}?{}", enabled.join("&"))
        }
    };
    let mut request = json!({
        "method": route.method,
        "header": headers,
        "url": {
            "raw": raw,
            "host": ["{{hub_url}}"],
            "path": path.trim_start_matches('/').split('/').collect::<Vec<_>>(),
            "query": query,
        },
        "description": description,
    });
    if matches!(credential(&route.auth), Credential::None) {
        request["auth"] = json!({ "type": "noauth" });
    }
    if let Some(body) = get("body") {
        request["header"]
            .as_array_mut()
            .expect("headers")
            .push(header("Content-Type", "application/json"));
        request["body"] = json!({
            "mode": "raw",
            "raw": serde_json::to_string_pretty(body).expect("body"),
            "options": { "raw": { "language": "json" } },
        });
    } else if get("file").and_then(Value::as_bool).unwrap_or(false) {
        request["header"]
            .as_array_mut()
            .expect("headers")
            .push(header("Content-Type", "application/octet-stream"));
        request["body"] = json!({ "mode": "file", "file": { "src": "" } });
    }

    let name = get("name")
        .and_then(Value::as_str)
        .map(str::to_string)
        .unwrap_or_else(|| key.clone());
    let mut out = json!({ "name": name, "request": request, "response": [] });
    if let Some(Value::Array(lines)) = get("test") {
        out["event"] =
            json!([{ "listen": "test", "script": { "type": "text/javascript", "exec": lines } }]);
    }
    out
}

fn description() -> String {
    format!(
        "Generated from `contracts/kernel/routes.snapshot` + `postman/overlay.json` by \
         `UPDATE_POSTMAN_COLLECTION=1 cargo test -p erplora-server --test postman_collection_hub1613` — \
         do not edit by hand; a test fails when this file and the routes disagree (hub#1613).\n\n\
         Start in the first folder: set `hub_url`, paste the SaaS `access_token` (the SaaS collection's \
         Login saves it), run **POST /api/auth/cloud** — it saves `hub_session` by itself — then set a PIN, \
         create an API key (saved as `hub_api_key`) and use `/api/query` and `/api/command`.\n\n\
         Credentials by route class: `X-Hub-Session` for session/admin routes, \
         `Authorization: Bearer erpl_live_…` for the module data API (`/api/v1/{{module}}/q|c/…`), \
         nothing for the public ones. The module data API is per hub: import `GET /api/v1/openapi.json` \
         into Postman to get the operations of the modules installed on THIS hub.\n\n\
         `hub_url` is {DEFAULT_HUB_URL} on purpose — the permanent PRE bench."
    )
}

fn generate() -> Value {
    let overlay = overlay();
    let routes = routes();
    let mut folders: BTreeMap<String, Vec<Value>> = BTreeMap::new();
    let mut start: Vec<(usize, Value)> = vec![];
    for route in &routes {
        let extra = overlay.get(&key_of(route));
        let rendered = item(route, extra);
        if let Some(pos) = START_ORDER
            .iter()
            .position(|(m, p)| *m == route.method && *p == route.path)
        {
            start.push((pos, rendered));
        } else {
            folders
                .entry(folder_of(&route.path))
                .or_default()
                .push(rendered);
        }
    }
    start.sort_by_key(|(pos, _)| *pos);
    let mut items: Vec<Value> = vec![json!({
        "name": START_HERE,
        "description": "JWT of the SaaS → hub session → PIN → API key. Each step saves what the next one needs.",
        "item": start.into_iter().map(|(_, v)| v).collect::<Vec<_>>(),
    })];
    for (name, mut list) in folders {
        list.sort_by(|a, b| {
            let ka = (
                a["request"]["url"]["raw"]
                    .as_str()
                    .unwrap_or_default()
                    .to_string(),
                method_rank(&a["request"]["method"]),
            );
            let kb = (
                b["request"]["url"]["raw"]
                    .as_str()
                    .unwrap_or_default()
                    .to_string(),
                method_rank(&b["request"]["method"]),
            );
            ka.cmp(&kb)
        });
        items.push(json!({ "name": name, "item": list }));
    }
    json!({
        "info": {
            "_postman_id": POSTMAN_ID,
            "name": COLLECTION_NAME,
            "description": description(),
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "variable": VARIABLES.iter().map(|(k, v, d)| json!({ "key": k, "value": v, "type": "string", "description": d })).collect::<Vec<_>>(),
        "item": items,
    })
}

fn method_rank(method: &Value) -> u8 {
    match method.as_str().unwrap_or_default() {
        "GET" => 0,
        "POST" => 1,
        "PUT" => 2,
        "PATCH" => 3,
        "DELETE" => 4,
        _ => 9,
    }
}

fn render(collection: &Value) -> String {
    let mut text = serde_json::to_string_pretty(collection).expect("collection");
    text.push('\n');
    text
}

/// Every `(METHOD, path)` of a rendered collection, with `{{x}}` folded back to `:x`.
fn requests_of(collection: &Value) -> BTreeSet<(String, String)> {
    fn walk(items: &[Value], out: &mut BTreeSet<(String, String)>) {
        for item in items {
            if let Some(children) = item.get("item").and_then(Value::as_array) {
                walk(children, out);
                continue;
            }
            let request = &item["request"];
            let raw = request["url"]["raw"].as_str().unwrap_or_default();
            let path = raw
                .trim_start_matches("{{hub_url}}")
                .split('?')
                .next()
                .unwrap_or_default()
                .split('/')
                .map(
                    |s| match s.strip_prefix("{{").and_then(|s| s.strip_suffix("}}")) {
                        Some(name) if name == "path" => "*path".to_string(),
                        Some(name) => format!(":{name}"),
                        None => s.to_string(),
                    },
                )
                .collect::<Vec<_>>()
                .join("/");
            out.insert((
                request["method"].as_str().unwrap_or_default().to_string(),
                path,
            ));
        }
    }
    let mut out = BTreeSet::new();
    walk(collection["item"].as_array().expect("items"), &mut out);
    out
}

fn committed() -> Value {
    let text = std::fs::read_to_string(repo(COLLECTION)).unwrap_or_else(|e| {
        panic!(
            "`{COLLECTION}` no se puede leer ({e}). Va COMMITEADO. Genéralo con:\n  \
             {UPDATE_ENV}=1 cargo test -p erplora-server --test postman_collection_hub1613"
        )
    });
    serde_json::from_str(&text).expect("la colección commiteada es JSON")
}

/// hub#1613: the committed collection IS a fresh generation, byte for byte.
#[test]
fn hub1613_postman_collection_matches_routes_snapshot_and_overlay() {
    let generated = render(&generate());
    let path = repo(COLLECTION);
    if std::env::var(UPDATE_ENV).as_deref() == Ok("1") {
        std::fs::create_dir_all(path.parent().expect("postman/")).expect("crear postman/");
        std::fs::write(&path, &generated).expect("escribir la colección");
        return;
    }
    let committed = std::fs::read_to_string(&path).unwrap_or_else(|e| {
        panic!(
            "`{COLLECTION}` no se puede leer ({e}). Genéralo con:\n  \
             {UPDATE_ENV}=1 cargo test -p erplora-server --test postman_collection_hub1613"
        )
    });
    if committed == generated {
        return;
    }
    let old: BTreeSet<&str> = committed.lines().collect();
    let new: BTreeSet<&str> = generated.lines().collect();
    let added: Vec<&&str> = new.difference(&old).take(20).collect();
    let removed: Vec<&&str> = old.difference(&new).take(20).collect();
    panic!(
        "`{COLLECTION}` ya no describe las rutas del kernel (hub#1613).\n\
         \n  AÑADIDO por el código (primeras {}):\n{}\
         \n  QUE FALTA en el código (primeras {}):\n{}\
         \nRegenera y revisa el diff:\n  \
         {UPDATE_ENV}=1 cargo test -p erplora-server --test postman_collection_hub1613\n",
        added.len(),
        added
            .iter()
            .map(|l| format!("    + {l}\n"))
            .collect::<String>(),
        removed.len(),
        removed
            .iter()
            .map(|l| format!("    - {l}\n"))
            .collect::<String>(),
    );
}

/// hub#1613: every route of the snapshot is a request, and no request names a route that is gone.
#[test]
fn hub1613_every_route_of_the_snapshot_is_a_request_and_nothing_else() {
    let expected: BTreeSet<(String, String)> =
        routes().into_iter().map(|r| (r.method, r.path)).collect();
    let found = requests_of(&committed());
    let missing: Vec<_> = expected.difference(&found).collect();
    let extra: Vec<_> = found.difference(&expected).collect();
    assert!(
        missing.is_empty(),
        "rutas del snapshot sin petición en la colección: {missing:?}"
    );
    assert!(
        extra.is_empty(),
        "peticiones de la colección que ya no son rutas: {extra:?}"
    );
}

/// hub#1613: the overlay only describes routes that exist — it shrinks with the surface.
#[test]
fn hub1613_overlay_names_only_routes_that_exist() {
    let known: BTreeSet<String> = routes().iter().map(key_of).collect();
    let stale: Vec<String> = overlay()
        .keys()
        .filter(|k| !known.contains(*k))
        .cloned()
        .collect();
    assert!(
        stale.is_empty(),
        "entradas de postman/overlay.json que no son rutas del kernel: {stale:?}"
    );
}

/// hub#1613: the first folder gets a newcomer from a SaaS JWT to an API key without pasting anything.
#[test]
fn hub1613_start_here_saves_the_session_and_the_api_key() {
    let collection = committed();
    let first = &collection["item"][0];
    assert_eq!(first["name"], START_HERE);
    let items = first["item"].as_array().expect("start-here items");
    let by_key: BTreeMap<String, &Value> = items
        .iter()
        .map(|i| {
            let r = &i["request"];
            let raw = r["url"]["raw"]
                .as_str()
                .unwrap_or_default()
                .trim_start_matches("{{hub_url}}");
            (
                format!("{} {}", r["method"].as_str().unwrap_or_default(), raw),
                i,
            )
        })
        .collect();
    let script = |key: &str| -> String {
        by_key[key]["event"][0]["script"]["exec"]
            .as_array()
            .map(|lines| {
                lines
                    .iter()
                    .filter_map(Value::as_str)
                    .collect::<Vec<_>>()
                    .join("\n")
            })
            .unwrap_or_default()
    };
    assert!(script("POST /api/auth/cloud").contains("hub_session"));
    assert!(script("POST /api/auth/pin").contains("hub_session"));
    assert!(script("POST /api/keys").contains("hub_api_key"));
    let cloud_headers: Vec<&str> = by_key["POST /api/auth/cloud"]["request"]["header"]
        .as_array()
        .expect("headers")
        .iter()
        .filter_map(|h| h["value"].as_str())
        .collect();
    assert!(
        cloud_headers.contains(&"Bearer {{access_token}}"),
        "auth/cloud lleva el JWT del SaaS"
    );
}

/// hub#1613: the credential follows the route's auth class, never a guess.
#[test]
fn hub1613_credential_follows_the_auth_class() {
    let session = item(
        &Route {
            method: "GET".into(),
            path: "/api/settings".into(),
            auth: "session".into(),
        },
        None,
    );
    assert_eq!(session["request"]["header"][0]["key"], "X-Hub-Session");
    let api_key = item(
        &Route {
            method: "GET".into(),
            path: "/ws".into(),
            auth: "api-key".into(),
        },
        None,
    );
    assert_eq!(
        api_key["request"]["header"][0]["value"],
        "Bearer {{hub_api_key}}"
    );
    let public = item(
        &Route {
            method: "GET".into(),
            path: "/healthz".into(),
            auth: "none".into(),
        },
        None,
    );
    assert_eq!(public["request"]["auth"]["type"], "noauth");
    assert!(public["request"]["header"]
        .as_array()
        .expect("headers")
        .is_empty());
    let with_param = item(
        &Route {
            method: "GET".into(),
            path: "/api/hub/flows/:id/runs".into(),
            auth: "admin".into(),
        },
        None,
    );
    assert_eq!(
        with_param["request"]["url"]["raw"],
        "{{hub_url}}/api/hub/flows/{{id}}/runs"
    );
    assert_eq!(templated("/modules/:id/*path"), "/modules/{{id}}/{{path}}");
}
