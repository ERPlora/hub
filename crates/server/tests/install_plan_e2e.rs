//! TDD (ADR-0060, hub#68): the Hub EXECUTES the install plan the Cloud computes.
//!
//! Until now `depends_on` was only *checked* (`MissingDependency`) or resolved by reading the
//! manifest of the already-downloaded zip. ADR-0060 decision (option B) is: the **Cloud** owns the
//! fresh dependency graph + the entitlement truth and returns the topo-ordered closure; the
//! **Hub** just runs it in order, skipping the `versions/` round-trip (the plan already carries
//! `version` + `sha256`).
//!
//! What is pinned here:
//!   1. installing a module whose dependencies are missing installs them FIRST, in plan order,
//!      and leaves everything active — without ever asking `versions/`;
//!   2. a `blocked` plan (premium dependency not bought) installs NOTHING and fails with a
//!      domain error carrying `blocked_on` + the purchase pointer (never auto-charge);
//!   3. the hub's real installed set travels in the request, so an already-satisfied dependency
//!      is not re-downloaded (idempotence);
//!   4. a Cloud without the endpoint (older deployment) still installs via the manifest-nested
//!      fallback — the safety net stays;
//!   5. a plan that arrives 200 but INCOMPLETE (it omits deps the downloaded manifest declares —
//!      hub#672, the saas#1352 empty-graph outage) degrades to the manifest fallback and
//!      RECOVERS instead of dying in `MissingDependency`.

use std::collections::HashMap;
use std::io::Write;
use std::sync::{Arc, Mutex};

use axum::extract::{Path, State};
use axum::routing::{get, post};
use axum::{Json, Router};
use cloud_client::Auth;
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::install::{install_from_cloud, InstallError};
use serde_json::{json, Value};

/// Zip in memory with the given entries.
fn build_zip(entries: &[(&str, &[u8])]) -> Vec<u8> {
    let mut buf = Vec::new();
    {
        let mut w = zip::ZipWriter::new(std::io::Cursor::new(&mut buf));
        let opts: zip::write::FileOptions<()> = zip::write::FileOptions::default();
        for (name, bytes) in entries {
            w.start_file(*name, opts).unwrap();
            w.write_all(bytes).unwrap();
        }
        w.finish().unwrap();
    }
    buf
}

fn sha256_hex(bytes: &[u8]) -> String {
    use sha2::{Digest, Sha256};
    Sha256::digest(bytes)
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect()
}

/// Minimal installable `module.zip`: `module.json` with id/name/version + `depends_on`.
fn module_zip(id: &str, deps: &[&str]) -> Vec<u8> {
    let manifest = json!({ "id": id, "name": id, "version": "1.0.0", "depends_on": deps });
    build_zip(&[(
        "module.json",
        serde_json::to_string(&manifest).unwrap().as_bytes(),
    )])
}

/// Everything the mock Cloud serves + the call log the assertions read.
struct MockCloud {
    /// module id → (zip bytes, sha256)
    catalog: HashMap<String, (Vec<u8>, String)>,
    /// Canned `install-plan` response. `None` → the endpoint answers 404 (older Cloud).
    plan: Option<Value>,
    /// Every path hit, in order (`versions:<id>`, `download:<id>`, `plan`, `mark:<id>`).
    calls: Mutex<Vec<String>>,
    /// Bodies received by `install-plan/` (to assert the installed set travels).
    plan_bodies: Mutex<Vec<Value>>,
}

type Shared = Arc<MockCloud>;

