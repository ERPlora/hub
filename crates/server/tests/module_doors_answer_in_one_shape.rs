//! **Every door a MODULE can reach answers in ONE shape** — the runtime's envelope (hub#1688).
//!
//! Module code never fetches. It goes through `@erplora/module-sdk`, and that transport ends every
//! single call in `unwrap(env)`: it reads `{"ok": true, "data": …}` or
//! `{"ok": false, "error": {"code", "message"}}` and nothing else. A body outside that shape does
//! not degrade — it reaches the module as `ErploraError('error', 'unknown error')`, with whatever
//! the answer actually said stripped off.
//!
//! hub#1682 shipped three doors that answered outside it: the WhatsApp templates proxy handed the
//! SaaS's plain body straight back, so a template **Meta had accepted** was reported to the
//! business as «error», and a refusal Meta explained (`invalid_name`) arrived with nothing to
//! explain it with. Its own test was green because it simulated an envelope the runtime never
//! produced.
//!
//! 🔴 **This is a PATTERN, not a point.** The runtime's proxy helpers hand the Cloud's body back
//! untouched by default, which is right for the doors the SHELL fetches itself and wrong for every
//! door a module reaches — so the next cloud proxy added to the module surface repeats it. Hence
//! this guard: it does not name the WhatsApp routes, it walks **every** module-reachable route in
//! `contracts/kernel/routes.snapshot` and refuses any answer the SDK could not read. A new door is
//! covered the day it is added, because the snapshot it is read from is regenerated from the
//! router by `kernel_contract_routes` — a route missing from it fails there first.
//!
//! ## What «module-reachable» means, and why the auth class alone does not say it (hub#1691)
//!
//! Until hub#1691 the walk was one filter: `auth:admin+capability`, the class the snapshot derives
//! for «an admin session AND the calling module's capability». That reads like «a module may call
//! this», and it is a class a module can reach — but it is **not the same set**. A door the SDK
//! offers can gate on the session alone: `GET /api/hub/flows/templates` (hub#1677) is `auth:admin`
//! on purpose, so a module may activate its own recipes WITHOUT declaring `manage_flows`. Measured
//! on the review of hub#1690: a cloud proxy added behind `require_owner` lands as `auth:admin`,
//! answers plain, and this guard stayed green — the exact hole hub#1688 was closed to prevent.
//!
//! So the scope is not a permission class, it is **who actually calls**. Module code has one way
//! in — `@erplora/module-sdk` — and every path that surface can build is written in its source.
//! The walk is therefore the union of two DERIVED sets, neither of them a list kept by hand:
//!
//! 1. every route in the module gate's class (`auth:admin+capability`), and
//! 2. every route the SDK **names**, read from its sources (`packages/module-sdk/src`, below).
//!
//! A door that answers plain now has to be invisible to BOTH to escape: outside the capability
//! class *and* absent from the SDK — which is to say, not reachable by a module at all.
//!
//! The two doors the SDK reaches without ever passing them through `unwrap(env)` are named in
//! [`ANSWERS_OUTSIDE_THE_ENVELOPE_ON_PURPOSE`], each with the reason. That list is for
//! **exceptions**, never for scope: adding a route to it is a decision a reviewer reads.
use axum::body::Body;
use axum::http::{Request, StatusCode};
use axum::{Json, Router};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use serde_json::{json, Value};
use std::collections::{BTreeMap, BTreeSet};
use std::path::PathBuf;
use tower::ServiceExt;

#[path = "support/kernel_snapshot.rs"]
mod kernel_snapshot;

/// The class the snapshot derives for «an admin session AND the calling module's capability».
/// One of the two sources of the walk, not the whole of it — see the module docs.
const MODULE_GATE_CLASS: &str = "auth:admin+capability";

/// The sources module code can reach the runtime through. Their paths ARE the module surface.
///
/// A DIRECTORY and not `index.ts`, even though `index.ts` is the only one that names a route
/// today: a scope pinned to one filename goes quiet the day a method moves out of it, and it goes
/// quiet the same way the permission class did — silently, with the walk still green and narrower.
/// The floors below are what say the reading happened at all.
const SDK_SOURCE_DIR: &str = "../../packages/module-sdk/src";

