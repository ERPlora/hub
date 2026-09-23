//! **The public door over HTTP** (hub#963) — the one route of this hub that answers a stranger.
//!
//! What these tests pin is the security model, because the door has no session to lean on:
//!
//!  - **The locator is the whole authorisation.** No session, no header, no cookie — and the
//!    command still runs, with the permission its own manifest declares.
//!  - **Minting is not.** Putting a locator on paper hands out that command, so it takes a session
//!    AND the same permission the command asks for.
//!  - **Once.** A second POST issues nothing and shows the first result.
//!  - **The seal holds.** A visitor who posts the fields the counter sealed changes nothing.
//!  - **No oracle.** An unknown locator, a neighbour's locator and a typo are the same answer.
//!  - **It is HTML with nothing inline** — the hub's CSP would drop an inline script silently; the
//!    only script is the optional same-origin one that names countries (sales#335).
//!
//! The fixture module is the same `catalog` one the public-API tests use: this issue is about the
//! door, and using a real installed command (rather than a stub) is what proves the door reaches
//! the dispatcher with a permission the dispatcher accepts.
use std::path::PathBuf;

use axum::body::Body;
use axum::http::{Request, StatusCode};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use http_body_util::BodyExt;
use serde_json::{json, Value};
use tower::ServiceExt;

const HUB_ID: &str = "hub-public-door";

fn fixture() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixture_public_api")
}

fn dev_config() -> HubConfig {
    HubConfig {
        demo: false,
        hub_id: HUB_ID.into(),
        cloud_base_url: "https://erplora.com".into(),
        module_cache: std::env::temp_dir().join("erplora-public-door-cache"),
        auth_mode: AuthMode::Dev,
        jwt_public_key: None,
        cloud_api_token: Some("test-machine-token".into()),
        device_trust_enforce: false,
        media_dir: std::env::temp_dir().join("erplora-public-door-media"),
        sector: None,
        dev_mode: false,
        dev_modules_dir: None,
        module_trusted_keys: Vec::new(),
    }
}

async fn make_app() -> axum::Router {
    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), HUB_ID);
    rt.ensure_system_tables().await.unwrap();
    rt.install_from_dir(&fixture()).await.unwrap();
    app(AppState::with_config(rt, dev_config()))
}

/// The counter minting a locator: a session (Dev mode trusts the headers) with the permission the
/// target command declares.
fn mint_request(permissions: &str, body: Value) -> Request<Body> {
    Request::builder()
        .method("POST")
        .uri("/api/hub/public-claims")
        .header("content-type", "application/json")
        .header("x-hub-id", HUB_ID)
        .header("x-user-id", "cashier-1")
        .header("x-permissions", permissions)
        .body(Body::from(body.to_string()))
        .unwrap()
}

fn ticket_claim(subject: &str) -> Value {
    json!({
        "kind": "invoice_request",
        "subject_id": subject,
        "command": "catalog.item.create",
        "sealed_payload": { "name": "sealed-by-the-counter" },
        "public_fields": ["note"],
    })
}

/// A stranger: no session header of any kind.
fn anonymous_get(uri: &str) -> Request<Body> {
    Request::builder()
        .method("GET")
        .uri(uri)
        .body(Body::empty())
        .unwrap()
}

fn anonymous_post(uri: &str, form: &str) -> Request<Body> {
    Request::builder()
        .method("POST")
        .uri(uri)
        .header("content-type", "application/x-www-form-urlencoded")
        .body(Body::from(form.to_owned()))
        .unwrap()
}

async fn body_text(resp: axum::response::Response) -> String {
    let bytes = resp.into_body().collect().await.unwrap().to_bytes();
    String::from_utf8(bytes.to_vec()).unwrap()
}

async fn body_json(resp: axum::response::Response) -> Value {
    let bytes = resp.into_body().collect().await.unwrap().to_bytes();
    serde_json::from_slice(&bytes).unwrap()
}

async fn mint(app: &axum::Router, subject: &str) -> String {
    let resp = app
        .clone()
        .oneshot(mint_request("*", ticket_claim(subject)))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    let json = body_json(resp).await;
    json["locator"].as_str().unwrap().to_string()
}

