//! Estado compartido del server: el runtime (tras un lock), el canal de eventos para WS,
//! y la configuración de despliegue (hub_id + Cloud Portal + cache de módulos).
use std::path::PathBuf;
use std::sync::{Arc, RwLock};

use erplora_runtime::{EventSink, EventSource, Runtime};
use erplora_vector::VectorStore;
use serde_json::{json, Value as Json};
use tokio::sync::broadcast;

/// Índice vectorial compartido para el routing de tools (§9.2b) y la ingestión de embeddings de
/// módulos al instalar (§9.6). `None` = no hay índice → el asistente degrada a "todos los tools"
/// (§9.5). Es un trait object para no acoplar el server a SQLite vs pgvector.
pub type SharedVectorStore = Arc<dyn VectorStore + Send + Sync>;

/// Frame que se reenvía tal cual a los clientes WebSocket (ya serializado como JSON `Value`).
///
/// Los eventos del runtime se publican con la forma `{"name":…, "payload":…}` (compat con el
/// `EventSink` previo); la instalación de módulos publica el frame exacto que espera el
/// frontend: `{"type":"module.installed","module_id":"…"}`.
pub type WsEvent = Json;

/// The field a frame carries its **emitting module** in (hub#529).
///
/// Written here, next to `name` and `payload`, by the sink — never by the module. It is what
/// `event_stream::may_receive` filters on, so it has to be something the emitter cannot choose:
/// a payload key or an event-name prefix would both be under the module's own control.
///
/// A frame **without** this field is the hub's own (see [`EventSource::Core`] and the raw frames
/// [`AppState::broadcast`] publishes).
pub const FRAME_MODULE: &str = "module";

/// The field a frame carries the **shell tab that caused it** in (hub#1980): the caller's
/// `X-Client-Instance`, stamped by the sink from the request context — like [`FRAME_MODULE`], out
/// of the payload's reach. Absent = no shell sent it (API, flow, scheduler, listener).
///
/// Every till hears every `sale.completed`; this is how the one that charged knows the sale is its
/// own and prints it, and the one next to it knows it is not.
pub const FRAME_CLIENT_INSTANCE: &str = "client_instance";

/// Turns an emitted event into the frame this channel carries. **One builder**, used by the sink
/// and by anything that needs the same shape, so the wire format is defined in exactly one place.
pub fn event_frame(source: EventSource<'_>, event: &str, payload: &Json) -> WsEvent {
    event_frame_from(source, None, event, payload)
}

/// [`event_frame`] for an event a shell's request caused (hub#1980, [`FRAME_CLIENT_INSTANCE`]).
pub fn event_frame_from(
    source: EventSource<'_>,
    client_instance: Option<&str>,
    event: &str,
    payload: &Json,
) -> WsEvent {
    let mut frame = json!({ "name": event, "payload": payload });
    if let Some(module_id) = source.module_id() {
        frame[FRAME_MODULE] = json!(module_id);
    }
    if let Some(instance) = client_instance {
        frame[FRAME_CLIENT_INSTANCE] = json!(instance);
    }
    frame
}

/// Implementa `EventSink` del runtime publicando en un canal broadcast (→ WebSocket).
#[derive(Debug)]
pub struct BroadcastSink {
    tx: broadcast::Sender<WsEvent>,
}

impl EventSink for BroadcastSink {
    fn emit(&self, source: EventSource<'_>, event: &str, payload: &Json) {
        // Si no hay suscriptores, `send` falla; lo ignoramos a propósito.
        let _ = self.tx.send(event_frame(source, event, payload));
    }

    fn emit_from(
        &self,
        source: EventSource<'_>,
        client_instance: Option<&str>,
        event: &str,
        payload: &Json,
    ) {
        let _ = self
            .tx
            .send(event_frame_from(source, client_instance, event, payload));
    }
}

/// Modo de autenticación del server (ARQUITECTURA.md §2.3/§2.9):
///  - `Dev`: confía en cabeceras `X-User-Id`/`X-Permissions` (desarrollo local, sin Cloud).
///  - `Session`: identidad LOCAL real. El login (PIN o JWT cloud) abre una **sesión server-side**
///    (`hub_session`); cada petición lleva `X-Hub-Session` y el runtime resuelve el `hub_user` y
///    sus permisos por rol. Es el modo de **producción** y el **default** (fail-closed).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum AuthMode {
    Dev,
    Session,
}

/// Variable de entorno que selecciona el [`AuthMode`].
pub const AUTH_MODE_ENV: &str = "HUB_AUTH";

/// Resuelve el [`AuthMode`] desde el valor crudo de `HUB_AUTH` (**fail-closed**, hub#241).
///
/// El default era `Dev`: un despliegue que olvidara la variable arrancaba **sin autenticación**
/// (el navegador dictaba `X-User-Id`/`X-Permissions`) y nadie se enteraba, porque todo "funcionaba".
/// Un fallo de configuración no puede abrir el hub: sin variable → [`AuthMode::Session`]
/// (producción/Cloud). El modo de desarrollo se pide **explícitamente** con `HUB_AUTH=dev`.
///
/// Un valor desconocido también cae a `Session` con un aviso: un typo (`HUB_AUTH=develop`) no
/// puede degradar la seguridad del hub.
pub fn parse_auth_mode(raw: Option<&str>) -> AuthMode {
    match raw.map(str::trim) {
        Some("dev") => AuthMode::Dev,
        Some("session") | None => AuthMode::Session,
        Some(other) => {
            eprintln!(
                "auth: {AUTH_MODE_ENV}=`{other}` no es un modo conocido (`dev`|`session`) → \
                 se usa `session` (fail-closed)"
            );
            AuthMode::Session
        }
    }
}

/// ¿Está **armada** la puerta de device-trust del login por PIN? (`HUB_DEVICE_TRUST`, hub#330.)
///
/// **Fail-closed, como su vecina de arriba**: sin variable, o con un valor que este build no
/// conoce, la puerta queda **armada**. El único valor que la desarma es la palabra `off`, escrita
/// a propósito por el despliegue.
///
/// Por qué el default cambió de lado: hasta ADR-0257 (hub#454) el navegador no tenía identidad
/// propia —presentaba el `hub_id`, o nada—, así que armarla habría dejado un hub recién creado sin
/// ningún login por PIN posible. Ya la tiene, y desde el primer arranque. Lo que queda al otro lado
/// del interruptor es un PIN de **cuatro dígitos** contestando a internet entero en
/// `{slug}.erplora.com`, con la lista de nombres publicada sin sesión por `GET /api/hub/context`:
/// el device-trust es el segundo factor de *sitio* que hace que esos cuatro dígitos valgan algo.
///
/// `false`, `0` y `no` **arman** la puerta, aunque suenen a interruptor. Honrarlos daría tres
/// grafías de «abierto» contra una de «cerrado», y la que se colara sería siempre la insegura.
pub fn parse_device_trust(raw: Option<&str>) -> bool {
    match raw.map(|s| s.trim().to_ascii_lowercase()).as_deref() {
        Some("off") => false,
        Some("enforce") | None => true,
        Some(other) => {
            eprintln!(
                "auth: HUB_DEVICE_TRUST=`{other}` no es un valor conocido (`enforce`|`off`) → \
                 se mantiene armada (fail-closed)"
            );
            true
        }
    }
}

/// Variable de entorno que marca este despliegue como **DEMO efímera** (ADR-0197, hub#376). Se
/// llama como la columna que la escribe (`Hub.is_demo` del SaaS) para que el contrato se lea de un
/// vistazo en `_build_hub_env_swarm`.
pub const DEMO_ENV: &str = "HUB_DEMO";

/// ¿El despliegue declara que este hub es una **demo efímera**? (ADR-0197 §4).
///
/// Solo `1`/`true`/`yes`/`on` (sin distinguir mayúsculas, recortado) encienden; ausente, vacío o
/// cualquier otra cosa = **hub normal**. Misma forma que [`crate::install_guard::parse_dev_mode`],
/// y el default apunta al otro lado a propósito: encender por error los cierres de la demo en un
/// hub REAL le congelaría la identidad fiscal y lo dejaría fuera de producción **en silencio**,
/// que es el peor de los dos errores posibles.
pub fn parse_demo_flag(raw: Option<&str>) -> bool {
    matches!(
        raw.map(|s| s.trim().to_ascii_lowercase()).as_deref(),
        Some("1" | "true" | "yes" | "on")
    )
}

/// The Cloud Portal URL [`HubConfig::from_env_with_auth`] falls back to when `HUB_CLOUD_API_URL`
/// is not set. Named as a constant so the default and [`cloud_url_guard`] always compare against
/// the exact same string — two literals here could silently drift apart.
pub const PRODUCTION_CLOUD_BASE_URL: &str = "https://erplora.com";

