//! TDD (ADR-0212, hub#406): the hub IMPORTS the blueprint the SaaS DECLARED for it.
//!
//! The SaaS cannot push: `X-Hub-Token` only travels hub→SaaS, and the runtime answers 428 to any
//! caller without a local session. So provisioning writes an **identity** into the hub's env —
//! `HUB_BOOTSTRAP_BLUEPRINT` (slug) + `HUB_BOOTSTRAP_BLUEPRINT_LOCALE` — and the hub reconciles it
//! once it is really up. Never a presigned URL: it carries a credential, it lands in a deploy log
//! and it expires in an hour.
//!
//! What is pinned here:
//!   1. WITHOUT the keys the hub does nothing — not one call to the Cloud (a mechanism that fires
//!      on its own would seed every hub, not the ones the SaaS chose);
//!   2. WITH them the declared bundle is resolved with the machine credential, its sha256 verified
//!      and its sections applied — and the declared locale travels, because a slug is unique *per
//!      language* and the download endpoint answers 400 to an ambiguous one;
//!   3. a failing import NEVER stops the hub from serving (this is the whole reason it is not a
//!      `HUB_SEED_SQL`, whose failure aborts the boot): a broken bundle leaves the visitor with the
//!      setup wizard, not without a hub;
//!   4. failure is bounded — retries, then it gives up and reports through the channel that already
//!      exists (`error_registry` → `POST /api/v1/hub/device/error-report/`);
//!   5. it is IDEMPOTENT across reboots: the container is rescheduled and reads the same value
//!      again (the SaaS sends identical bytes every redeploy — it is a state, not an order), so the
//!      marker lives in the hub's DB, which survives. Re-importing would duplicate the catalogue;
//!   6. the defenses of hub#331 and hub#405 hold: this import cannot install another business's
//!      accounts nor its fiscal identity, because it goes through the very same engine.
//!
//! No modules-workspace needed: the bundle is produced by the real `export_hub` and carries only
//! `hub_users` + `hub_settings`, which exist in every hub (system migration v4).

use std::io::Write as _;
use std::sync::{Arc, Mutex, Once};
use std::time::Duration;

use axum::body::Body;
use axum::extract::{Path as AxumPath, RawQuery, State};
use axum::http::{Request, StatusCode};
use axum::routing::get;
use axum::{Json, Router};
use erplora_db::{testutil::fresh_db, Params};
use erplora_runtime::error_registry::{ErrorEvent, ErrorRegistry, ErrorSink};
use erplora_runtime::export::{export_hub, BundlePurpose, ExportSelection};
use erplora_runtime::reset::list_import_batches;
use erplora_runtime::Runtime;
use erplora_server::bootstrap::{
    import_declared_blueprint, spawn_declared_blueprint_import, BootstrapBlueprint,
    BootstrapOutcome, RetryPolicy, BOOTSTRAP_FAILED_CODE,
};
use erplora_server::{app, AppState, AuthMode, HubConfig};
use serde_json::{json, Value};
use tower::ServiceExt; // oneshot

const CREATED_AT: &str = "2026-08-07T00:00:00Z";
/// Identity of the business that produced the bundle. None of it may land in the destination hub.
const ORIGIN_TAX_ID: &str = "B12345678";
const DESTINATION_HUB: &str = "hub-under-test";

// ─────────────────────────────── the bundle ──────────────────────────────────

