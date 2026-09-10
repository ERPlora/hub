//! **`POST /api/auth/handoff`** — the door that hands the till's session to the browser (pm#196,
//! hub#1400).
//!
//! The till links out to erplora.com for everything it deliberately does not sell: the plan, the
//! invoices, the module checkout (ADR-0114 §4, ADR-0251, ADR-0255). Until now that link carried
//! **nothing**: the address went to the system browser as it stood, and inside the installed app
//! that browser is a different cookie jar from the webview — so the owner typed their password and
//! their second factor again, right before paying. This endpoint is the symmetric half of
//! `AuthExchangeCode` (ADR-0157 §8): the SaaS→Hub direction already mints a one-time courier
//! (`hub_handoff.py`), and this is Hub→SaaS.
//!
//! **Why the runtime is in the middle at all**, when the browser already holds the user's JWT and
//! could ask the SaaS itself: because the SaaS cannot see what this endpoint is here to check.
//! Whether the person standing at the till proved who they are with **their email and password**
//! or with a **four-digit PIN** is written in `hub_session.credential_kind` (hub#658) and nowhere
//! else. Ioan's lock (hub#1400, 2026-09-01) is that only the first may be handed a browser
//! session:
//!
//!   - a PIN is a credential of the SHIFT — short, memorable and typed in front of people
//!     (ADR-0226 says the local user's credential is never administrative);
//!   - turning it into the key to the billing panel would hand the business's money to whoever
//!     opens the register.
//!
//! So `hub.administer` (ADR-0248) is necessary and **not sufficient**: it is a permission of the
//! ROLE, and the question here is about the METHOD of authentication. Both are checked, and the
//! third one closes the gap the other two leave open — the JWT presented must name the very person
//! the session names. A till that has not been logged out keeps the previous user's tokens in
//! `localStorage`, so without that check a cashier's PIN session could spend the owner's JWT.
//!
//! Every refusal is asserted on its CODE, never on its prose (ADR-0055).
use axum::body::Body;
use axum::http::{HeaderMap, Request, StatusCode};
use axum::routing::post;
use axum::{Json as AxumJson, Router};
use erplora_db::testutil::TestDb;
use erplora_runtime::identity::Credential;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use http_body_util::BodyExt;
use jsonwebtoken::{encode, Algorithm, EncodingKey, Header};
use openssl::pkey::PKey;
use openssl::rsa::Rsa;
use serde_json::{json, Value};
use std::sync::LazyLock;
use tower::ServiceExt; // oneshot

type Response = axum::response::Response;

const HUB_ID: &str = "hub-handoff";

/// A throw-away RSA pair: the "SaaS" signs the user JWT with the private half and the hub
/// verifies it with the public one.
///
/// It is generated here rather than written down on purpose — no key material lives in this
/// repo, the same reason the machine-identity tests mint a disposable CA (hub#1457). Generated
/// once per test binary because RSA-2048 keygen is the slowest thing in this file.
static JWT_PAIR: LazyLock<(String, String)> = LazyLock::new(|| {
    let pair = PKey::from_rsa(Rsa::generate(2048).unwrap()).unwrap();
    (
        String::from_utf8(pair.private_key_to_pem_pkcs8().unwrap()).unwrap(),
        String::from_utf8(pair.public_key_to_pem().unwrap()).unwrap(),
    )
});

async fn body_json(response: Response) -> Value {
    let bytes = response.into_body().collect().await.unwrap().to_bytes();
    serde_json::from_slice(&bytes).unwrap_or(Value::Null)
}

/// A signed user JWT for `cloud_user_id`, present in this hub (ADR-0157 §5 presence claim).
fn sign_user_jwt(cloud_user_id: i64) -> String {
    let claims = json!({
        "user_id": cloud_user_id,
        "email": "jefa@bar.com",
        "token_type": "access",
        "exp": 9_999_999_999_i64,
        "organizations": [{"id": "org-A", "role": "admin"}],
        "hubs": [{"id": HUB_ID, "org": "org-A", "role": "admin"}],
    });
    let key = EncodingKey::from_rsa_pem(JWT_PAIR.0.as_bytes()).unwrap();
    encode(&Header::new(Algorithm::RS256), &claims, &key).unwrap()
}