/// Doors the SDK names but never reads with `unwrap(env)`, so the envelope does not apply.
///
/// Each entry is a decision with a reason, and the reason is what a reviewer checks: the question
/// is not «does this answer plain?» but «does the transport that reads it look for `ok`?». Adding
/// a line here is how a door OPTS OUT of the shape every other module door owes.
const ANSWERS_OUTSIDE_THE_ENVELOPE_ON_PURPOSE: &[(&str, &str, &str)] = &[
    (
        "GET",
        "/api/events",
        "the event stream: `EventSource` reads `text/event-stream` frame by frame (`openSse`), \
         there is no JSON body to wrap and no `unwrap` on the way in",
    ),
    (
        "GET",
        "/api/media/raw",
        "bytes, not JSON: the SDK reads it with `fetchMediaBlob`, which hands the module a `Blob` \
         and never looks for `ok`",
    ),
];

/// `(method, path)` of every route in the committed kernel contract, with its auth class.
fn snapshot_routes() -> Vec<(String, String, String)> {
    let snapshot = std::fs::read_to_string(kernel_snapshot::snapshot_path("routes.snapshot"))
        .expect("contracts/kernel/routes.snapshot is part of the kernel contract and is committed");
    let routes: Vec<(String, String, String)> = snapshot
        .lines()
        .filter(|line| !line.starts_with('#') && !line.trim().is_empty())
        .filter_map(|line| {
            let mut parts = line.split_whitespace();
            Some((
                parts.next()?.to_string(),
                parts.next()?.to_string(),
                parts.next()?.to_string(),
            ))
        })
        .collect();
    assert!(
        routes.len() >= 100,
        "the router cannot have shrunk to {} routes — the snapshot is not being read",
        routes.len()
    );
    routes
}

/// A path with every `:param` turned into `*`, so a route and an SDK template compare as shapes.
fn shape(path: &str) -> String {
    path.split('/')
        .map(|s| if s.starts_with(':') { "*" } else { s })
        .collect::<Vec<_>>()
        .join("/")
}

/// Every string literal in TypeScript source, comments skipped, in ONE pass.
///
/// One pass and not three (one per quote character) for a reason that was measured on this very
/// guard: scanning the file once per quote type desynchronises on the first apostrophe that is not
/// a delimiter, and everything after it is read as «inside a string». It silently lost
/// `/api/query`, `/api/command` and `/api/events` — three doors the walk then skipped, with the
/// test still green. A parser that loses input quietly is worse than no parser.
///
/// Comments are skipped HERE and not in an earlier pass, because a pass that does not know what a
/// string is eats the `//` of a URL. And they have to be skipped at all: `/api/hub/context`
/// appears six times in `index.ts` and every one of them is a doc comment saying **the shell**
/// fetches it and injects the result. Counting prose would put a door no module calls in the walk,
/// and the first thing a false entry buys is an allowlist.
fn string_literals(source: &str) -> Vec<String> {
    let chars: Vec<char> = source.chars().collect();
    let mut literals = Vec::new();
    let mut i = 0usize;
    while i < chars.len() {
        match chars[i] {
            '/' if chars.get(i + 1) == Some(&'/') => {
                while i < chars.len() && chars[i] != '\n' {
                    i += 1;
                }
            }
            '/' if chars.get(i + 1) == Some(&'*') => {
                i += 2;
                while i < chars.len() && !(chars[i] == '*' && chars.get(i + 1) == Some(&'/')) {
                    i += 1;
                }
                i += 2;
            }
            quote @ ('\'' | '"' | '`') => {
                let start = i + 1;
                i = start;
                let mut closed = false;
                while i < chars.len() {
                    match chars[i] {
                        // An escape swallows whatever follows, delimiter included.
                        '\\' => i += 2,
                        // A `${…}` may carry a quote of its own; skipping it by brace depth keeps
                        // the template from ending in the middle of an interpolation.
                        '$' if quote == '`' && chars.get(i + 1) == Some(&'{') => {
                            let mut depth = 1usize;
                            i += 2;
                            while i < chars.len() && depth > 0 {
                                match chars[i] {
                                    '{' => depth += 1,
                                    '}' => depth -= 1,
                                    _ => {}
                                }
                                i += 1;
                            }
                        }
                        // `'` and `"` do not span lines: a newline inside one means the scan lost
                        // its place, and carrying on would read code as text for the rest of the
                        // file. Stopping here keeps the damage to one literal.
                        '\n' if quote != '`' => break,
                        c if c == quote => {
                            closed = true;
                            break;
                        }
                        _ => i += 1,
                    }
                }
                if closed {
                    literals.push(chars[start..i].iter().collect());
                }
                i += 1;
            }
            _ => i += 1,
        }
    }
    literals
}