fn build_zip(entries: &[(String, Vec<u8>)]) -> Vec<u8> {
    let mut buf = Vec::new();
    {
        let mut w = zip::ZipWriter::new(std::io::Cursor::new(&mut buf));
        let opts: zip::write::FileOptions<()> = zip::write::FileOptions::default();
        for (name, bytes) in entries {
            w.start_file(name.clone(), opts).unwrap();
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

async fn fresh_runtime(hub: &str) -> Runtime {
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), hub);
    rt.ensure_system_tables().await.expect("system tables");
    rt
}

/// A real `.blueprint.zip`, produced by the real exporter from ANOTHER hub — which is exactly what
/// a published blueprint is (and what the four in the catalogue are: bundles older than `purpose`,
/// so they read as `backup` and carry the origin's accounts and tax id).
async fn foreign_blueprint_zip() -> Vec<u8> {
    let origin = fresh_runtime("origin-hub").await;
    erplora_runtime::settings::set_many(
        origin.db(),
        "origin-hub",
        json!({
            // Configuration — what a sector template is for.
            "country_code": "ES",
            "currency": "EUR",
            "language": "es",
            "theme_palette": "ocean",
            // Identity of ONE business: it may not travel (ADR-0195 §4, hub#405).
            "business_tax_id": ORIGIN_TAX_ID,
            "business_legal_name": "Bar Pepe SL",
        })
        .as_object()
        .expect("settings map"),
        "hub_user:owner",
        false, // the ORIGIN hub is a normal one: hub#376's demo lock is not what this fixture tests
    )
    .await
    .expect("seed origin settings");

    let selection = ExportSelection {
        users: true,
        settings: true,
        purpose: BundlePurpose::Backup,
        ..Default::default()
    };
    let bundle = export_hub(
        &origin,
        "origin-hub",
        &selection,
        "restaurante",
        "es",
        CREATED_AT,
    )
    .await
    .expect("export the origin hub");

    let manifest = serde_json::to_vec(&bundle.manifest).expect("serialize manifest");
    let mut entries = vec![("manifest.json".to_string(), manifest)];
    for (path, bytes) in &bundle.files {
        entries.push((path.clone(), bytes.clone()));
    }
    build_zip(&entries)
}

// ─────────────────────────────── the mock Cloud ──────────────────────────────

struct MockCloud {
    /// The `.blueprint.zip` this Cloud serves.
    zip: Vec<u8>,
    /// sha256 announced by `download/`. Not always the zip's: an announced-but-wrong hash is the
    /// tampering case, and nothing may be applied then.
    announced_sha256: String,
    /// HTTP status the resolve endpoint answers with. 200 = happy path.
    resolve_status: u16,
    /// Every call, in order: `resolve:<slug>?<query>`, `storage`.
    calls: Mutex<Vec<String>>,
}

type Shared = Arc<MockCloud>;

impl MockCloud {
    fn serving(zip: Vec<u8>) -> Shared {
        let sha = sha256_hex(&zip);
        Arc::new(MockCloud {
            zip,
            announced_sha256: sha,
            resolve_status: 200,
            calls: Mutex::new(Vec::new()),
        })
    }

    fn calls(&self) -> Vec<String> {
        self.calls.lock().unwrap().clone()
    }
}

async fn spawn_mock_cloud(mock: Shared) -> String {
    async fn resolve(
        State(m): State<Shared>,
        AxumPath(slug): AxumPath<String>,
        RawQuery(query): RawQuery,
    ) -> axum::response::Response {
        use axum::response::IntoResponse;
        m.calls
            .lock()
            .unwrap()
            .push(format!("resolve:{slug}?{}", query.unwrap_or_default()));
        if m.resolve_status != 200 {
            return (
                StatusCode::from_u16(m.resolve_status).unwrap(),
                Json(json!({ "error": "blueprint unavailable" })),
            )
                .into_response();
        }
        Json(json!({
            "slug": slug,
            "version": "1.4.0",
            "sha256": m.announced_sha256,
            "size_bytes": m.zip.len(),
            // Object Storage presigned URL — served by this same mock for the test.
            "url": "__BASE__/storage/blueprint.zip",
        }))
        .into_response()
    }
    async fn storage(State(m): State<Shared>) -> Vec<u8> {
        m.calls.lock().unwrap().push("storage".to_string());
        m.zip.clone()
    }

    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let addr = listener.local_addr().unwrap();
    let base = format!("http://{addr}");
    // The presigned URL is absolute: rewrite the placeholder with the port we just got.
    let base_for_rewrite = base.clone();
    let app = Router::new()
        .route("/api/v1/catalog/blueprints/:slug/download/", get(resolve))
        .route("/storage/blueprint.zip", get(storage))
        .layer(axum::middleware::map_response(
            move |resp: axum::response::Response| {
                let base = base_for_rewrite.clone();
                async move { rewrite_base(resp, &base).await }
            },
        ))
        .with_state(mock);
    tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
    base
}

/// Replaces the `__BASE__` placeholder of the presigned URL with the mock's real origin.
async fn rewrite_base(resp: axum::response::Response, base: &str) -> axum::response::Response {
    let (parts, body) = resp.into_parts();
    let bytes = axum::body::to_bytes(body, 32 * 1024 * 1024)
        .await
        .unwrap_or_default();
    match std::str::from_utf8(&bytes) {
        Ok(text) if text.contains("__BASE__") => {
            let patched = text.replace("__BASE__", base);
            axum::response::Response::from_parts(parts, Body::from(patched))
        }
        _ => axum::response::Response::from_parts(parts, Body::from(bytes)),
    }
}

// ─────────────────────────────── the hub under test ──────────────────────────

fn test_config(cloud: &str, blueprint: Option<BootstrapBlueprint>, tag: &str) -> HubConfig {
    let base = std::env::temp_dir().join(format!("erplora_bootstrap_{}_{tag}", std::process::id()));
    HubConfig {
        demo: false,
        hub_id: DESTINATION_HUB.into(),
        cloud_base_url: cloud.into(),
        module_cache: base.join("module_cache"),
        auth_mode: AuthMode::Dev,
        jwt_public_key: None,
        // The demo's env carries it: the hub authenticates ITSELF to resolve the blueprint.
        cloud_api_token: Some("machine-token".into()),
        device_trust_enforce: false,
        media_dir: base.join("media"),
        sector: None,
        dev_mode: false,
        dev_modules_dir: None,
        module_trusted_keys: Vec::new(),
        bootstrap_blueprint: blueprint,
    }
}

async fn hub_with(cloud: &str, blueprint: Option<BootstrapBlueprint>, tag: &str) -> AppState {
    let rt = fresh_runtime(DESTINATION_HUB).await;
    AppState::with_config(rt, test_config(cloud, blueprint, tag))
}

fn declared(slug: &str, locale: Option<&str>) -> Option<BootstrapBlueprint> {
    Some(BootstrapBlueprint {
        slug: slug.to_string(),
        locale: locale.map(str::to_string),
    })
}

/// Fast retries: the policy under test is "bounded", not "slow".
fn quick_retry(attempts: u32) -> RetryPolicy {
    RetryPolicy {
        attempts,
        backoff: Duration::from_millis(1),
    }
}

async fn setting_value(st: &AppState, key: &str) -> Option<String> {
    let rt = st.runtime.lock().await;
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(DESTINATION_HUB));
    p.insert("key".into(), json!(key));
    let res = rt
        .db()
        .query(
            "SELECT value FROM hub_settings WHERE hub_id = :hub_id AND key = :key",
            &p,
        )
        .await
        .expect("read hub_settings");
    res.rows
        .first()
        .and_then(|r| r["value"].as_str().map(str::to_string))
}