/// What a `HUB_DEV_MODE=1` runtime should do about a `cloud_base_url` that resolved to the
/// **production** default (hub#1279).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CloudUrlGuard {
    /// Nothing to flag: not dev mode, or `cloud_base_url` isn't the production default.
    Ok,
    /// Dev mode + production default + not CI: warn loudly, keep starting.
    Warn,
    /// Dev mode + production default + CI: refuse to start.
    Refuse,
}

/// Decides [`CloudUrlGuard`] from the three inputs that matter, as a **pure function** — so both
/// branches are unit-tested without touching process env or actually starting the server.
///
/// The gap this closes (hub#1279): a **deployed** hub always has `HUB_CLOUD_API_URL` injected by
/// provisioning (Hetzner and AWS providers both set it from `settings.CLOUD_BASE_URL`), so the
/// fallback in [`HubConfig::from_env_with_auth`] only ever fires for a process started OUTSIDE
/// provisioning — a Playwright bench, a `cargo run` helper, `pnpm dev`. Exactly that silently
/// called PRODUCTION from the CI runner before hub#1277 pinned the one caller that mattered
/// (`apps/web/tests/playwright.config.ts`); nothing stopped the *next* bench from repeating it.
///
/// `dev_mode` scopes the guard on purpose: it is the only signal that this is a bench/dev
/// process, not a real hub. `pnpm dev` (`scripts/dev.mjs`) sets `HUB_DEV_MODE=1` and deliberately
/// keeps pointing at production (see the `/hub-local` skill) — refusing on `dev_mode` alone would
/// break it. `ci` is what tells the two apart: it is the signal that nobody is at the terminal to
/// read a warning, so unattended-in-CI is the only case that hard-refuses.
pub fn cloud_url_guard(dev_mode: bool, cloud_base_url: &str, ci: bool) -> CloudUrlGuard {
    if !dev_mode || cloud_base_url.trim() != PRODUCTION_CLOUD_BASE_URL {
        return CloudUrlGuard::Ok;
    }
    if ci {
        CloudUrlGuard::Refuse
    } else {
        CloudUrlGuard::Warn
    }
}

/// Carpeta media del hub (`HUB_MEDIA_DIR`, por defecto `./media`).
///
/// Aparte de [`HubConfig::from_env_with_auth`] porque el arranque la necesita **antes** de que
/// exista el `AppState`: el backend de ficheros de módulos se inyecta en el runtime antes de
/// instalar nada (hub#1477). Una sola definición para que las dos rutas no puedan discrepar — dos
/// hubs mirando carpetas distintas es exactamente el fallo que nadie encuentra.
pub fn media_dir_from_env() -> PathBuf {
    std::env::var("HUB_MEDIA_DIR")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("media"))
}

/// Configuración de despliegue del hub (ARQUITECTURA.md §2.3; decisiones del humano):
///  - `hub_id`: lo inyecta el despliegue vía env `HUB_ID` (sin selector de hub).
///  - `cloud_base_url`: el Cloud Portal contra el que se resuelven marketplace + asistente.
///  - `module_cache`: raíz local donde `erplora-source` descomprime los módulos descargados.
///  - `auth_mode` + `jwt_public_key`: ver [`AuthMode`]. La clave pública (PEM) la resuelve
///    `main` al arrancar (env `HUB_JWT_PUBLIC_KEY` o `GET /api/v1/auth/public-key/` del Cloud).
#[derive(Clone, Debug)]
pub struct HubConfig {
    pub hub_id: String,
    pub cloud_base_url: String,
    pub module_cache: PathBuf,
    pub auth_mode: AuthMode,
    pub jwt_public_key: Option<String>,
    /// Credencial de **máquina** del hub para hablar con el Cloud en endpoints hub-scoped
    /// (marketplace, entitlement, asistente, install) **sin** usuario logueado.
    ///
    /// **La inyecta el aprovisionamiento** como env `HUB_CLOUD_API_TOKEN`. Desde ADR-0467
    /// (saas#1928) es una **API key** (`erpk_<live|pre>_…`) que el SaaS acuña **en cada
    /// despliegue** y guarda solo como hash; la anterior caduca a los 7 días. Viaja como
    /// `X-Api-Key`; un hub desplegado antes del cambio aún lleva el `cloud_api_token` legado y lo
    /// manda como `X-Hub-Token` — el header lo decide la forma (`cloud_client::is_api_key`) y el
    /// SaaS acepta los dos. No lo pide nadie.
    ///
    /// Es un **secreto del runtime**: vive solo aquí, nunca en el navegador. Y como desde ADR-0154 el
    /// runtime corre en el contenedor del hub —no dentro de la app instalable—, **la app NUNCA lo
    /// tiene**: N dispositivos con la app hablan con UN hub, que es quien lo guarda.
    ///
    /// ⚠️ Aquí ponía que «la persiste el shell Tauri tras enrolar». Era de cuando la app llevaba el
    /// runtime dentro, y ADR-0154 se lo llevó: no hay una sola línea en `apps/tauri` que toque este
    /// token. `cloud-client` sigue exponiendo `GET/POST /api/v1/hub/device/enroll/`, pero **nadie en
    /// el hub lo llama**.
    ///
    /// `None` = hub creado **fuera** del aprovisionamiento (un `pnpm dev` local): el SaaS no sabe que
    /// existe, así que marketplace, entitlement, asistente y el almacenamiento de VeriFactu quedan
    /// muertos. Se cae al JWT del usuario activo donde eso basta. Ver ARQUITECTURA.md §2.3.
    pub cloud_api_token: Option<String>,
    /// Raíz de la carpeta `media/` del hub: path por defecto de TODOS los ficheros (adjuntos de
    /// módulos, registros `_logs/`, actividad `_system/`). La navega la pantalla /files
    /// (`crate::media`). La inyecta el despliegue vía env `HUB_MEDIA_DIR`; default `./media`
    /// (relativo al CWD del proceso), creado de forma perezosa al primer acceso. En cloud (S3) el
    /// listado de objetos es follow-up del humano (igual que documentos en `system.rs`).
    pub media_dir: PathBuf,
    /// **Device-trust** del login por PIN (§2.9, hub#15 · hub#330). Armada, la puerta del PIN exige
    /// que el cliente identifique el dispositivo **y** que ese dispositivo sea de confianza (lo pasa
    /// a serlo un login online previo *en él*). Sin `device_id` se rechaza: omitirlo era el bypass.
    ///
    /// **Armada por defecto**; `HUB_DEVICE_TRUST=off` la desarma (ver [`parse_device_trust`]). Lo
    /// que cambia para quien la encuentra cerrada: el PIN no vale todavía en ese dispositivo y hay
    /// que entrar **una vez** con la cuenta ahí — la pantalla de login lo dice con esas palabras y
    /// ofrece esa puerta, que es más fuerte, nunca más débil. Desarmarla es un gesto para un
    /// despliegue que sepa por qué (p. ej. un banco de pruebas sin cuenta que acreditar).
    pub device_trust_enforce: bool,
    /// **Sector / tipo de negocio** del hub (`hosteleria`|`retail`|`gestoria`|`rrhh`|`belleza`|`general`), lo
    /// inyecta el despliegue vía env `HUB_SECTOR` (hermano de `HUB_LANGUAGE`/`HUB_CURRENCY`). Lo
    /// expone `GET /api/hub/context` para que el dashboard derive el preset "Recomendado" de widgets
    /// (ADR-0054). `None` = sector no determinable → el board degrada (preset vacío, el usuario activa
    /// widgets a mano). El Cloud captura el tipo de negocio en el onboarding y lo traduce a este env en
    /// la inyección ECS (`aws.py::BUSINESS_TYPE_TO_SECTOR`, ADR-0071); `belleza` = preset del vertical
    /// servicios/peluquería. El sector NO se persiste en el modelo `Hub` (vive en
    /// `pending_metadata['business_type']`): este env es la fuente del contrato runtime↔Cloud.
    pub sector: Option<String>,
    /// **Modo desarrollo explícito** (`HUB_DEV_MODE`, hub#239). Abre las vías de carga de código
    /// LOCAL —`POST /api/modules/install {dir}` y el escaneo de [`Self::dev_modules_dir`] al
    /// arrancar— que esquivan el pipeline del marketplace (grant + SHA256 obligatorio, ADR-0015).
    /// **Fail-closed**: `false` salvo que el env lo active (el provisioning del SaaS nunca lo
    /// inyecta ⇒ en producción esas vías están apagadas). Ver [`crate::install_guard`].
    pub dev_mode: bool,
    /// `HUB_MODULES_DIR`: carpeta de módulos de DESARROLLO (el workspace de módulos del monorepo).
    /// Se escanea al arrancar **solo** con [`Self::dev_mode`], y es la segunda raíz de staging
    /// admitida por `POST /api/modules/install`. En producción el despliegue la fija a
    /// `/tmp/modules` (contenedor stateless) y se IGNORA.
    pub dev_modules_dir: Option<PathBuf>,
    /// Claves públicas ed25519 de confianza para verificar la firma de módulos del marketplace
    /// (hub#239), codificadas en hex o base64. Se cargan de `HUB_MODULE_TRUSTED_KEYS` (coma-sep);
    /// los tests pueden inyectarlas directamente aquí (sin tocar el env global del proceso).
    /// Vacío ⇒ anillo vacío ⇒ **deny-all** bajo [`Self::signature_policy`] en producción.
    pub module_trusted_keys: Vec<String>,
    /// **Este despliegue es una DEMO efímera** (`HUB_DEMO`, ADR-0197 — hub#376). Lo escribe el
    /// provisioning del SaaS al crear la instancia (espejo de su columna `Hub.is_demo`), por el
    /// mismo canal que `HUB_AUTH` o `HUB_CLOUD_API_TOKEN`: env del contenedor.
    ///
    /// **Qué lo hace no falsificable**: es env del despliegue, se lee UNA vez al arrancar y no
    /// tiene escritor en el hub — ni cabecera, ni campo de payload, ni clave de `hub_settings`, ni
    /// endpoint. El navegador no puede tocarlo, y un `command` tampoco. Es el mismo argumento por
    /// el que vale `X-Hub-Id`: la autoridad la pone quien despliega, no quien llama.
    ///
    /// **Fail-closed hacia hub NORMAL**: ausente ⇒ `false`. Es la dirección segura de las dos.
    /// Tomar por demo a un hub REAL le congelaría la identidad fiscal y lo dejaría fuera de
    /// producción sin decir nada — que es exactamente la clase de error que auto-borraba el hub
    /// propio de ERPlora. Al revés, una demo sin la variable solo queda topada por la guarda R5
    /// del SaaS (hub#315): desde `verifactu-gateway.md` §3.4 (supersede ADR-0197 §2) la demo SÍ
    /// lleva el certificado delegado, así que quien escriba esta clave es parte de la guarda.
    ///
    /// ⚠️ No confundir con [`AppState::is_dev_hub`], que es el modo `dev` de auth.
    pub demo: bool,
}

