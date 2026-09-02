//! The server's half of the fiscal-gateway route (hub#1432, hub#985 §1): the broker that turns
//! «the engine wants to transmit» into a [`GatewayAccess`] — and nothing else ever sees how.
//!
//! Mirror of `fiscal_certificate.rs` in discipline: the machine credential never leaves this
//! crate, an unreadable control-plane body is NEVER interpolated into an error (it carries a
//! bearer token), and a 409 is an ANSWER (that hub goes direct), not a failure. The token lives
//! 300 seconds and the mint quota is 60/h, so the broker caches until `expires_at − 30 s` and
//! brakes for 10 s after a failure — a contingency queue draining N records against a fallen
//! SaaS must not burn the quota.

use std::sync::Arc;
use std::time::{Duration, Instant};

use cloud_client::{Auth, CloudClient};
use erplora_runtime::fiscal_gateway::{GatewayAccess, GatewayBroker};
use erplora_runtime::gateway_identity;

/// What `POST /api/v1/hub/device/fiscal/gateway-token/` answers (saas#1794: it AUTHORISES, it
/// does not route — there is no `environment` field any more; the Hub stamps the environment in
/// each envelope from its own fiscal config).
pub struct GatewayToken {
    pub token: String,
    pub expires_in: i64,
    pub gateway_url: String,
    pub obligado_nif: String,
    pub grant_version: Option<i64>,
    pub presenter_nif: String,
    pub presenter_name: String,
    pub mtls_common_name: String,
}

impl std::fmt::Debug for GatewayToken {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        // The bearer is the one field that must never reach a log; everything else is public.
        f.debug_struct("GatewayToken")
            .field("token", &"[redacted]")
            .field("gateway_url", &self.gateway_url)
            .field("mtls_common_name", &self.mtls_common_name)
            .finish_non_exhaustive()
    }
}

impl GatewayToken {
    /// Parses the 200 body. Field-by-field on purpose (no derive): the error names the FIELD
    /// that was missing, never the body — which carries the bearer.
    pub fn parse(body: &str) -> Result<Self, String> {
        let value: serde_json::Value =
            serde_json::from_str(body).map_err(|e| format!("respuesta ilegible ({e})"))?;
        let text = |name: &str| -> Result<String, String> {
            value
                .get(name)
                .and_then(|v| v.as_str())
                .map(str::to_owned)
                .filter(|s| !s.is_empty())
                .ok_or_else(|| format!("respuesta sin el campo `{name}`"))
        };
        Ok(Self {
            token: text("token")?,
            expires_in: value
                .get("expires_in")
                .and_then(|v| v.as_i64())
                .unwrap_or(300),
            gateway_url: text("gateway_url")?,
            obligado_nif: text("obligado_nif")?,
            grant_version: value.get("grant_version").and_then(|v| v.as_i64()),
            presenter_nif: text("presenter_nif")?,
            presenter_name: text("presenter_name")?,
            mtls_common_name: text("mtls_common_name")?,
        })
    }
}

/// Outcome of one mint attempt against the control plane.
pub enum TokenAnswer {
    Minted(GatewayToken),
    /// 409 `own_certificate_direct`: this hub holds its own certificate and transmits direct.
    /// An answer, not an error — the caller reports «gateway route not applicable».
    GoDirect,
}

/// One mint. The machine credential rides the headers `CloudClient` prepared; the body of a
/// non-2xx answer is summarised by STATUS only — it may carry a bearer on a proxy mishap, and
/// `fiscal_certificate.rs` learned that lesson first.
pub async fn fetch_gateway_token(
    http: &reqwest::Client,
    cloud_base_url: &str,
    auth: &Auth,
) -> Result<TokenAnswer, String> {
    let prepared = CloudClient::new(cloud_base_url).fiscal_gateway_token(auth);
    let mut request = http.post(&prepared.url);
    for (name, value) in prepared.headers {
        request = request.header(name, value);
    }
    let response = request.send().await.map_err(|e| e.to_string())?;
    let status = response.status();
    if status == reqwest::StatusCode::CONFLICT {
        return Ok(TokenAnswer::GoDirect);
    }
    if !status.is_success() {
        return Err(format!("{}: status {status}", prepared.url));
    }
    let body = response.text().await.map_err(|e| e.to_string())?;
    GatewayToken::parse(&body)
        .map(TokenAnswer::Minted)
        .map_err(|e| format!("{}: {e}", prepared.url))
}

