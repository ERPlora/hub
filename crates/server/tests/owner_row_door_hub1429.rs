//! **The owner's row, through the real door** (hub#1429) — `PUT/DELETE /api/hub/users/{id}`.
//!
//! Two defects of the same handler, and both need the HTTP door rather than the pure guard: a rule
//! that is only proven on `guard_decision` proves the function, not that anything calls it.
//!
//! 1. **Any `admin` session could edit the row of the account OWNER** — their PIN, their badge,
//!    their name. The SaaS cannot police this (the runtime talks to it with the machine credential,
//!    which `assert_can_manage_hub_member` treats as owner rank), and until now the hub could not
//!    either, because hub#349 retired the local `owner` role and left the owner and any
//!    administrator sharing one word. The SaaS's blanket `403` hid it by accident — and hid the
//!    owner's own PIN rotation with it (pm#167) — until saas#1638/#1788 lifted it.
//! 2. **The local row was written BEFORE the SaaS was asked**, so a refusal came back as an error
//!    with the change already applied: the screen said "could not be saved" and the PIN had changed.
use axum::body::Body;
use axum::http::{Request, StatusCode};
use erplora_db::testutil::fresh_db;
use erplora_runtime::hub_users::NewHubUser;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use http_body_util::BodyExt;
use serde_json::{json, Value};
use tower::ServiceExt;

struct Fixture {
    router: axum::Router,
    /// The account owner: seeded from the provisioning env (`HUB_OWNER_EMAIL`, ADR-0157).
    owner_session: String,
    owner_id: String,
    /// A second administrator — an ordinary `admin`, exactly like the owner in the business plane.
    admin_session: String,
    /// An employee with an account (email), used for the write-order half.
    employee_id: String,
    rt_hub_id: String,
}

async fn fixture(hub_id: &str) -> Fixture {
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), hub_id);
    rt.ensure_system_tables().await.unwrap();

    // Boot: the deployment names the creator, and the row is marked as the account owner's.
    assert!(rt.seed_owner("ioan@example.com").await.unwrap());
    let owner = rt
        .get_or_link_cloud_user(
            "cloud-1",
            "Ioan Beilic",
            "admin",
            Some("ioan@example.com"),
            None,
        )
        .await
        .unwrap();

    let admin = rt
        .create_hub_user(&NewHubUser {
            name: "Ana Soto".into(),
            email: "ana@example.com".into(),
            role: "admin".into(),
            ..NewHubUser::default()
        })
        .await
        .unwrap();
    let employee = rt
        .create_hub_user(&NewHubUser {
            name: "Luis Prat".into(),
            email: "luis@example.com".into(),
            role: "employee".into(),
            ..NewHubUser::default()
        })
        .await
        .unwrap();

    let owner_session = rt.create_session(&owner.id, 3600, None).await.unwrap();
    let admin_session = rt.create_session(&admin, 3600, None).await.unwrap();

    let media = std::env::temp_dir().join(format!("erplora-{hub_id}-{}", std::process::id()));
    let cfg = HubConfig {
        demo: false,
        hub_id: hub_id.into(),
        // Unreachable on purpose: every call to the SaaS fails, which is the only way to see WHICH
        // side of the write happened first.
        cloud_base_url: "https://example.invalid".into(),
        module_cache: media.join("modules"),
        auth_mode: AuthMode::Session,
        jwt_public_key: None,
        cloud_api_token: Some("test-machine-token".into()),
        device_trust_enforce: false,
        media_dir: media,
        sector: None,
        dev_mode: false,
        dev_modules_dir: None,
        module_trusted_keys: Vec::new(),
    };
    Fixture {
        router: app(AppState::with_config(rt, cfg)),
        owner_session,
        owner_id: owner.id,
        admin_session,
        employee_id: employee,
        rt_hub_id: hub_id.into(),
    }
}

async fn body_json(response: axum::response::Response) -> Value {
    let bytes = response.into_body().collect().await.unwrap().to_bytes();
    serde_json::from_slice(&bytes).unwrap()
}