/// Spawns the mini-Cloud on an ephemeral port and returns its base URL.
async fn spawn_mock_cloud(mock: Shared) -> String {
    async fn versions(State(m): State<Shared>, Path(id): Path<String>) -> Json<Value> {
        m.calls.lock().unwrap().push(format!("versions:{id}"));
        let sha = m
            .catalog
            .get(&id)
            .map(|(_, s)| s.clone())
            .unwrap_or_default();
        Json(json!([{ "version": "1.0.0", "is_active": true, "sha256": sha }]))
    }
    async fn download(State(m): State<Shared>, Path(id): Path<String>) -> Vec<u8> {
        m.calls.lock().unwrap().push(format!("download:{id}"));
        m.catalog
            .get(&id)
            .map(|(z, _)| z.clone())
            .unwrap_or_default()
    }
    async fn mark_installed(State(m): State<Shared>, Path(id): Path<String>) -> Json<Value> {
        m.calls.lock().unwrap().push(format!("mark:{id}"));
        Json(json!({ "ok": true }))
    }
    async fn install_plan(
        State(m): State<Shared>,
        Json(body): Json<Value>,
    ) -> axum::response::Response {
        use axum::response::IntoResponse;
        m.calls.lock().unwrap().push("plan".to_string());
        m.plan_bodies.lock().unwrap().push(body);
        match &m.plan {
            Some(p) => Json(p.clone()).into_response(),
            // Older Cloud without ADR-0060 wired: the Hub must degrade, not break.
            None => (
                axum::http::StatusCode::NOT_FOUND,
                Json(json!({"detail": "Not found."})),
            )
                .into_response(),
        }
    }
    let app = Router::new()
        .route("/api/v1/marketplace/modules/:id/versions/", get(versions))
        .route("/api/v1/marketplace/modules/:id/download/", get(download))
        .route(
            "/api/v1/marketplace/modules/:id/mark_installed/",
            post(mark_installed),
        )
        .route("/api/v1/marketplace/install-plan/", post(install_plan))
        .with_state(mock);
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let addr = listener.local_addr().unwrap();
    tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
    format!("http://{addr}")
}

/// One plan node as the Cloud serializes it (`InstallPlanNodeSerializer`).
fn node(module_id: &str, sha: &str, reason: &str) -> Value {
    json!({
        "module_id": module_id, "version": "1.0.0", "sha256": sha, "tier": "free",
        "entitled": true, "requires_purchase": false, "reason": reason,
    })
}

fn cache_dir(tag: &str) -> std::path::PathBuf {
    let dir = std::env::temp_dir().join(format!(
        "erplora-install-plan-{}-{tag}",
        std::process::id()
    ));
    let _ = std::fs::remove_dir_all(&dir);
    dir
}

fn dev_policy() -> cloud_client::SignaturePolicy {
    erplora_server::install::dev_signature_policy()
}

/// (1) The plan is executed in order: the dependency is installed BEFORE the requested module,
/// both end up active, and `versions/` is never asked (the plan carries version + sha256).
#[tokio::test]
async fn executes_the_plan_in_order_installing_missing_dependencies() {
    let leaf = module_zip("leaf", &[]);
    let dependent = module_zip("dependent", &["leaf"]);
    let (leaf_sha, dependent_sha) = (sha256_hex(&leaf), sha256_hex(&dependent));
    let mut catalog = HashMap::new();
    catalog.insert("leaf".to_string(), (leaf, leaf_sha.clone()));
    catalog.insert("dependent".to_string(), (dependent, dependent_sha.clone()));

    let mock = Arc::new(MockCloud {
        catalog,
        plan: Some(json!({
            "requested": "dependent",
            "plan": [node("leaf", &leaf_sha, "dependency"),
                     node("dependent", &dependent_sha, "requested")],
            "already_satisfied": [],
            "blocked": false,
            "blocked_on": [],
        })),
        calls: Mutex::new(Vec::new()),
        plan_bodies: Mutex::new(Vec::new()),
    });
    let base_url = spawn_mock_cloud(mock.clone()).await;

    let mut rt = Runtime::new(Box::new(fresh_db().await));
    let installed = install_from_cloud(
        &reqwest::Client::new(),
        &base_url,
        &cache_dir("order"),
        &Auth::HubToken {
            hub_id: "hub-test".into(),
            token: "tok".into(),
        },
        &mut rt,
        "dependent",
        "latest",
        &|_, _| {},
        &dev_policy(),
    )
    .await
    .expect("the plan resolves and installs the whole closure");

    assert_eq!(installed.module_id, "dependent", "headline = requested module");
    assert!(
        rt.registry().is_installed("leaf"),
        "the missing dependency must be installed by the plan"
    );
    assert!(rt.registry().is_installed("dependent"));

    let calls = mock.calls.lock().unwrap().clone();
    assert_eq!(calls.first().map(String::as_str), Some("plan"), "{calls:?}");
    let dep_at = calls.iter().position(|c| c == "download:leaf");
    let root_at = calls.iter().position(|c| c == "download:dependent");
    assert!(
        dep_at < root_at && dep_at.is_some(),
        "the dependency is downloaded BEFORE the requested module: {calls:?}"
    );
    assert!(
        !calls.iter().any(|c| c.starts_with("versions:")),
        "the plan carries version+sha256: the versions/ round-trip is skipped ({calls:?})"
    );
}

