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
pub mod signature;
pub mod user_jwt;

pub use entitlement::{
    verify_entitlement, EntitledModule, EntitlementClaims, EntitlementError, EntitlementResponse,
};
pub use integrity::{verify_sha256, IntegrityError};
pub use signature::{
    ModuleSignature, SignatureError, SignaturePolicy, Signer, TrustedKeyRing,
    PUBLIC_KEY_LEN, SIGNATURE_LEN,
};
pub use user_jwt::{verify_user_jwt, HubMembership, UserClaims, UserJwtError};

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
                vec![
                    ("X-Hub-Id", hub_id.clone()),
                    ("Authorization", format!("Bearer {access}")),
                ]
            }
            Auth::Webhook { hub_id, secret } => {
                vec![
                    ("X-Hub-Id", hub_id.clone()),
                    ("X-Webhook-Secret", secret.clone()),
                ]
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

/// Percent-encode de un valor que va en **un segmento de path** (RFC 3986). Deja intacto el
/// conjunto *unreserved* (`A-Z a-z 0-9 - . _ ~`) y codifica el resto como `%XX`. Sin dependencias
/// (el crate no arrastra `url`/`percent-encoding`). Lo usa `members_remove` para poner el email en
/// el path: `ana+x@bar.com` → `ana%2Bx%40bar.com` (el `.` del dominio se preserva por legibilidad).
fn encode_path_segment(s: &str) -> String {
    let mut out = String::with_capacity(s.len());
    for &b in s.as_bytes() {
        match b {
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'.' | b'_' | b'~' => {
                out.push(b as char)
            }
            _ => out.push_str(&format!("%{b:02X}")),
        }
    }
    out
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
        PreparedRequest {
            method: "GET",
            url: format!("{}{}", self.base_url, path),
            headers: auth.headers(),
        }
    }

    fn public_get(&self, path: &str) -> PreparedRequest {
        PreparedRequest {
            method: "GET",
            url: format!("{}{}", self.base_url, path),
            headers: Vec::new(),
        }
    }

    /// Bootstrap del hub (config inicial), con el token de aplicación. §2.3.
    pub fn bootstrap(&self, hub_id: &str, token: &str) -> PreparedRequest {
        self.get(
            &format!("/api/hubs/{hub_id}/bootstrap/"),
            &Auth::HubToken {
                hub_id: hub_id.to_string(),
                token: token.to_string(),
            },
        )
    }

    /// Lista de módulos del marketplace para el hub (con JWT de usuario). §2.2.
    pub fn marketplace_modules(&self, auth: &Auth) -> PreparedRequest {
        self.get("/api/v1/marketplace/modules/", auth)
    }

    /// Catálogo público de metadatos para Demo. No concede descarga, compra ni entitlement.
    pub fn public_marketplace_modules(&self) -> PreparedRequest {
        self.public_get("/api/v1/marketplace/catalog/")
    }

    /// **Gate de arranque de la app Tauri** — entitlement firmado de módulos del hub
    /// (con JWT de usuario). `GET /api/v1/hub/device/entitlement/`. La respuesta es un
    /// [`EntitlementResponse`]; su `token` se verifica offline con
    /// [`verify_entitlement`] contra la clave pública del Cloud. Ver `entitlement.rs`.
    pub fn entitlement(&self, auth: &Auth) -> PreparedRequest {
        self.get("/api/v1/hub/device/entitlement/", auth)
    }

    /// **Heartbeat de uso/liveness** del Hub hacia el Cloud (hub#199 / saas#806).
    /// `POST /api/v1/hub/device/heartbeat/` con la credencial de máquina; el body
    /// (`orders_today`, `last_sale_at`, `terminals`) lo construye el server desde
    /// la base de datos local. Se ejecuta en el mismo tick que el entitlement.
    pub fn heartbeat(&self, auth: &Auth) -> PreparedRequest {
        PreparedRequest {
            method: "POST",
            url: format!("{}/api/v1/hub/device/heartbeat/", self.base_url),
            headers: auth.headers(),
        }
    }

    /// **Token del Bridge local** — el SaaS emite un JWT dedicado (`aud=erplora-bridge` + `hub_id`,
    /// exp corto) para autorizar el daemon de hardware. `GET /api/v1/hub/device/bridge-token/`. El
    /// runtime lo proxya a la app (el `cloud_api_token` nunca llega al navegador); la app lo presenta
    /// al Bridge en `ws://localhost:12321/ws?token=`. El Bridge lo verifica offline contra la clave
    /// pública del SaaS. Un token de usuario/máquina robado NO sirve (audience distinta). ADR-0050 §2.7.
    pub fn bridge_token(&self, auth: &Auth) -> PreparedRequest {
        self.get("/api/v1/hub/device/bridge-token/", auth)
    }

    /// Redeems the native-shell one-time courier code.  This request is made by the Hub runtime
    /// with its machine credential, never by browser JavaScript, so the SaaS can bind redemption
    /// to the exact destination Hub.  The body (`{"code":"…"}`) is supplied by the caller.
    pub fn session_courier(&self, auth: &Auth) -> PreparedRequest {
        PreparedRequest {
            method: "POST",
            url: format!("{}/api/v1/hub/device/session-courier/", self.base_url),
            headers: auth.headers(),
        }
    }

    /// **Catálogo de blueprints** — plantillas de hub publicadas en el vendor portal del SaaS
    /// ([ADR-0121]). `GET /api/v1/catalog/blueprints/`. Es la **«fuente nube»** del panel de
    /// import (Ajustes → Datos). Hub-scoped: el runtime se autentica **a sí mismo**
    /// (`X-Hub-Token`), así que funciona sin JWT de usuario fresco (el día a día del POS es
    /// sesión local/PIN).
    pub fn blueprints_catalog(&self, auth: &Auth) -> PreparedRequest {
        self.get("/api/v1/catalog/blueprints/", auth)
    }

    /// **Descarga de un blueprint** — devuelve URL **firmada** de Object Storage + `version` +
    /// `sha256`. `GET /api/v1/catalog/blueprints/{slug}/download/`. El runtime baja el zip de esa
    /// URL y **verifica el sha256 ANTES de aplicar nada** (mismo contrato que el install de
    /// módulos: ruta inmutable + hash). [ADR-0121]
    pub fn blueprint_download(&self, slug: &str, auth: &Auth) -> PreparedRequest {
        self.get(
            &format!("/api/v1/catalog/blueprints/{slug}/download/"),
            auth,
        )
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

    /// **Alta de un miembro del hub** (ADR-0157 §7) — `POST /api/v1/hub/device/members/` con la
    /// credencial de **máquina** (`X-Hub-Token`). Cuando un admin del hub da de alta a un usuario
    /// local (con su rol Hub), el runtime avisa al SaaS: éste crea/enlaza la identidad **por email**
    /// + una membresía (pending) + la **invitación**. El SaaS es la fuente de verdad del acceso; el
    /// Hub solo la administra vía esta API. Se usa el token de máquina (no el JWT de usuario) porque
    /// el día a día del POS es sesión local/PIN: casi nunca hay un JWT del SaaS fresco. El body
    /// `{email, role}` lo construye el llamador (server). Ver `members_remove` para la baja.
    pub fn members_add(&self, auth: &Auth) -> PreparedRequest {
        PreparedRequest {
            method: "POST",
            url: format!("{}/api/v1/hub/device/members/", self.base_url),
            headers: auth.headers(),
        }
    }

    /// **Baja de un miembro del hub** (ADR-0157 §7, *simetría obligatoria* del deprovisioning) —
    /// `DELETE /api/v1/hub/device/members/{email}/` con `X-Hub-Token`. Revoca la membresía: el
    /// usuario sigue autenticándose en el SaaS, pero este hub/org **desaparece de su payload** (y el
    /// gate de presencia del Hub deja de dejarle entrar; ventana ≤1 h hasta que caduque su access,
    /// ADR-0157 §9). El `email` va en el path **percent-encoded** (un email lleva `@`/`+`, que no
    /// son seguros en un segmento crudo). El deprovisioning es el fallo típico del invitation flow:
    /// esta baja es su contrapartida obligatoria del alta.
    pub fn members_remove(&self, auth: &Auth, email: &str) -> PreparedRequest {
        PreparedRequest {
            method: "DELETE",
            url: format!(
                "{}/api/v1/hub/device/members/{}/",
                self.base_url,
                encode_path_segment(email)
            ),
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
        self.get(
            &format!("/api/v1/marketplace/modules/{module_id}/versions/"),
            auth,
        )
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
            url: format!(
                "{}/api/v1/marketplace/modules/{module_id}/mark_installed/",
                self.base_url
            ),
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

    /// **Embeddings vía el proxy del Cloud** (§9.3/§9.4/§9.6 — el Hub nunca llama a un proveedor
    /// de embeddings directamente; va por el Cloud, que mide el coste en `AssistantUsage`).
    /// `POST /api/v1/hub/device/assistant/embeddings/` (verificado contra
    /// `cloud/apps/assistant/api/views.py::embed_texts_view`). El body es un
    /// [`EmbeddingsRequest`] (`{"texts":[…], "model"?}`) y la respuesta un
    /// [`EmbeddingsResponse`] (`{"embeddings":[[…]], "model"}`). El cuerpo lo construye el
    /// llamador (server) a partir de los textos a indexar (routing de módulos §9.2b o RAG §9.4).
    ///
    /// Es un endpoint **hub-scoped**: se firma con la credencial de **máquina** del hub
    /// (`X-Hub-Token`) cuando se llama desde el lifecycle de install (sin usuario logueado), o
    /// con el JWT de usuario para la embebida de la petición en query-time del router. El I/O de
    /// red lo hace el cliente HTTP del llamador (espejo de [`assistant_chat_stream`]).
    pub fn embeddings(&self, auth: &Auth) -> PreparedRequest {
        PreparedRequest {
            method: "POST",
            url: format!("{}/api/v1/hub/device/assistant/embeddings/", self.base_url),
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

    /// **Reporte de error del Hub → Cloud** (registro global de errores, "todo controlado"). El
    /// registro del Hub reenvía aquí TODO error (core, módulos, panics, frontend), best-effort.
    /// `POST /api/v1/hub/device/error-report/` con la credencial de **máquina** del hub
    /// (`X-Hub-Token` + `X-Hub-Id`, contexto hub-scoped sin usuario: el reporte lo dispara el
    /// runtime, no un JWT cloud fresco). El **body** es el contrato JSON
    /// `{ source, module_id, error_code, message, stack, severity, context, occurred_at }`, lo
    /// construye el llamador (server) a partir de su `ErrorEvent`. La respuesta
    /// (`{ ok, report_id, fingerprint, count, deduped, issue_queued }`) se ignora: cualquier 2xx
    /// es éxito. Espejo del estilo de [`notify_whatsapp`]: aquí solo se construye la petición
    /// (método/URL/cabeceras); el I/O del POST lo hace el cliente HTTP del llamador.
    pub fn report_error(&self, auth: &Auth) -> PreparedRequest {
        PreparedRequest {
            method: "POST",
            url: format!("{}/api/v1/hub/device/error-report/", self.base_url),
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
    /// Firma ed25519 detached del ZIP (autenticidad, hub#239). `None` si el Cloud aún no la
    /// expone o el publicador no firmó. Bajo `SignaturePolicy::Enforce` un `None` aquí aborta la
    /// instalación (DEFAULT deny); TODO: el serializer del Cloud debe exponerla siempre.
    #[serde(default)]
    pub signature: Option<ModuleSignature>,
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
    /// Firma ed25519 detached del `module.zip` (autenticidad, hub#239). Opcional: el Cloud la
    /// expone cuando el publicador firmó; si falta y la política es `Enforce`, la instalación se
    /// rechaza (`SignatureError::Missing`). Acepta ausencia en el JSON para compat hacia atrás.
    #[serde(default)]
    pub signature: Option<ModuleSignature>,
}

impl InstallGrant {
    pub fn parse(json: &str) -> Result<Self, serde_json::Error> {
        serde_json::from_str(json)
    }

    /// Verifica que `bytes` (el zip descargado) coincide con el `sha256` esperado.
    pub fn verify(&self, bytes: &[u8]) -> Result<(), IntegrityError> {
        verify_sha256(bytes, &self.sha256)
    }

    /// Verifica la **firma** ed25519 de `bytes` bajo `policy` (hub#239). Bajo `Enforce`, exige
    /// firma presente y válida contra el anillo; bajo `DevTrust`, acepta todo. Devuelve el
    /// `key_id` verificado bajo `Enforce` (`None` bajo `DevTrust`).
    pub fn verify_signature(
        &self,
        bytes: &[u8],
        policy: &SignaturePolicy,
    ) -> Result<Option<String>, SignatureError> {
        policy.check(self.signature.as_ref(), bytes)
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

/// Body de [`CloudClient::embeddings`]: los textos a embeber + el modelo opcional. El Cloud
/// usa su modelo por defecto (`text-embedding-3-small`, 1536 dims, casa con `vector(1536)` de
/// §9.4) si `model` es `None`. El límite de `texts` por llamada lo aplica el Cloud (256 hoy);
/// el llamador debe trocear lotes grandes. Se serializa al body de la petición.
#[derive(Debug, Clone, serde::Serialize, PartialEq, Eq)]
pub struct EmbeddingsRequest {
    pub texts: Vec<String>,
    /// Modelo de embeddings; `None` → el Cloud usa su `DEFAULT_EMBED_MODEL`.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub model: Option<String>,
}

impl EmbeddingsRequest {
    /// Construye una petición con los textos dados y el modelo por defecto del Cloud.
    pub fn new(texts: Vec<String>) -> Self {
        Self { texts, model: None }
    }
}

/// Respuesta de [`CloudClient::embeddings`]: un vector por cada texto de entrada (mismo orden) +
/// el modelo realmente usado. El hub almacena estos vectores en su índice local
/// (`erplora-vector`); NUNCA genera embeddings por su cuenta (§9.3).
#[derive(Debug, Clone, Deserialize, PartialEq)]
pub struct EmbeddingsResponse {
    pub embeddings: Vec<Vec<f32>>,
    #[serde(default)]
    pub model: String,
}

impl EmbeddingsResponse {
    pub fn parse(json: &str) -> Result<Self, serde_json::Error> {
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
        let auth = Auth::UserJwt {
            hub_id: "h1".into(),
            access: "abc".into(),
        };
        let r = c.marketplace_modules(&auth);
        assert_eq!(r.url, "https://erplora.com/api/v1/marketplace/modules/");
        assert!(r
            .headers
            .contains(&("Authorization", "Bearer abc".to_string())));
        assert!(r.headers.contains(&("X-Hub-Id", "h1".to_string())));
    }

    /// ADR-0157 §7: alta de un miembro del hub. `POST /api/v1/hub/device/members/` firmado con la
    /// credencial de MÁQUINA (`X-Hub-Token`) — el alta la dispara el runtime, no un usuario con JWT
    /// fresco. El body `{email, role}` lo construye el llamador (server); aquí solo la petición.
    #[test]
    fn members_add_is_machine_token_post() {
        let c = CloudClient::new("https://erplora.com");
        let auth = Auth::HubToken {
            hub_id: "h1".into(),
            token: "tok".into(),
        };
        let r = c.members_add(&auth);
        assert_eq!(r.method, "POST");
        assert_eq!(r.url, "https://erplora.com/api/v1/hub/device/members/");
        assert!(r.headers.contains(&("X-Hub-Token", "tok".to_string())));
        assert!(r.headers.contains(&("X-Hub-Id", "h1".to_string())));
        // Nunca lleva el JWT del usuario: es el HUB quien se autentica a sí mismo.
        assert!(!r.headers.iter().any(|(k, _)| *k == "Authorization"));
    }

    #[test]
    fn session_courier_is_a_machine_authenticated_post() {
        let c = CloudClient::new("https://erplora.com");
        let auth = Auth::HubToken {
            hub_id: "hub-1".into(),
            token: "machine-secret".into(),
        };
        let r = c.session_courier(&auth);
        assert_eq!(r.method, "POST");
        assert_eq!(
            r.url,
            "https://erplora.com/api/v1/hub/device/session-courier/"
        );
        assert!(r
            .headers
            .contains(&("X-Hub-Token", "machine-secret".to_string())));
        assert!(r.headers.contains(&("X-Hub-Id", "hub-1".to_string())));
    }

    /// ADR-0157 §7 (simetría obligatoria del deprovisioning): baja de un miembro por email.
    /// `DELETE /api/v1/hub/device/members/{email}/` con `X-Hub-Token`. El email va en el path
    /// **percent-encoded** (`@`, `+`… no son seguros en un segmento crudo).
    #[test]
    fn members_remove_is_machine_token_delete_with_encoded_email() {
        let c = CloudClient::new("https://erplora.com");
        let auth = Auth::HubToken {
            hub_id: "h1".into(),
            token: "tok".into(),
        };
        let r = c.members_remove(&auth, "ana+x@bar.com");
        assert_eq!(r.method, "DELETE");
        assert_eq!(
            r.url,
            "https://erplora.com/api/v1/hub/device/members/ana%2Bx%40bar.com/",
            "el email va percent-encoded en el path (@→%40, +→%2B); el punto se preserva"
        );
        assert!(r.headers.contains(&("X-Hub-Token", "tok".to_string())));
        assert!(r.headers.contains(&("X-Hub-Id", "h1".to_string())));
    }

    #[test]
    fn public_marketplace_catalog_has_no_hub_credentials() {
        let c = CloudClient::new("https://erplora.com");
        let r = c.public_marketplace_modules();
        assert_eq!(r.url, "https://erplora.com/api/v1/marketplace/catalog/");
        assert!(r.headers.is_empty());
    }

    /// ADR-0121: catálogo de blueprints (la «fuente nube» del import). Hub-scoped: el runtime
    /// se autentica a sí mismo con `X-Hub-Token` — el token NUNCA llega al navegador.
    #[test]
    fn blueprint_catalog_paths_are_hub_scoped() {
        let c = CloudClient::new("https://erplora.com");
        let auth = Auth::HubToken {
            hub_id: "h1".into(),
            token: "tok".into(),
        };

        let list = c.blueprints_catalog(&auth);
        assert_eq!(list.url, "https://erplora.com/api/v1/catalog/blueprints/");
        assert!(list.headers.contains(&("X-Hub-Token", "tok".to_string())));
        assert!(list.headers.contains(&("X-Hub-Id", "h1".to_string())));

        let dl = c.blueprint_download("barberia-basica", &auth);
        assert_eq!(
            dl.url,
            "https://erplora.com/api/v1/catalog/blueprints/barberia-basica/download/"
        );
        assert!(dl.headers.contains(&("X-Hub-Token", "tok".to_string())));
    }

    #[test]
    fn real_install_flow_paths() {
        let c = CloudClient::new("https://erplora.com");
        let auth = Auth::UserJwt {
            hub_id: "h1".into(),
            access: "abc".into(),
        };

        let v = c.versions(&auth, "inventory");
        assert_eq!(v.method, "GET");
        assert_eq!(
            v.url,
            "https://erplora.com/api/v1/marketplace/modules/inventory/versions/"
        );

        let d = c.download(&auth, "inventory", "1.0.0");
        assert_eq!(
            d.url,
            "https://erplora.com/api/v1/marketplace/modules/inventory/download/?version=1.0.0"
        );

        let m = c.mark_installed(&auth, "inventory");
        assert_eq!(m.method, "POST");
        assert_eq!(
            m.url,
            "https://erplora.com/api/v1/marketplace/modules/inventory/mark_installed/"
        );

        let s = c.assistant_chat_stream(&auth);
        assert_eq!(s.method, "POST");
        assert_eq!(
            s.url,
            "https://erplora.com/api/v1/hub/device/assistant/chat/stream/"
        );
        assert!(s
            .headers
            .contains(&("Authorization", "Bearer abc".to_string())));
        assert!(s.headers.contains(&("X-Hub-Id", "h1".to_string())));
    }

    #[test]
    fn embeddings_endpoint_and_machine_token() {
        // La embebida en el lifecycle de install va con la credencial de MÁQUINA del hub
        // (X-Hub-Token): no hay usuario logueado al instalar (§9.6 + ADR-0003).
        let c = CloudClient::new("https://erplora.com");
        let auth = Auth::HubToken {
            hub_id: "h1".into(),
            token: "machine-tok".into(),
        };
        let r = c.embeddings(&auth);
        assert_eq!(r.method, "POST");
        assert_eq!(
            r.url,
            "https://erplora.com/api/v1/hub/device/assistant/embeddings/"
        );
        assert!(r
            .headers
            .contains(&("X-Hub-Token", "machine-tok".to_string())));
        assert!(r.headers.contains(&("X-Hub-Id", "h1".to_string())));
    }

    #[test]
    fn embeddings_request_serializes_with_and_without_model() {
        // Sin modelo: no se serializa la clave `model` (el Cloud usa su default).
        let req = EmbeddingsRequest::new(vec!["hello".into(), "world".into()]);
        let body = serde_json::to_value(&req).unwrap();
        assert_eq!(body["texts"][0], "hello");
        assert!(body.get("model").is_none(), "model None no se serializa");

        // Con modelo explícito.
        let req = EmbeddingsRequest {
            texts: vec!["x".into()],
            model: Some("custom".into()),
        };
        let body = serde_json::to_value(&req).unwrap();
        assert_eq!(body["model"], "custom");
    }

    #[test]
    fn heartbeat_uses_machine_token_and_canonical_path() {
        let c = CloudClient::new("https://erplora.com/");
        let auth = Auth::HubToken {
            hub_id: "h1".into(),
            token: "machine-tok".into(),
        };
        let r = c.heartbeat(&auth);
        assert_eq!(r.method, "POST");
        assert_eq!(r.url, "https://erplora.com/api/v1/hub/device/heartbeat/");
        assert!(r.headers.contains(&("X-Hub-Id", "h1".to_string())));
        assert!(r
            .headers
            .contains(&("X-Hub-Token", "machine-tok".to_string())));
    }

    #[test]
    fn embeddings_response_parses() {
        // El Cloud devuelve un vector por texto (mismo orden) + el modelo usado.
        let body =
            r#"{"embeddings":[[0.1,0.2,0.3],[0.4,0.5,0.6]],"model":"text-embedding-3-small"}"#;
        let resp = EmbeddingsResponse::parse(body).unwrap();
        assert_eq!(resp.embeddings.len(), 2);
        assert_eq!(resp.embeddings[0], vec![0.1, 0.2, 0.3]);
        assert_eq!(resp.model, "text-embedding-3-small");
    }

    #[test]
    fn notify_whatsapp_uses_machine_token() {
        // WhatsApp premium sale por el proxy de Cloud con la credencial de máquina del hub
        // (X-Hub-Token), no con JWT de usuario: lo dispara una scheduled task / el relay del
        // outbox, sin usuario logueado (ADR-0012/ADR-0003).
        let c = CloudClient::new("https://erplora.com");
        let auth = Auth::HubToken {
            hub_id: "h1".into(),
            token: "machine-tok".into(),
        };
        let r = c.notify_whatsapp(&auth);
        assert_eq!(r.method, "POST");
        assert_eq!(
            r.url,
            "https://erplora.com/api/v1/hub/device/notify/whatsapp/"
        );
        assert!(r
            .headers
            .contains(&("X-Hub-Token", "machine-tok".to_string())));
        assert!(r.headers.contains(&("X-Hub-Id", "h1".to_string())));
    }

    #[test]
    fn report_error_uses_machine_token() {
        // El reporte de error lo dispara el runtime con la credencial de MÁQUINA del hub
        // (X-Hub-Token), sin usuario logueado (registro global de errores → Cloud).
        let c = CloudClient::new("https://erplora.com");
        let auth = Auth::HubToken {
            hub_id: "h1".into(),
            token: "machine-tok".into(),
        };
        let r = c.report_error(&auth);
        assert_eq!(r.method, "POST");
        assert_eq!(r.url, "https://erplora.com/api/v1/hub/device/error-report/");
        assert!(r
            .headers
            .contains(&("X-Hub-Token", "machine-tok".to_string())));
        assert!(r.headers.contains(&("X-Hub-Id", "h1".to_string())));
    }

    #[test]
    fn refresh_is_public_post_with_body_token() {
        // El refresh del JWT de usuario va sin cabeceras de auth (el refresh token va en el body).
        let c = CloudClient::new("https://erplora.com");
        let r = c.refresh();
        assert_eq!(r.method, "POST");
        assert_eq!(r.url, "https://erplora.com/api/v1/auth/refresh/");
        assert!(
            r.headers.is_empty(),
            "refresh no lleva Authorization ni X-Hub-Id"
        );

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