/// Un locator del mismo largo y alfabeto que `real` pero **garantizado distinto** — la «errata al
/// teclear» con la que se prueba que la puerta no es un oráculo.
fn a_different_locator(real: &str) -> String {
    // El último carácter se cambia por OTRO del alfabeto, elegido en función del que había: así la
    // sonda difiere siempre, en vez de depender de que el locator no acabase ya en la letra fija.
    // `X` e `Y` valen los dos como sustituto — están en Crockford y `normalize_locator` no los
    // remapea (solo toca `O`→`0` e `I`/`L`→`1`), así que la puerta los ve tal cual se escriben.
    let last = real.chars().last().expect("un locator nunca está vacío");
    let other = if last == 'X' { 'Y' } else { 'X' };
    format!("{}{}", &real[..real.len() - 1], other)
}

/// 🔴 La sonda tiene que diferir **por construcción, no por suerte**.
///
/// Escrita como `<15 primeros> + "X"` falla 1 de cada 32 ejecuciones: la `X` está en el alfabeto
/// Crockford (`0123456789ABCDEFGHJKMNPQRSTVWXYZ`, `public_claim.rs`), así que cuando el locator
/// real ya termina en `X` la «errata» ES el locator real, la puerta responde 200 con toda la razón
/// y el test cae. Enrojeció CI en hub#1008 sin tener nada que ver con aquel cambio, y el mensaje
/// de fallo delató el caso: la sonda impresa era `SM5WF4VB0XG6CBNX`.
#[test]
fn la_sonda_nunca_coincide_con_el_locator_real() {
    // El caso que enrojeció CI: un locator que ya acaba en `X`.
    let acaba_en_x = "SM5WF4VB0XG6CBNX";
    assert_ne!(
        a_different_locator(acaba_en_x),
        acaba_en_x,
        "la errata no puede ser el locator real"
    );
    // Y el caso corriente sigue difiriendo.
    let corriente = "SM5WF4VB0XG6CBNZ";
    assert_ne!(a_different_locator(corriente), corriente);
    // Conserva forma: mismo largo, para que la puerta lo trate como un locator y no como basura.
    assert_eq!(a_different_locator(acaba_en_x).len(), acaba_en_x.len());
}

/// How many rows the fixture command has written, read straight from the database through the
/// module's own query — the door is not asked to report on itself.
async fn items(app: &axum::Router) -> Vec<Value> {
    let resp = app
        .clone()
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/api/query")
                .header("content-type", "application/json")
                .header("x-hub-id", HUB_ID)
                .header("x-user-id", "admin-1")
                .header("x-permissions", "*")
                .body(Body::from(
                    json!({"name": "catalog.items.list", "params": {}}).to_string(),
                ))
                .unwrap(),
        )
        .await
        .unwrap();
    let status = resp.status();
    let raw = body_text(resp).await;
    let json: Value = serde_json::from_str(&raw)
        .unwrap_or_else(|e| panic!("query failed ({status}): {raw} — {e}"));
    // `catalog.items.list` declares a `list` block, so the envelope is the pager's
    // `{rows,total,…}`; a plain query would hand back the array directly.
    json["data"]["rows"]
        .as_array()
        .or_else(|| json["data"].as_array())
        .cloned()
        .unwrap_or_else(|| panic!("unexpected query envelope: {json}"))
}

// ── the door ────────────────────────────────────────────────────────────────────────────────