/// (2) A blocked plan (premium dependency not bought) installs NOTHING and surfaces a domain
/// error naming what blocks it — never a mute failure, never an auto-charge.
#[tokio::test]
async fn a_blocked_plan_installs_nothing_and_names_what_blocks_it() {
    let verifactu = module_zip("verifactu", &["invoice"]);
    let sha = sha256_hex(&verifactu);
    let mut catalog = HashMap::new();
    catalog.insert("verifactu".to_string(), (verifactu, sha.clone()));

    let mock = Arc::new(MockCloud {
        catalog,
        plan: Some(json!({
            "requested": "verifactu",
            "plan": [
                {"module_id":"invoice","version":"1.0.0","sha256":"aa","tier":"premium",
                 "entitled":false,"requires_purchase":true,"reason":"dependency",
                 "purchase":{"module_type":"premium","price":"9.00","currency":"EUR",
                             "purchase_url":"/marketplace/invoice/"}},
                {"module_id":"verifactu","version":"1.0.0","sha256": sha, "tier":"free",
                 "entitled":true,"requires_purchase":false,"reason":"requested"}
            ],
            "already_satisfied": [],
            "blocked": true,
            "blocked_on": ["invoice"],
        })),
        calls: Mutex::new(Vec::new()),
        plan_bodies: Mutex::new(Vec::new()),
    });
    let base_url = spawn_mock_cloud(mock.clone()).await;

    let mut rt = Runtime::new(Box::new(fresh_db().await));
    let err = install_from_cloud(
        &reqwest::Client::new(),
        &base_url,
        &cache_dir("blocked"),
        &Auth::HubToken {
            hub_id: "hub-test".into(),
            token: "tok".into(),
        },
        &mut rt,
        "verifactu",
        "latest",
        &|_, _| {},
        &dev_policy(),
    )
    .await
    .expect_err("a blocked plan must NOT install");

    match &err {
        InstallError::Blocked {
            requested,
            blocked_on,
            purchase,
        } => {
            assert_eq!(requested, "verifactu");
            assert_eq!(blocked_on, &["invoice".to_string()]);
            let p = purchase
                .iter()
                .find(|p| p.module_id == "invoice")
                .expect("the purchase pointer travels to the UI");
            assert_eq!(p.price, "9.00");
            assert_eq!(p.purchase_url, "/marketplace/invoice/");
        }
        other => panic!("expected InstallError::Blocked, got {other:?}"),
    }
    // Stable, machine-readable error code (hub#139 domain error channel).
    assert_eq!(err.code(), "install_blocked");
    assert!(
        !rt.registry().is_installed("verifactu") && !rt.registry().is_installed("invoice"),
        "nothing may be installed when the plan is blocked"
    );
    let calls = mock.calls.lock().unwrap().clone();
    assert!(
        !calls.iter().any(|c| c.starts_with("download:")),
        "a blocked plan must not download anything: {calls:?}"
    );
}

