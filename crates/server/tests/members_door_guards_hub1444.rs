//! **The other door's missing handrails** (hub#1444) — `POST`/`DELETE /api/members`.
//!
//! `/api/hub/users` (Personal) runs every write through `guard_decision`; `/api/members` — the door
//! ADR-0157 §7 gives the admin panel, where a person is named by EMAIL instead of by id — went
//! straight to `identity::{create_login_user, deactivate_login_user}`. hub#1429 closed the half
//! about the OWNER's row on both doors; these two were still open on this one:
//!
//!  1. **`self_deactivation`** — an administrator could sign themselves out of their own hub with
//!     `DELETE /api/members/{their own email}`.
//!  2. **`last_admin`** — and, worse, could DEMOTE themselves with `POST /api/members {email,
//!     role: employee}`: `create_login_user` writes the role straight onto the row it finds by
//!     email, so the hub was left with nobody who could install a module, touch a setting or bring
//!     anybody back. `self_deactivation` does not catch this one — a demotion is not a baja.
//!
//! The proof has to go through the HTTP door: a rule that is only exercised on `guard_decision`
//! proves the function, not that this handler calls it. Same reason as `owner_row_door_hub1429.rs`.
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
    /// The only active administrator of this hub, and the one who makes every request below.
    admin_session: String,
    admin_email: String,
    /// Who reads the census back. It is a DIFFERENT administrator whenever there is one, because a
    /// legitimate self-demotion leaves the actor without the rank `GET /api/members` asks for — and
    /// reading the result of the change through a session the change just downgraded would come
    /// back `401` and prove nothing.
    reader_session: String,
}

/// A hub that never booted with `HUB_OWNER_EMAIL`, so **no row is marked as the account owner's**
/// and hub#1429's guard cannot be what answers: what these tests exercise is the pair of handrails
/// that were missing on top of it. `second_admin` decides whether the administrator below is the
/// last one — the whole point of `last_admin` is that the same gesture is fine when they are not.
async fn fixture(hub_id: &str, second_admin: bool) -> Fixture {
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), hub_id);
    rt.ensure_system_tables().await.unwrap();

    let admin = rt
        .create_hub_user(
            &NewHubUser {
                name: "Ana Soto".into(),
                email: "ana@example.com".into(),
                role: "admin".into(),
                ..NewHubUser::default()
            },
            0,
        )
        .await
        .unwrap();
    rt.create_hub_user(
        &NewHubUser {
            name: "Luis Prat".into(),
            email: "luis@example.com".into(),
            role: "employee".into(),
            ..NewHubUser::default()
        },
        0,
    )
    .await
    .unwrap();
    let second = if second_admin {
        Some(
            rt.create_hub_user(
                &NewHubUser {
                    name: "Bea Roig".into(),
                    email: "bea@example.com".into(),
                    role: "admin".into(),
                    ..NewHubUser::default()
                },
                0,
            )
            .await
            .unwrap(),
        )
    } else {
        None
    };
    let admin_session = rt.create_session(&admin, 3600, None).await.unwrap();
    let reader_session = match &second {
        Some(id) => rt.create_session(id, 3600, None).await.unwrap(),
        None => admin_session.clone(),
    };

    let media = std::env::temp_dir().join(format!("erplora-{hub_id}-{}", std::process::id()));
    let cfg = HubConfig {
        demo: false,
        hub_id: hub_id.into(),
        // Unreachable on purpose: a request that gets as far as the SaaS comes back
        // `424 cloud_unreachable` (hub#1763), which is how these tests tell "the guard let it
        // through and the local write happened" from "the guard refused before writing anything".
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
        admin_session,
        admin_email: "ana@example.com".into(),
        reader_session,
    }
}

async fn body_json(response: axum::response::Response) -> Value {
    let bytes = response.into_body().collect().await.unwrap().to_bytes();
    serde_json::from_slice(&bytes).unwrap()
}

async fn add_member(fx: &Fixture, email: &str, role: &str) -> (StatusCode, Value) {
    let request = Request::builder()
        .method("POST")
        .uri("/api/members")
        .header("content-type", "application/json")
        .header("x-hub-session", &fx.admin_session)
        .body(Body::from(
            json!({ "email": email, "role": role }).to_string(),
        ))
        .unwrap();
    let response = fx.router.clone().oneshot(request).await.unwrap();
    let status = response.status();
    (status, body_json(response).await)
}

