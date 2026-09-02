//! The server's half of «call MY cloud with MY machine credential» (hub#1459): the caller that
//! turns a [`CloudRequest`] from a first-party engine into an HTTP call carrying the machine
//! credential — and nothing else ever sees that credential.
//!
//! Mirror of `fiscal_certificate.rs` in discipline: the machine credential never leaves this
//! crate, and the body of an answer is handed to the engine but NEVER interpolated into an error
//! or a log line — a control-plane body routinely carries a bearer, and on a proxy mishap so can
//! the body of a non-2xx. What describes a failure here is the STATUS.
//!
//! What this file deliberately does NOT know: what the engine is asking for. The cache, the
//! retry, the meaning of a 409 and the freshness of whatever token comes back all belong to the
//! engine that asked — the core stopped brokering use cases when `fiscal_gateway_access` was
//! dissolved.

use std::sync::Arc;

use cloud_client::{Auth, CloudClient};
use erplora_runtime::cloud_call::{check_path, CloudCaller, CloudRequest, CloudResponse};

/// One call. The machine credential rides the headers `CloudClient` prepared; a non-2xx is an
/// ANSWER (status + body), not an error — only a transport failure or a refused path is.
pub async fn call_cloud(
    http: &reqwest::Client,
    cloud_base_url: &str,
    auth: &Auth,
    request: CloudRequest,
) -> Result<CloudResponse, String> {
    check_path(&request.path).map_err(|e| e.to_string())?;
    let prepared = CloudClient::new(cloud_base_url).machine_request(
        request.method.as_str(),
        &request.path,
        auth,
    );
    let mut outgoing = http.request(
        reqwest::Method::from_bytes(prepared.method.as_bytes())
            .map_err(|_| format!("verbo no soportado: {}", prepared.method))?,
        &prepared.url,
    );
    for (name, value) in prepared.headers {
        outgoing = outgoing.header(name, value);
    }
    if let Some(body) = request.body {
        outgoing = outgoing
            .header("Content-Type", "application/json")
            .body(body);
    }
    let response = outgoing.send().await.map_err(|e| e.to_string())?;
    let status = response.status().as_u16();
    // The body is read whole and handed BACK, never read INTO an error: it can carry a bearer.
    let body = response.text().await.map_err(|e| e.to_string())?;
    Ok(CloudResponse { status, body })
}

/// The caller the composition root installs into the runtime's `CloudCallerCell`.
pub struct HubCloudCaller {
    state: crate::state::AppState,
}

impl HubCloudCaller {
    pub fn new(state: &crate::state::AppState) -> Self {
        Self {
            state: state.clone(),
        }
    }

    pub fn installed(state: &crate::state::AppState) -> Arc<dyn CloudCaller> {
        Arc::new(Self::new(state))
    }
}