/// `${…}` spans of a template literal, brace-depth aware — `${queryString({ status: f })}` carries
/// a `}` of its own and a naive scan ends the span on it.
fn interpolations(template: &str) -> Vec<(usize, usize)> {
    let chars: Vec<char> = template.chars().collect();
    let mut spans = Vec::new();
    let mut i = 0usize;
    while i + 1 < chars.len() {
        if chars[i] == '$' && chars[i + 1] == '{' {
            let mut depth = 1usize;
            let mut j = i + 2;
            while j < chars.len() && depth > 0 {
                match chars[j] {
                    '{' => depth += 1,
                    '}' => depth -= 1,
                    _ => {}
                }
                j += 1;
            }
            if depth == 0 {
                spans.push((i, j));
                i = j;
                continue;
            }
            break;
        }
        i += 1;
    }
    spans
}

/// The path shape an SDK template builds, or `None` when it does not build an `/api/…` path.
///
/// A whole segment (`/${flow}/`) is the route's `:param` and becomes `*`; anything else glued to a
/// segment is the query string the SDK appends (`/runs${search}`) and drops off, because a route
/// is its path and the snapshot carries no query.
fn sdk_path_shape(raw: &str, bases: &BTreeMap<String, String>) -> Option<String> {
    let chars: Vec<char> = raw.chars().collect();
    let mut resolved = String::new();
    let mut cursor = 0usize;
    for (start, end) in interpolations(raw) {
        resolved.extend(chars[cursor..start].iter());
        let inner: String = chars[start + 2..end - 1].iter().collect();
        let whole_segment = resolved.ends_with('/')
            && (end >= chars.len() || chars[end] == '/' || chars[end] == '?');
        if start == 0 {
            // A leading `${CONST}` is the base path the surface is built from; an expression we
            // cannot resolve means we cannot know the path, so the template is not counted.
            resolved.push_str(bases.get(inner.trim())?);
        } else if whole_segment {
            resolved.push('*');
        }
        cursor = end;
    }
    resolved.extend(chars[cursor..].iter());
    let path = resolved.split(['?', '#']).next().unwrap_or("").to_string();
    path.starts_with("/api/").then_some(path)
}

/// Every non-test TypeScript source of `@erplora/module-sdk`, concatenated.
///
/// `*.test.ts` is left out on purpose: a test names paths that do not exist, and a door in this
/// walk that no module can call is the first thing that buys an allowlist — after which the
/// allowlist is where the next real door gets parked.
fn sdk_source() -> String {
    let dir = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join(SDK_SOURCE_DIR);
    let entries = std::fs::read_dir(&dir).unwrap_or_else(|e| {
        panic!(
            "{} is the module surface this guard derives its scope from ({e})",
            dir.display()
        )
    });
    let mut files: Vec<PathBuf> = entries
        .filter_map(|entry| entry.ok().map(|e| e.path()))
        .filter(|file| {
            let name = file
                .file_name()
                .and_then(|n| n.to_str())
                .unwrap_or_default();
            name.ends_with(".ts") && !name.ends_with(".test.ts")
        })
        .collect();
    files.sort();
    assert!(
        files.iter().any(|file| file.ends_with("index.ts")),
        "`index.ts` is not among the {} source/s read from {} — the surface this guard derives its \
         scope from is not being read, and the walk is about to narrow with nothing turning red",
        files.len(),
        dir.display()
    );
    files
        .iter()
        .map(|file| {
            std::fs::read_to_string(file)
                .unwrap_or_else(|e| panic!("{} is part of the module surface ({e})", file.display()))
        })
        .collect::<Vec<_>>()
        .join("\n")
}