async fn remove_member(fx: &Fixture, email: &str) -> (StatusCode, Value) {
    let request = Request::builder()
        .method("DELETE")
        .uri(format!("/api/members/{email}"))
        .header("x-hub-session", &fx.admin_session)
        .body(Body::empty())
        .unwrap();
    let response = fx.router.clone().oneshot(request).await.unwrap();
    let status = response.status();
    (status, body_json(response).await)
}

/// The census as `/api/members` itself reports it — the same door, so a change that did not persist
/// cannot hide behind a different reader.
async fn member(fx: &Fixture, email: &str) -> Value {
    let request = Request::builder()
        .uri("/api/members")
        .header("x-hub-session", &fx.reader_session)
        .body(Body::empty())
        .unwrap();
    let listed = body_json(fx.router.clone().oneshot(request).await.unwrap()).await;
    listed["members"]
        .as_array()
        .expect("the members door lists the census")
        .iter()
        .find(|u| u["email"] == email)
        .cloned()
        .unwrap_or_else(|| panic!("{email} is in the census"))
}

/// **Nobody signs themselves out of their own hub.** The baja by email took no decision at all, so
/// the administrator making the request could deactivate their own row and lose the session that
/// was making it.
#[tokio::test]
async fn hub1444_an_admin_cannot_deactivate_themselves_through_the_members_door() {
    let fx = fixture("hub-1444-a", true).await;

    let (status, body) = remove_member(&fx, &fx.admin_email.clone()).await;
    assert_eq!(status, StatusCode::BAD_REQUEST, "{body}");
    assert_eq!(body["error"]["code"], "self_deactivation");
    assert_eq!(
        member(&fx, "ana@example.com").await["is_active"],
        true,
        "a refused baja writes nothing"
    );
}

/// **And the hub is never left without an administrator.** This is the one `self_deactivation` does
/// NOT cover: a demotion is not a baja, and `create_login_user` writes the role straight onto the
/// row it finds by email — so the last admin could hand themselves `employee` and lock everybody
/// out, this door being the only one that never asked.
#[tokio::test]
async fn hub1444_the_last_admin_cannot_demote_themselves_through_the_members_door() {
    let fx = fixture("hub-1444-b", false).await;

    let (status, body) = add_member(&fx, &fx.admin_email.clone(), "employee").await;
    assert_eq!(status, StatusCode::BAD_REQUEST, "{body}");
    assert_eq!(body["error"]["code"], "last_admin");
    assert_eq!(
        member(&fx, "ana@example.com").await["role"],
        "admin",
        "a refused demotion writes nothing"
    );
}

/// The same gesture with **another administrator standing**: allowed. The rule is `last_admin`, not
/// "no self-demotion" — a guard that also blocks the legitimate case is a bug of its own, and this
/// is the control that says the two tests above are not passing by simply closing the door.
#[tokio::test]
async fn hub1444_demoting_yourself_is_fine_while_another_admin_is_active() {
    let fx = fixture("hub-1444-c", true).await;

    let (status, body) = add_member(&fx, &fx.admin_email.clone(), "employee").await;
    assert_eq!(
        status,
        StatusCode::FAILED_DEPENDENCY,
        "the guard let it through and only the (unreachable) SaaS failed: {body}"
    );
    assert_eq!(body["error"]["code"], "cloud_unreachable");
    assert_eq!(
        member(&fx, "ana@example.com").await["role"],
        "employee",
        "the local write happened"
    );
}

/// And the ordinary traffic of this door still goes through: an employee's baja, and an alta of
/// somebody who is not in the census yet (there is no row to decide about — only the rank rule of
/// hub#356 applies, and an admin may hand out `employee`).
#[tokio::test]
async fn hub1444_the_ordinary_alta_and_baja_still_go_through() {
    let fx = fixture("hub-1444-d", true).await;

    let (status, body) = remove_member(&fx, "luis@example.com").await;
    assert_eq!(status, StatusCode::FAILED_DEPENDENCY, "{body}");
    assert_eq!(body["error"]["code"], "cloud_unreachable");
    assert_eq!(member(&fx, "luis@example.com").await["is_active"], false);

    let (status, body) = add_member(&fx, "nueva@example.com", "employee").await;
    assert_eq!(status, StatusCode::FAILED_DEPENDENCY, "{body}");
    assert_eq!(body["error"]["code"], "cloud_unreachable");
    assert_eq!(member(&fx, "nueva@example.com").await["role"], "employee");
}