/// (3) The hub's REAL installed set travels in the request, so the Cloud can drop what is already
/// there. Re-running an install whose closure is satisfied is a no-op on the wire.
#[tokio::test]
async fn sends_the_installed_set_and_does_not_reinstall_whats_satisfied() {
    let leaf = module_zip("leaf", &[]);
    let dependent = module_zip("dependent", &["leaf"]);
    let (leaf_sha, dependent_sha) = (sha256_hex(&leaf), sha256_hex(&dependent));
    let mut catalog = HashMap::new();
    catalog.insert("leaf".to_string(), (leaf, leaf_sha.clone()));
    catalog.insert("dependent".to_string(), (dependent, dependent_sha.clone()));

    // The Cloud already knows `leaf` is there: it only plans `dependent`.
    let mock = Arc::new(MockCloud {
        catalog,
        plan: Some(json!({
            "requested": "dependent",
            "plan": [node("dependent", &dependent_sha, "requested")],
            "already_satisfied": ["leaf"],
            "blocked": false,
            "blocked_on": [],
        })),
        calls: Mutex::new(Vec::new()),
        plan_bodies: Mutex::new(Vec::new()),
    });
    let base_url = spawn_mock_cloud(mock.clone()).await;

    let auth = Auth::HubToken {
        hub_id: "hub-test".into(),
        token: "tok".into(),
    };
    let cache = cache_dir("satisfied");
    let mut rt = Runtime::new(Box::new(fresh_db().await));

    // Pre-install the dependency straight from disk so the registry really holds it.
    let leaf_dir = cache.join("preinstalled-leaf");
    std::fs::create_dir_all(&leaf_dir).unwrap();
    std::fs::write(
        leaf_dir.join("module.json"),
        serde_json::to_vec(&json!({"id":"leaf","name":"leaf","version":"1.0.0"})).unwrap(),
    )
    .unwrap();
    rt.install_from_dir(&leaf_dir).await.unwrap();
    assert!(rt.registry().is_installed("leaf"));

    install_from_cloud(
        &reqwest::Client::new(),
        &base_url,
        &cache,
        &auth,
        &mut rt,
        "dependent",
        "latest",
        &|_, _| {},
        &dev_policy(),
    )
    .await
    .expect("installs only what the plan lists");

    let bodies = mock.plan_bodies.lock().unwrap().clone();
    let sent = bodies.first().expect("install-plan was asked");
    let installed = sent["installed"]
        .as_array()
        .expect("the request carries the installed set");
    assert!(
        installed.iter().any(|v| v == "leaf"),
        "the hub's registry is the authority on what is installed: {sent}"
    );
    let calls = mock.calls.lock().unwrap().clone();
    assert!(
        !calls.iter().any(|c| c == "download:leaf"),
        "an already-satisfied dependency is not re-downloaded: {calls:?}"
    );
}

/// (4) Safety net: a Cloud that does not expose `install-plan/` (older deployment) still installs
/// through the manifest-nested resolution. The feature degrades, it does not break the hub.
#[tokio::test]
async fn falls_back_to_nested_resolution_when_the_cloud_has_no_plan_endpoint() {
    let leaf = module_zip("leaf", &[]);
    let dependent = module_zip("dependent", &["leaf"]);
    let (leaf_sha, dependent_sha) = (sha256_hex(&leaf), sha256_hex(&dependent));
    let mut catalog = HashMap::new();
    catalog.insert("leaf".to_string(), (leaf, leaf_sha));
    catalog.insert("dependent".to_string(), (dependent, dependent_sha));

    let mock = Arc::new(MockCloud {
        catalog,
        plan: None, // 404: endpoint not deployed
        calls: Mutex::new(Vec::new()),
        plan_bodies: Mutex::new(Vec::new()),
    });
    let base_url = spawn_mock_cloud(mock.clone()).await;

    let mut rt = Runtime::new(Box::new(fresh_db().await));
    install_from_cloud(
        &reqwest::Client::new(),
        &base_url,
        &cache_dir("fallback"),
        &Auth::HubToken {
            hub_id: "hub-test".into(),
            token: "tok".into(),
        },
        &mut rt,
        "dependent",
        "latest",
        &|_, _| {},
        &dev_policy(),
    )
    .await
    .expect("without a plan the hub still resolves deps from the manifest");

    assert!(rt.registry().is_installed("leaf"));
    assert!(rt.registry().is_installed("dependent"));
    let calls = mock.calls.lock().unwrap().clone();
    assert!(
        calls.iter().any(|c| c.starts_with("versions:")),
        "the fallback path does use versions/: {calls:?}"
    );
}