/// UUID fijo de desarrollo si no se inyecta `HUB_ID` (decisión tomada — flag para humano).
pub const DEV_HUB_ID: &str = "00000000-0000-0000-0000-000000000001";

impl HubConfig {
    /// Lee la configuración del entorno. El [`AuthMode`] sale de `HUB_AUTH` **fail-closed**
    /// (sin variable → `Session`, ver [`parse_auth_mode`]).
    pub fn from_env() -> Self {
        // Fail-closed (hub#241): sin `HUB_AUTH` se arranca en modo producción (`Session`).
        let raw_auth = std::env::var(AUTH_MODE_ENV).ok();
        Self::from_env_with_auth(parse_auth_mode(raw_auth.as_deref()))
    }

    /// Como [`from_env`](Self::from_env) pero con el [`AuthMode`] **explícito**. Es la vía por la
    /// que un test (o un arranque controlado) pide el modo `Dev` sin depender de una variable de
    /// proceso compartida: desde hub#241 el default del entorno es `Session` (fail-closed), así
    /// que el modo permisivo hay que pedirlo a propósito, también en los tests.
    pub fn from_env_with_auth(auth_mode: AuthMode) -> Self {
        let hub_id = std::env::var("HUB_ID").unwrap_or_else(|_| DEV_HUB_ID.to_string());
        let cloud_base_url = std::env::var("HUB_CLOUD_API_URL")
            .unwrap_or_else(|_| PRODUCTION_CLOUD_BASE_URL.to_string());
        let module_cache = std::env::var("HUB_MODULE_CACHE")
            .map(PathBuf::from)
            .unwrap_or_else(|_| std::env::temp_dir().join("erplora-modules"));
        // Inyección directa de la clave (PEM) por entorno; si no, `main` la trae del Cloud.
        let jwt_public_key = std::env::var("HUB_JWT_PUBLIC_KEY")
            .ok()
            .filter(|s| !s.trim().is_empty());
        // Token de máquina: lo inyecta el APROVISIONAMIENTO como `HUB_CLOUD_API_TOKEN`. Vacío = hub
        // creado fuera de él (p. ej. `pnpm dev`) → sin marketplace/entitlement/asistente/VeriFactu.
        let cloud_api_token = std::env::var("HUB_CLOUD_API_TOKEN")
            .ok()
            .filter(|s| !s.trim().is_empty());
        // Armed by default (hub#330). The precondition that kept it opt-in — a browser with no
        // identity of its own — went away with hub#454; see `parse_device_trust`.
        let device_trust_enforce =
            parse_device_trust(std::env::var("HUB_DEVICE_TRUST").ok().as_deref());
        // Sector / tipo de negocio del hub (preset "Recomendado" del dashboard, ADR-0054). Vacío o
        // ausente → `None` (degradación elegante; el board sigue funcionando sin preset).
        let sector = std::env::var("HUB_SECTOR")
            .ok()
            .map(|s| s.trim().to_string())
            .filter(|s| !s.is_empty());
        // Carpeta media del hub (logs `_logs/`, perfiles, export/import…). Por defecto `./media`;
        // el despliegue la fija explícitamente con `HUB_MEDIA_DIR`. En Hub Cloud (ADR-0154) los
        // ficheros de módulos viven en Object Storage vía el Cloud; `media_dir` es scratch local.
        let media_dir = media_dir_from_env();
        // Modo desarrollo explícito (hub#239): abre las vías de carga de código LOCAL. Ausente o
        // con cualquier otro valor ⇒ producción (fail-closed).
        let dev_mode =
            crate::install_guard::parse_dev_mode(std::env::var("HUB_DEV_MODE").ok().as_deref());
        let dev_modules_dir = std::env::var("HUB_MODULES_DIR")
            .ok()
            .filter(|s| !s.trim().is_empty())
            .map(PathBuf::from);
        // Claves públicas ed25519 de confianza para verificar firma de módulos (hub#239):
        // `HUB_MODULE_TRUSTED_KEYS=k1=hex,k2=base64,...`. Vacío/ausente ⇒ anillo vacío (deny-all
        // en producción). Las entradas ilegibles se ignoran con WARN en `signature_policy`.
        let module_trusted_keys = std::env::var("HUB_MODULE_TRUSTED_KEYS")
            .ok()
            .map(|raw| {
                raw.split(',')
                    .map(str::trim)
                    .filter(|s| !s.is_empty())
                    .map(str::to_string)
                    .collect::<Vec<_>>()
            })
            .unwrap_or_default();
        // ⚠️ `HUB_BOOTSTRAP_BLUEPRINT` / `HUB_BOOTSTRAP_BLUEPRINT_LOCALE` ya NO se leen: un hub nace
        // VACÍO (ADR-0293). El despliegue puede seguir inyectándolas —el SaaS lo hace para las
        // demos— y el hub las ignora a propósito. Ver `crates/server/src/lib.rs` (final de `serve`).
        //
        // Marcador de DEMO efímera (ADR-0197). Ausente o con cualquier otro valor ⇒ hub normal.
        let demo = parse_demo_flag(std::env::var(DEMO_ENV).ok().as_deref());
        Self {
            hub_id,
            cloud_base_url,
            module_cache,
            auth_mode,
            jwt_public_key,
            cloud_api_token,
            device_trust_enforce,
            media_dir,
            sector,
            dev_mode,
            dev_modules_dir,
            module_trusted_keys,
            demo,
        }
    }

    /// Raíces de staging admitidas por `POST /api/modules/install {dir}` (hub#239): la **caché de
    /// descargas** (donde `erplora-source` extrae los zips ya verificados por SHA256) y, **solo en
    /// modo desarrollo**, la carpeta de módulos de dev. Cualquier `dir` fuera de estas raíces
    /// —tras canonicalizar— se rechaza. Ver [`crate::install_guard::resolve_install_dir`].
    ///
    /// En producción `dev_modules_dir` es `/tmp/modules` (contenedor stateless): un directorio
    /// escribible que NO debe ser staging válido ni aunque la vía se reabriera por error.
    pub fn install_staging_roots(&self) -> Vec<PathBuf> {
        let mut roots = vec![self.module_cache.clone()];
        if self.dev_mode {
            if let Some(dev_dir) = &self.dev_modules_dir {
                roots.push(dev_dir.clone());
            }
        }
        roots
    }