/// A hub whose only user is Ana. Her LOCAL role is given by the caller, because the two halves of
/// the lock — "may administer" and "proved it with a password" — have to be varied independently.
///
/// `cloud_base_url` points wherever the test wants the SaaS to be; the ones that never reach it
/// pass an address nothing listens on, so a refusal that silently called out would still fail.
async fn fixture(role: &str, cloud_base_url: String) -> (axum::Router, Runtime, String) {
    let test_db = TestDb::new().await;
    let rt = Runtime::with_hub_id(Box::new(test_db.adapter().await), HUB_ID);
    rt.ensure_system_tables().await.unwrap();
    let ana = rt.create_user("Ana", "4729", role, Some("77")).await.unwrap();

    let temp = std::env::temp_dir().join(format!("erplora-handoff-{}", std::process::id()));
    let cfg = HubConfig {
        demo: false,
        hub_id: HUB_ID.into(),
        cloud_base_url,
        module_cache: temp.join("modules-cache"),
        auth_mode: AuthMode::Session,
        jwt_public_key: Some(JWT_PAIR.1.clone()),
        cloud_api_token: Some("machine-secret".into()),
        device_trust_enforce: false,
        media_dir: temp,
        sector: None,
        dev_mode: false,
        dev_modules_dir: None,
        module_trusted_keys: Vec::new(),
    };
    let served = Runtime::with_hub_id(Box::new(test_db.adapter().await), HUB_ID);
    served.ensure_system_tables().await.unwrap();
    (app(AppState::with_config(served, cfg)), rt, ana)
}

/// The address of a SaaS that mints `code-abc` for anybody who asks with a user JWT, and refuses
/// anything else. Returns the base URL and the join handle so the test can stop it.
///
/// It checks the credential on purpose: "the runtime asked with the user's own JWT, not with the
/// machine token" is the security property, and a mock that accepted both would not see it. The
/// machine token must never be able to mint a browser session for a member — that would make a
/// leaked deployment secret a way into somebody's billing.
fn mock_saas() -> (String, tokio::task::JoinHandle<()>) {
    let listener = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
    listener.set_nonblocking(true).unwrap();
    let address = listener.local_addr().unwrap();
    let router = Router::new().route(
        "/api/v1/auth/handoff/issue/",
        post(|headers: HeaderMap, _body: AxumJson<Value>| async move {
            let bearer = headers
                .get("authorization")
                .and_then(|v| v.to_str().ok())
                .unwrap_or_default()
                .to_string();
            if !bearer.starts_with("Bearer ") || headers.contains_key("x-hub-token") {
                return (
                    StatusCode::UNAUTHORIZED,
                    AxumJson(json!({ "detail": "the hub asked with the wrong credential" })),
                );
            }
            if headers.get("x-hub-id").and_then(|v| v.to_str().ok()) != Some(HUB_ID) {
                return (
                    StatusCode::BAD_REQUEST,
                    AxumJson(json!({ "detail": "no hub named" })),
                );
            }
            (
                StatusCode::OK,
                AxumJson(json!({ "code": "code-abc", "expires_in": 120 })),
            )
        }),
    );
    let handle = tokio::spawn(async move {
        let listener = tokio::net::TcpListener::from_std(listener).unwrap();
        axum::serve(listener, router).await.unwrap();
    });
    (format!("http://{address}"), handle)
}

/// A SaaS that is there but says no — the hub must not invent a URL out of a refusal.
fn mock_saas_refusing() -> (String, tokio::task::JoinHandle<()>) {
    let listener = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
    listener.set_nonblocking(true).unwrap();
    let address = listener.local_addr().unwrap();
    let router = Router::new().route(
        "/api/v1/auth/handoff/issue/",
        post(|| async {
            (
                StatusCode::FORBIDDEN,
                AxumJson(json!({ "detail": "not a member" })),
            )
        }),
    );
    let handle = tokio::spawn(async move {
        let listener = tokio::net::TcpListener::from_std(listener).unwrap();
        axum::serve(listener, router).await.unwrap();
    });
    (format!("http://{address}"), handle)
}

/// Somewhere nothing listens: a refusal that quietly called the SaaS anyway would hang or 502
/// instead of answering its own code, and the test would see it.
fn nowhere() -> String {
    "http://127.0.0.1:1".to_string()
}