/// Every `/api/…` path shape `@erplora/module-sdk` can build, read from its source.
///
/// Two forms, and both are how the surface is actually written: a quoted literal
/// (`path: '/api/query'`) and a template built from an exported base constant
/// (`` `${FLOWS_BASE_PATH}/templates/${own}/${target}/activate` ``). Reading the source rather
/// than a list kept here is the whole point: a method added to the SDK tomorrow widens this walk
/// the same day, with nobody remembering to come back.
fn sdk_named_shapes() -> BTreeSet<String> {
    let source = sdk_source();
    let literals = string_literals(&source);

    // `export const FLOWS_BASE_PATH = '/api/hub/flows';` — the constants the templates start from.
    let mut bases: BTreeMap<String, String> = BTreeMap::new();
    for line in source.lines() {
        let Some((left, right)) = line.split_once('=') else {
            continue;
        };
        let name = left.split_whitespace().last().unwrap_or_default();
        if name.is_empty() || !name.chars().all(|c| c.is_ascii_uppercase() || c == '_') {
            continue;
        }
        let value = right.trim().trim_end_matches(';').trim();
        let unquoted = value.trim_matches(|c| c == '\'' || c == '"' || c == '`');
        if unquoted.starts_with("/api/") && !unquoted.contains(char::is_whitespace) {
            bases.insert(name.to_string(), unquoted.to_string());
        }
    }
    assert!(
        bases.len() >= 4,
        "only {} base-path constants were read out of the SDK — the source is not being parsed",
        bases.len()
    );

    let mut shapes = BTreeSet::new();
    for literal in &literals {
        if let Some(shape) = sdk_path_shape(literal, &bases) {
            shapes.insert(shape);
        }
    }

    // Read a SECOND time, by a method that shares nothing with the first: every `/api/…` the
    // source mentions at all, found by walking characters with no idea what a string or a comment
    // is. Every family it sees has to be represented in what the lexer built.
    //
    // This is the assertion that makes the parser above honest. A parser that quietly matches
    // less still satisfies a count floor — the three doors it lost were lost UNDER a floor of five
    // — so the floor cannot be the check. Two readings that disagree can.
    let mut mentioned: BTreeSet<String> = BTreeSet::new();
    for line in source.lines() {
        // Comments dropped LINE BY LINE — a rule with nothing in common with the state machine
        // above, which is the point: an apostrophe cannot desynchronise it, so it still sees the
        // literals the lexer lost. Prose is dropped because it names doors nobody calls
        // (`/api/hub/context`, `POST /api/events/ticket`: both are the SHELL's, said in a comment
        // to explain where a module's value comes from).
        let trimmed = line.trim_start();
        if trimmed.starts_with("//") || trimmed.starts_with('*') || trimmed.starts_with("/*") {
            continue;
        }
        // A trailing comment on a line of code. Spaces on both sides, so the `//` of a URL — the
        // one thing that could hide a real path — is never what gets cut.
        let code = line.split(" // ").next().unwrap_or(line);
        let mut rest = code;
        while let Some(at) = rest.find("/api/") {
            let tail = &rest[at..];
            let path: String = tail
                .chars()
                .take_while(|c| c.is_ascii_alphanumeric() || matches!(c, '/' | '_' | '-' | '.'))
                .collect();
            let path = path.trim_end_matches(['/', '.']).to_string();
            if path.len() > "/api/".len() {
                mentioned.insert(path);
            }
            rest = &tail["/api/".len()..];
        }
    }
    let unseen: Vec<&String> = mentioned
        .iter()
        .filter(|m| !shapes.iter().any(|s| s == *m || s.starts_with(&format!("{m}/"))))
        .collect();
    assert!(
        unseen.is_empty(),
        "{} path/s the SDK source names are missing from what the parser read: {unseen:?}\n\
         Both readings look at the same file, so they cannot disagree: the lexer above lost them, \
         and every door underneath one of them silently drops out of this walk.",
        unseen.len()
    );

    // A THIRD reading, for the half the second one structurally CANNOT see. A path the SDK builds
    // from a base constant (`` `${FLOWS_BASE_PATH}/templates/${own}/${target}/activate` ``) never
    // contains the text `/api/`, so the mention scan above is blind to it by construction: a lexer
    // that stops reading template literals loses every one of them in silence. Measured on the
    // review of hub#1691 — dropping the backtick arm of the lexer took the shapes from 34 to 9 and
    // the walk from 39 doors to 36 with EVERY floor still satisfied, and the three doors it took
    // were `GET /api/hub/flows/templates` and its activate/deactivate: the very doors this guard
    // was widened for.
    //
    // The mark is the interpolation itself, found by plain substring over the raw source: a base
    // the SDK extends has to have produced at least one shape BELOW it.
    for (name, base) in &bases {
        let extended_in_source = source.lines().any(|line| {
            let trimmed = line.trim_start();
            if trimmed.starts_with("//") || trimmed.starts_with('*') || trimmed.starts_with("/*") {
                return false;
            }
            line.split(" // ")
                .next()
                .unwrap_or(line)
                .contains(&format!("${{{name}}}/"))
        });
        if !extended_in_source {
            continue;
        }
        let below = format!("{base}/");
        assert!(
            shapes.iter().any(|shape| shape.starts_with(&below)),
            "the SDK builds paths under `{name}` (`{base}/…`) and the parser read NONE of them. \
             The template half of the reading is gone, so every door below that base has just \
             dropped out of the walk — and the mention scan cannot see it, because a path built \
             from a base never spells `/api/`"
        );
    }
    shapes
}