/// **The point of the issue.** No session anywhere in the request, and the command runs.
#[tokio::test]
async fn a_stranger_with_the_locator_gets_the_form_and_can_redeem_it() {
    let app = make_app().await;
    let locator = mint(&app, "ticket-1").await;

    let page = app
        .clone()
        .oneshot(anonymous_get(&format!("/p/{locator}")))
        .await
        .unwrap();
    assert_eq!(page.status(), StatusCode::OK);
    assert_eq!(
        page.headers()
            .get("content-type")
            .and_then(|v| v.to_str().ok()),
        Some("text/html; charset=utf-8")
    );
    let html = body_text(page).await;
    assert!(html.contains("<form method=\"post\""), "{html}");
    assert!(
        html.contains(&locator),
        "the page echoes the code back: {html}"
    );

    assert!(items(&app).await.is_empty(), "nothing written by looking");

    let done = app
        .clone()
        .oneshot(anonymous_post(
            &format!("/p/{locator}"),
            "customer_tax_id=B12345674&customer_name=ACME+SL",
        ))
        .await
        .unwrap();
    assert_eq!(done.status(), StatusCode::OK);
    let rows = items(&app).await;
    assert_eq!(rows.len(), 1, "the command ran: {rows:?}");
    assert_eq!(rows[0]["name"], json!("sealed-by-the-counter"));
}

/// **Once.** The second POST — a double tap, a refresh, the back button — issues nothing.
#[tokio::test]
async fn redeeming_twice_issues_exactly_one_document() {
    let app = make_app().await;
    let locator = mint(&app, "ticket-2").await;
    let form = "customer_tax_id=B12345674&customer_name=ACME+SL";

    let first = app
        .clone()
        .oneshot(anonymous_post(&format!("/p/{locator}"), form))
        .await
        .unwrap();
    assert_eq!(first.status(), StatusCode::OK);
    let second = app
        .clone()
        .oneshot(anonymous_post(&format!("/p/{locator}"), form))
        .await
        .unwrap();
    assert_eq!(
        second.status(),
        StatusCode::OK,
        "the customer is shown their invoice, not an error"
    );
    assert_eq!(items(&app).await.len(), 1, "and only one was ever issued");
}

/// **The seal.** The visitor posts the field the counter sealed; the counter's value is what runs.
#[tokio::test]
async fn what_the_counter_sealed_survives_what_the_visitor_posts() {
    let app = make_app().await;
    let locator = mint(&app, "ticket-3").await;
    app.clone()
        .oneshot(anonymous_post(
            &format!("/p/{locator}"),
            "name=chosen-by-the-visitor&customer_tax_id=B1&customer_name=X",
        ))
        .await
        .unwrap();
    let rows = items(&app).await;
    assert_eq!(rows.len(), 1);
    assert_eq!(
        rows[0]["name"],
        json!("sealed-by-the-counter"),
        "`name` was never a public field: the visitor's copy is dropped"
    );
}

/// **The other half of the seal, and the control that proves the first one is not passing by
/// accident.** A key the claim DOES declare public reaches the command with the visitor's value.
///
/// Without this, `what_the_counter_sealed_survives_what_the_visitor_posts` would still be green on
/// a door that dropped the whole form on the floor — which is exactly the shape of a check that
/// happens to be right.
#[tokio::test]
async fn a_declared_public_field_reaches_the_command_with_what_the_visitor_typed() {
    let app = make_app().await;
    let resp = app
        .clone()
        .oneshot(mint_request(
            "*",
            json!({
                "kind": "invoice_request",
                "subject_id": "ticket-open",
                "command": "catalog.item.create",
                "sealed_payload": {},
                "public_fields": ["name"],
            }),
        ))
        .await
        .unwrap();
    let locator = body_json(resp).await["locator"]
        .as_str()
        .unwrap()
        .to_string();

    app.clone()
        .oneshot(anonymous_post(
            &format!("/p/{locator}"),
            "name=typed-by-the-visitor",
        ))
        .await
        .unwrap();
    let rows = items(&app).await;
    assert_eq!(rows.len(), 1, "the command ran: {rows:?}");
    assert_eq!(rows[0]["name"], json!("typed-by-the-visitor"));
}

/// **No oracle.** An unknown locator, one belonging to another hub and a typo all answer the same:
/// a 404 page that says nothing about which locators exist.
#[tokio::test]
async fn an_unknown_locator_is_a_plain_404_with_nothing_to_learn_from() {
    let app = make_app().await;
    let real = mint(&app, "ticket-4").await;
    for probe in ["ZZZZZZZZZZZZZZZZ", "short", &a_different_locator(&real)] {
        let resp = app
            .clone()
            .oneshot(anonymous_get(&format!("/p/{probe}")))
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::NOT_FOUND, "{probe}");
        let html = body_text(resp).await;
        assert!(!html.contains("<form"), "no form for a code we do not know");
    }
}

