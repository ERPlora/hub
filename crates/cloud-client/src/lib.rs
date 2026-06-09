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

    /// **Flujo real de instalación, paso 1** — lista las versiones activas de un módulo.
    /// `GET /api/v1/marketplace/modules/{module_id}/versions/` (verificado contra
    /// `cloud/apps/public/modules/api_views.py::versions`). La respuesta es un array JSON
    /// (`ModuleVersionSerializer`): `version`, `changelog`, `is_active`, `file_size_bytes`,
    /// `created_at`. El `sha256` se parsea si el Cloud lo expone (ver `ModuleVersion`). §2.2.
    pub fn versions(&self, auth: &Auth, module_id: &str) -> PreparedRequest {
        self.get(&format!("/api/v1/marketplace/modules/{module_id}/versions/"), auth)
    }

    /// **Flujo real de instalación, paso 2** — descarga el ZIP binario de una versión.
    /// `GET /api/v1/marketplace/modules/{module_id}/download/?version={version}` (FileResponse,
    /// verificado en `api_views.py::download`). §2.2.
    pub fn download(&self, auth: &Auth, module_id: &str, version: &str) -> PreparedRequest {
        self.get(
            &format!("/api/v1/marketplace/modules/{module_id}/download/?version={version}"),
            auth,
        )
    }

    /// **Flujo real de instalación, paso 3** — registra la instalación en el Cloud.
    /// `POST /api/v1/marketplace/modules/{module_id}/mark_installed/` con body
    /// `{"version":"…"}` (verificado en `api_views.py::mark_installed`). §2.2.
    pub fn mark_installed(&self, auth: &Auth, module_id: &str) -> PreparedRequest {
        PreparedRequest {
            method: "POST",
            url: format!("{}/api/v1/marketplace/modules/{module_id}/mark_installed/", self.base_url),
            headers: auth.headers(),
        }
    }

    /// Stream SSE del asistente vía el proxy del Cloud (§9.3 — el Hub nunca habla con el LLM
    /// directamente). `POST /api/v1/hub/device/assistant/chat/stream/` con el JWT del usuario
    /// + `X-Hub-Id`. El body lo construye el llamador (server) a partir del payload del frontend.
    pub fn assistant_chat_stream(&self, auth: &Auth) -> PreparedRequest {
        PreparedRequest {
            method: "POST",
            url: format!("{}/api/v1/hub/device/assistant/chat/stream/", self.base_url),
            headers: auth.headers(),
        }
    }

    /// **DEPRECADO** — apuntaba a un endpoint ficticio `…/versions/{version}/install/` que
    /// **no existe** en el Cloud. Usa el flujo real [`CloudClient::versions`] +
    /// [`CloudClient::download`] + [`CloudClient::mark_installed`]. Se mantiene solo para no
    /// romper a `erplora-installer` (que lo migrará por separado).
    #[deprecated(note = "endpoint ficticio; usar versions()/download()/mark_installed()")]
    pub fn request_install(&self, auth: &Auth, module_id: &str, version: &str) -> PreparedRequest {
        self.get(
            &format!("/api/v1/marketplace/modules/{module_id}/versions/{version}/install/"),
            auth,
        )
    }
}

/// Una versión de módulo tal como la devuelve el endpoint `versions/` del Cloud
/// (`ModuleVersionSerializer`). El `sha256` es **opcional**: el serializer público actual
/// (`cloud/apps/public/modules/serializers.py`) **no** lo incluye todavía — vive en el modelo
/// `ModuleVersion.sha256` y sí se expone en el endpoint de sync. Se parsea si está presente
/// para verificar integridad; si falta, el llamador debe decidir su política (ver server).
#[derive(Debug, Clone, Deserialize, PartialEq, Eq)]
pub struct ModuleVersion {
    pub version: String,
    #[serde(default)]
    pub changelog: String,
    #[serde(default)]
    pub is_active: bool,
    #[serde(default)]
    pub file_size_bytes: u64,
    /// SHA256 hex esperado del ZIP. `None` si el Cloud no lo expone en este endpoint.
    #[serde(default)]
    pub sha256: Option<String>,
}

impl ModuleVersion {
    /// Parsea la lista JSON del endpoint `versions/`.
    pub fn parse_list(json: &str) -> Result<Vec<ModuleVersion>, serde_json::Error> {
        serde_json::from_str(json)
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
    fn real_install_flow_paths() {
        let c = CloudClient::new("https://erplora.com");
        let auth = Auth::UserJwt { hub_id: "h1".into(), access: "abc".into() };

        let v = c.versions(&auth, "inventory");
        assert_eq!(v.method, "GET");
        assert_eq!(v.url, "https://erplora.com/api/v1/marketplace/modules/inventory/versions/");

        let d = c.download(&auth, "inventory", "1.0.0");
        assert_eq!(d.url, "https://erplora.com/api/v1/marketplace/modules/inventory/download/?version=1.0.0");

        let m = c.mark_installed(&auth, "inventory");
        assert_eq!(m.method, "POST");
        assert_eq!(m.url, "https://erplora.com/api/v1/marketplace/modules/inventory/mark_installed/");

        let s = c.assistant_chat_stream(&auth);
        assert_eq!(s.method, "POST");
        assert_eq!(s.url, "https://erplora.com/api/v1/hub/device/assistant/chat/stream/");
        assert!(s.headers.contains(&("Authorization", "Bearer abc".to_string())));
        assert!(s.headers.contains(&("X-Hub-Id", "h1".to_string())));
    }

    #[test]
    fn module_version_list_parses_with_and_without_sha() {
        // El serializer público actual NO trae sha256 → debe parsear igualmente (None).
        let body = r#"[{"version":"1.0.0","changelog":"init","is_active":true,
            "file_size_bytes":1234,"created_at":"2026-01-01T00:00:00Z"}]"#;
        let vs = ModuleVersion::parse_list(body).unwrap();
        assert_eq!(vs.len(), 1);
        assert_eq!(vs[0].version, "1.0.0");
        assert!(vs[0].is_active);
        assert_eq!(vs[0].sha256, None);

        // Si el Cloud lo expone, se captura.
        let with_sha = r#"[{"version":"2.0.0","sha256":"deadbeef"}]"#;
        let vs = ModuleVersion::parse_list(with_sha).unwrap();
        assert_eq!(vs[0].sha256.as_deref(), Some("deadbeef"));
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