fn ask(session: Option<&str>, jwt: Option<&str>, body: Value) -> Request<Body> {
    let mut builder = Request::builder()
        .method("POST")
        .uri("/api/auth/handoff")
        .header("content-type", "application/json");
    if let Some(session) = session {
        builder = builder.header("x-hub-session", session);
    }
    if let Some(jwt) = jwt {
        builder = builder.header("authorization", format!("Bearer {jwt}"));
    }
    builder.body(Body::from(body.to_string())).unwrap()
}

// ── The lock: how you proved who you are decides whether you may be handed a session ──────────

#[tokio::test]
async fn a_pin_session_is_refused_even_when_its_role_administers_the_hub() {
    let (router, rt, ana) = fixture("admin", nowhere()).await;
    // Ana is an admin: `hub.administer` is hers. What she did NOT do is type her password.
    assert!(rt
        .session_permissions("admin")
        .contains(erplora_runtime::hub_users::ADMINISTER_PERMISSION));
    let session = rt
        .create_session_with_credential(&ana, 3600, Some("till-1"), &Credential::pin())
        .await
        .unwrap();

    let response = router
        .oneshot(ask(Some(&session), Some(&sign_user_jwt(77)), json!({})))
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::FORBIDDEN);
    assert_eq!(
        body_json(response).await["code"],
        json!("handoff_requires_cloud_login")
    );
}

#[tokio::test]
async fn a_badge_session_is_refused_for_the_same_reason() {
    let (router, rt, ana) = fixture("owner", nowhere()).await;
    let session = rt
        .create_session_with_credential(&ana, 3600, Some("till-1"), &Credential::badge("3"))
        .await
        .unwrap();

    let response = router
        .oneshot(ask(Some(&session), Some(&sign_user_jwt(77)), json!({})))
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::FORBIDDEN);
    assert_eq!(
        body_json(response).await["code"],
        json!("handoff_requires_cloud_login")
    );
}

#[tokio::test]
async fn a_session_that_did_not_say_how_it_was_opened_is_refused() {
    // `Credential::unknown()` is what the internal paths write. "Not stated" and "it was a
    // password" are different answers, and this door reads the second one only.
    let (router, rt, ana) = fixture("owner", nowhere()).await;
    let session = rt
        .create_session_with_credential(&ana, 3600, None, &Credential::unknown())
        .await
        .unwrap();

    let response = router
        .oneshot(ask(Some(&session), Some(&sign_user_jwt(77)), json!({})))
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::FORBIDDEN);
    assert_eq!(
        body_json(response).await["code"],
        json!("handoff_requires_cloud_login")
    );
}

#[tokio::test]
async fn a_cloud_session_without_the_permission_is_refused() {
    let (router, rt, ana) = fixture("employee", nowhere()).await;
    let session = rt
        .create_session_with_credential(&ana, 3600, Some("till-1"), &Credential::cloud())
        .await
        .unwrap();

    let response = router
        .oneshot(ask(Some(&session), Some(&sign_user_jwt(77)), json!({})))
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::FORBIDDEN);
    assert_eq!(
        body_json(response).await["code"],
        json!("handoff_requires_administer")
    );
}

#[tokio::test]
async fn a_jwt_that_names_somebody_else_is_refused() {
    // The till was not logged out: the owner's tokens are still in `localStorage` while the
    // cashier's session is the live one. The session and the token have to name the same person.
    let (router, rt, ana) = fixture("owner", nowhere()).await;
    let session = rt
        .create_session_with_credential(&ana, 3600, Some("till-1"), &Credential::cloud())
        .await
        .unwrap();

    let response = router
        .oneshot(ask(Some(&session), Some(&sign_user_jwt(99)), json!({})))
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::FORBIDDEN);
    assert_eq!(
        body_json(response).await["code"],
        json!("handoff_identity_mismatch")
    );
}

#[tokio::test]
async fn without_a_user_token_there_is_nothing_to_hand_over() {
    let (router, rt, ana) = fixture("owner", nowhere()).await;
    let session = rt
        .create_session_with_credential(&ana, 3600, Some("till-1"), &Credential::cloud())
        .await
        .unwrap();

    let response = router
        .oneshot(ask(Some(&session), None, json!({})))
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
    assert_eq!(
        body_json(response).await["code"],
        json!("handoff_user_token_required")
    );
}