#[async_trait::async_trait]
impl CloudCaller for HubCloudCaller {
    async fn call(
        &self,
        request: CloudRequest,
    ) -> erplora_runtime::errors::Result<Option<CloudResponse>> {
        check_path(&request.path)?;
        let Some(auth) = crate::auth::machine_auth(&self.state) else {
            // No machine credential = this hub cannot call its cloud. An ANSWER, not a failure:
            // a hub whose bootstrap never finished keeps working locally.
            return Ok(None);
        };
        call_cloud(
            &self.state.http,
            &self.state.config.cloud_base_url,
            &auth,
            request,
        )
        .await
        .map(Some)
        .map_err(erplora_runtime::errors::RuntimeError::Native)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::http::{HeaderMap, StatusCode};
    use axum::routing::{get, post};
    use axum::Router;
    use erplora_runtime::cloud_call::{CloudMethod, PATH_NOT_MINE};
    use std::sync::Mutex;

    const PATH: &str = "/api/v1/hub/device/fiscal/gateway-token/";

    struct Seen {
        hits: u32,
        hub_id: String,
        hub_token: String,
        body: String,
    }

    /// A stub control plane on the real path, recording what actually arrived on the wire.
    async fn cloud_stub(
        status: StatusCode,
        body: String,
    ) -> (String, Arc<Mutex<Seen>>, tokio::task::JoinHandle<()>) {
        let seen = Arc::new(Mutex::new(Seen {
            hits: 0,
            hub_id: String::new(),
            hub_token: String::new(),
            body: String::new(),
        }));
        let record = {
            let seen = seen.clone();
            move |headers: HeaderMap, sent: String| {
                let mut s = seen.lock().unwrap();
                s.hits += 1;
                let header = |name: &str| {
                    headers
                        .get(name)
                        .and_then(|v| v.to_str().ok())
                        .unwrap_or_default()
                        .to_owned()
                };
                s.hub_id = header("X-Hub-Id");
                s.hub_token = header("X-Hub-Token");
                s.body = sent;
            }
        };
        let app = Router::new()
            .route(
                PATH,
                post({
                    let record = record.clone();
                    let body = body.clone();
                    move |headers: HeaderMap, sent: String| {
                        record(headers, sent);
                        let body = body.clone();
                        async move { (status, body) }
                    }
                }),
            )
            .route(
                "/api/v1/hub/device/heartbeat/",
                get({
                    let record = record.clone();
                    let body = body.clone();
                    move |headers: HeaderMap| {
                        record(headers, String::new());
                        let body = body.clone();
                        async move { (status, body) }
                    }
                }),
            );
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let address = listener.local_addr().unwrap();
        let server = tokio::spawn(async move {
            axum::serve(listener, app).await.unwrap();
        });
        (format!("http://{address}"), seen, server)
    }

    fn machine() -> Auth {
        Auth::HubToken {
            hub_id: "hub-1".into(),
            token: "machine-token".into(),
        }
    }

    fn request(method: CloudMethod, path: &str, body: Option<&str>) -> CloudRequest {
        CloudRequest {
            method,
            path: path.to_owned(),
            body: body.map(str::to_owned),
        }
    }

    /// The split that IS the primitive: the engine chose the method, the path and the body; the
    /// host put the destination and the credential — and the engine gets the answer back whole.
    #[tokio::test]
    async fn the_host_puts_the_destination_and_the_credential() {
        let (base, seen, server) = cloud_stub(StatusCode::OK, r#"{"token":"abc"}"#.into()).await;

        let response = call_cloud(
            &reqwest::Client::new(),
            &base,
            &machine(),
            request(CloudMethod::Post, PATH, Some(r#"{"why":"because"}"#)),
        )
        .await
        .expect("the cloud answered");

        assert_eq!(response.status, 200);
        assert_eq!(response.body, r#"{"token":"abc"}"#);
        let seen = seen.lock().unwrap();
        assert_eq!(seen.hits, 1);
        assert_eq!(seen.hub_id, "hub-1");
        assert_eq!(seen.hub_token, "machine-token");
        assert_eq!(seen.body, r#"{"why":"because"}"#);
        server.abort();
    }

    /// A GET is the other half of the closed verb set, and it carries no body.
    #[tokio::test]
    async fn a_get_reaches_its_path_with_no_body() {
        let (base, seen, server) = cloud_stub(StatusCode::OK, "{}".into()).await;

        let response = call_cloud(
            &reqwest::Client::new(),
            &base,
            &machine(),
            request(CloudMethod::Get, "/api/v1/hub/device/heartbeat/", None),
        )
        .await
        .expect("the cloud answered");

        assert_eq!(response.status, 200);
        assert_eq!(seen.lock().unwrap().hits, 1);
        server.abort();
    }

    /// 🔒 A non-2xx is an ANSWER: the engine decides what a 409 or a 404 means to it. The core
    /// used to decide that for it (`TokenAnswer::GoDirect`), which is the coupling hub#1459 cuts.
    #[tokio::test]
    async fn a_non_2xx_comes_back_with_its_status_instead_of_failing() {
        let (base, _seen, server) = cloud_stub(
            StatusCode::CONFLICT,
            r#"{"detail":"own_certificate_direct"}"#.into(),
        )
        .await;

        let response = call_cloud(
            &reqwest::Client::new(),
            &base,
            &machine(),
            request(CloudMethod::Post, PATH, None),
        )
        .await
        .expect("409 is not a failure");

        assert_eq!(response.status, 409);
        assert!(response.body.contains("own_certificate_direct"));
        server.abort();
    }

    /// 🔒 Defence in depth: the runtime checks the path before it reaches any caller, and so does
    /// the caller. The machine credential must not reach a destination the engine chose — the
    /// stub is on the SAME server, so a hit here would mean the check let it through.
    #[tokio::test]
    async fn a_path_that_is_not_mine_never_reaches_the_wire() {
        let (base, seen, server) = cloud_stub(StatusCode::OK, "{}".into()).await;

        let error = call_cloud(
            &reqwest::Client::new(),
            &base,
            &machine(),
            request(CloudMethod::Post, "/api/v1/../../steal/", None),
        )
        .await
        .err()
        .expect("a path that climbs out of the API is refused");

        assert!(error.contains(PATH_NOT_MINE), "{error}");
        assert_eq!(seen.lock().unwrap().hits, 0);
        server.abort();
    }
}