/// (5) hub#672: a plan that arrives 200 but is INCOMPLETE — it omits a dependency that the
/// downloaded module's manifest DOES declare (the saas#1352 empty-`Module.dependencies` outage:
/// every plan came back as a single node) — must NOT be executed as-is and die in the runtime's
/// `MissingDependency` net. The hub detects the drift against the real manifest and degrades to
/// the manifest-nested fallback, which installs the whole closure. The net RECOVERS, not just kills.
#[tokio::test]
async fn an_incomplete_plan_degrades_to_the_manifest_fallback_and_recovers() {
    let leaf = module_zip("leaf", &[]);
    let dependent = module_zip("dependent", &["leaf"]);
    let (leaf_sha, dependent_sha) = (sha256_hex(&leaf), sha256_hex(&dependent));
    let mut catalog = HashMap::new();
    catalog.insert("leaf".to_string(), (leaf, leaf_sha));
    catalog.insert("dependent".to_string(), (dependent, dependent_sha.clone()));

    // The Cloud's graph is broken: the plan holds ONLY the requested module, even though the
    // published zip's manifest declares `depends_on: ["leaf"]` and nothing is installed yet.
    let mock = Arc::new(MockCloud {
        catalog,
        plan: Some(json!({
            "requested": "dependent",
            "plan": [node("dependent", &dependent_sha, "requested")],
            "already_satisfied": [],
            "blocked": false,
            "blocked_on": [],
        })),
        calls: Mutex::new(Vec::new()),
        plan_bodies: Mutex::new(Vec::new()),
    });
    let base_url = spawn_mock_cloud(mock.clone()).await;

    let mut rt = Runtime::new(Box::new(fresh_db().await));
    install_from_cloud(
        &reqwest::Client::new(),
        &base_url,
        &cache_dir("incomplete"),
        &Auth::HubToken {
            hub_id: "hub-test".into(),
            token: "tok".into(),
        },
        &mut rt,
        "dependent",
        "latest",
        &|_, _| {},
        &dev_policy(),
    )
    .await
    .expect(
        "an incomplete plan must degrade to the manifest fallback, not die in MissingDependency",
    );

    assert!(
        rt.registry().is_installed("leaf"),
        "the dependency the plan omitted must be installed via the manifest fallback"
    );
    assert!(rt.registry().is_installed("dependent"));
    let calls = mock.calls.lock().unwrap().clone();
    assert!(
        calls.iter().any(|c| c.starts_with("versions:")),
        "recovery goes through the manifest fallback (versions/ round-trip): {calls:?}"
    );
}

// ── hub#1130: the response must SAY what it dragged in ─────────────────────────────────────
//
// `POST /api/modules/request-install` only ever answered the headline `module_id`. Installing
// `dependent` silently installed `leaf` too (ADR-0060's own topological closure), and nothing in
// the response told the caller — the owner saw new icons nobody asked for, and the assistant/a
// script could not report or undo what had just changed. The reverse door already names what it
// removes (hub#1101, `409 has_dependents` + `error.dependents`); this pins the forward door naming
// what it added.