struct CachedToken {
    token: GatewayToken,
    fresh_until: Instant,
}

/// Cache + brake, both here so every caller shares them. `fresh_until` is `expires_in − 30 s`:
/// a token handed out with less margin could expire in flight between broker and cell.
#[derive(Default)]
pub struct GatewayTokenCache {
    slot: tokio::sync::Mutex<(Option<CachedToken>, Option<Instant>)>,
}

const EXPIRY_MARGIN: Duration = Duration::from_secs(30);
const FAILURE_BRAKE: Duration = Duration::from_secs(10);

/// The broker the composition root installs into the runtime's `GatewayBrokerCell`.
pub struct HubGatewayBroker {
    state: crate::state::AppState,
    cache: GatewayTokenCache,
}

impl HubGatewayBroker {
    pub fn new(state: &crate::state::AppState) -> Self {
        Self {
            state: state.clone(),
            cache: GatewayTokenCache::default(),
        }
    }

    async fn token(&self) -> Result<Option<GatewayToken>, String> {
        let mut slot = self.cache.slot.lock().await;
        if let (Some(cached), _) = &*slot {
            if cached.fresh_until > Instant::now() {
                return Ok(Some(clone_token(&cached.token)));
            }
        }
        if let (_, Some(last_failure)) = &*slot {
            if last_failure.elapsed() < FAILURE_BRAKE {
                return Err("la última petición de token falló hace un instante; frenando para no quemar la cuota".to_owned());
            }
        }
        let Some(auth) = crate::auth::machine_auth(&self.state) else {
            return Ok(None);
        };
        match fetch_gateway_token(&self.state.http, &self.state.config.cloud_base_url, &auth).await
        {
            Ok(TokenAnswer::Minted(token)) => {
                let margin = Duration::from_secs(token.expires_in.max(31) as u64) - EXPIRY_MARGIN;
                *slot = (
                    Some(CachedToken {
                        token: clone_token(&token),
                        fresh_until: Instant::now() + margin,
                    }),
                    None,
                );
                Ok(Some(token))
            }
            Ok(TokenAnswer::GoDirect) => {
                *slot = (None, None);
                Ok(None)
            }
            Err(error) => {
                slot.1 = Some(Instant::now());
                Err(error)
            }
        }
    }
}

fn clone_token(t: &GatewayToken) -> GatewayToken {
    GatewayToken {
        token: t.token.clone(),
        expires_in: t.expires_in,
        gateway_url: t.gateway_url.clone(),
        obligado_nif: t.obligado_nif.clone(),
        grant_version: t.grant_version,
        presenter_nif: t.presenter_nif.clone(),
        presenter_name: t.presenter_name.clone(),
        mtls_common_name: t.mtls_common_name.clone(),
    }
}

#[async_trait::async_trait]
impl GatewayBroker for HubGatewayBroker {
    async fn access(&self, hub_id: &str) -> erplora_runtime::errors::Result<Option<GatewayAccess>> {
        // Local identity FIRST: without it there is nothing to present at the ingress, and the
        // control-plane quota must not be spent asking for a token nobody can use.
        let identity = {
            let rt = self.state.runtime.read().await;
            gateway_identity::client_identity(rt.db(), hub_id).await?
        };
        let Some((identity, ca_pem)) = identity else {
            return Ok(None);
        };

        let token = self.token().await.map_err(|error| {
            erplora_runtime::errors::RuntimeError::Certificate(format!("gateway token: {error}"))
        })?;
        let Some(token) = token else {
            return Ok(None);
        };

        // The control plane and this hub must agree on WHO this machine is: a mismatch means an
        // identity enrolled for another hub, and the ingress would refuse it anyway — with a far
        // less actionable message.
        let expected = gateway_identity::common_name(hub_id);
        if token.mtls_common_name != expected {
            return Err(erplora_runtime::errors::RuntimeError::Certificate(format!(
                "gateway token: el plano de control espera '{}' y este hub es '{expected}'",
                token.mtls_common_name
            )));
        }

        Ok(Some(GatewayAccess {
            url: token.gateway_url,
            token: token.token,
            identity,
            ca_pem,
        }))
    }