async fn put(fx: &Fixture, id: &str, session: &str, payload: Value) -> (StatusCode, Value) {
    let request = Request::builder()
        .method("PUT")
        .uri(format!("/api/hub/users/{id}"))
        .header("content-type", "application/json")
        .header("x-hub-session", session)
        .body(Body::from(payload.to_string()))
        .unwrap();
    let response = fx.router.clone().oneshot(request).await.unwrap();
    let status = response.status();
    (status, body_json(response).await)
}

async fn row(fx: &Fixture, id: &str) -> Value {
    let request = Request::builder()
        .uri("/api/hub/users")
        .header("x-hub-session", &fx.owner_session)
        .body(Body::empty())
        .unwrap();
    let listed = body_json(fx.router.clone().oneshot(request).await.unwrap()).await;
    listed["data"]
        .as_array()
        .unwrap()
        .iter()
        .find(|u| u["id"] == id)
        .cloned()
        .unwrap_or_else(|| panic!("{id} is in Personal (hub {})", fx.rt_hub_id))
}

/// **The escalation**: a second administrator rotating the owner's PIN is a credential that opens
/// the till AS the owner. It comes back `403` with the core's stable code, and the row is untouched.
#[tokio::test]
async fn another_admin_cannot_touch_the_owners_row() {
    let fx = fixture("hub-1429-a").await;

    let (status, body) = put(
        &fx,
        &fx.owner_id,
        &fx.admin_session,
        json!({ "pin": "4271" }),
    )
    .await;
    assert_eq!(status, StatusCode::FORBIDDEN, "{body}");
    assert_eq!(body["error"]["code"], "hub.users.owner_row");
    assert!(
        !row(&fx, &fx.owner_id).await["has_pin"]
            .as_bool()
            .unwrap_or(true),
        "a refused edit writes nothing: the owner still has no PIN"
    );

    // The same for the name, the role and the baja — the whole record, not just the credential.
    let name_before = row(&fx, &fx.owner_id).await["name"].clone();
    let (status, _) = put(
        &fx,
        &fx.owner_id,
        &fx.admin_session,
        json!({ "name": "Secuestrada" }),
    )
    .await;
    assert_eq!(status, StatusCode::FORBIDDEN);
    assert_eq!(row(&fx, &fx.owner_id).await["name"], name_before);

    let request = Request::builder()
        .method("DELETE")
        .uri(format!("/api/hub/users/{}", fx.owner_id))
        .header("x-hub-session", &fx.admin_session)
        .body(Body::empty())
        .unwrap();
    let response = fx.router.clone().oneshot(request).await.unwrap();
    assert_eq!(response.status(), StatusCode::FORBIDDEN);
    assert_eq!(row(&fx, &fx.owner_id).await["is_active"], true);
}

/// **The second door to the same row** (`/api/members`, ADR-0157 §7). It names people by EMAIL
/// instead of by id, and `create_login_user` writes `role` straight onto the row it finds — so an
/// alta with the owner's address and `role: employee` demotes the owner, and the baja deactivates
/// them. A guard on one door and not the other is a locked door beside an open window.
#[tokio::test]
async fn the_members_door_cannot_demote_or_remove_the_owner_either() {
    let fx = fixture("hub-1429-f").await;

    let request = Request::builder()
        .method("POST")
        .uri("/api/members")
        .header("content-type", "application/json")
        .header("x-hub-session", &fx.admin_session)
        .body(Body::from(
            json!({ "email": "ioan@example.com", "role": "employee" }).to_string(),
        ))
        .unwrap();
    let response = fx.router.clone().oneshot(request).await.unwrap();
    assert_eq!(response.status(), StatusCode::FORBIDDEN);
    assert_eq!(
        body_json(response).await["error"]["code"],
        "hub.users.owner_row"
    );
    assert_eq!(row(&fx, &fx.owner_id).await["role"], "admin");

    let request = Request::builder()
        .method("DELETE")
        .uri("/api/members/ioan@example.com")
        .header("x-hub-session", &fx.admin_session)
        .body(Body::empty())
        .unwrap();
    let response = fx.router.clone().oneshot(request).await.unwrap();
    assert_eq!(response.status(), StatusCode::FORBIDDEN);
    assert_eq!(row(&fx, &fx.owner_id).await["is_active"], true);

    // …and the door still works for everybody else.
    let request = Request::builder()
        .method("DELETE")
        .uri("/api/members/luis@example.com")
        .header("x-hub-session", &fx.admin_session)
        .body(Body::empty())
        .unwrap();
    let response = fx.router.clone().oneshot(request).await.unwrap();
    assert_ne!(
        response.status(),
        StatusCode::FORBIDDEN,
        "the guard names one row, not the screen"
    );
    assert_eq!(row(&fx, &fx.employee_id).await["is_active"], false);
}