async fn hub_user_count(st: &AppState) -> i64 {
    let rt = st.runtime.lock().await;
    let res = rt
        .db()
        .query("SELECT count(*) AS n FROM hub_user", &Params::new())
        .await
        .expect("count hub_user");
    res.rows
        .first()
        .and_then(|r| r["n"].as_i64())
        .unwrap_or_default()
}

async fn import_batch_count(st: &AppState) -> usize {
    let rt = st.runtime.lock().await;
    list_import_batches(&rt, DESTINATION_HUB)
        .await
        .expect("list import batches")
        .len()
}

// ───────────────────────────── 1. no keys, no import ─────────────────────────

/// Without the two env keys the hub does NOT import anything, and does not even ask the Cloud.
/// The mechanism is generic (like `HUB_SEED_SQL`): the SaaS decides who receives it — a runtime
/// that seeded itself would populate every hub, including the paying customer's.
#[tokio::test]
async fn without_the_declared_blueprint_the_hub_imports_nothing() {
    let mock = MockCloud::serving(foreign_blueprint_zip().await);
    let cloud = spawn_mock_cloud(mock.clone()).await;
    let st = hub_with(&cloud, None, "nokeys").await;

    assert!(
        spawn_declared_blueprint_import(&st).is_none(),
        "with no blueprint declared there is nothing to spawn at boot"
    );
    let outcome = import_declared_blueprint(&st, quick_retry(3)).await;
    assert_eq!(outcome, BootstrapOutcome::NotDeclared);
    assert!(
        mock.calls().is_empty(),
        "an undeclared hub must not touch the Cloud: {:?}",
        mock.calls()
    );
    assert_eq!(import_batch_count(&st).await, 0);
}

