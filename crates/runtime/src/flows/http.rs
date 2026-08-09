//! **The `http` step, up to the moment it leaves** (ADR-0283 §4 / K3, hub#662).
//!
//! This file builds the request and answers the two questions that must be answered BEFORE the hub
//! talks to anybody; the call itself is `crates/server/src/flow_io.rs`, outside the global lock.
//!
//! ```text
//!   step + run scope ──▶ template ──▶ substitute secrets ──▶ ALLOW-LIST ──▶ PendingIo ──▶ server
//!                                            │                                 (no lock)
//!                                            └── and, separately, the REDACTED copy that is what
//!                                                gets written to `_flow_run_steps`
//! ```
//!
//! **Why the allow-list is checked here and not there.** The URL a step calls is not in the
//! document — it is the document *rendered against this run*, so `https://api.example.com/{{input.
//! path}}` is only an URL once an event has filled it in. Judging the un-rendered form would
//! authorise a shape and call whatever the event carried. And judging it after the `PendingIo` has
//! been handed over would be judging it after the secret was already packed into the request that
//! is about to go out — the check has to be the last thing that happens on this side of the seam.
//!
//! **Why there are two renders.** One with the real secrets, which exists only in memory and only
//! until the server has made the call; one with `***` in their place, which is what
//! `_flow_run_steps` stores. A single render would force a choice between an audit trail that
//! shows nothing and one that shows the credential, and the run history is read by whoever is
//! debugging at the time — not necessarily by whoever is trusted with the key.
use std::fmt;

use erplora_db::DatabaseAdapter;
use serde_json::{json, Map, Value as Json};

use crate::errors::{Result, RuntimeError};
use crate::flows::def::{self, StepDef, StepSpec};
use crate::flows::grants::{Authority, ERR_GRANT_DENIED};
use crate::flows::secrets;

/// What a secret looks like once it is written down.
pub const REDACTED: &str = "***";

pub const ERR_HTTP_URL_INVALID: &str = "flow.http_url_invalid";

/// One outbound request, fully built: nothing about it is decided after this point.
///
/// It is carried by `PendingIo::Http` across the seam to the server and dropped as soon as the
/// call is over. It is never serialised, never stored, and its [`fmt::Debug`] is redacted, because
/// `eprintln!("{e:?}")` in a background tick is the likeliest way a credential ends up in a log.
#[derive(Clone, PartialEq)]
pub struct HttpRequest {
    pub method: String,
    pub url: String,
    pub headers: Vec<(String, String)>,
    pub body: Option<String>,
    pub timeout_seconds: u64,
    /// The secret VALUES that went into the fields above. Kept so that everything coming back —
    /// the response, and the text of any error — can be [`scrub`](Self::scrub)bed of them before it
    /// is written anywhere. A server that echoes the credential it was sent must not be able to get
    /// it into the run history.
    secrets: Vec<String>,
}

impl HttpRequest {
    /// Replaces every secret this request carries with [`REDACTED`].
    ///
    /// Used on the response body and on error text. It is a plain substring replace on purpose: the
    /// value may come back inside JSON, inside an URL, inside a message — anywhere — and the only
    /// property that matters is that the exact bytes of the credential do not survive.
    pub fn scrub(&self, text: &str) -> String {
        let mut out = text.to_string();
        for secret in &self.secrets {
            if !secret.is_empty() && out.contains(secret.as_str()) {
                out = out.replace(secret.as_str(), REDACTED);
            }
        }
        out
    }

    /// Same as [`scrub`](Self::scrub), for the URL and headers this request already holds — used by
    /// the server when it has to name the request in an error.
    pub fn redacted_url(&self) -> String {
        self.scrub(&self.url)
    }
}

impl fmt::Debug for HttpRequest {
    /// Redacted. The URL can carry a token in a query parameter and a header IS the credential, so
    /// what a `{:?}` shows is the method, the scrubbed URL, the header NAMES and how big the body
    /// was. Enough to debug a flow; not enough to reuse anybody's key.
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("HttpRequest")
            .field("method", &self.method)
            .field("url", &self.redacted_url())
            .field(
                "headers",
                &self.headers.iter().map(|(k, _)| k).collect::<Vec<_>>(),
            )
            .field("body_bytes", &self.body.as_ref().map_or(0, |b| b.len()))
            .field("timeout_seconds", &self.timeout_seconds)
            .finish()
    }
}

/// The two halves of a prepared step: the one that goes out and the one that gets written down.
pub(crate) struct Prepared {
    pub request: HttpRequest,
    /// What `_flow_run_steps.input` records — the same request with [`REDACTED`] where each secret
    /// was.
    pub recorded_input: Json,
}