/// (6) A module whose dependency is missing reports it in `also_installed`, in the plan's own
/// topological (installation) order — the headline module itself is never in its own list.
#[tokio::test]
async fn install_reports_the_modules_it_dragged_in_hub1130() {
    let dep_a = module_zip("dep_a", &[]);
    let dep_b = module_zip("dep_b", &[]);
    let requested = module_zip("verifactu", &["dep_a", "dep_b"]);
    let (sha_a, sha_b, sha_req) = (
        sha256_hex(&dep_a),
        sha256_hex(&dep_b),
        sha256_hex(&requested),
    );
    let mut catalog = HashMap::new();
    catalog.insert("dep_a".to_string(), (dep_a, sha_a.clone()));
    catalog.insert("dep_b".to_string(), (dep_b, sha_b.clone()));
    catalog.insert("verifactu".to_string(), (requested, sha_req.clone()));

    let mock = Arc::new(MockCloud {
        catalog,
        plan: Some(json!({
            "requested": "verifactu",
            "plan": [node("dep_a", &sha_a, "dependency"),
                     node("dep_b", &sha_b, "dependency"),
                     node("verifactu", &sha_req, "requested")],
            "already_satisfied": [],
            "blocked": false,
            "blocked_on": [],
        })),
        calls: Mutex::new(Vec::new()),
        plan_bodies: Mutex::new(Vec::new()),
    });
    let base_url = spawn_mock_cloud(mock.clone()).await;

    let mut rt = Runtime::new(Box::new(fresh_db().await));
    let installed = install_from_cloud(
        &reqwest::Client::new(),
        &base_url,
        &cache_dir("dragged-in"),
        &Auth::HubToken {
            hub_id: "hub-test".into(),
            token: "tok".into(),
        },
        &mut rt,
        "verifactu",
        "latest",
        &|_, _| {},
        &dev_policy(),
    )
    .await
    .expect("the plan resolves and installs the whole closure");

    assert_eq!(installed.module_id, "verifactu");
    assert_eq!(
        installed.also_installed,
        vec!["dep_a".to_string(), "dep_b".to_string()],
        "also_installed must name what got dragged in, in installation order"
    );
}

/// (7) A module with no pending dependencies reports an EMPTY `also_installed` — never absent, so
/// a caller never has to special-case the shape.
#[tokio::test]
async fn install_with_no_pending_dependencies_reports_empty_also_installed_hub1130() {
    let standalone = module_zip("customers", &[]);
    let sha = sha256_hex(&standalone);
    let mut catalog = HashMap::new();
    catalog.insert("customers".to_string(), (standalone, sha.clone()));

    let mock = Arc::new(MockCloud {
        catalog,
        plan: Some(json!({
            "requested": "customers",
            "plan": [node("customers", &sha, "requested")],
            "already_satisfied": [],
            "blocked": false,
            "blocked_on": [],
        })),
        calls: Mutex::new(Vec::new()),
        plan_bodies: Mutex::new(Vec::new()),
    });
    let base_url = spawn_mock_cloud(mock.clone()).await;

    let mut rt = Runtime::new(Box::new(fresh_db().await));
    let installed = install_from_cloud(
        &reqwest::Client::new(),
        &base_url,
        &cache_dir("no-deps"),
        &Auth::HubToken {
            hub_id: "hub-test".into(),
            token: "tok".into(),
        },
        &mut rt,
        "customers",
        "latest",
        &|_, _| {},
        &dev_policy(),
    )
    .await
    .expect("a module without dependencies still installs");

    assert_eq!(installed.module_id, "customers");
    assert!(
        installed.also_installed.is_empty(),
        "no dependency was dragged in: {:?}",
        installed.also_installed
    );
}