    /// Política de verificación de **firma** de módulos (hub#239, ADR-0193/0194). Tres casos, y el
    /// que los separa es **si el despliegue dijo algo o no**:
    ///
    /// - **Desarrollo** (`dev_mode`): [`SignaturePolicy::DevTrust`] — acepta módulos sin firmar
    ///   (los módulos horneados del monorepo y los instalados desde carpeta no se firman en local).
    ///   Es el escape hatch **explícito** del flag de dev; si `HUB_MODULE_TRUSTED_KEYS` trae claves,
    ///   se respetan igual (un módulo firmado valida; uno sin firma se admite por el hatch).
    /// - **Producción con anillo** (una clave o más cargan): [`SignaturePolicy::Enforce`]. Desplegar
    ///   la clave es el interruptor que enciende la verificación, sin tocar código ni imagen.
    /// - **Producción sin anillo**: depende de si `HUB_MODULE_TRUSTED_KEYS` venía **vacío/ausente**
    ///   o **puesto pero ilegible**:
    ///   - vacío/ausente ⇒ [`SignaturePolicy::Sha256Only`], el modo `warn` de ADR-0193: no hay
    ///     infraestructura de firma desplegada y la integridad la cubre el SHA256 del grant
    ///     (ADR-0015). Exigir firma aquí denegaría el 100 % de las instalaciones legítimas
    ///     (ADR-0194: así se tumbó el arranque de todo hub nuevo el 2026-08-03);
    ///   - puesto y sin NINGUNA clave legible ⇒ `Enforce` con el anillo vacío (hub#870). Eso no es
    ///     «no hay firma»: es una configuración rota en un hub que alguien creyó haber protegido,
    ///     y degradar ahí es fail-open mudo. No instala, pero sigue vendiendo.
    ///
    /// El anillo es **estático por arranque**: cambiarlo o revocar una clave exige redesplegar el
    /// hub. Es suficiente para el día 1 y es lo que sigue hub#1751.
    pub fn signature_policy(&self) -> cloud_client::SignaturePolicy {
        self.resolve_signature().0
    }

    /// What the boot has to TELL about the policy above (hub#1754). Same resolution, different
    /// question: [`Self::signature_policy`] answers what this hub enforces, this answers what the
    /// operator is owed about it — including the two cases the policy alone cannot express (a ring
    /// that loaded with entries dropped, and a ring that loaded with none).
    pub fn signature_mode(&self) -> SignatureMode {
        self.resolve_signature().1
    }

    /// Writes the ONE line that says whether this hub verifies module signatures (hub#1754).
    ///
    /// Called once from the composition root, **unconditionally**. Until hub#1754 the policy was
    /// logged as a side effect of [`Self::signature_policy`] being called, and that only happens
    /// when something installs: a hub that was just provisioned installs nothing at boot, so the
    /// deployment whose ring was pasted a minute ago —the one where a typo costs most— was also
    /// the one that started up mute. Whoever redeploys now sees the mode in the first screen of
    /// the log instead of discovering it later, through an install that will not go through.
    pub fn announce_signature_policy(&self) {
        let mode = self.signature_mode();
        let tag = mode.tag();
        let message = mode.message();
        // The level comes from `SignatureMode::level` and nowhere else, so the boot line and the
        // test that pins its severity read the same source.
        match mode.level() {
            tracing::Level::ERROR => tracing::error!(signature = tag, "{}", message),
            tracing::Level::WARN => tracing::warn!(signature = tag, "{}", message),
            _ => tracing::info!(signature = tag, "{}", message),
        }
    }

    /// Builds the trust ring ONCE and answers both questions about it at the same time. Splitting
    /// it in two would let the announced mode and the enforced policy drift apart, which is the
    /// one bug this whole area cannot afford.
    fn resolve_signature(&self) -> (cloud_client::SignaturePolicy, SignatureMode) {
        // The ring is built from the config's `module_trusted_keys` (read from the env in
        // `from_env`, or injected by tests). `from_env` takes the raw format with or without
        // `key_id=`; reusing it avoids a second parser.
        let joined = self.module_trusted_keys.join(",");
        let (ring, bad) = cloud_client::TrustedKeyRing::from_env(Some(&joined));

        if self.dev_mode {
            // Explicit escape hatch: dev accepts unsigned modules. The ring is still built in case
            // a dev flow wants to exercise verification (nothing is forced here).
            return (cloud_client::SignaturePolicy::DevTrust, SignatureMode::DevTrust);
        }
        if ring.is_empty() {
            if !bad.is_empty() {
                // hub#870: the variable came WITH content and not one key could be loaded. That is
                // not "no signing deployed" (the case below): it is a deployment somebody believes
                // is protected —a hex truncated on paste, a `key_id` split in the wrong place—.
                // Degrading here would be fail-open exactly where trust is highest. Signature is
                // required against the ring that did load (empty): **nothing installs**, but the
                // hub keeps selling, which is what cannot stop.
                return (
                    cloud_client::SignaturePolicy::Enforce(ring),
                    SignatureMode::Misconfigured {
                        unreadable: bad.len(),
                    },
                );
            }
            // ADR-0194: an empty ring means **no signing infrastructure is deployed**, not "reject
            // everything". It is the `warn` mode ADR-0193 already required in its consequences.
            // `Enforce` here protected nothing: it denied 100 % of the legitimate installs (403 on
            // `request-install` and on blueprint import) because NOBODY signs yet. The control in
            // force is still the mandatory grant SHA256 (ADR-0015).
            return (
                cloud_client::SignaturePolicy::Sha256Only,
                SignatureMode::NotVerifying,
            );
        }
        let mode = SignatureMode::Verifying {
            keys: ring.len(),
            ignored: bad.len(),
        };
        (cloud_client::SignaturePolicy::Enforce(ring), mode)
    }
}

/// How this hub ended up verifying module signatures, as the boot announces it (hub#1754).
///
/// It is not a second policy: it is the same resolution seen from the operator's side, carrying
/// the counters the policy drops (how many keys loaded, how many entries were unreadable) because
/// those are exactly what tells a ring that was pasted whole from one that was pasted half.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SignatureMode {
    /// A ring loaded: this hub checks WHO signed each module. `ignored` entries were dropped.
    Verifying { keys: usize, ignored: usize },
    /// No ring deployed — the whole fleet, today. Integrity is the grant SHA256 (ADR-0015/0194).
    NotVerifying,
    /// `HUB_MODULE_TRUSTED_KEYS` is set and not one entry parsed (hub#870): nothing will install.
    Misconfigured { unreadable: usize },
    /// `HUB_DEV_MODE`: unsigned modules are accepted on purpose.
    DevTrust,
}

impl SignatureMode {
    /// Greppable tag written as `signature=<tag>`, so the boot line can be found by mode without
    /// matching on prose (ADR-0055: the code is the contract, not the sentence).
    pub fn tag(self) -> &'static str {
        match self {
            Self::Verifying { .. } => "verifying",
            Self::NotVerifying => "not_verifying",
            Self::Misconfigured { .. } => "misconfigured",
            Self::DevTrust => "dev_trust",
        }
    }

    /// Severity of the boot line: INFO when the hub verifies, WARN when it does not, ERROR when
    /// the configuration is broken and no module will install.
    ///
    /// A ring that loaded **with entries dropped** verifies, so its mode is `Verifying` — but it
    /// keeps the WARN it had before hub#1754. Folding it into the INFO would hide a half-pasted
    /// ring behind good news, which is the same silence this issue came to remove.
    pub fn level(self) -> tracing::Level {
        match self {
            Self::Verifying { ignored: 0, .. } => tracing::Level::INFO,
            Self::Verifying { .. } | Self::NotVerifying | Self::DevTrust => tracing::Level::WARN,
            Self::Misconfigured { .. } => tracing::Level::ERROR,
        }
    }

    /// The sentence the operator reads, with what to do next when there is something to do.
    pub fn message(self) -> String {
        match self {
            Self::Verifying { keys, ignored: 0 } => format!(
                "module signatures ARE verified: {keys} trusted key(s) loaded from \
                 `HUB_MODULE_TRUSTED_KEYS`"
            ),
            Self::Verifying { keys, ignored } => format!(
                "module signatures ARE verified with {keys} trusted key(s), but {ignored} entry \
                 (entries) of `HUB_MODULE_TRUSTED_KEYS` could not be read and were ignored. \
                 Expected format per entry: `<key_id>=<64 hex chars>`."
            ),
            Self::NotVerifying => "module signatures are NOT verified: `HUB_MODULE_TRUSTED_KEYS` \
                 is empty, so nothing checks who signed a module. Integrity is the mandatory \
                 grant SHA256 (ADR-0015). Deploy the marketplace public key to turn verification \
                 on (ADR-0194)."
                .to_string(),
            Self::Misconfigured { unreadable } => format!(
                "`HUB_MODULE_TRUSTED_KEYS` is set but NONE of its {unreadable} entries can be \
                 read: no module will install until it is fixed. Expected format: \
                 `<key_id>=<64 hex chars>` (what `GET /api/v1/marketplace/signing-key/` serves)."
            ),
            Self::DevTrust => "module signatures are NOT enforced: `HUB_DEV_MODE` accepts \
                 unsigned modules on purpose. A production deployment must never boot like this."
                .to_string(),
        }
    }
}

#[cfg(test)]
mod staging_tests {
    use super::*;

    fn config(dev_mode: bool) -> HubConfig {
        config_with_keys(dev_mode, Vec::new())
    }