// ───────────────────────────── 2. the happy path ─────────────────────────────

/// The declared blueprint is resolved with the machine credential, downloaded, verified and
/// applied — and the LOCALE travels, because the slug is unique per language and the download
/// endpoint answers 400 to an ambiguous one.
#[tokio::test]
async fn a_declared_blueprint_is_imported_after_boot() {
    let mock = MockCloud::serving(foreign_blueprint_zip().await);
    let cloud = spawn_mock_cloud(mock.clone()).await;
    let st = hub_with(&cloud, declared("restaurante", Some("es")), "happy").await;

    let outcome = import_declared_blueprint(&st, quick_retry(3)).await;
    match &outcome {
        BootstrapOutcome::Imported { slug, version, .. } => {
            assert_eq!(slug, "restaurante");
            assert_eq!(version, "1.4.0");
        }
        other => panic!("the declared blueprint must be imported, got {other:?}"),
    }

    let calls = mock.calls();
    assert!(
        calls
            .iter()
            .any(|c| c.starts_with("resolve:restaurante?") && c.contains("locale=es")),
        "the declared locale must travel to the download endpoint: {calls:?}"
    );
    assert!(calls.contains(&"storage".to_string()), "{calls:?}");

    // The configuration of the bundle landed: this is what makes the demo not be born empty.
    assert_eq!(setting_value(&st, "language").await.as_deref(), Some("es"));
    assert_eq!(
        setting_value(&st, "theme_palette").await.as_deref(),
        Some("ocean")
    );
    assert_eq!(import_batch_count(&st).await, 1);
}

// ───────────────────── 3. a failure never takes the hub down ─────────────────