/// Every (method, path) a module can reach: the module gate's class UNION what the SDK names.
fn module_reachable_routes() -> Vec<(String, String)> {
    let sdk = sdk_named_shapes();
    let mut routes = Vec::new();
    let mut beyond_the_gate = 0usize;
    let mut inside_the_gate = 0usize;
    for (method, path, class) in snapshot_routes() {
        let in_gate_class = class == MODULE_GATE_CLASS;
        let named_by_the_sdk = sdk.contains(&shape(&path));
        if !in_gate_class && !named_by_the_sdk {
            continue;
        }
        if in_gate_class {
            inside_the_gate += 1;
        } else {
            beyond_the_gate += 1;
        }
        if ANSWERS_OUTSIDE_THE_ENVELOPE_ON_PURPOSE
            .iter()
            .any(|(m, p, _)| *m == method && *p == path)
        {
            continue;
        }
        routes.push((method, path));
    }
    assert!(
        routes.len() >= 30,
        "the module surface cannot have shrunk to {} routes — the snapshot is not being read",
        routes.len()
    );
    // A floor on EACH half of the union, because the union is only as wide as its narrower source
    // and either one can go quiet without a single test turning red.
    //
    // The SDK half first — the reason this guard exists (hub#1691). If the source stops being read
    // (a rename, a parser that quietly matches nothing) the walk falls back to the capability
    // class and the hole reopens.
    assert!(
        beyond_the_gate >= 5,
        "the SDK named only {beyond_the_gate} route/s outside `{MODULE_GATE_CLASS}` — it names \
         several ({} shapes read). The scope has fallen back to the auth class, which is the hole \
         hub#1691 closed",
        sdk.len()
    );
    // And the class half, which today happens to be a SUBSET of what the SDK names (measured on
    // this snapshot: 31 routes, every one of them also named by the SDK). That is exactly why it
    // needs its own floor and cannot lean on `routes.len()`: dropping this half changes nothing
    // TODAY, so a class string that stops matching what the snapshot writes — the format is
    // regenerated by `kernel_contract_routes`, `auth:admin+capability` is not a constant of
    // nature — costs nothing until the first module door the SDK does not spell out, and then it
    // is gone with every test green.
    assert!(
        inside_the_gate >= 20,
        "`{MODULE_GATE_CLASS}` matched only {inside_the_gate} route/s of the snapshot — the class \
         no longer names what the snapshot writes, so half of the walk's scope is whatever the \
         SDK parser happened to read, with nothing left to cross-check it"
    );
    routes
}

/// A path with its `:params` filled in. Nothing must EXIST: a `404` is an answer like any other,
/// and this test is about the shape of the answer, not about finding a row.
fn concrete(path: &str) -> String {
    path.split('/')
        .map(|segment| match segment {
            // Lowercase letters, digits and underscores: what a template name and a secret name
            // both accept, so neither is refused before its handler runs.
            ":name" => "not_here",
            s if s.starts_with(':') => "00000000-0000-0000-0000-000000000000",
            s => s,
        })
        .collect::<Vec<_>>()
        .join("/")
}