/// Builds the request of an `http` step, or refuses it.
///
/// Refuses when: the rendered URL is not an absolute http(s) URL, a referenced secret does not
/// exist, or — the one that matters — the flow has no live `http` grant covering the URL it just
/// built. In every refusal the message carries the REDACTED URL, since a refusal is written to the
/// run exactly like a success is.
pub(crate) async fn prepare(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    flow_id: &str,
    step: &StepDef,
    scope: &Json,
    authority: &Authority,
) -> Result<Prepared> {
    let StepSpec::Http {
        method,
        url,
        headers,
        body,
        timeout_seconds,
    } = &step.spec
    else {
        return Err(RuntimeError::Domain {
            code: ERR_HTTP_URL_INVALID.to_string(),
            message: format!("step `{}` is not an http step", step.id),
        });
    };

    // Exactly the secrets this step names, decrypted for as long as this function's caller needs
    // them. A hub with fifty credentials opens the one the step mentions.
    let values = secrets::resolve(db, hub_id, &step.secret_names()).await?;
    let real = with_secrets(scope, values.iter().map(|(k, v)| (k.clone(), v.clone())));
    let shown = with_secrets(
        scope,
        values.keys().map(|k| (k.clone(), REDACTED.to_string())),
    );

    let real_url = as_text(&def::resolve(&json!(url), &real));
    let shown_url = as_text(&def::resolve(&json!(url), &shown));

    if !def::is_http_url(&real_url) {
        return Err(RuntimeError::Domain {
            code: ERR_HTTP_URL_INVALID.to_string(),
            message: format!(
                "step `{}`: `{shown_url}` is not an absolute http(s) URL once the run filled it in",
                step.id
            ),
        });
    }

    // **The allow-list**, on the URL that would really be called, as the last thing before the
    // request crosses the seam. Default-deny: no live `http` grant covering it, no call.
    if !authority.allows_http(&real_url) {
        return Err(RuntimeError::Domain {
            code: ERR_GRANT_DENIED.to_string(),
            message: format!(
                "step `{}`: flow `{flow_id}` has no live `http` grant covering `{shown_url}`. A \
                 flow calls the URLs an admin listed for it, and nothing else (ADR-0283 §4).",
                step.id
            ),
        });
    }

    let real_headers = render_headers(headers, &real);
    let shown_headers = render_headers(headers, &shown);
    let (real_body, content_type) = render_body(body.as_ref(), &real);
    let (shown_body, _) = render_body(body.as_ref(), &shown);

    let mut out_headers = real_headers.clone();
    // A JSON body without a declared content type gets one: an API that receives an object with no
    // type answers 415, and «the flow is broken» is not what happened.
    if let Some(ct) = content_type {
        if !out_headers
            .iter()
            .any(|(k, _)| k.eq_ignore_ascii_case("content-type"))
        {
            out_headers.push(("content-type".to_string(), ct.to_string()));
        }
    }

    let recorded_input = json!({
        "method": method,
        "url": shown_url,
        "headers": Json::Object(shown_headers.into_iter().map(|(k, v)| (k, json!(v))).collect()),
        "body": shown_body,
        "timeout": timeout_seconds,
    });

    Ok(Prepared {
        request: HttpRequest {
            method: method.clone(),
            url: real_url,
            headers: out_headers,
            body: real_body,
            timeout_seconds: *timeout_seconds,
            secrets: values.into_values().filter(|v| !v.is_empty()).collect(),
        },
        recorded_input,
    })
}

/// The run scope plus a `secret` root — the only place that root ever exists, and it is built per
/// step and dropped with it.
fn with_secrets(scope: &Json, entries: impl Iterator<Item = (String, String)>) -> Json {
    let mut out = scope.clone();
    let map = out.as_object_mut().expect("the run scope is an object");
    map.insert(
        "secret".to_string(),
        Json::Object(entries.map(|(k, v)| (k, json!(v))).collect()),
    );
    out
}

fn render_headers(headers: &Map<String, Json>, scope: &Json) -> Vec<(String, String)> {
    headers
        .iter()
        .map(|(name, expr)| (name.clone(), as_text(&def::resolve(expr, scope))))
        .collect()
}

/// The body as it goes on the wire, plus the content type it implies. An object or array is JSON;
/// anything else is sent as text, because a step that posts a form or an XML envelope writes the
/// string itself and sets its own header.
fn render_body(body: Option<&Json>, scope: &Json) -> (Option<String>, Option<&'static str>) {
    match body.map(|b| def::resolve(b, scope)) {
        None | Some(Json::Null) => (None, None),
        Some(value @ (Json::Object(_) | Json::Array(_))) => {
            (Some(value.to_string()), Some("application/json"))
        }
        Some(other) => (Some(as_text(&other)), None),
    }
}

