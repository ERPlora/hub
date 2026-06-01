//! erplora-cloud-client — cliente del Cloud Portal (ARQUITECTURA.md §2.1–2.3).
//!
//! El Cloud Portal es el plano de control: auth, marketplace, billing, proxy AI. Este crate
//! construye las **peticiones** (URLs + cabeceras) y **verifica la integridad** de los zips
//! descargados (SHA256), pero deja el I/O de red al llamador (inyectable → testeable sin red,
//! y sin atar el runtime a un cliente HTTP concreto todavía).
//!
//! Tres credenciales (verificadas en el hub actual, §2.3):
//!  1. `cloud_api_token` del hub → header `X-Hub-Token` (+ `X-Hub-Id`): bootstrap/máquina.
//!  2. JWT del usuario activo → `Authorization: Bearer …` (+ `X-Hub-Id`).
//!  3. `X-Webhook-Secret` (+ `X-Hub-Id`): M2M de fondo.

use serde::Deserialize;

pub mod integrity;

pub use integrity::{verify_sha256, IntegrityError};

/// Credenciales con las que firmar una petición al Cloud.
#[derive(Debug, Clone)]
pub enum Auth {
    /// Token de aplicación del hub (bootstrap / contexto máquina).
    HubToken { hub_id: String, token: String },
    /// JWT del usuario activo.
    UserJwt { hub_id: String, access: String },
    /// Secreto de webhook para M2M de fondo.
    Webhook { hub_id: String, secret: String },
}

impl Auth {
    /// Cabeceras `(nombre, valor)` para esta credencial. Siempre incluye `X-Hub-Id`.
    pub fn headers(&self) -> Vec<(&'static str, String)> {
        match self {
            Auth::HubToken { hub_id, token } => {
                vec![("X-Hub-Id", hub_id.clone()), ("X-Hub-Token", token.clone())]
            }
            Auth::UserJwt { hub_id, access } => {
                vec![("X-Hub-Id", hub_id.clone()), ("Authorization", format!("Bearer {access}"))]
            }
            Auth::Webhook { hub_id, secret } => {
                vec![("X-Hub-Id", hub_id.clone()), ("X-Webhook-Secret", secret.clone())]
            }
        }
    }
}

/// Una petición lista para ejecutar por el cliente HTTP del llamador.
#[derive(Debug, Clone)]
pub struct PreparedRequest {
    pub method: &'static str,
    pub url: String,
    pub headers: Vec<(&'static str, String)>,
}

/// Construye peticiones contra un Cloud Portal concreto.
#[derive(Debug, Clone)]
pub struct CloudClient {
    base_url: String,
}

impl CloudClient {
    pub fn new(base_url: impl Into<String>) -> Self {
        // normaliza sin barra final
        let mut b = base_url.into();
        while b.ends_with('/') {
            b.pop();
        }
        Self { base_url: b }
    }

    fn get(&self, path: &str, auth: &Auth) -> PreparedRequest {
        PreparedRequest { method: "GET", url: format!("{}{}", self.base_url, path), headers: auth.headers() }
    }

    /// Bootstrap del hub (config inicial), con el token de aplicación. §2.3.
    pub fn bootstrap(&self, hub_id: &str, token: &str) -> PreparedRequest {
        self.get(
            &format!("/api/hubs/{hub_id}/bootstrap/"),
            &Auth::HubToken { hub_id: hub_id.to_string(), token: token.to_string() },
        )
    }

    /// Lista de módulos del marketplace para el hub (con JWT de usuario). §2.2.
    pub fn marketplace_modules(&self, auth: &Auth) -> PreparedRequest {
        self.get("/api/v1/marketplace/modules/", auth)
    }

    /// Solicita la instalación/entitlement de un módulo → el Portal devuelve la URL S3 firmada
    /// + sha256 (ese parseo es `InstallGrant`). §2.2.
    pub fn request_install(&self, auth: &Auth, module_id: &str, version: &str) -> PreparedRequest {
        self.get(
            &format!("/api/v1/marketplace/modules/{module_id}/versions/{version}/install/"),
            auth,
        )
    }
}

/// Respuesta del Portal al pedir instalar: dónde está el zip y su hash esperado. §2.2.
#[derive(Debug, Clone, Deserialize, PartialEq, Eq)]
pub struct InstallGrant {
    pub module_id: String,
    pub version: String,
    /// URL S3 firmada (temporal) para descargar el `module.zip`.
    pub download_url: String,
    /// SHA256 hex esperado del zip (integridad, §2.2).
    pub sha256: String,
}

impl InstallGrant {
    pub fn parse(json: &str) -> Result<Self, serde_json::Error> {
        serde_json::from_str(json)
    }

    /// Verifica que `bytes` (el zip descargado) coincide con el `sha256` esperado.
    pub fn verify(&self, bytes: &[u8]) -> Result<(), IntegrityError> {
        verify_sha256(bytes, &self.sha256)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn base_url_normalized_and_paths() {
        let c = CloudClient::new("https://erplora.com/");
        let r = c.bootstrap("hub-123", "tok");
        assert_eq!(r.url, "https://erplora.com/api/hubs/hub-123/bootstrap/");
        assert_eq!(r.method, "GET");
        // cabeceras de bootstrap: X-Hub-Id + X-Hub-Token
        assert!(r.headers.contains(&("X-Hub-Id", "hub-123".to_string())));
        assert!(r.headers.contains(&("X-Hub-Token", "tok".to_string())));
    }

    #[test]
    fn user_jwt_headers() {
        let c = CloudClient::new("https://erplora.com");
        let auth = Auth::UserJwt { hub_id: "h1".into(), access: "abc".into() };
        let r = c.marketplace_modules(&auth);
        assert_eq!(r.url, "https://erplora.com/api/v1/marketplace/modules/");
        assert!(r.headers.contains(&("Authorization", "Bearer abc".to_string())));
        assert!(r.headers.contains(&("X-Hub-Id", "h1".to_string())));
    }

    #[test]
    fn install_grant_parse_and_verify() {
        let body = r#"{"module_id":"inventory","version":"1.0.0",
            "download_url":"https://s3/x.zip","sha256":"PLACEHOLDER"}"#;
        // calcula el sha real de unos bytes y mete el grant con ese hash
        let bytes = b"zip-bytes";
        let real = crate::integrity::sha256_hex(bytes);
        let body = body.replace("PLACEHOLDER", &real);
        let g = InstallGrant::parse(&body).unwrap();
        assert_eq!(g.module_id, "inventory");
        assert!(g.verify(bytes).is_ok());
        assert!(g.verify(b"otros-bytes").is_err());
    }
}