    fn config_with_keys(dev_mode: bool, module_trusted_keys: Vec<String>) -> HubConfig {
        HubConfig {
            demo: false,
            hub_id: "h1".into(),
            cloud_base_url: "http://127.0.0.1:1".into(),
            module_cache: PathBuf::from("/var/cache/erplora"),
            auth_mode: AuthMode::Session,
            jwt_public_key: None,
            cloud_api_token: None,
            device_trust_enforce: false,
            media_dir: PathBuf::from("/var/media"),
            sector: None,
            dev_mode,
            dev_modules_dir: Some(PathBuf::from("/tmp/modules")),
            module_trusted_keys,
        }
    }

    /// 🔴 El defecto que tumbó producción (2026-08-03): un hub desplegado SIN
    /// `HUB_MODULE_TRUSTED_KEYS` quedaba en `Enforce(<anillo vacío>)` = **deny-all**, y como el
    /// marketplace NO firma ningún módulo (el `ModuleVersionSerializer` del SaaS ni siquiera tiene
    /// campo `signature`), TODA instalación devolvía 403: catálogo e import de blueprint muertos.
    ///
    /// El anillo vacío significa «no hay infraestructura de firma desplegada», no «rechaza todo».
    /// Sin emisor, el control vigente es el SHA256 obligatorio de ADR-0015 — que es exactamente el
    /// modo `warn` que ADR-0193 ya exigía.
    #[test]
    fn sin_anillo_de_claves_la_produccion_no_puede_exigir_firma() {
        let policy = config(false).signature_policy();
        assert!(
            policy.check(None, b"module.zip").is_ok(),
            "un hub de producción sin claves desplegadas debe poder instalar del marketplace \
             (integridad = SHA256, ADR-0015); si no, el producto no arranca: {policy:?}"
        );
        assert!(
            !policy.requires_signature(),
            "sin claves de confianza no hay firma que exigir: {policy:?}"
        );
    }

    /// El envés de la moneda: **desplegar una clave ENCIENDE el enforcement**. Es lo que convierte
    /// el fix en un rollout progresivo y no en «hemos quitado el gate».
    #[test]
    fn con_anillo_de_claves_la_produccion_si_exige_firma() {
        // Cualquier pubkey ed25519 bien formada (32 bytes = 64 chars hex) basta: lo que se prueba
        // es que un anillo NO vacío enciende el enforcement, no la criptografía en sí.
        let key = "a".repeat(64);
        let policy = config_with_keys(false, vec![format!("marketplace={key}")]).signature_policy();

        assert!(
            policy.requires_signature(),
            "con clave desplegada la política debe exigir firma: {policy:?}"
        );
        assert!(
            policy.check(None, b"module.zip").is_err(),
            "con clave desplegada, un módulo SIN firma se rechaza: {policy:?}"
        );
    }

    /// Dev sigue siendo el escape hatch explícito, sin cambio (hub#239).
    #[test]
    fn en_modo_desarrollo_se_admite_sin_firma() {
        assert!(config(true).signature_policy().check(None, b"zip").is_ok());
    }

    /// 🔴 hub#870: **el fail-open que queda es el de la configuración rota.** Ausente o vacío,
    /// `HUB_MODULE_TRUSTED_KEYS` significa «no hay infraestructura de firma desplegada» y degrada
    /// a propósito (ADR-0194, test de arriba). Pero una variable que SÍ trae contenido y cuyas
    /// entradas son **todas ilegibles** —un hex truncado al pegarlo, una clave con el `key_id`
    /// mal partido— es un despliegue que alguien creyó haber protegido: degradar ahí deja al hub
    /// instalando módulos sin verificar procedencia y con el operador convencido de lo contrario.
    ///
    /// Se responde `Enforce` con el anillo (vacío) que se pudo cargar: el hub **deja de instalar**
    /// —loud, y con el error de firma— pero **sigue vendiendo**, que es lo que no puede pararse.
    #[test]
    fn una_clave_de_confianza_ilegible_no_degrada_a_sha256only() {
        // Las tres formas reales de romper el valor al pegarlo en el env del despliegue.
        for broken in [
            "marketplace=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", // hex truncado (63)
            "marketplace=no-es-una-clave",
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", // sin key_id y truncada
        ] {
            let policy = config_with_keys(false, vec![broken.to_string()]).signature_policy();

            assert!(
                policy.requires_signature(),
                "`HUB_MODULE_TRUSTED_KEYS` venía puesto ({broken}): el hub tiene que seguir \
                 exigiendo firma, no degradar a Sha256Only: {policy:?}"
            );
            assert!(
                policy.check(None, b"module.zip").is_err(),
                "con la única clave del anillo ilegible ({broken}), un módulo SIN firma no puede \
                 instalarse: {policy:?}"
            );
        }
    }

    /// El envés: si **alguna** clave sí carga, el anillo tiene con qué verificar y las ilegibles
    /// solo cuestan un WARN. No se degrada ni se aborta por una entrada mala entre varias.
    #[test]
    fn una_clave_ilegible_entre_varias_no_tumba_el_anillo() {
        let good = "a".repeat(64);
        let policy = config_with_keys(
            false,
            vec![format!("rota=zz, marketplace={good}")],
        )
        .signature_policy();

        assert!(policy.requires_signature(), "{policy:?}");
    }

    /// El `/tmp/modules` que inyecta el despliegue NO es staging válido en producción.
    #[test]
    fn el_dir_de_modulos_de_dev_solo_es_staging_en_modo_desarrollo() {
        assert_eq!(
            config(false).install_staging_roots(),
            vec![PathBuf::from("/var/cache/erplora")]
        );
        assert_eq!(
            config(true).install_staging_roots(),
            vec![
                PathBuf::from("/var/cache/erplora"),
                PathBuf::from("/tmp/modules")
            ]
        );
    }

    // ---------------------------------------------------------------------------------------
    // hub#1754 — the boot announcement of the module-signature policy.
    //
    // The policy used to be logged only as a SIDE EFFECT of `signature_policy()` being called,
    // and that call only happens when something installs. A freshly provisioned hub —exactly the
    // one whose trust ring was just pasted into the deployment— installs nothing at boot, so it
    // started up mute: nobody could tell whether it verified signatures until an install failed.
    // ---------------------------------------------------------------------------------------

    use crate::log_capture::captured as captured_boot_log;

    /// How many events the capture holds: the announcement is ONE line, not a paragraph.
    fn lines(log: &str) -> Vec<&str> {
        log.lines().filter(|l| !l.trim().is_empty()).collect()
    }

    fn ring_of_one() -> Vec<String> {
        vec![format!("marketplace={}", "a".repeat(64))]
    }