/// How a resolved value reads on the wire: a string is itself, a null is empty, a structure is
/// compact JSON. Same rule the template language uses, so a header and a `{{…}}` never disagree.
fn as_text(value: &Json) -> String {
    match value {
        Json::String(s) => s.clone(),
        Json::Null => String::new(),
        other => other.to_string(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::flows::def::FlowDefinition;
    use crate::flows::grants::{self, GrantKind};
    use crate::flows::test_support;
    use crate::registry::Registry;
    use crate::secret_box::test_support::{env_lock, test_key_b64, EnvVarGuard};
    use erplora_db::testutil::fresh_db;

    const HUB: &str = "hub-http";
    const FLOW: &str = "flow-1";

    async fn db() -> impl DatabaseAdapter {
        let db = fresh_db().await;
        test_support::ensure_schema(&db, HUB).await;
        db
    }

    async fn allow(db: &dyn DatabaseAdapter, pattern: &str) -> Authority {
        grants::replace(
            db,
            HUB,
            FLOW,
            &Registry::new(),
            &[(GrantKind::Http, pattern.to_string())],
            "hub_user:1",
        )
        .await
        .unwrap();
        grants::authority(db, HUB, FLOW).await.unwrap()
    }

    fn step(spec: Json) -> StepDef {
        FlowDefinition::parse(&json!({ "schema_version": 1, "steps": [spec] }))
            .unwrap()
            .steps
            .remove(0)
    }

    fn scope() -> Json {
        json!({ "input": { "phone": "+34600111222", "text": "hola" }, "steps": {} })
    }

    fn calling_step() -> StepDef {
        step(json!({
            "id": "call", "kind": "http", "method": "POST",
            "url": "https://api.example.com/v1/send?to={{input.phone}}",
            "headers": { "Authorization": "Bearer {{secret.API_KEY}}" },
            "body": { "text": "input.text" }
        }))
    }

    #[tokio::test]
    async fn the_request_carries_the_secret_and_the_run_history_never_does() {
        let _lock = env_lock();
        let _key = EnvVarGuard::set(&test_key_b64(3));
        let db = db().await;
        secrets::put(&db, HUB, "API_KEY", "sk-live-42", "hub_user:1").await.unwrap();
        let authority = allow(&db, "https://api.example.com/v1/*").await;

        let prepared = prepare(&db, HUB, FLOW, &calling_step(), &scope(), &authority)
            .await
            .unwrap();

        // What goes out: templated, with the real credential.
        assert_eq!(prepared.request.method, "POST");
        assert_eq!(
            prepared.request.url,
            "https://api.example.com/v1/send?to=+34600111222"
        );
        assert!(prepared
            .request
            .headers
            .iter()
            .any(|(k, v)| k == "Authorization" && v == "Bearer sk-live-42"));
        assert_eq!(prepared.request.body.as_deref(), Some(r#"{"text":"hola"}"#));

        // What is written down: the same request with `***` where the credential was.
        let recorded = prepared.recorded_input.to_string();
        assert!(!recorded.contains("sk-live-42"), "the run history never holds it: {recorded}");
        assert!(recorded.contains(REDACTED), "{recorded}");
        // …and the rest of the request IS there, or the audit would be useless.
        assert!(recorded.contains("+34600111222"), "{recorded}");

        // And a `{:?}` in a background tick cannot leak it either.
        let debug = format!("{:?}", prepared.request);
        assert!(!debug.contains("sk-live-42"), "{debug}");
    }

    #[tokio::test]
    async fn whatever_comes_back_is_scrubbed_of_the_credential_that_went_out() {
        let _lock = env_lock();
        let _key = EnvVarGuard::set(&test_key_b64(3));
        let db = db().await;
        secrets::put(&db, HUB, "API_KEY", "sk-live-42", "hub_user:1").await.unwrap();
        let authority = allow(&db, "https://api.example.com/v1/*").await;
        let prepared = prepare(&db, HUB, FLOW, &calling_step(), &scope(), &authority)
            .await
            .unwrap();

        // A server that echoes the key back (plenty do, in an error message) must not be able to
        // write it into the run.
        let echoed = prepared
            .request
            .scrub(r#"{"error":"bad key sk-live-42","ok":false}"#);
        assert_eq!(echoed, r#"{"error":"bad key ***","ok":false}"#);
    }

    #[tokio::test]
    async fn without_a_covering_grant_nothing_is_prepared_and_the_refusal_names_the_url() {
        let _lock = env_lock();
        let _key = EnvVarGuard::set(&test_key_b64(3));
        let db = db().await;
        secrets::put(&db, HUB, "API_KEY", "sk-live-42", "hub_user:1").await.unwrap();
        // A grant for a NEIGHBOURING path of the same host: the flow may call, just not this.
        let authority = allow(&db, "https://api.example.com/v2/*").await;

        let err = prepare(&db, HUB, FLOW, &calling_step(), &scope(), &authority)
            .await
            .expect_err("no grant covers this URL");
        let text = format!("{err}");
        assert!(text.contains("api.example.com/v1/send"), "{text}");
        assert!(!text.contains("sk-live-42"), "not even in the refusal: {text}");
        assert!(
            matches!(&err, RuntimeError::Domain { code, .. } if code == ERR_GRANT_DENIED),
            "the code the module `flows` offers «grant it» from: {err}"
        );
    }

    #[tokio::test]
    async fn the_allow_list_judges_the_url_the_run_built_not_the_one_the_author_wrote() {
        let _lock = env_lock();
        let _key = EnvVarGuard::set(&test_key_b64(3));
        let db = db().await;
        let authority = allow(&db, "https://api.example.com/v1/*").await;
        let templated = step(json!({
            "id": "call", "kind": "http", "url": "{{input.target}}"
        }));

        // The same document, two runs. Only the one whose input lands inside the grant goes out —
        // which is the whole reason the match happens after templating.
        let inside = json!({ "input": { "target": "https://api.example.com/v1/ping" }, "steps": {} });
        assert!(prepare(&db, HUB, FLOW, &templated, &inside, &authority).await.is_ok());

        let outside = json!({ "input": { "target": "https://evil.test/steal" }, "steps": {} });
        assert!(prepare(&db, HUB, FLOW, &templated, &outside, &authority)
            .await
            .is_err());
    }

    #[tokio::test]
    async fn a_rendered_url_that_is_not_http_is_refused_before_anything_leaves() {
        let _lock = env_lock();
        let _key = EnvVarGuard::set(&test_key_b64(3));
        let db = db().await;
        let authority = allow(&db, "https://api.example.com/v1/*").await;
        let templated = step(json!({ "id": "call", "kind": "http", "url": "{{input.target}}" }));

        for target in ["file:///etc/passwd", "", "//evil.test/x"] {
            let scope = json!({ "input": { "target": target }, "steps": {} });
            assert!(
                prepare(&db, HUB, FLOW, &templated, &scope, &authority).await.is_err(),
                "`{target}` is not something this hub calls"
            );
        }
    }

    #[tokio::test]
    async fn a_secret_the_hub_does_not_hold_stops_the_step_instead_of_sending_an_empty_header() {
        let _lock = env_lock();
        let _key = EnvVarGuard::set(&test_key_b64(3));
        let db = db().await;
        let authority = allow(&db, "https://api.example.com/v1/*").await;

        let err = prepare(&db, HUB, FLOW, &calling_step(), &scope(), &authority)
            .await
            .expect_err("`Authorization: Bearer ` looks like the API is down");
        assert!(format!("{err}").contains("API_KEY"), "{err}");
    }

    #[tokio::test]
    async fn a_json_body_gets_its_content_type_and_a_string_body_does_not() {
        let _lock = env_lock();
        let _key = EnvVarGuard::set(&test_key_b64(3));
        let db = db().await;
        let authority = allow(&db, "https://api.example.com/v1/*").await;

        let with_object = prepare(
            &db,
            HUB,
            FLOW,
            &step(json!({
                "id": "c", "kind": "http", "method": "POST",
                "url": "https://api.example.com/v1/x", "body": { "a": 1 }
            })),
            &scope(),
            &authority,
        )
        .await
        .unwrap();
        assert!(with_object
            .request
            .headers
            .iter()
            .any(|(k, v)| k == "content-type" && v == "application/json"));

        let with_text = prepare(
            &db,
            HUB,
            FLOW,
            &step(json!({
                "id": "c", "kind": "http", "method": "POST",
                "url": "https://api.example.com/v1/x",
                "headers": { "Content-Type": "application/xml" },
                "body": "<a>{{input.text}}</a>"
            })),
            &scope(),
            &authority,
        )
        .await
        .unwrap();
        assert_eq!(with_text.request.body.as_deref(), Some("<a>hola</a>"));
        assert_eq!(
            with_text.request.headers.len(),
            1,
            "the author declared the type; nothing is added on top"
        );
    }
}
