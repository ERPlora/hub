//! Serve configuration, CSP policy and DSN normalisation — split out of `lib.rs` verbatim (hub#1404).
//!
//! **`HUB_TRUSTED_HOSTS`** (hub#1464, ADR-0431 §2) no vive en esta struct a propósito: la lee
//! `cloud-client` (`trusted::trusted_from_env`), que es donde se firma. Se documenta aquí porque
//! es donde alguien busca «qué env consume el hub»: lista de hosts **de ERPlora**, separados por
//! comas, con `*.sufijo` admitido (`*.erplora.com,*.pre.erplora.com`). `HUB_CLOUD_API_URL` es de
//! confianza SIEMPRE y no hace falta repetirlo. Ausente = solo esa; a cualquier otro destino la
//! petición sale **sin** `X-Hub-Token`/`X-Hub-Id`/Bearer/`X-Webhook-Secret` y se registra un aviso.
//!
//! ⚠️ Cuando aterrice hub#1470 esta variable pasa a ser **infraestructura fiscal**: sin el FQDN de
//! la celda dentro, la ruta por la pasarela deja de transmitir.

use crate::*;

/// Configuración de arranque del runtime del hub — la usa el binario (`main.rs`). Envuelve la
/// [`HubConfig`] de despliegue + parámetros de proceso. Hub Cloud es Postgres-only (ADR-0154).
#[derive(Clone, Debug)]
pub struct ServeConfig {
    /// DSN de Postgres (`HUB_DATABASE_URL`) — **obligatorio** (ADR-0154). Vacío ⇒ el arranque
    /// falla con un error claro (`serve` hace fail-fast). El Cloud lo inyecta al desplegar.
    pub database_url: String,
    /// Dirección de escucha. Por defecto `127.0.0.1:8787`.
    pub bind: String,
    /// Carpeta opcional de módulos a instalar al arrancar (hub vacío / dev).
    pub modules_dir: Option<String>,
    /// Configuración de despliegue (hub_id, Cloud, `auth_mode`, token de máquina…).
    pub hub: HubConfig,
    /// Celda **externa** del token de máquina (hot-reload tras enrolar/rotar sin reiniciar). Si
    /// `None`, el runtime crea la suya sembrada con `hub.cloud_api_token` (caso binario/Cloud).
    pub machine_token_cell: Option<state::MachineToken>,
    /// Celda externa del `hub_id` vivo. Cloud/binario usa una celda interna sembrada desde `HUB_ID`.
    pub hub_id_cell: Option<state::HubId>,
    /// Ruta del `dist/` de Vite a servir en el **MISMO origen** que `/api` (ADR-0050). `Some` ⇒ el
    /// runtime monta el front con fallback SPA (`with_static_frontend`), de modo que
    /// `HttpWsTransport` (RUNTIME_URL='') alcance el loopback sin CORS; `from_env` lo vuelca desde
    /// `HUB_WEB_DIR`. `None` ⇒ solo API (dev con Vite, que proxya, o binario sin front).
    pub web_dir: Option<String>,
    /// Valor del header `Content-Security-Policy` a emitir (ADR-0050). Cuando el doc lo sirve Axum
    /// —que es SIEMPRE, en cloud y en la app instalada, porque la ventana de Tauri navega a este
    /// mismo servidor— la CSP de `tauri.conf` no alcanza al documento y esta es la única que hay.
    ///
    /// `String`, no `Option<String>`: «hub sin política» dejó de ser un estado representable
    /// (hub#708). Lo era, y por eso la flota entera sirvió la app a pelo durante semanas. Se
    /// rellena con [`resolve_csp`], que solo deja pasar un valor que el navegador pueda recibir.
    pub csp: String,
}