/// **The page is HTML with no script.** Under `script-src 'self'` an inline one is dropped in
/// silence, so a page that needed one would pass review and fail on the customer's phone.
#[tokio::test]
async fn the_page_never_carries_a_script() {
    let app = make_app().await;
    let locator = mint(&app, "ticket-5").await;
    let html = body_text(
        app.clone()
            .oneshot(anonymous_get(&format!("/p/{locator}")))
            .await
            .unwrap(),
    )
    .await;
    assert!(!html.contains("<script"), "{html}");
    assert!(html.contains("<style"), "but it is styled: {html}");
}

/// sales#335 — a ticket whose claim lets the customer say where they are from shows the country
/// and document pickers, loads the one same-origin script that names the countries, and that
/// script answers a stranger on a hub in the REAL session mode (the diner has no session).
#[tokio::test]
async fn a_foreign_customer_can_say_their_country_and_document() {
    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), "hub-public-door-foreign");
    rt.ensure_system_tables().await.unwrap();
    rt.install_from_dir(&fixture()).await.unwrap();
    let admin_id = rt
        .create_user("Admin", "1111", "admin", None)
        .await
        .unwrap();
    let admin = rt.create_session(&admin_id, 3600, None).await.unwrap();
    let mut cfg = dev_config();
    cfg.auth_mode = AuthMode::Session;
    cfg.hub_id = "hub-public-door-foreign".into();
    let app = app(AppState::with_config(rt, cfg));

    let mut claim = ticket_claim("ticket-foreign");
    claim["public_fields"] = json!([
        "customer_tax_id",
        "customer_name",
        "customer_address",
        "customer_country",
        "customer_id_type"
    ]);
    let minted = app
        .clone()
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/api/hub/public-claims")
                .header("content-type", "application/json")
                .header("x-hub-session", &admin)
                .body(Body::from(claim.to_string()))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(minted.status(), StatusCode::OK);
    let locator = body_json(minted).await["locator"]
        .as_str()
        .unwrap()
        .to_string();

    let page = app
        .clone()
        .oneshot(anonymous_get(&format!("/p/{locator}")))
        .await
        .unwrap();
    assert_eq!(page.status(), StatusCode::OK);
    let html = body_text(page).await;
    assert!(html.contains("name=\"customer_country\""), "{html}");
    assert!(html.contains("<option value=\"US\">US</option>"), "{html}");
    assert!(html.contains("name=\"customer_id_type\""), "{html}");
    assert!(
        html.contains("<script src=\"/p/-/country-names.js\" defer></script>"),
        "{html}"
    );

    let script = app
        .clone()
        .oneshot(anonymous_get("/p/-/country-names.js"))
        .await
        .unwrap();
    assert_eq!(script.status(), StatusCode::OK);
    assert_eq!(
        script
            .headers()
            .get("content-type")
            .and_then(|v| v.to_str().ok()),
        Some("text/javascript; charset=utf-8")
    );
    assert!(body_text(script).await.contains("Intl.DisplayNames"));
}

/// When the command refuses (a mistyped number), the form comes back — and a foreign customer
/// must still find their country and document pickers on it, or the retry declares them Spanish.
#[tokio::test]
async fn a_refused_attempt_brings_the_foreign_pickers_back() {
    let app = make_app().await;
    let resp = app
        .clone()
        .oneshot(mint_request(
            "*",
            json!({
                "kind": "invoice_request",
                "subject_id": "ticket-retry",
                "command": "catalog.item.create",
                "sealed_payload": {},
                "public_fields": ["name", "customer_country", "customer_id_type"],
            }),
        ))
        .await
        .unwrap();
    let locator = body_json(resp).await["locator"]
        .as_str()
        .unwrap()
        .to_string();

    // No `name`: the command's NOT NULL refuses it, which is the door's retry path.
    let retry = app
        .clone()
        .oneshot(anonymous_post(
            &format!("/p/{locator}"),
            "customer_country=US",
        ))
        .await
        .unwrap();
    assert_eq!(retry.status(), StatusCode::UNPROCESSABLE_ENTITY);
    let html = body_text(retry).await;
    assert!(html.contains("<form method=\"post\""), "{html}");
    assert!(html.contains("name=\"customer_country\""), "{html}");
    assert!(html.contains("name=\"customer_id_type\""), "{html}");
}