    /// **The silent case that hub#1754 exists for.** A hub with its trust ring deployed verifies
    /// every module it installs — and said so NOWHERE. Whoever pasted the key had no way of
    /// telling it had taken, short of provoking an install.
    #[test]
    fn a_hub_that_verifies_signatures_announces_it_at_boot() {
        let config = config_with_keys(false, ring_of_one());

        let log = captured_boot_log(|| config.announce_signature_policy());

        assert_eq!(
            lines(&log).len(),
            1,
            "the boot announcement is exactly one line: {log}"
        );
        assert!(
            log.contains("INFO"),
            "a hub that DOES verify is good news, not a warning: {log}"
        );
        assert!(
            log.contains(r#"signature="verifying""#),
            "the line has to be greppable by mode: {log}"
        );
    }

    /// The whole fleet, today: no ring deployed. It is not a failure, but the operator has to know
    /// that nothing is checking WHO signed the modules (ADR-0194: integrity is the grant SHA256).
    #[test]
    fn a_hub_without_a_trust_ring_warns_that_it_verifies_nothing() {
        let config = config_with_keys(false, Vec::new());

        let log = captured_boot_log(|| config.announce_signature_policy());

        assert_eq!(lines(&log).len(), 1, "one line: {log}");
        assert!(
            log.contains("WARN"),
            "not verifying is a warning, never an INFO: {log}"
        );
        assert!(
            log.contains("HUB_MODULE_TRUSTED_KEYS"),
            "the line names the variable to deploy: {log}"
        );
    }

    /// **The case in the issue title.** The key was pasted wrong, so the hub enforces against an
    /// empty ring (hub#870) and no module will ever install. That is an ERROR at boot, not a
    /// surprise at the first install.
    #[test]
    fn a_hub_with_an_unreadable_trust_ring_errors_at_boot() {
        let config = config_with_keys(false, vec!["marketplace=no-es-una-clave".into()]);

        let log = captured_boot_log(|| config.announce_signature_policy());

        assert_eq!(lines(&log).len(), 1, "one line: {log}");
        assert!(
            log.contains("ERROR"),
            "a hub that cannot install anything is broken, not merely warned: {log}"
        );
        assert!(
            log.contains(r#"signature="misconfigured""#),
            "the line has to be greppable by mode: {log}"
        );
    }

    /// A ring that loads WITH some unreadable entries still verifies, so the mode is `verifying` —
    /// but the entries that were dropped keep the WARN they had before hub#1754. Losing that would
    /// hide a half-pasted ring behind an INFO.
    #[test]
    fn a_partly_unreadable_ring_still_verifies_but_keeps_its_warning() {
        let config = config_with_keys(false, vec![format!("rota=zz, marketplace={}", "a".repeat(64))]);

        let log = captured_boot_log(|| config.announce_signature_policy());

        assert_eq!(lines(&log).len(), 1, "one line: {log}");
        assert!(
            log.contains("WARN"),
            "an ignored key is a warning even though the hub verifies: {log}"
        );
        assert!(
            log.contains(r#"signature="verifying""#),
            "it still verifies — the mode does not change: {log}"
        );
    }

    /// Dev mode accepts unsigned modules on purpose. It still has to say so: `HUB_DEV_MODE` on a
    /// machine that someone believes is production is the same silence with a different cause.
    #[test]
    fn a_dev_hub_says_it_is_not_enforcing_signatures() {
        let config = config_with_keys(true, ring_of_one());

        let log = captured_boot_log(|| config.announce_signature_policy());

        assert_eq!(lines(&log).len(), 1, "one line: {log}");
        assert!(log.contains("WARN"), "dev trust is not INFO: {log}");
        assert!(
            log.contains(r#"signature="dev_trust""#),
            "the line has to be greppable by mode: {log}"
        );
    }

    /// The announcement must not change WHAT the hub enforces — it only makes it visible. Each
    /// mode is pinned to the policy it announces, so a future edit cannot drift them apart.
    #[test]
    fn announcing_never_changes_the_policy_that_is_enforced() {
        for (keys, dev, mode) in [
            (ring_of_one(), false, SignatureMode::Verifying { keys: 1, ignored: 0 }),
            (Vec::new(), false, SignatureMode::NotVerifying),
            (
                vec!["marketplace=no-es-una-clave".to_string()],
                false,
                SignatureMode::Misconfigured { unreadable: 1 },
            ),
            (Vec::new(), true, SignatureMode::DevTrust),
        ] {
            let config = config_with_keys(dev, keys);
            assert_eq!(config.signature_mode(), mode, "{config:?}");
            // Same resolution behind both doors: the announcement reads the policy, it does not
            // invent one.
            let announced = config.signature_mode();
            let enforced = config.signature_policy();
            match (announced, &enforced) {
                (SignatureMode::Verifying { .. }, cloud_client::SignaturePolicy::Enforce(ring)) => {
                    assert!(!ring.is_empty())
                }
                (
                    SignatureMode::Misconfigured { .. },
                    cloud_client::SignaturePolicy::Enforce(ring),
                ) => assert!(ring.is_empty()),
                (SignatureMode::NotVerifying, cloud_client::SignaturePolicy::Sha256Only) => {}
                (SignatureMode::DevTrust, cloud_client::SignaturePolicy::DevTrust) => {}
                (m, p) => panic!("mode {m:?} does not match the policy it announces: {p:?}"),
            }
        }
    }
}

/// Celda compartida del **token de máquina** (`cloud_api_token`). Mutable en vivo: el shell Tauri
/// la actualiza tras enrolar/rotar y el runtime embebido toma el token nuevo **sin reiniciar la
/// app** (`auth::machine_auth` la lee en cada petición). En ECS basta el valor inicial del env.
pub type MachineToken = Arc<RwLock<Option<String>>>;

/// `hub_id` vivo de la máquina. Durante el primer arranque Tauri nace con [`DEV_HUB_ID`] y, tras
/// registrar el `device_id` en el Cloud, adopta el UUID real en la misma operación que el token.
/// En Cloud ya viene fijado por el despliegue y la celda no cambia.
pub type HubId = Arc<RwLock<String>>;

/// The runtime as every host shares it (hub#978).
///
/// A `RwLock`, not a `Mutex`: commands, queries, the relay tick and every read-only route take
/// the **shared** guard and overlap, so N tills cost N× the database, not N× a queue. Only what
/// needs `&mut Runtime` — installing, updating, activating or removing a module, adopting the
/// real `hub_id` at bootstrap — takes the **exclusive** guard, and waits for the requests in
/// flight to finish first. Everything an overlapping command mutates (a step-up approval being
/// spent, the WASM cache, the outbox) is already atomic on its own — a `std::sync::Mutex`
/// inside the store or a transaction in Postgres — which is what makes the shared guard safe.
///
/// Until hub#978 this was a `tokio::Mutex` held for the whole `execute_command`, and the p50 of
/// a sale scaled linearly with the number of tills (11 ms → 197 ms from 1 to 10 tills, measured).
pub type SharedRuntime = Arc<tokio::sync::RwLock<Runtime>>;

/// Estado de la app Axum. El runtime va tras el [`SharedRuntime`] de arriba (lectores en
/// paralelo, escritores exclusivos); para 1–30 usuarios por hub (ARQUITECTURA.md §7.5) sobra.
///
/// **Dos modos de topología** (ADR-0005):
///  - **single-tenant (N=1)** — `tenants = None`: hay UN runtime (`runtime`), el del hub/org del
///    despliegue. Es el modo actual (un contenedor ECS por hub, o local Tauri). Todas las
///    peticiones usan ese runtime. **Comportamiento sin cambios.**
///  - **cloud compartido (N orgs)** — `tenants = Some(router)`: el proceso sirve **N** orgs; el
///    runtime de cada petición se resuelve por su `hub_id` vía el [`TenantRouter`] (un pool por
///    org). El campo `runtime` sigue existiendo como **fallback/bootstrap** (tablas de sistema,
///    arranque), pero el camino de datos va por el router. Ver [`AppState::runtime_for`].
#[derive(Clone)]
pub struct AppState {
    pub runtime: SharedRuntime,
    pub events: broadcast::Sender<WsEvent>,
    pub config: HubConfig,
    /// Token de máquina **vivo** (hot-reload). Se siembra del `config.cloud_api_token` o de una
    /// celda externa (shell Tauri). Léelo con [`AppState::machine_token`].
    pub machine_token: MachineToken,
    /// Identidad de Hub **viva**. Token e id se actualizan juntos al completar el registro de la
    /// máquina, evitando firmar una llamada con el token nuevo y el UUID placeholder anterior.
    pub hub_id: HubId,
    /// Cliente HTTP async (rustls) compartido para hablar con el Cloud (descargas + proxy SSE).
    pub http: reqwest::Client,
    /// Gateway multi-tenant (ADR-0005, hub#24). `None` = modo single-tenant actual (N=1); `Some` =
    /// tier "cloud compartido" (N orgs, un pool por org). Aditivo: no rompe el modo single-tenant.
    pub tenants: Option<Arc<crate::tenant::TenantRouter>>,
    /// Índice vectorial para routing de tools (§9.2b) + ingestión de embeddings (§9.6). `None` =
    /// sin índice (degradación §9.5: el asistente manda todos los tools). Lo siembra `serve()`.
    pub vector: Option<SharedVectorStore>,
    /// Estado de la **revalidación híbrida del entitlement** (módulos de pago): lo escribe el job
    /// periódico de `serve()` y lo leen el gate de `query`/`command` y el proxy `/api/entitlement`.
    /// Estado inicial = fail-open (nada bloqueado). Ver `crate::entitlement`.
    pub entitlement: crate::entitlement::SharedRevalidation,
    /// Caché del proxy `GET /api/entitlement` (hub#1167). El shell pregunta por el entitlement una
    /// vez por `focus` de ventana y otra por cada vista de módulo que monta; sin esta celda cada
    /// una de esas veces era una llamada al SaaS, y el cubo de tasa del SaaS lo comparte toda la
    /// flota (saas#1640). Guarda además el último cuerpo BUENO para poder servirlo cuando el Cloud
    /// responde 429, en vez de degradar a «sin módulos». Ver `crate::entitlement::ProxyCache`.
    pub entitlement_proxy: crate::entitlement::SharedProxyCache,
    /// Marca de **actividad de usuario**: la toca cada petición autenticada (middleware del router)
    /// y viaja al Cloud en el heartbeat de `daily_usage`. Es el reloj con el que el Cloud apaga
    /// (60d) y acaba borrando (120d) los hubs free en los que nadie entra. Ver `crate::activity`.
    pub activity: Arc<crate::activity::ActivityState>,
    /// Brute-force guard for the PIN login (hub#329). A PIN is 4 digits on a host that lives on
    /// the public internet; without a failure counter those are 10,000 free tries.
    pub login_throttle: Arc<crate::login_throttle::LoginThrottle>,
    /// Short-lived, single-use credentials for the event stream (hub#504). In memory: they must
    /// not survive a restart, and above all they must not travel in a backup or a blueprint.
    pub stream_tickets: Arc<crate::event_stream::StreamTickets>,
    /// Per-key cap on simultaneous stream connections (hub#531). One API key should not be able to
    /// exhaust the hub by opening N sockets — a reconnection bug reaches the ceiling, not just malice.
    pub stream_limiter: Arc<crate::event_stream::StreamLimiter>,
    /// Cap on simultaneous media object downloads (hub#759). A catalog page mounts hundreds of
    /// `/api/media/raw` URLs at once; without this bound, N concurrent proxied downloads stack
    /// their buffers simultaneously — enough to OOM a 96 MiB container (exit 137). Requests
    /// beyond the cap queue on the semaphore instead of failing. Each permit is held for the
    /// whole life of the streamed response body, not just the handler call.
    pub media_fetch_limiter: Arc<tokio::sync::Semaphore>,
}

impl AppState {
    /// Crea el estado y conecta el `EventSink` del runtime al canal broadcast.
    pub fn new(runtime: Runtime) -> Self {
        Self::with_config(runtime, HubConfig::from_env())
    }

    /// Variante con config explícita (tests / arranque controlado). Crea la celda del token de
    /// máquina sembrada con `config.cloud_api_token`.
    pub fn with_config(runtime: Runtime, config: HubConfig) -> Self {
        let token = Arc::new(RwLock::new(config.cloud_api_token.clone()));
        let hub_id = Arc::new(RwLock::new(config.hub_id.clone()));
        Self::with_config_cells(runtime, config, token, hub_id)
    }

    /// Como [`with_config`](Self::with_config) pero con una **celda de token externa** compartida
    /// (el shell Tauri la conserva para actualizarla en caliente tras enrolar/rotar).
    pub fn with_config_cell(
        runtime: Runtime,
        config: HubConfig,
        machine_token: MachineToken,
    ) -> Self {
        let hub_id = Arc::new(RwLock::new(config.hub_id.clone()));
        Self::with_config_cells(runtime, config, machine_token, hub_id)
    }

    /// Variante completa para hosts embebidos: comparte tanto el token como el `hub_id` vivo.
    /// El shell los adopta de forma atómica desde la perspectiva del flujo de bootstrap.
    pub fn with_config_cells(
        mut runtime: Runtime,
        config: HubConfig,
        machine_token: MachineToken,
        hub_id: HubId,
    ) -> Self {
        let (tx, _rx) = broadcast::channel::<WsEvent>(256);
        let sink = Arc::new(BroadcastSink { tx: tx.clone() });
        runtime.set_event_sink(sink);
        // DEMO efímera (ADR-0197 §4, hub#376): se sella AQUÍ porque este constructor es el embudo
        // por el que pasan TODOS los hosts —`serve()`, el shell Tauri y cada test—, igual que el
        // `event_sink` de la línea de arriba. Sellarlo solo en `serve()` habría dejado los cierres
        // apagados en cualquier otro arranque, y un cierre que depende de que alguien se acuerde de
        // encenderlo no es un cierre.
        runtime.set_demo_hub(config.demo);
        Self {
            runtime: Arc::new(tokio::sync::RwLock::new(runtime)),
            events: tx,
            config,
            machine_token,
            hub_id,
            http: reqwest::Client::new(),
            tenants: None,
            vector: None,
            entitlement: crate::entitlement::new_shared(),
            entitlement_proxy: crate::entitlement::new_shared_proxy_cache(),
            activity: Arc::new(crate::activity::ActivityState::new()),
            login_throttle: Arc::new(crate::login_throttle::LoginThrottle::new()),
            stream_tickets: Arc::new(crate::event_stream::StreamTickets::default()),
            stream_limiter: Arc::new(crate::event_stream::StreamLimiter::default()),
            media_fetch_limiter: Arc::new(tokio::sync::Semaphore::new(
                crate::media::MAX_CONCURRENT_MEDIA_FETCHES,
            )),
        }
    }

    /// Adjunta el índice vectorial (routing §9.2b + ingestión §9.6). Aditivo: sin él, el asistente
    /// degrada a "todos los tools" (§9.5).
    pub fn with_vector(mut self, store: SharedVectorStore) -> Self {
        self.vector = Some(store);
        self
    }

    /// Activa el modo **cloud compartido** (ADR-0005): adjunta el gateway multi-tenant. A partir de
    /// aquí, [`runtime_for`](Self::runtime_for) resuelve el runtime por org. Aditivo: el `runtime`
    /// single-tenant sigue ahí como fallback de bootstrap.
    pub fn with_tenants(mut self, router: Arc<crate::tenant::TenantRouter>) -> Self {
        self.tenants = Some(router);
        self
    }

    /// Resuelve el [`Runtime`] a usar para esta petición:
    ///  - **single-tenant** (`tenants = None`): siempre el `runtime` del despliegue (modo actual).
    ///  - **cloud compartido** (`tenants = Some`): el runtime de la org dueña del `hub_id` de la
    ///    petición, vía el [`TenantRouter`]. Si el `hub_id` no mapea a ninguna org, **se rechaza**
    ///    (`TenantError::UnknownOrg`) — un token de la org A no puede resolver el pool de la B.
    ///
    /// El `hub_id` viene de la auth ya existente (`X-Hub-Id` inyectado por el despliegue, no
    /// spoofable; ver `auth.rs`). La autoridad sigue **server-side**: el gate de permisos + el
    /// scoping `hub_id` los aplica el `Runtime` resuelto en `execute_query`/`execute_command`.
    pub async fn runtime_for(
        &self,
        hub_id: &str,
    ) -> Result<SharedRuntime, crate::tenant::TenantError> {
        match &self.tenants {
            Some(router) => router.resolve_runtime(hub_id).await,
            None => {
                // En single-tenant el primer login puede sustituir el placeholder de arranque por
                // el UUID real. Sincronizamos el Runtime antes de devolverlo para que sus helpers
                // internos (settings, perfil, instalación…) usen el mismo scope que la auth. La
                // autoridad es la celda del host, NUNCA el argumento (que en query/command puede
                // proceder de `X-Hub-Id` en modo dev).
                //
                // Read first, write only on the (once-per-life) mismatch: this runs on EVERY
                // request, and an exclusive guard here would put the queue hub#978 removed
                // right back — a writer waits for every reader and blocks the ones behind it.
                let effective_hub_id = self.hub_id();
                if self.runtime.read().await.hub_id() != effective_hub_id {
                    let mut runtime = self.runtime.write().await;
                    if runtime.hub_id() != effective_hub_id {
                        runtime.adopt_hub_id(effective_hub_id);
                    }
                }
                Ok(self.runtime.clone())
            }
        }
    }

    /// Lee el `hub_id` vivo (clona). Si el lock estuviera envenenado, conserva el valor de
    /// arranque; nunca acepta un id aportado por el navegador como autoridad.
    pub fn hub_id(&self) -> String {
        self.hub_id
            .read()
            .map(|g| g.clone())
            .unwrap_or_else(|_| self.config.hub_id.clone())
    }

    /// Copia de configuración para gates de auth con el `hub_id` vivo ya reconciliado. Mantiene el
    /// resto de opciones inmutables y evita que un handler use accidentalmente el placeholder que
    /// existía antes del registro de la máquina.
    pub fn effective_config(&self) -> HubConfig {
        let mut config = self.config.clone();
        config.hub_id = self.hub_id();
        config
    }

    /// Un hub de **desarrollo sin enrolar** (`HUB_AUTH=dev` + el `hub_id` placeholder) es la única
    /// excepción al registro de máquina obligatorio.
    ///
    /// Se llamaba `is_demo()` y **no tenía nada que ver con la demo** (ADR-0212 ya avisaba de la
    /// confusión por escrito). Ahora que la demo efímera de ADR-0197 sí existe en el hub
    /// ([`HubConfig::demo`]), dos cosas distintas no pueden compartir nombre: el siguiente que
    /// escriba un cierre de demo llamaría a esta y le abriría el hub a cualquiera en `dev`.
    /// Renombrar es seguro — no es columna, ni clave de manifest, ni ruta, ni evento.
    pub fn is_dev_hub(&self) -> bool {
        self.config.auth_mode == AuthMode::Dev && self.hub_id() == DEV_HUB_ID
    }

    /// Una máquina real está vinculada solo si posee las dos mitades de su identidad: UUID Cloud
    /// y credencial secreta. Tener un JWT de usuario abierto no sustituye este estado.
    pub fn machine_registered(&self) -> bool {
        !self.is_dev_hub() && self.hub_id() != DEV_HUB_ID && self.machine_token().is_some()
    }

    /// Lee el token de máquina vivo (clona). `None` si el hub no está enrolado.
    pub fn machine_token(&self) -> Option<String> {
        self.machine_token.read().ok().and_then(|g| g.clone())
    }

    /// Publica un frame WS crudo (lo usa el flujo de instalación → `module.installed`).
    pub fn broadcast(&self, frame: Json) {
        let _ = self.events.send(frame);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// **Fail-closed (hub#241).** Sin `HUB_AUTH` el hub NO puede arrancar sin autenticación: el
    /// default es producción (`Session`). Antes era `Dev` y un despliegue que olvidara la variable
    /// aceptaba la identidad y los permisos que dictase el navegador (`X-User-Id`/`X-Permissions`).
    #[test]
    fn missing_env_defaults_to_session_not_dev() {
        assert_eq!(parse_auth_mode(None), AuthMode::Session);
        assert_ne!(parse_auth_mode(None), AuthMode::Dev);
    }

    /// El modo de desarrollo se pide EXPLÍCITAMENTE.
    #[test]
    fn dev_mode_must_be_requested_explicitly() {
        assert_eq!(parse_auth_mode(Some("dev")), AuthMode::Dev);
        assert_eq!(parse_auth_mode(Some(" dev ")), AuthMode::Dev);
    }

    #[test]
    fn session_is_accepted_verbatim() {
        assert_eq!(parse_auth_mode(Some("session")), AuthMode::Session);
    }

    /// Un typo (`develop`, `DEV`, vacío) NO degrada la seguridad: cae a `Session`.
    #[test]
    fn unknown_or_empty_value_falls_back_to_session() {
        for raw in ["develop", "DEV", "Dev", "", "true", "1"] {
            assert_eq!(
                parse_auth_mode(Some(raw)),
                AuthMode::Session,
                "`{raw}` no debe abrir el hub"
            );
        }
    }

    /// **The gate is armed by default (hub#330).** A deployment that never heard of
    /// `HUB_DEVICE_TRUST` gets the protected behaviour, not the open one: the PIN door of a hub on
    /// the public internet answers four digits, and until hub#454 gave every browser an identity
    /// of its own there was no way to demand one. There is now, so the default flips.
    #[test]
    fn missing_env_arms_the_device_trust_gate() {
        assert!(parse_device_trust(None));
    }

    /// Disarming it is a deliberate word, and the only one.
    #[test]
    fn off_is_the_word_that_disarms_it() {
        assert!(!parse_device_trust(Some("off")));
    }

    /// `enforce` keeps meaning what it always meant: the deployments that already set it do not
    /// change behaviour when the default flips under them.
    #[test]
    fn enforce_still_arms_it() {
        assert!(parse_device_trust(Some("enforce")));
    }

    /// Surrounding blanks and capitals in an env var are the deployment's typing, not a decision:
    /// `HUB_DEVICE_TRUST=OFF ` is somebody turning it off on purpose and must be obeyed. (The
    /// mirror of `parse_dev_mode`, which trims and lowercases for the same reason.)
    #[test]
    fn off_is_read_through_blanks_and_capitals() {
        for raw in [" off", "off ", " off ", "OFF", "Off", "\toff\n"] {
            assert!(
                !parse_device_trust(Some(raw)),
                "`{raw}` is an operator saying off"
            );
        }
    }

    // ── El marcador de DEMO efímera (ADR-0197 · hub#376) ───────────────────────────────────

    /// 🔴 **Un hub que ya existe NO se vuelve demo por este cambio.** Sin `HUB_DEMO`, hub normal.
    /// La dirección del default es una decisión, no una comodidad: dar por demo a un hub REAL le
    /// congelaría la identidad fiscal y lo dejaría fuera de producción **sin decir nada** — la
    /// misma clase de error que auto-borraba el hub propio de ERPlora a los 120 días.
    #[test]
    fn without_the_env_a_hub_is_never_a_demo() {
        assert!(!parse_demo_flag(None));
        assert!(!parse_demo_flag(Some("")));
        assert!(!parse_demo_flag(Some("   ")));
    }

    /// Ser demo se pide EXPLÍCITAMENTE, y en las grafías de siempre (`parse_dev_mode`).
    #[test]
    fn the_demo_marker_is_requested_explicitly() {
        for raw in ["1", "true", "TRUE", " yes ", "on", "On"] {
            assert!(parse_demo_flag(Some(raw)), "`{raw}` debía activar la demo");
        }
    }

    /// Un valor que no reconocemos NO enciende los cierres: `HUB_DEMO=maybe` es un hub normal.
    #[test]
    fn an_unknown_value_leaves_the_hub_normal() {
        for raw in ["0", "false", "no", "off", "demo", "sí", "2"] {
            assert!(
                !parse_demo_flag(Some(raw)),
                "`{raw}` no debía marcar el hub como demo"
            );
        }
    }

    // ── hub#1279: a dev/bench runtime must not silently call PRODUCTION ────────────────────

    /// 🔴 The bug: a runtime started with `HUB_DEV_MODE=1` (a Playwright bench, a CI job) and no
    /// explicit `HUB_CLOUD_API_URL` inherited the production default in silence — exactly what
    /// made the web e2e bench call `erplora.com` from the CI runner before hub#1277 pinned that
    /// one caller's env. `CI` is the signal nobody is there to read a warning: it must refuse.
    #[test]
    fn hub1279_missing_cloud_url_is_a_startup_error_not_a_prod_default() {
        let outcome = cloud_url_guard(true, PRODUCTION_CLOUD_BASE_URL, true);
        assert_eq!(
            outcome,
            CloudUrlGuard::Refuse,
            "HUB_DEV_MODE=1 + the production default + CI must refuse to start, not silently \
             call production: {outcome:?}"
        );
    }

    /// The local counterpart: `pnpm dev` (`scripts/dev.mjs`) sets `HUB_DEV_MODE=1` and points at
    /// production ON PURPOSE (`/hub-local`) — a developer sitting at the terminal can read a
    /// warning, so outside CI the guard must not break that flow. It still has to say something.
    #[test]
    fn hub1279_dev_mode_outside_ci_warns_but_keeps_starting() {
        let outcome = cloud_url_guard(true, PRODUCTION_CLOUD_BASE_URL, false);
        assert_eq!(
            outcome,
            CloudUrlGuard::Warn,
            "HUB_DEV_MODE=1 + the production default outside CI must warn, not refuse (that \
             would break `pnpm dev`): {outcome:?}"
        );
    }

    /// A deployed hub is out of scope on purpose: provisioning (Hetzner and AWS) always injects
    /// `HUB_CLOUD_API_URL`, so a production runtime (`dev_mode = false`) never has a reason to be
    /// flagged even if its `cloud_base_url` happened to equal the production default.
    #[test]
    fn hub1279_non_dev_mode_default_is_never_flagged() {
        assert_eq!(
            cloud_url_guard(false, PRODUCTION_CLOUD_BASE_URL, true),
            CloudUrlGuard::Ok
        );
        assert_eq!(
            cloud_url_guard(false, PRODUCTION_CLOUD_BASE_URL, false),
            CloudUrlGuard::Ok
        );
    }

    /// Explicitly setting `HUB_CLOUD_API_URL` to a bench stub (or anything other than the
    /// production URL) never trips the guard, in or out of CI — this is exactly the fix hub#1277
    /// already applied to `apps/web/tests/playwright.config.ts`.
    #[test]
    fn hub1279_explicit_non_production_url_is_never_flagged() {
        for ci in [true, false] {
            assert_eq!(
                cloud_url_guard(true, "http://127.0.0.1:1", ci),
                CloudUrlGuard::Ok,
                "an explicit non-production URL must never be flagged (ci={ci})"
            );
        }
    }

    /// **Anything else arms it.** A typo must not be a silent way to open the PIN door — the same
    /// direction as `parse_auth_mode`, where an unknown mode falls back to `Session`. Note `false`,
    /// `0` and `no`: they read like a switch, and honouring them would mean three spellings of
    /// "open" against one of "closed".
    #[test]
    fn a_typo_never_disarms_it() {
        for raw in [
            "", " ", "0", "false", "no", "disabled", "of", "offf", "on", "enforced",
        ] {
            assert!(
                parse_device_trust(Some(raw)),
                "`{raw}` must not open the PIN door"
            );
        }
    }

    /// 🔴 Ser demo y ser hub de **dev** son cosas DISTINTAS, y por eso ya no comparten nombre.
    /// `is_dev_hub()` (antes `is_demo()`) abre el hub a las cabeceras del navegador; el marcador de
    /// ADR-0197 lo CIERRA. Confundirlos era abrir una demo pública en modo dev.
    #[test]
    fn the_ephemeral_demo_marker_is_not_the_dev_hub_flag() {
        // Dos variables, dos dueños, dos efectos OPUESTOS: `HUB_AUTH=dev` ABRE el hub (el
        // navegador dicta identidad y permisos), `HUB_DEMO=1` lo CIERRA (entorno fiscal clavado,
        // certificado e identidad congelados). Ni el valor de una activa la otra.
        assert!(
            !parse_demo_flag(Some("dev")),
            "`HUB_DEMO=dev` no es una demo"
        );
        assert_eq!(
            parse_auth_mode(Some("1")),
            AuthMode::Session,
            "`HUB_AUTH=1` no abre el hub"
        );
        assert_eq!(parse_auth_mode(Some("true")), AuthMode::Session);
    }
}