/// La parte de la política que NO depende del despliegue (hub#708). Es el gemelo de la CSP del
/// shell de Tauri (`apps/tauri/src-tauri/tauri.conf.json`), y las diferencias están enumeradas una
/// a una en `crates/server/tests/cloud_csp.rs` — un test falla si aparece una que nadie explicó.
///
/// Cada ensanche respecto del shell tiene un motivo concreto:
/// - `img-src blob:` / `media-src blob:` — el visor de `/files` y el avatar pintan bytes que YA
///   trajo el runtime, vía `URL.createObjectURL`; el navegador nunca toca el almacenamiento
///   (ADR-0047). Sin `media-src` explícito la etiqueta `<video>` cae en `default-src` y no pinta.
/// - `script-src 'self'` y `worker-src 'self'` explícitos aunque `default-src` ya los cubra: son
///   las dos directivas que deciden si un módulo puede ejecutar código ajeno, y así ensanchar
///   `default-src` mañana no las ensancha de rebote.
///
/// Y lo que NO lleva, también a propósito: **`form-action`**. No hereda de `default-src`, así que
/// su ausencia es una decisión: fijarla rompe el login con Google, cuya cadena de redirección sale
/// del hub, pasa por el SaaS y vuelve — sin error que el usuario pueda accionar.
///
/// Y lo que SÍ lleva desde hub#1447: **`report-uri`**, la única directiva que no autoriza nada.
/// Sin ella la política es una pared que salta en silencio — el navegador escribe una línea en la
/// consola del dispositivo donde pasó y ahí se acaba el registro. Eso es lo que costó
/// `ERPlora/infra#73`: Cloudflare inyectando su beacon en el HTML desde el edge, `script-src
/// 'self'` rechazándolo en **todas** las páginas de **todos** los hubs, y nosotros enterándonos
/// porque alguien abrió la consola a mano. Apunta a este mismo hub —no al SaaS— para que un
/// self-host sin Cloud detrás siga teniendo dónde reportar; el receptor es
/// [`crate::csp_report`].
/// And the one foreign script the page may run, with its frames (hub#1600, ADR-0452): Meta's JS
/// SDK, `https://connect.facebook.net`, which is how the owner connects the WhatsApp number of
/// the business FROM THE HUB (the «Connect WhatsApp» button in the module's settings opens
/// Meta's Embedded Signup popup and the QR is scanned with the WhatsApp Business app). The SDK
/// talks to its popup through hidden iframes on `*.facebook.com` and calls `graph.facebook.com`
/// on its own; block any of the three and the popup never opens, silently. Kept to exact hosts —
/// never `https:` — and mirrored in `tests/cloud_csp.rs` as explained widenings.
pub(crate) const CSP_BASE: &str = "default-src 'self'; \
                        script-src 'self' https://connect.facebook.net; \
                        worker-src 'self'; \
                        style-src 'self' 'unsafe-inline'; \
                        img-src 'self' data: blob:; \
                        media-src 'self' blob:; \
                        frame-src https://*.facebook.com; \
                        object-src 'none'; \
                        base-uri 'self'; \
                        report-uri /csp-report/";

/// El `connect-src` mínimo: el propio origen **y el canal IPC de Tauri**.
///
/// Lo segundo no es cosmético y es fácil de pasar por alto: la ventana de la app instalada NO carga
/// un `dist` empaquetado, navega a `https://<hub>.erplora.com` (ADR-0159, `remote.urls` de
/// `capabilities/default.json`), así que el documento que gobierna esta política ES el de la app —
/// y su `invoke` viaja por `fetch("ipc://localhost/<cmd>")` (`tauri/src/ipc/protocol.rs`), que en
/// Windows y Android reescribe a `http://ipc.localhost/<cmd>`. Sin estas dos fuentes, `connect-src`
/// tumba TODO el hardware de la app instalada —imprimir, cajón, descubrimiento— en silencio.
///
/// En un navegador a secas son inertes: `ipc:` no es un esquema navegable y `ipc.localhost` no
/// resuelve. Cuestan cero fuera de la app.
pub(crate) const CSP_CONNECT_BASE: &str =
    "connect-src 'self' ipc: http://ipc.localhost https://*.facebook.com https://graph.facebook.com";

/// La política que sirve este hub. Lo único que no puede ser constante es el **origen del Cloud**:
/// el front habla directo con él para el login, el refresh de JWT y las facturas
/// (`apps/web/src/lib/cloud.ts`), así que con `connect-src 'self'` a secas el hub se queda sin
/// login cloud. Sale de `HUB_CLOUD_API_URL` —lo que ESTE hub tiene configurado— y no de una
/// constante `https://erplora.com`, que es justo el pendiente (c) de ADR-0050: un self-host o un
/// staging con otro `VITE_CLOUD_API_URL` quedaba bloqueado por su propia CSP.
///
/// Sin Cloud configurado (dev, binario suelto) la política se queda en `'self'`: nada que permitir.
pub fn default_csp(cloud_base_url: &str) -> String {
    match cloud_origin(cloud_base_url) {
        Some(origin) => format!("{CSP_BASE}; {CSP_CONNECT_BASE} {origin}"),
        None => format!("{CSP_BASE}; {CSP_CONNECT_BASE}"),
    }
}