#[tokio::test]
async fn an_unsigned_in_caller_is_refused() {
    let (router, _rt, _ana) = fixture("owner", nowhere()).await;

    let response = router
        .oneshot(ask(None, Some(&sign_user_jwt(77)), json!({})))
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
}

// ── The trip itself ───────────────────────────────────────────────────────────────────────────

#[tokio::test]
async fn a_password_session_that_administers_gets_a_one_time_address_for_the_browser() {
    let (cloud, serving) = mock_saas();
    let (router, rt, ana) = fixture("admin", cloud.clone()).await;
    let session = rt
        .create_session_with_credential(&ana, 3600, Some("till-1"), &Credential::cloud())
        .await
        .unwrap();

    let response = router
        .oneshot(ask(
            Some(&session),
            Some(&sign_user_jwt(77)),
            json!({ "next": "/dashboard/?view=advanced&hub=hub-handoff" }),
        ))
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::OK);
    let body = body_json(response).await;
    let url = body["url"].as_str().unwrap_or_default().to_string();
    // The address is built from the runtime's OWN idea of where the SaaS is, never from anything
    // the page said: a page that could choose the host would be choosing where the code is spent.
    assert!(
        url.starts_with(&format!("{cloud}/auth/handoff/code-abc/")),
        "expected the one-time door of the configured Cloud, got {url}"
    );
    assert!(
        url.contains("next=%2Fdashboard%2F%3Fview%3Dadvanced%26hub%3Dhub-handoff"),
        "expected the destination to travel escaped, got {url}"
    );
    // The one-time code is the whole credential: nothing else may ride along.
    assert!(
        !url.contains("Bearer") && !url.contains("machine-secret"),
        "no other credential may appear in an address that goes to a browser: {url}"
    );
    serving.abort();
}

#[tokio::test]
async fn the_destination_defaults_to_the_panel_when_the_caller_names_none() {
    let (cloud, serving) = mock_saas();
    let (router, rt, ana) = fixture("owner", cloud.clone()).await;
    let session = rt
        .create_session_with_credential(&ana, 3600, Some("till-1"), &Credential::cloud())
        .await
        .unwrap();

    let response = router
        .oneshot(ask(Some(&session), Some(&sign_user_jwt(77)), json!({})))
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::OK);
    let url = body_json(response).await["url"]
        .as_str()
        .unwrap_or_default()
        .to_string();
    assert!(
        url.contains("next=%2Fdashboard%2F"),
        "expected the dashboard as the default destination, got {url}"
    );
    serving.abort();
}

#[tokio::test]
async fn a_destination_that_leaves_the_saas_is_refused_before_a_code_is_minted() {
    // The `next` reaches the SaaS, which has its own allow-list — but a hub that forwards an
    // absolute address is a hub that would happily point a freshly-opened session at somebody
    // else's site. It is refused HERE, so the code is never spent on the attempt.
    let (router, rt, ana) = fixture("owner", nowhere()).await;
    let session = rt
        .create_session_with_credential(&ana, 3600, Some("till-1"), &Credential::cloud())
        .await
        .unwrap();

    for hostile in [
        "https://evil.example/steal",
        "//evil.example/steal",
        "http://erplora.com.evil.example/",
        "/\\evil.example",
    ] {
        let response = router
            .clone()
            .oneshot(ask(
                Some(&session),
                Some(&sign_user_jwt(77)),
                json!({ "next": hostile }),
            ))
            .await
            .unwrap();

        assert_eq!(
            response.status(),
            StatusCode::BAD_REQUEST,
            "«{hostile}» should not be a destination this hub forwards"
        );
        assert_eq!(
            body_json(response).await["code"],
            json!("handoff_destination_not_allowed"),
            "«{hostile}»"
        );
    }
}