    async fn invalidate_token(&self) {
        let mut slot = self.cache.slot.lock().await;
        *slot = (None, None);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::http::{HeaderMap, StatusCode};
    use axum::routing::post;
    use axum::Router;
    use std::sync::Mutex;

    fn token_body(common_name: &str) -> String {
        serde_json::json!({
            "token": "SECRET-BEARER-VALUE",
            "token_type": "Bearer",
            "expires_in": 300,
            "expires_at": "2026-09-02T10:00:00+00:00",
            "route": "gateway",
            "gateway_url": "https://cell.internal.example",
            "obligado_nif": "B12345678",
            "grant_version": null,
            "via": null,
            "presenter_nif": "B27593136",
            "presenter_name": "ERPLORA CLOUD SL",
            "mtls_common_name": common_name,
        })
        .to_string()
    }

    /// A stub of the control plane's token endpoint that counts its hits.
    async fn cloud_stub(
        status: StatusCode,
        body: String,
    ) -> (String, Arc<Mutex<u32>>, tokio::task::JoinHandle<()>) {
        let hits: Arc<Mutex<u32>> = Arc::new(Mutex::new(0));
        let app = Router::new().route(
            "/api/v1/hub/device/fiscal/gateway-token/",
            post({
                let hits = hits.clone();
                move |_headers: HeaderMap| {
                    *hits.lock().unwrap() += 1;
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
        (format!("http://{address}"), hits, server)
    }

    fn machine() -> Auth {
        Auth::HubToken {
            hub_id: "hub-1".into(),
            token: "machine-token".into(),
        }
    }

    /// 🔒 The rule BEFORE the feature, like `fiscal_certificate.rs`: an unreadable body is never
    /// quoted — on a proxy mishap it could carry the bearer itself.
    #[tokio::test]
    async fn a_bad_token_response_never_quotes_the_body() {
        let (base, _hits, server) = cloud_stub(
            StatusCode::OK,
            "SECRET-BEARER-IN-BROKEN-BODY not json".into(),
        )
        .await;

        let error = fetch_gateway_token(&reqwest::Client::new(), &base, &machine())
            .await
            .err()
            .expect("a broken body is an error");

        assert!(!error.contains("SECRET-BEARER-IN-BROKEN-BODY"), "{error}");
        server.abort();
    }

    #[tokio::test]
    async fn a_409_is_an_answer_not_an_error() {
        let (base, _hits, server) = cloud_stub(
            StatusCode::CONFLICT,
            r#"{"detail":"own_certificate_direct","route":"direct"}"#.into(),
        )
        .await;

        let answer = fetch_gateway_token(&reqwest::Client::new(), &base, &machine())
            .await
            .expect("409 is not a failure");
        assert!(matches!(answer, TokenAnswer::GoDirect));
        server.abort();
    }

    #[tokio::test]
    async fn the_minted_token_carries_the_contract() {
        let (base, hits, server) =
            cloud_stub(StatusCode::OK, token_body("hub-x.fiscal.erplora.internal")).await;

        let answer = fetch_gateway_token(&reqwest::Client::new(), &base, &machine())
            .await
            .expect("mint");
        let TokenAnswer::Minted(token) = answer else {
            panic!("expected a minted token");
        };
        assert_eq!(token.token, "SECRET-BEARER-VALUE");
        assert_eq!(token.gateway_url, "https://cell.internal.example");
        assert_eq!(token.mtls_common_name, "hub-x.fiscal.erplora.internal");
        assert_eq!(token.grant_version, None);
        assert_eq!(*hits.lock().unwrap(), 1);
        server.abort();
    }

    /// The Debug never prints the bearer — the one shape that slips into logs by accident.
    #[test]
    fn the_debug_of_a_token_redacts_the_bearer() {
        let token = GatewayToken::parse(&token_body("cn")).unwrap();
        let printed = format!("{token:?}");
        assert!(!printed.contains("SECRET-BEARER-VALUE"), "{printed}");
        assert!(printed.contains("[redacted]"));
    }

    /// A missing field names the FIELD, never the body (which holds the bearer).
    #[test]
    fn a_missing_field_is_named_without_the_body() {
        let mut value: serde_json::Value = serde_json::from_str(&token_body("cn")).unwrap();
        value.as_object_mut().unwrap().remove("gateway_url");
        let error = GatewayToken::parse(&value.to_string()).unwrap_err();
        assert!(error.contains("gateway_url"), "{error}");
        assert!(!error.contains("SECRET-BEARER-VALUE"), "{error}");
    }
}