fn config(cloud_base_url: String) -> HubConfig {
    let temp = std::env::temp_dir().join(format!("erplora-one-shape-{}", std::process::id()));
    HubConfig {
        demo: false,
        hub_id: "hub-shape".into(),
        cloud_base_url,
        module_cache: temp.join("modules-cache"),
        auth_mode: AuthMode::Session,
        jwt_public_key: None,
        cloud_api_token: Some("machine-secret".into()),
        device_trust_enforce: false,
        media_dir: temp,
        sector: None,
        dev_mode: false,
        dev_modules_dir: None,
        module_trusted_keys: Vec::new(),
    }
}

/// A SaaS that answers every path with a **plain** body — no envelope anywhere.
///
/// That is what the real one answers (`{"templates": […], "stale": false}`, `serialize(row)`,
/// `{"error": "<code>"}`), and it is the input that made hub#1682 fail: a proxy that hands this
/// back untouched is a door the SDK cannot read.
async fn fake_plain_saas() -> String {
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    let saas = Router::new().fallback(|| async {
        (
            StatusCode::OK,
            Json(json!({ "templates": [], "stale": false })),
        )
    });
    tokio::spawn(async move { axum::serve(listener, saas).await.unwrap() });
    format!("http://{address}")
}

#[tokio::test]
async fn every_door_a_module_can_reach_answers_in_the_envelope_the_sdk_reads() {
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), "hub-shape");
    rt.ensure_system_tables().await.unwrap();
    let admin = rt.create_user("Ana", "1111", "admin", None).await.unwrap();
    let session = rt.create_session(&admin, 3600, None).await.unwrap();
    let router = app(AppState::with_config(rt, config(fake_plain_saas().await)));

    let mut checked = 0;
    let mut offenders: Vec<String> = Vec::new();
    for (method, path) in module_reachable_routes() {
        let uri = concrete(&path);
        let carries_body = matches!(method.as_str(), "POST" | "PUT" | "PATCH");
        let mut request = Request::builder()
            .method(method.as_str())
            .uri(&uri)
            .header("x-hub-session", &session);
        if carries_body {
            request = request.header("content-type", "application/json");
        }
        let request = request
            .body(if carries_body {
                Body::from("{}")
            } else {
                Body::empty()
            })
            .unwrap();

        let response = router.clone().oneshot(request).await.unwrap();
        let status = response.status();
        let bytes = axum::body::to_bytes(response.into_body(), usize::MAX)
            .await
            .unwrap();
        let door = format!("{method} {path}");

        // A body-less answer is fine and needs no envelope: a `204` says «done» by definition of
        // the status, and the SDK transport reads it as such before it ever looks for `ok`.
        if bytes.is_empty() {
            checked += 1;
            continue;
        }

        let Ok(body) = serde_json::from_slice::<Value>(&bytes) else {
            offenders.push(format!(
                "{door} answered {status} with a body that is not JSON: {}",
                String::from_utf8_lossy(&bytes)
            ));
            checked += 1;
            continue;
        };
        if body.get("ok").and_then(Value::as_bool).is_none() {
            offenders.push(format!("{door} answered {status} outside the envelope: {body}"));
        } else if body["ok"] == Value::Bool(false)
            && body
                .get("error")
                .and_then(|e| e.get("code"))
                .and_then(Value::as_str)
                .is_none_or(|c| c.is_empty())
        {
            offenders.push(format!(
                "{door} refused with {status} and no `error.code`: {body}"
            ));
        }
        checked += 1;
    }
    assert!(checked >= 30, "only {checked} doors were driven");
    // Named ALL AT ONCE and not one per run: this walk is the whole module surface, so a change
    // that misses the shape usually misses it on several doors, and finding them one `cargo test`
    // at a time is how the second one gets shipped.
    assert!(
        offenders.is_empty(),
        "{} module door/s answer in a shape `@erplora/module-sdk` cannot read — every one of them \
         reaches the module as `ErploraError('error', 'unknown error')`, with whatever the answer \
         actually said stripped off:\n  - {}\n\nA door a module reaches answers `{{\"ok\": true, \
         \"data\": …}}` or `{{\"ok\": false, \"error\": {{\"code\", \"message\"}}}}`. For a cloud \
         proxy that is `cloud_proxy::proxy_cloud_*_enveloped`, not the passthrough the shell's own \
         doors use. A door whose transport does NOT read `ok` (a stream, bytes) belongs in \
         `ANSWERS_OUTSIDE_THE_ENVELOPE_ON_PURPOSE`, with its reason.",
        offenders.len(),
        offenders.join("\n  - ")
    );
}