/// The customer never chose a locale. Spanish by default, English on request — both real pages.
#[tokio::test]
async fn the_page_is_served_in_spanish_and_in_english() {
    let app = make_app().await;
    let locator = mint(&app, "ticket-6").await;
    let es = body_text(
        app.clone()
            .oneshot(anonymous_get(&format!("/p/{locator}")))
            .await
            .unwrap(),
    )
    .await;
    assert!(es.contains("Pide tu factura"), "{es}");
    assert!(es.contains("lang=\"es\""));
    let en = body_text(
        app.clone()
            .oneshot(anonymous_get(&format!("/p/{locator}?lang=en")))
            .await
            .unwrap(),
    )
    .await;
    assert!(en.contains("Get your invoice"), "{en}");
    assert!(en.contains("lang=\"en\""));
}

// ── minting is NOT public ───────────────────────────────────────────────────────────────────

/// Putting a locator on paper hands out the command it names. Anonymous callers cannot — and this
/// one asks a hub in the REAL session mode, because `AuthMode::Dev` trusts headers by design and
/// would prove nothing about the door a deployed hub serves.
#[tokio::test]
async fn minting_a_claim_takes_a_session() {
    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), "hub-public-door-session");
    rt.ensure_system_tables().await.unwrap();
    rt.install_from_dir(&fixture()).await.unwrap();
    let admin_id = rt
        .create_user("Admin", "1111", "admin", None)
        .await
        .unwrap();
    let admin = rt.create_session(&admin_id, 3600, None).await.unwrap();
    let mut cfg = dev_config();
    cfg.auth_mode = AuthMode::Session;
    cfg.hub_id = "hub-public-door-session".into();
    let app = app(AppState::with_config(rt, cfg));

    let anonymous = app
        .clone()
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/api/hub/public-claims")
                .header("content-type", "application/json")
                .body(Body::from(ticket_claim("ticket-7").to_string()))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(anonymous.status(), StatusCode::UNAUTHORIZED);

    // …and the check detects the positive: the same request WITH the session mints.
    let signed_in = app
        .clone()
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/api/hub/public-claims")
                .header("content-type", "application/json")
                .header("x-hub-session", &admin)
                .body(Body::from(ticket_claim("ticket-7").to_string()))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(signed_in.status(), StatusCode::OK);
}

/// **The escalation this closes.** Without it, a cashier who cannot run a command could print a
/// receipt that lets a stranger run it for them.
#[tokio::test]
async fn minting_refuses_a_command_the_minter_could_not_run() {
    let app = make_app().await;
    let resp = app
        .clone()
        .oneshot(mint_request("catalog.read", ticket_claim("ticket-8")))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::FORBIDDEN);
    let json = body_json(resp).await;
    assert_eq!(json["error"]["code"], json!("permission_denied"));
}

/// A claim over a command this hub does not have is refused at the counter, where somebody can
/// still do something about it — not discovered by a customer holding a dead locator.
#[tokio::test]
async fn minting_refuses_a_command_this_hub_does_not_have() {
    let app = make_app().await;
    let mut spec = ticket_claim("ticket-9");
    spec["command"] = json!("nosuch.command");
    let resp = app.clone().oneshot(mint_request("*", spec)).await.unwrap();
    assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
}

/// Reprinting a lost ticket must hand back the locator the customer's first copy already carries.
#[tokio::test]
async fn minting_twice_for_one_ticket_returns_one_locator() {
    let app = make_app().await;
    assert_eq!(mint(&app, "ticket-10").await, mint(&app, "ticket-10").await);
}
