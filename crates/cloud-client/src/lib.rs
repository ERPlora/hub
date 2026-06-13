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

pub mod entitlement;
pub mod integrity;
pub mod user_jwt;

pub use entitlement::{
    verify_entitlement, EntitledModule, EntitlementClaims, EntitlementError, EntitlementResponse,
};
pub use integrity::{verify_sha256, IntegrityError};
pub use user_jwt::{verify_user_jwt, UserClaims, UserJwtError};

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

    /// **Gate de arranque de la app Tauri** — entitlement firmado de módulos del hub
    /// (con JWT de usuario). `GET /api/v1/hub/device/entitlement/`. La respuesta es un
    /// [`EntitlementResponse`]; su `token` se verifica offline con
    /// [`verify_entitlement`] contra la clave pública del Cloud. Ver `entitlement.rs`.
    pub fn entitlement(&self, auth: &Auth) -> PreparedRequest {
        self.get("/api/v1/hub/device/entitlement/", auth)
    }

    /// **Enrolamiento del dispositivo** — el runtime obtiene su credencial de máquina
    /// (`cloud_api_token`) una sola vez. `GET /api/v1/hub/device/enroll/` con el JWT de un
    /// **owner/admin** de la org del hub (`IsHubAdmin`) + `X-Hub-Id`. La respuesta es
    /// [`EnrollGrant`] (`hub_id` + `cloud_api_token`); el runtime la persiste de forma segura
    /// y a partir de ahí usa [`Auth::HubToken`] (`X-Hub-Token`) para llamadas hub-scoped sin
    /// usuario logueado (marketplace, entitlement…). §2.3.
    pub fn enroll(&self, auth: &Auth) -> PreparedRequest {
        self.get("/api/v1/hub/device/enroll/", auth)
    }

    /// **Rotación** de la credencial de máquina — `POST /api/v1/hub/device/enroll/` (mismo endpoint,
    /// `IsHubAdmin`). El Cloud genera un `cloud_api_token` **nuevo** (invalida el anterior) y lo
    /// devuelve como [`EnrollGrant`]; el runtime lo re-persiste. Usar deliberadamente (compromiso de
    /// credencial / rotación periódica): un hub en ECS necesita redeploy para tomar el nuevo env. §2.3.
    pub fn enroll_rotate(&self, auth: &Auth) -> PreparedRequest {
        PreparedRequest {
            method: "POST",
            url: format!("{}/api/v1/hub/device/enroll/", self.base_url),
            headers: auth.headers(),
        }
    }

    /// **Revocación** (kill-switch) de la credencial de máquina — `DELETE /api/v1/hub/device/enroll/`
    /// (`IsHubAdmin`). Desactiva el token de máquina al instante sin emitir uno nuevo (dispositivo
    /// perdido/robado); se re-habilita re-enrolando (`enroll_rotate`). Normalmente lo invoca el
    /// dashboard/admin del owner (revoca un dispositivo que NO tiene a mano), no el propio hub. §2.3.
    pub fn enroll_revoke(&self, auth: &Auth) -> PreparedRequest {
        PreparedRequest {
            method: "DELETE",
            url: format!("{}/api/v1/hub/device/enroll/", self.base_url),
            headers: auth.headers(),
        }
    }

    /// **Refresh del JWT de usuario** contra el Cloud (hub#15, §2.3) — `POST /api/v1/auth/refresh/`
    /// (verificado: `cloud/apps/auth/users/api/urls.py` → `RotatingTokenRefreshView`, rota el
    /// refresh). Es un endpoint **público** en cuanto a cabeceras: NO lleva `Authorization` ni
    /// `X-Hub-Id`; el `refresh` token va en el **body** `{"refresh":"<token>"}`. La respuesta es un
    /// [`RefreshGrant`] (`access` nuevo + `refresh` rotado). El interceptor del Hub lo invoca al
    /// recibir un 401 con un access caducado. El body lo construye el llamador (server).
    pub fn refresh(&self) -> PreparedRequest {
        PreparedRequest {
            method: "POST",
            url: format!("{}/api/v1/auth/refresh/", self.base_url),
            headers: vec![],
        }
    }

    /// Clave pública RSA del Cloud (para verificar el token de entitlement offline).
    /// `GET /api/v1/auth/public-key/`. Sin auth (endpoint público).
    pub fn public_key(&self) -> PreparedRequest {
        PreparedRequest {
            method: "GET",
            url: format!("{}/api/v1/auth/public-key/", self.base_url),
            headers: vec![],
        }
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

    /// **Notificación WhatsApp PREMIUM de ERPlora vía el proxy del Cloud** (ADR-0012 + ADR-0006).
    /// Como el asistente, el Hub no habla con la Graph API de Meta directamente: la llamada sale
    /// por Cloud, que aplica `check_quota`, inyecta el token de Meta de ERPlora y bloquea al
    /// agotar la cuota (el Hub solo refleja el estado). `POST /api/v1/hub/device/notify/whatsapp/`
    /// con la credencial de **máquina** (`X-Hub-Token`, contexto hub-scoped sin usuario; el envío
    /// lo dispara una scheduled task / un listener del outbox, no un usuario). El body
    /// (`{to, template, vars}`) lo construye el llamador (server) desde la `NotifyIntent`.
    ///
    /// Los canales **del tenant** (email/sms/WhatsApp self-hosted) NO pasan por aquí: usan el
    /// secreto local cifrado del hub y el host llama directo (sin cuota ERPlora).
    pub fn notify_whatsapp(&self, auth: &Auth) -> PreparedRequest {
        PreparedRequest {
            method: "POST",
            url: format!("{}/api/v1/hub/device/notify/whatsapp/", self.base_url),
            headers: auth.headers(),
        }
    }

    /// **Subida (stream) del backup local → Cloud** (ADR-0040, **opción B** 2026-06-13). La app
    /// **Local (free)** NO habla con S3 ni guarda credenciales AWS: **streamea el dump** (bytes en
    /// claro sobre TLS) a un endpoint del Cloud, que lo escribe a S3 con **cifrado de servidor (SSE)**.
    /// `POST /api/v1/hub/device/backup/` con la credencial de **máquina** del hub (`X-Hub-Token` +
    /// `X-Hub-Id`, contexto hub-scoped sin usuario: el backup lo dispara una scheduled task / la UI,
    /// no un JWT cloud fresco). El Cloud valida entitlement del módulo `backup`, streamea a S3
    /// (`erplora-storage`, key inmutable `backups/local/{hub}/{ts}.dump`) y responde con un
    /// [`BackupUploadResult`] (`s3_key`, `bytes`, ...).
    ///
    /// El **body es el dump** (stream binario, en claro); el cifrado lo hace el Cloud (SSE), **no**
    /// el hub. Metadatos opcionales (tamaño, sha256, versión de esquema, timestamp del cliente) van
    /// en cabeceras. El cuerpo lo aporta el llamador (server/runtime) desde el dump del SQLite.
    /// Espejo del estilo de [`assistant_chat_stream`]/[`notify_whatsapp`]: aquí solo se construye la
    /// petición (método/URL/cabeceras); el I/O del stream lo hace el cliente HTTP del llamador.
    ///
    /// TODO (columna humano, otra capa): el endpoint Django del Cloud no existe aún — lo crea el
    /// humano (`cloud/apps/dashboard/hubs/main/api/hub_api.py`). Contrato fijado aquí.
    pub fn backup_upload(&self, auth: &Auth) -> PreparedRequest {
        PreparedRequest {
            method: "POST",
            url: format!("{}/api/v1/hub/device/backup/", self.base_url),
            headers: auth.headers(),
        }
    }

    /// **Restore, paso 1 — lista las copias del usuario** (ADR-0040, opción B). Mostrar las copias
    /// de las orgs/hubs del usuario (también para "mover a otro equipo") requiere **JWT de usuario**
    /// (no el machine token, que es de un solo hub): `GET /api/v1/hub/device/backup/` con
    /// `Authorization: Bearer …` + `X-Hub-Id`. La respuesta es un array de [`BackupEntry`]
    /// (`s3_key`, `created_at`, `bytes`, `hub_id`, ...). TODO endpoint Django = humano.
    pub fn backup_list(&self, auth: &Auth) -> PreparedRequest {
        self.get("/api/v1/hub/device/backup/", auth)
    }

    /// **Restore, paso 2 — descarga los bytes de una copia** (ADR-0040, opción B). El Cloud sirve el
    /// dump (SSE es transparente: el Cloud lo lee descifrado de S3); el hub lo aplica (reemplaza el
    /// SQLite + reinicia). `GET /api/v1/hub/device/backup/download/?s3_key={s3_key}` con
    /// `Authorization: Bearer …` + `X-Hub-Id` (flujo de usuario, posiblemente cross-hub). Respuesta =
    /// stream binario del dump (en claro). TODO endpoint Django = humano.
    pub fn backup_download(&self, auth: &Auth, s3_key: &str) -> PreparedRequest {
        // El s3_key viaja en query; el llamador debe URL-encodearlo (contiene `/` y `:`).
        self.get(&format!("/api/v1/hub/device/backup/download/?s3_key={s3_key}"), auth)
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

/// Respuesta de [`CloudClient::enroll`]: la credencial de máquina del hub. §2.3.
#[derive(Debug, Clone, Deserialize, PartialEq, Eq)]
pub struct EnrollGrant {
    pub hub_id: String,
    /// Token de aplicación del hub para el header `X-Hub-Token` (contexto máquina).
    pub cloud_api_token: String,
}

impl EnrollGrant {
    pub fn parse(json: &str) -> Result<Self, serde_json::Error> {
        serde_json::from_str(json)
    }
}

/// Respuesta de [`CloudClient::refresh`]: el par de tokens renovado por SimpleJWT (hub#15, §2.3).
/// El `refresh` viene rotado (la vista del Cloud es `RotatingTokenRefreshView`); el Hub debe
/// **persistir el refresh nuevo** y reintentar la petición original con el `access` nuevo.
#[derive(Debug, Clone, Deserialize, PartialEq, Eq)]
pub struct RefreshGrant {
    /// Access JWT nuevo (RS256, ~1h).
    pub access: String,
    /// Refresh token rotado. `None` si el Cloud no rota (no debería con la vista actual).
    #[serde(default)]
    pub refresh: Option<String>,
}

impl RefreshGrant {
    pub fn parse(json: &str) -> Result<Self, serde_json::Error> {
        serde_json::from_str(json)
    }
}

/// Respuesta de [`CloudClient::backup_upload`] (ADR-0040, **opción B**): el resultado de subir
/// (stream) el dump al Cloud, que lo guardó en S3 con **cifrado de servidor (SSE)**. El hub **no**
/// recibe credenciales AWS ni URLs S3: solo dónde quedó la copia y su tamaño, para reflejarlo en
/// `backup_log`. La ruta S3 la fija el Cloud (inmutable/create-only `backups/local/{hub}/{ts}.dump`).
#[derive(Debug, Clone, Deserialize, PartialEq, Eq)]
pub struct BackupUploadResult {
    /// Clave S3 donde quedó el blob (la fija el Cloud).
    pub s3_key: String,
    /// Tamaño en bytes del dump subido (en claro; el cifrado es SSE en reposo, transparente).
    #[serde(default)]
    pub bytes: u64,
    /// SHA256 hex que calculó el Cloud al recibir el stream (opcional, para verificación).
    #[serde(default)]
    pub sha256: Option<String>,
}

impl BackupUploadResult {
    pub fn parse(json: &str) -> Result<Self, serde_json::Error> {
        serde_json::from_str(json)
    }
}

/// Una copia de seguridad tal como la lista [`CloudClient::backup_list`] (restore, opción B). El
/// Cloud devuelve las copias de las orgs/hubs del usuario (también sirve para "mover a otro equipo").
#[derive(Debug, Clone, Deserialize, PartialEq, Eq)]
pub struct BackupEntry {
    /// Clave S3 de la copia (lo que se pasa a [`CloudClient::backup_download`]).
    pub s3_key: String,
    /// Hub al que pertenece la copia (puede no ser el hub actual: restore cross-hub/migración).
    #[serde(default)]
    pub hub_id: String,
    /// Instante de creación (RFC3339).
    #[serde(default)]
    pub created_at: String,
    /// Tamaño en bytes de la copia.
    #[serde(default)]
    pub bytes: u64,
}

impl BackupEntry {
    /// Parsea la lista JSON del endpoint `backup_list`.
    pub fn parse_list(json: &str) -> Result<Vec<BackupEntry>, serde_json::Error> {
        serde_json::from_str(json)
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
    fn notify_whatsapp_uses_machine_token() {
        // WhatsApp premium sale por el proxy de Cloud con la credencial de máquina del hub
        // (X-Hub-Token), no con JWT de usuario: lo dispara una scheduled task / el relay del
        // outbox, sin usuario logueado (ADR-0012/ADR-0003).
        let c = CloudClient::new("https://erplora.com");
        let auth = Auth::HubToken { hub_id: "h1".into(), token: "machine-tok".into() };
        let r = c.notify_whatsapp(&auth);
        assert_eq!(r.method, "POST");
        assert_eq!(r.url, "https://erplora.com/api/v1/hub/device/notify/whatsapp/");
        assert!(r.headers.contains(&("X-Hub-Token", "machine-tok".to_string())));
        assert!(r.headers.contains(&("X-Hub-Id", "h1".to_string())));
    }

    #[test]
    fn backup_upload_uses_machine_token() {
        // El stream del backup lo sube el hub con su credencial de MÁQUINA (X-Hub-Token), no con
        // JWT de usuario: el backup lo dispara una scheduled task / la UI, sin un JWT cloud fresco
        // (ADR-0040 opción B + ADR-0003, contexto hub-scoped sin usuario). El Cloud cifra (SSE).
        let c = CloudClient::new("https://erplora.com");
        let auth = Auth::HubToken { hub_id: "h1".into(), token: "machine-tok".into() };
        let r = c.backup_upload(&auth);
        assert_eq!(r.method, "POST");
        assert_eq!(r.url, "https://erplora.com/api/v1/hub/device/backup/");
        assert!(r.headers.contains(&("X-Hub-Token", "machine-tok".to_string())));
        assert!(r.headers.contains(&("X-Hub-Id", "h1".to_string())));
    }

    #[test]
    fn backup_upload_result_parses() {
        // El Cloud responde con dónde quedó la copia (s3_key) + tamaño/sha (sin URLs ni credenciales).
        let body = r#"{"s3_key":"backups/local/h1/2026-06-13T10:00:00Z.dump",
            "bytes":12345,"sha256":"deadbeef"}"#;
        let g = BackupUploadResult::parse(body).unwrap();
        assert_eq!(g.s3_key, "backups/local/h1/2026-06-13T10:00:00Z.dump");
        assert_eq!(g.bytes, 12345);
        assert_eq!(g.sha256.as_deref(), Some("deadbeef"));
    }

    #[test]
    fn backup_restore_list_and_download_use_user_jwt() {
        // Listar las copias del usuario (posiblemente cross-hub) y descargarlas va con JWT de
        // usuario (opción B): el listado cross-org/hub no lo cubre el machine token (ADR-0040 §4).
        let c = CloudClient::new("https://erplora.com");
        let auth = Auth::UserJwt { hub_id: "h1".into(), access: "abc".into() };

        let l = c.backup_list(&auth);
        assert_eq!(l.method, "GET");
        assert_eq!(l.url, "https://erplora.com/api/v1/hub/device/backup/");
        assert!(l.headers.contains(&("Authorization", "Bearer abc".to_string())));

        let d = c.backup_download(&auth, "backups/local/h1/x.dump");
        assert_eq!(d.method, "GET");
        assert_eq!(d.url, "https://erplora.com/api/v1/hub/device/backup/download/?s3_key=backups/local/h1/x.dump");

        // La lista de copias parsea (array de BackupEntry).
        let body = r#"[{"s3_key":"backups/local/h1/x.dump","hub_id":"h1",
            "created_at":"2026-06-13T10:00:00Z","bytes":999}]"#;
        let entries = BackupEntry::parse_list(body).unwrap();
        assert_eq!(entries.len(), 1);
        assert_eq!(entries[0].hub_id, "h1");
        assert_eq!(entries[0].bytes, 999);
    }

    #[test]
    fn refresh_is_public_post_with_body_token() {
        // El refresh del JWT de usuario va sin cabeceras de auth (el refresh token va en el body).
        let c = CloudClient::new("https://erplora.com");
        let r = c.refresh();
        assert_eq!(r.method, "POST");
        assert_eq!(r.url, "https://erplora.com/api/v1/auth/refresh/");
        assert!(r.headers.is_empty(), "refresh no lleva Authorization ni X-Hub-Id");

        // La respuesta (access nuevo + refresh rotado) parsea.
        let g = RefreshGrant::parse(r#"{"access":"a2","refresh":"r2"}"#).unwrap();
        assert_eq!(g.access, "a2");
        assert_eq!(g.refresh.as_deref(), Some("r2"));
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