/// 🔴 The reason this is NOT a `HUB_SEED_SQL`: that one is applied with `?` inside `serve()` and a
/// broken seed ABORTS the boot. A blueprint that cannot be imported must leave a hub that WORKS
/// (the visitor sees the setup wizard) — never a visitor without a hub.
#[tokio::test]
async fn a_failing_import_never_stops_the_hub_from_serving() {
    // A Cloud that answers 500 to the resolve: nothing can be downloaded.
    let zip = foreign_blueprint_zip().await;
    let sha = sha256_hex(&zip);
    let mock = Arc::new(MockCloud {
        zip,
        announced_sha256: sha,
        resolve_status: 500,
        calls: Mutex::new(Vec::new()),
    });
    let cloud = spawn_mock_cloud(mock.clone()).await;
    let st = hub_with(&cloud, declared("roto", Some("es")), "serving").await;

    // The import runs in its own task, exactly as `serve()` spawns it — so while it retries and
    // fails, the router keeps answering.
    let task_state = st.clone();
    let handle = tokio::spawn(async move {
        import_declared_blueprint(
            &task_state,
            RetryPolicy {
                attempts: 3,
                backoff: Duration::from_millis(40),
            },
        )
        .await
    });

    let router = app(st.clone());
    let resp = router
        .oneshot(
            Request::builder()
                .uri("/healthz")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(
        resp.status(),
        StatusCode::OK,
        "the hub must serve while the bootstrap import is failing"
    );

    let outcome = handle.await.expect("the bootstrap task must not panic");
    match &outcome {
        BootstrapOutcome::GaveUp { attempts, .. } => assert_eq!(*attempts, 3),
        other => panic!("a Cloud answering 500 must end in GaveUp, got {other:?}"),
    }

    // And it still serves afterwards.
    let resp = app(st.clone())
        .oneshot(
            Request::builder()
                .uri("/healthz")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    assert_eq!(import_batch_count(&st).await, 0, "nothing was applied");
}

/// Bounded: it retries a fixed number of times and then stops. A hub that retried forever against a
/// Cloud that is down would be a loop nobody stops on a host that lives 60 minutes.
#[tokio::test]
async fn the_retry_is_bounded_and_then_it_gives_up() {
    let zip = foreign_blueprint_zip().await;
    let sha = sha256_hex(&zip);
    let mock = Arc::new(MockCloud {
        zip,
        announced_sha256: sha,
        resolve_status: 503,
        calls: Mutex::new(Vec::new()),
    });
    let cloud = spawn_mock_cloud(mock.clone()).await;
    let st = hub_with(&cloud, declared("no-existe", Some("es")), "bounded").await;

    let outcome = import_declared_blueprint(&st, quick_retry(2)).await;
    assert!(matches!(
        outcome,
        BootstrapOutcome::GaveUp { attempts: 2, .. }
    ));
    assert_eq!(
        mock.calls().len(),
        2,
        "exactly one resolve per attempt, no more: {:?}",
        mock.calls()
    );
}

// ───────────────────── 4. giving up is REPORTED, not swallowed ───────────────

/// Collects every event the runtime reports, so the test can assert the give-up travelled through
/// the channel that already exists (`error_registry` → `POST /api/v1/hub/device/error-report/`).
#[derive(Default)]
struct CapturingSink {
    events: Mutex<Vec<ErrorEvent>>,
}

static SINK: std::sync::OnceLock<Arc<CapturingSink>> = std::sync::OnceLock::new();
static INSTALL: Once = Once::new();

impl ErrorSink for CapturingSink {
    fn submit(&self, event: ErrorEvent) {
        self.events.lock().unwrap().push(event);
    }
}

fn capturing_sink() -> Arc<CapturingSink> {
    let sink = SINK
        .get_or_init(|| Arc::new(CapturingSink::default()))
        .clone();
    INSTALL.call_once(|| ErrorRegistry::install(sink.clone()));
    sink
}

/// A demo whose blueprint could not be imported is DEGRADED, never discarded — but it is not
/// silent either: the hub says so through the error channel, and the reaper takes the demo down at
/// its TTL just the same (`is_demo` + `expires_at` are written in the very `INSERT` of the row).
#[tokio::test]
async fn giving_up_is_reported_through_the_existing_error_channel() {
    let sink = capturing_sink();
    let zip = foreign_blueprint_zip().await;
    let sha = sha256_hex(&zip);
    let mock = Arc::new(MockCloud {
        zip,
        announced_sha256: sha,
        resolve_status: 500,
        calls: Mutex::new(Vec::new()),
    });
    let cloud = spawn_mock_cloud(mock).await;
    // A slug of its own: the registry dedups by fingerprint, and another test must not eat this one.
    let st = hub_with(&cloud, declared("reported-slug", Some("es")), "reported").await;

    let outcome = import_declared_blueprint(&st, quick_retry(1)).await;
    assert!(matches!(outcome, BootstrapOutcome::GaveUp { .. }));

    let events = sink.events.lock().unwrap().clone();
    let reported = events
        .iter()
        .find(|e| {
            e.error_code == BOOTSTRAP_FAILED_CODE && e.context["slug"] == json!("reported-slug")
        })
        .unwrap_or_else(|| {
            panic!("the give-up must be reported with a stable code, got {events:?}")
        });
    assert_eq!(reported.source, "hub");
    assert_eq!(reported.context["locale"], json!("es"));
}

// ───────────────────────────── 5. idempotence ────────────────────────────────

/// The container is stateless and gets rescheduled: it reads the SAME value again (the SaaS sends
/// identical bytes on every redeploy, on purpose — it is a state, not an order). So the second boot
/// must be a no-op: re-importing would duplicate the whole catalogue.
#[tokio::test]
async fn a_second_boot_does_not_import_the_blueprint_twice() {
    let mock = MockCloud::serving(foreign_blueprint_zip().await);
    let cloud = spawn_mock_cloud(mock.clone()).await;
    let st = hub_with(&cloud, declared("restaurante", Some("es")), "idempotent").await;

    let first = import_declared_blueprint(&st, quick_retry(3)).await;
    assert!(
        matches!(first, BootstrapOutcome::Imported { .. }),
        "{first:?}"
    );
    let batches_after_first = import_batch_count(&st).await;
    assert_eq!(batches_after_first, 1);

    // Same hub, same DB, same declared value — the reboot.
    let second = import_declared_blueprint(&st, quick_retry(3)).await;
    match &second {
        BootstrapOutcome::AlreadyApplied { slug, version } => {
            assert_eq!(slug, "restaurante");
            assert_eq!(version, "1.4.0");
        }
        other => panic!("a second boot must be a no-op, got {other:?}"),
    }
    assert_eq!(
        import_batch_count(&st).await,
        1,
        "a reboot must not open a second import batch"
    );
    assert_eq!(
        mock.calls()
            .iter()
            .filter(|c| c.starts_with("resolve:"))
            .count(),
        1,
        "the marker is read BEFORE the network: a reboot must not even resolve again"
    );
}

// ───────────────── 6. the defenses of hub#331 / hub#405 hold ─────────────────

/// This import is not a back door. It goes through the same engine as the UI, so a bundle produced
/// by ANOTHER hub cannot install its accounts (hub#331) nor write its fiscal identity (hub#405) —
/// which matters most precisely here, where nobody is watching the screen.
#[tokio::test]
async fn the_bootstrap_import_applies_neither_accounts_nor_the_foreign_tax_id() {
    let mock = MockCloud::serving(foreign_blueprint_zip().await);
    let cloud = spawn_mock_cloud(mock).await;
    let st = hub_with(&cloud, declared("restaurante", Some("es")), "defenses").await;

    let users_before = hub_user_count(&st).await;
    let outcome = import_declared_blueprint(&st, quick_retry(3)).await;
    let report = match outcome {
        BootstrapOutcome::Imported { report, .. } => report,
        other => panic!("expected an import, got {other:?}"),
    };

    assert_eq!(
        hub_user_count(&st).await,
        users_before,
        "the accounts of the origin hub must NOT be created here (ADR-0195 §3)"
    );
    assert_eq!(
        setting_value(&st, "business_tax_id").await,
        None,
        "the tax id of another business must NOT land in this hub (ADR-0195 §4)"
    );

    let sections = report["sections"].as_array().expect("sections").clone();
    let users = section(&sections, "hub_users");
    assert!(
        users["status"]["Ignored"].is_string(),
        "hub_users must be reported as Ignored with its reason: {users}"
    );
    let settings = section(&sections, "hub_settings");
    assert_eq!(
        settings["status"]["PartiallyApplied"],
        json!("settings_not_portable"),
        "hub_settings must be reported as partially applied with its stable code, never a green tick: {settings}"
    );
    assert!(
        settings["discarded_rows"].as_u64().unwrap_or(0) >= 2,
        "the report must say HOW MANY rows stayed out (the tax id and the legal name): {settings}"
    );
}

fn section(sections: &[Value], name: &str) -> Value {
    sections
        .iter()
        .find(|s| s["section"] == json!(name))
        .unwrap_or_else(|| panic!("section `{name}` missing from the report: {sections:?}"))
        .clone()
}

// ───────────────────────── 7. integrity is not skippable ─────────────────────

/// ADR-0015/ADR-0121: the sha256 announced by the SaaS is verified BEFORE anything is applied. A
/// zip that does not match is not "best effort" — nothing lands and the hub gives up.
#[tokio::test]
async fn a_blueprint_whose_sha256_does_not_match_is_never_applied() {
    let mock = Arc::new(MockCloud {
        zip: foreign_blueprint_zip().await,
        announced_sha256: "00".repeat(32),
        resolve_status: 200,
        calls: Mutex::new(Vec::new()),
    });
    let cloud = spawn_mock_cloud(mock).await;
    let st = hub_with(&cloud, declared("tampered", Some("es")), "integrity").await;

    let outcome = import_declared_blueprint(&st, quick_retry(1)).await;
    match &outcome {
        BootstrapOutcome::GaveUp { error, .. } => {
            assert!(
                error.contains("sha256"),
                "the give-up must name the integrity check: {error}"
            );
        }
        other => panic!("a tampered bundle must not be applied, got {other:?}"),
    }
    assert_eq!(import_batch_count(&st).await, 0);
    assert_eq!(setting_value(&st, "language").await, None);
}

// ───────────────────── 8. the boot path spawns, never blocks ─────────────────

/// `serve()` must SPAWN this, not await it: the hub has to be listening while the blueprint is
/// being fetched. What the spawn returns is a handle, never an error that could bubble up into the
/// boot — which is the difference with the seed.
#[tokio::test]
async fn the_boot_spawns_the_import_instead_of_awaiting_it() {
    let mock = MockCloud::serving(foreign_blueprint_zip().await);
    let cloud = spawn_mock_cloud(mock.clone()).await;
    let st = hub_with(&cloud, declared("restaurante", Some("es")), "spawned").await;

    let handle = spawn_declared_blueprint_import(&st).expect("a declared blueprint must spawn");
    // The router is usable straight away — the import is still in flight behind us.
    let resp = app(st.clone())
        .oneshot(
            Request::builder()
                .uri("/healthz")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK);

    let outcome = handle.await.expect("the spawned task must not panic");
    assert!(
        matches!(outcome, BootstrapOutcome::Imported { .. }),
        "{outcome:?}"
    );
}

// ─────────────────── 9. the env keys are actually read ───────────────────────

/// One row of the env table below: the two raw values and the declaration they must produce.
type EnvCase = (
    Option<&'static str>,
    Option<&'static str>,
    Option<(&'static str, Option<&'static str>)>,
);

/// ⚠️ An env key without a reader is a DEAD contract, and it already happened: `HUB_COUNTRY`
/// (ADR-0207) and `HUB_NAME` are injected by both provider builders and `grep -rn HUB_COUNTRY hub/`
/// returns nothing. This test is what stops `HUB_BOOTSTRAP_BLUEPRINT` from ending up the same.
#[tokio::test]
async fn the_two_env_keys_are_read_into_the_config() {
    let _guard = env_lock();
    // (HUB_BOOTSTRAP_BLUEPRINT, HUB_BOOTSTRAP_BLUEPRINT_LOCALE) → what the config must hold.
    let cases: Vec<EnvCase> = vec![
        (
            Some("restaurante"),
            Some("es"),
            Some(("restaurante", Some("es"))),
        ),
        // Whitespace is not a declaration.
        (Some("  "), Some("es"), None),
        (None, Some("es"), None),
        (None, None, None),
        // A slug without locale is still a declaration: silently doing nothing would be the dead
        // contract all over again. The SaaS answers 400 if the slug is ambiguous, and that is a
        // reported failure instead of a hub that quietly stays empty.
        (Some("restaurante"), None, Some(("restaurante", None))),
        (
            Some(" restaurante "),
            Some(" es "),
            Some(("restaurante", Some("es"))),
        ),
    ];
    for (slug, locale, expected) in cases {
        set_env("HUB_BOOTSTRAP_BLUEPRINT", slug);
        set_env("HUB_BOOTSTRAP_BLUEPRINT_LOCALE", locale);
        let cfg = HubConfig::from_env_with_auth(AuthMode::Dev);
        match (&cfg.bootstrap_blueprint, expected) {
            (None, None) => {}
            (Some(got), Some((slug, locale))) => {
                assert_eq!(got.slug, slug);
                assert_eq!(got.locale.as_deref(), locale);
            }
            (got, expected) => {
                panic!("slug={slug:?} locale={locale:?} → got {got:?}, expected {expected:?}")
            }
        }
    }
    set_env("HUB_BOOTSTRAP_BLUEPRINT", None);
    set_env("HUB_BOOTSTRAP_BLUEPRINT_LOCALE", None);
}

/// Env vars are process-global: the cases above run under one lock so they cannot race another
/// test that reads the environment.
fn env_lock() -> std::sync::MutexGuard<'static, ()> {
    static LOCK: std::sync::OnceLock<Mutex<()>> = std::sync::OnceLock::new();
    LOCK.get_or_init(|| Mutex::new(()))
        .lock()
        .unwrap_or_else(|p| p.into_inner())
}

fn set_env(key: &str, value: Option<&str>) {
    match value {
        Some(v) => std::env::set_var(key, v),
        None => std::env::remove_var(key),
    }
}