/// The other half, and the one pm#167 is about: **the owner rotates their own PIN.** The SaaS is
/// unreachable in this fixture, so this also fixes the second defect — a PIN is not something the
/// SaaS knows about, so nothing is asked of it and nothing can refuse it.
#[tokio::test]
async fn the_owner_rotates_their_own_pin_without_asking_the_saas() {
    let fx = fixture("hub-1429-b").await;

    let (status, body) = put(
        &fx,
        &fx.owner_id,
        &fx.owner_session,
        json!({ "pin": "4271" }),
    )
    .await;
    assert_eq!(status, StatusCode::OK, "{body}");
    assert_eq!(body["ok"], true);
    assert_eq!(row(&fx, &fx.owner_id).await["has_pin"], true);
}

/// **The write order** (hub#1429, second defect): what the SaaS administers — the role of the
/// membership — is asked FIRST. A refusal leaves the local row exactly as it was, so the error the
/// screen paints is true.
#[tokio::test]
async fn a_refused_role_change_leaves_the_local_row_untouched() {
    let fx = fixture("hub-1429-c").await;

    let (status, body) = put(
        &fx,
        &fx.employee_id,
        &fx.admin_session,
        json!({ "role": "manager" }),
    )
    .await;
    assert_eq!(
        status,
        StatusCode::BAD_GATEWAY,
        "the SaaS is unreachable, so the change cannot be honoured: {body}"
    );
    assert_eq!(body["error"]["code"], "cloud_unreachable");
    assert_eq!(
        row(&fx, &fx.employee_id).await["role"],
        "employee",
        "the local row must not carry a change the SaaS refused"
    );
}

/// …and the edits the SaaS knows nothing about are not held hostage by it: renaming somebody or
/// giving them a PIN keeps working with the cloud down, which is the whole point of a POS.
#[tokio::test]
async fn an_edit_the_saas_knows_nothing_about_does_not_call_it() {
    let fx = fixture("hub-1429-d").await;

    let (status, body) = put(
        &fx,
        &fx.employee_id,
        &fx.admin_session,
        json!({ "name": "Luis Prat Roca", "pin": "5150" }),
    )
    .await;
    assert_eq!(status, StatusCode::OK, "{body}");
    let luis = row(&fx, &fx.employee_id).await;
    assert_eq!(luis["name"], "Luis Prat Roca");
    assert_eq!(luis["has_pin"], true);
}

/// A **baja** is the exception, and deliberately so: closing a door must never depend on the cloud
/// being up. The local deactivation is applied first and the honest `502` still says the cloud half
/// failed — which is what the screen already tells the administrator ("the user is saved here").
#[tokio::test]
async fn a_baja_closes_the_local_door_even_with_the_cloud_down() {
    let fx = fixture("hub-1429-e").await;

    let request = Request::builder()
        .method("DELETE")
        .uri(format!("/api/hub/users/{}", fx.employee_id))
        .header("x-hub-session", &fx.admin_session)
        .body(Body::empty())
        .unwrap();
    let response = fx.router.clone().oneshot(request).await.unwrap();
    assert_eq!(response.status(), StatusCode::BAD_GATEWAY);
    assert_eq!(
        row(&fx, &fx.employee_id).await["is_active"],
        false,
        "an unreachable SaaS may not keep a revoked person inside the hub"
    );
}