/// (8) A dependency that was ALREADY installed before this call is not something THIS call
/// installed — it must not show up in `also_installed` (it is not a surprise to the caller).
#[tokio::test]
async fn already_installed_dependency_is_not_reported_as_also_installed_hub1130() {
    let leaf = module_zip("leaf", &[]);
    let dependent = module_zip("dependent", &["leaf"]);
    let (leaf_sha, dependent_sha) = (sha256_hex(&leaf), sha256_hex(&dependent));
    let mut catalog = HashMap::new();
    catalog.insert("leaf".to_string(), (leaf, leaf_sha.clone()));
    catalog.insert("dependent".to_string(), (dependent, dependent_sha.clone()));

    // The Cloud already knows `leaf` is there: it only plans `dependent`.
    let mock = Arc::new(MockCloud {
        catalog,
        plan: Some(json!({
            "requested": "dependent",
            "plan": [node("dependent", &dependent_sha, "requested")],
            "already_satisfied": ["leaf"],
            "blocked": false,
            "blocked_on": [],
        })),
        calls: Mutex::new(Vec::new()),
        plan_bodies: Mutex::new(Vec::new()),
    });
    let base_url = spawn_mock_cloud(mock.clone()).await;

    let auth = Auth::HubToken {
        hub_id: "hub-test".into(),
        token: "tok".into(),
    };
    let cache = cache_dir("satisfied-also-installed");
    let mut rt = Runtime::new(Box::new(fresh_db().await));

    // Pre-install the dependency straight from disk so the registry really holds it BEFORE this
    // request-install call — the same setup as scenario (3) above.
    let leaf_dir = cache.join("preinstalled-leaf");
    std::fs::create_dir_all(&leaf_dir).unwrap();
    std::fs::write(
        leaf_dir.join("module.json"),
        serde_json::to_vec(&json!({"id":"leaf","name":"leaf","version":"1.0.0"})).unwrap(),
    )
    .unwrap();
    rt.install_from_dir(&leaf_dir).await.unwrap();

    let installed = install_from_cloud(
        &reqwest::Client::new(),
        &base_url,
        &cache,
        &auth,
        &mut rt,
        "dependent",
        "latest",
        &|_, _| {},
        &dev_policy(),
    )
    .await
    .expect("installs only what the plan lists");

    assert_eq!(installed.module_id, "dependent");
    assert!(
        installed.also_installed.is_empty(),
        "a pre-existing dependency was not dragged in by THIS call: {:?}",
        installed.also_installed
    );
}

/// (9) The manifest-nested fallback (Cloud without `install-plan/`) drags dependencies in exactly
/// like the plan path — the caller must not lose the "what did you drag in" answer just because
/// the safety net took over.
#[tokio::test]
async fn manifest_fallback_also_reports_dragged_in_dependencies_hub1130() {
    let leaf = module_zip("leaf", &[]);
    let dependent = module_zip("dependent", &["leaf"]);
    let (leaf_sha, dependent_sha) = (sha256_hex(&leaf), sha256_hex(&dependent));
    let mut catalog = HashMap::new();
    catalog.insert("leaf".to_string(), (leaf, leaf_sha));
    catalog.insert("dependent".to_string(), (dependent, dependent_sha));

    let mock = Arc::new(MockCloud {
        catalog,
        plan: None, // 404: endpoint not deployed → manifest-nested fallback
        calls: Mutex::new(Vec::new()),
        plan_bodies: Mutex::new(Vec::new()),
    });
    let base_url = spawn_mock_cloud(mock.clone()).await;

    let mut rt = Runtime::new(Box::new(fresh_db().await));
    let installed = install_from_cloud(
        &reqwest::Client::new(),
        &base_url,
        &cache_dir("fallback-dragged-in"),
        &Auth::HubToken {
            hub_id: "hub-test".into(),
            token: "tok".into(),
        },
        &mut rt,
        "dependent",
        "latest",
        &|_, _| {},
        &dev_policy(),
    )
    .await
    .expect("without a plan the hub still resolves deps from the manifest");

    assert_eq!(installed.module_id, "dependent");
    assert_eq!(
        installed.also_installed,
        vec!["leaf".to_string()],
        "the manifest fallback must report the dependency it installed too"
    );
}