/// `https://erplora.com/algo/` → `https://erplora.com`. Una fuente de CSP es un ORIGEN: con la
/// ruta pegada el navegador la trata como path-matching y deja de casar con `/api/v1/...`.
/// Devuelve `None` si el valor no es una URL absoluta con host (incluye el string vacío).
pub(crate) fn cloud_origin(cloud_base_url: &str) -> Option<String> {
    let raw = cloud_base_url.trim();
    let (scheme, rest) = raw.split_once("://")?;
    if !scheme.eq_ignore_ascii_case("http") && !scheme.eq_ignore_ascii_case("https") {
        return None;
    }
    let authority = rest.split(['/', '?', '#']).next().unwrap_or("");
    // Un host con espacios, comillas o `;` rompería el header o inyectaría otra directiva.
    if authority.is_empty()
        || !authority
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || matches!(c, '.' | '-' | ':' | '[' | ']'))
    {
        return None;
    }
    Some(format!("{}://{}", scheme.to_ascii_lowercase(), authority))
}

/// Resuelve la CSP que va a servir el hub a partir del valor crudo de `HUB_CSP` (hub#708).
///
/// `HUB_CSP` **sustituye** la política; no la quita. Vacío, en blanco o imposible de meter en un
/// header (un salto de línea, un byte no-ASCII) cae a [`default_csp`] en vez de dejar el hub
/// desnudo — que es exactamente cómo se sirvió la flota entera hasta ahora: el aprovisionador
/// escribía `HUB_CSP_ENFORCE` y el runtime leía `HUB_CSP`, así que la rama "no hay valor" era la
/// única que corría y no emitía nada.
pub fn resolve_csp(raw: Option<String>, cloud_base_url: &str) -> String {
    raw.map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty() && HeaderValue::from_str(value).is_ok())
        .unwrap_or_else(|| default_csp(cloud_base_url))
}

impl ServeConfig {
    /// Igual que el binario: `HUB_DATABASE_URL` (obligatorio) / `HUB_BIND` / `HUB_MODULES_DIR` +
    /// [`HubConfig::from_env`].
    pub fn from_env() -> Self {
        let hub = HubConfig::from_env();
        // Antes del literal: `hub` se mueve dentro y la política necesita su `cloud_base_url`.
        let csp = resolve_csp(std::env::var("HUB_CSP").ok(), &hub.cloud_base_url);
        Self {
            database_url: std::env::var("HUB_DATABASE_URL").unwrap_or_default(),
            bind: std::env::var("HUB_BIND").unwrap_or_else(|_| "127.0.0.1:8787".into()),
            // Una sola lectura de `HUB_MODULES_DIR` (la de `HubConfig`): el mismo valor gobierna el
            // escaneo de arranque y el staging admitido por `/api/modules/install` (hub#239).
            modules_dir: hub
                .dev_modules_dir
                .as_ref()
                .map(|p| p.to_string_lossy().into_owned()),
            hub,
            machine_token_cell: None,
            hub_id_cell: None,
            // ECS/binario: el `dist/` se sirve de disco por `HUB_WEB_DIR` (paridad Hub Cloud).
            web_dir: std::env::var("HUB_WEB_DIR").ok().filter(|s| !s.is_empty()),
            // Nunca `None`: `HUB_CSP` solo puede SUSTITUIR la política (ver `resolve_csp`).
            csp,
        }
    }
}

/// Normaliza el DSN de `HUB_DATABASE_URL` para sqlx. El Cloud lo inyecta en forma SQLAlchemy
/// (`postgresql+asyncpg://user:pass@host:5432/db`), pero sqlx (`PgPool::connect`) espera el esquema
/// estándar `postgresql://`/`postgres://` (sin el sufijo de driver `+asyncpg`/`+psycopg`). Se quita
/// solo ese sufijo; el resto del DSN (credenciales/host/db) se respeta tal cual.
pub fn normalize_pg_dsn(url: &str) -> String {
    url.replacen("postgresql+asyncpg://", "postgresql://", 1)
        .replacen("postgres+asyncpg://", "postgres://", 1)
        .replacen("postgresql+psycopg://", "postgresql://", 1)
        .replacen("postgresql+psycopg2://", "postgresql://", 1)
}