#[tokio::test]
async fn a_refusal_from_the_saas_is_not_turned_into_an_address() {
    let (cloud, serving) = mock_saas_refusing();
    let (router, rt, ana) = fixture("owner", cloud).await;
    let session = rt
        .create_session_with_credential(&ana, 3600, Some("till-1"), &Credential::cloud())
        .await
        .unwrap();

    let response = router
        .oneshot(ask(Some(&session), Some(&sign_user_jwt(77)), json!({})))
        .await
        .unwrap();

    // hub#1763: `424`, no `502`. The edge replaces the body of a `5xx` with its own page, and the
    // `handoff_unavailable` the next line demands would never reach the browser.
    assert_eq!(response.status(), StatusCode::FAILED_DEPENDENCY);
    let body = body_json(response).await;
    assert_eq!(body["code"], json!("handoff_unavailable"));
    assert!(body.get("url").is_none(), "a refusal is not a door");
    serving.abort();
}

#[tokio::test]
async fn a_cloud_that_cannot_be_reached_says_so_instead_of_failing_silently() {
    let (router, rt, ana) = fixture("owner", nowhere()).await;
    let session = rt
        .create_session_with_credential(&ana, 3600, Some("till-1"), &Credential::cloud())
        .await
        .unwrap();

    let response = router
        .oneshot(ask(Some(&session), Some(&sign_user_jwt(77)), json!({})))
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::FAILED_DEPENDENCY); // hub#1763
    assert_eq!(body_json(response).await["code"], json!("handoff_unavailable"));
}

// ── The own-account door: your own account is not somebody else's task (hub#1539) ──────────────
//
// The three checks above were written for the doors this app links to for MANAGEMENT — the plan,
// the invoices, the fiscal representation grant. «Mi perfil» links to a fourth one that is not
// management at all: the person's own account at erplora.com, where they change their password,
// their email and their second factor. It was left out of pm#196 on purpose, because it needed
// this decision first — and the decision is that `hub.administer` has no business here:
//
//   - What the lock protects is that a **shift PIN** never carries off a browser session. That is
//     checks (1) `credential_kind == cloud` and (3) the JWT names the session's own person, and
//     both stay exactly as they were for every destination.
//   - `hub.administer` answers a different question — «is this task yours?» — and for one's own
//     account the answer is yes by definition. An assistant manager who typed her email and her
//     password has every right to change her own password, and today the pass is denied to her.
//   - It grants nothing: the pass mints the browser session of the very person standing there,
//     which is precisely what she would get by typing that same password into the browser. So
//     refusing it does not withhold authority, it only withholds the typing.
//
// **What the destination does NOT do is confine the browser** — and it must not be read as if it
// did. The one-time code the SaaS mints (`/api/v1/auth/handoff/issue/`) opens a full session; the
// `next` only decides the landing page, so whoever lands on the account page can click onwards. Its
// job here is narrower and honest: it scopes WHERE THIS HUB RELAXES ITS OWN CHECK, so that
// hub#1400's lock keeps applying, untouched, to every management destination.
//
// Which is why the matching has to be exact rather than a prefix — see the address that only
// *looks* like the account page below.

/// The account page of the SaaS, which is what «Mi perfil» links to.
const OWN_ACCOUNT: &str = "/dashboard/profile/";

#[tokio::test]
async fn a_cloud_session_that_does_not_administer_is_handed_a_pass_for_its_own_account() {
    let (cloud, serving) = mock_saas();
    let (router, rt, ana) = fixture("employee", cloud.clone()).await;
    // The half that matters is missing on purpose: Ana cannot administer this hub.
    assert!(!rt
        .session_permissions("employee")
        .contains(erplora_runtime::hub_users::ADMINISTER_PERMISSION));
    let session = rt
        .create_session_with_credential(&ana, 3600, Some("till-1"), &Credential::cloud())
        .await
        .unwrap();

    let response = router
        .oneshot(ask(
            Some(&session),
            Some(&sign_user_jwt(77)),
            json!({ "next": OWN_ACCOUNT }),
        ))
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::OK);
    let url = body_json(response).await["url"]
        .as_str()
        .unwrap_or_default()
        .to_string();
    assert!(
        url.starts_with(&format!("{cloud}/auth/handoff/code-abc/")),
        "expected the one-time door of the configured Cloud, got {url}"
    );
    assert!(
        url.contains("next=%2Fdashboard%2Fprofile%2F"),
        "expected to land on her own account page, got {url}"
    );
    serving.abort();
}

#[tokio::test]
async fn the_account_page_is_still_the_account_page_when_it_carries_a_marker() {
    // The callers of `saasDoor` hang `utm_source` and friends off the path. A query string does
    // not change which page the browser lands on, so it must not change the answer either.
    let (cloud, serving) = mock_saas();
    let (router, rt, ana) = fixture("employee", cloud).await;
    let session = rt
        .create_session_with_credential(&ana, 3600, Some("till-1"), &Credential::cloud())
        .await
        .unwrap();

    let response = router
        .oneshot(ask(
            Some(&session),
            Some(&sign_user_jwt(77)),
            json!({ "next": "/dashboard/profile/?utm_source=hub" }),
        ))
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::OK);
    serving.abort();
}

#[tokio::test]
async fn the_same_session_is_still_refused_a_pass_for_management() {
    // The negative half of the decision, and the reason this is not simply "drop the permission
    // check": hub#1400's lock on the management doors is untouched.
    let (router, rt, ana) = fixture("employee", nowhere()).await;
    let session = rt
        .create_session_with_credential(&ana, 3600, Some("till-1"), &Credential::cloud())
        .await
        .unwrap();

    let response = router
        .oneshot(ask(
            Some(&session),
            Some(&sign_user_jwt(77)),
            json!({ "next": "/dashboard/?view=advanced" }),
        ))
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::FORBIDDEN);
    assert_eq!(
        body_json(response).await["code"],
        json!("handoff_requires_administer")
    );
}

#[tokio::test]
async fn an_address_that_only_looks_like_the_account_page_opens_nothing() {
    // The classifier is what decides whether a check gets skipped, so it may not be foolable: a
    // prefix match would have taken every one of these for the account page. `..` never survives
    // an exact comparison, which is why traversal is not a separate rule.
    let (router, rt, ana) = fixture("employee", nowhere()).await;
    let session = rt
        .create_session_with_credential(&ana, 3600, Some("till-1"), &Credential::cloud())
        .await
        .unwrap();

    for disguise in [
        "/dashboard/profile/../billing/",
        "/dashboard/profile/../../dashboard/",
        "/dashboard/profilex/",
        "/dashboard/profile-of-somebody-else/",
        "/dashboard/?next=/dashboard/profile/",
        "/dashboard/billing/#/dashboard/profile/",
    ] {
        let response = router
            .clone()
            .oneshot(ask(
                Some(&session),
                Some(&sign_user_jwt(77)),
                json!({ "next": disguise }),
            ))
            .await
            .unwrap();

        assert_eq!(
            response.status(),
            StatusCode::FORBIDDEN,
            "«{disguise}» is not the account page"
        );
        assert_eq!(
            body_json(response).await["code"],
            json!("handoff_requires_administer"),
            "«{disguise}»"
        );
    }
}

#[tokio::test]
async fn a_pin_session_is_refused_its_own_account_too() {
    // The lock this door exists for is untouched by the decision above: what is relaxed is the
    // permission of the ROLE, never the METHOD of authentication. A four-digit code typed in front
    // of people does not carry off a browser session, not even to the account page.
    let (router, rt, ana) = fixture("owner", nowhere()).await;
    let session = rt
        .create_session_with_credential(&ana, 3600, Some("till-1"), &Credential::pin())
        .await
        .unwrap();

    let response = router
        .oneshot(ask(
            Some(&session),
            Some(&sign_user_jwt(77)),
            json!({ "next": OWN_ACCOUNT }),
        ))
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::FORBIDDEN);
    assert_eq!(
        body_json(response).await["code"],
        json!("handoff_requires_cloud_login")
    );
}

#[tokio::test]
async fn the_account_page_is_no_excuse_to_spend_somebody_elses_token() {
    // The till was not logged out and the previous person's JWT is still in `localStorage`. "Their
    // own account" is only true while the session and the token name the same person.
    let (router, rt, ana) = fixture("employee", nowhere()).await;
    let session = rt
        .create_session_with_credential(&ana, 3600, Some("till-1"), &Credential::cloud())
        .await
        .unwrap();

    let response = router
        .oneshot(ask(
            Some(&session),
            Some(&sign_user_jwt(99)),
            json!({ "next": OWN_ACCOUNT }),
        ))
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::FORBIDDEN);
    assert_eq!(
        body_json(response).await["code"],
        json!("handoff_identity_mismatch")
    );
}
