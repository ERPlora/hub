//! El hub IMPORTA el blueprint que el SaaS le DECLARÓ ([ADR-0212], hub#406).
//!
//! El seed (`HUB_SEED_SQL`) compra **acceso**; no puede comprar **datos**: corre antes de que
//! exista módulo alguno. El catálogo va por **import de blueprint**, que es HTTP y post-arranque —
//! y hasta ahora nadie lo disparaba, así que un hub recién provisionado (la demo de ADR-0197)
//! aterrizaba en el asistente de setup, que es demostrar lo contrario de un producto.
//!
//! ## Por qué lo hace el hub y no el SaaS
//!
//! La credencial solo va en un sentido: `X-Hub-Token` viaja hub→SaaS, y el runtime contesta **428**
//! a todo caller sin sesión local. Empujar exigiría inventar un plano de auth SaaS→hub — superficie
//! nueva en internet para un hub de 60 minutos. Además solo el hub sabe cuándo está listo **de
//! verdad** (la sonda del SaaS dice «el proceso sirve HTTP», no «se puede instalar un módulo»), y
//! la task es *stateless*: un **estado declarado** se vuelve a leer solo tras un reschedule,
//! mientras que un **evento empujado** habría que repetirlo desde fuera.
//!
//! ## Reglas que este módulo no puede romper
//!
//! - 🔴 **Un fallo NO tumba el arranque.** El seed se aplica con `?` dentro de `serve()` y un seed
//!   roto aborta el boot; esto no puede hacer eso — un blueprint roto dejaría al visitante **sin
//!   hub** en vez de con un hub sin catálogo. Por eso [`spawn_declared_blueprint_import`] devuelve
//!   un `JoinHandle`, nunca un `Result` que pueda subir al camino de `axum::serve`.
//! - **Reintentos acotados**, y luego rendición con reporte por el canal que ya existe
//!   (`error_registry` → `POST /api/v1/hub/device/error-report/`). Una demo sin catálogo sigue
//!   siendo un hub que funciona, y se recoge sola: `is_demo` + `expires_at` se escriben en el mismo
//!   `INSERT` que la fila, así que el reaper la destruye al vencer el TTL, sana o rota.
//! - **Idempotente entre reinicios.** El SaaS manda **bytes idénticos** en cada redespliegue (es un
//!   estado, no una orden), así que el marcador vive en la **BD del hub**, que sí sobrevive al
//!   contenedor. Reimportar duplicaría el catálogo entero.
//! - **`users` y `fiscal` fuera.** ADR-0195 los prohíbe en una plantilla y el motor los descarta
//!   igualmente (hub#331/hub#405): este import entra por el **mismo** `run_import` que la UI, así
//!   que no es una puerta trasera. El usuario `Demo` lo pone el seed, no el bundle.
//!
//! [ADR-0212]: architecture/saas/hub-provisioning.md

use std::time::Duration;

use erplora_runtime::error_registry::{severity, source, ErrorEvent, ErrorRegistry};
use erplora_runtime::import::ImportSelection;
use serde_json::{json, Value};
use tokio::task::JoinHandle;

use crate::state::AppState;

/// Clave del marcador en `_hub_meta`: qué blueprint declarado ya se aplicó en este hub.
pub const BOOTSTRAP_MARKER_KEY: &str = "bootstrap_blueprint";

/// Código estable del error que se reporta al Cloud cuando el import se rinde. Estable = contra él
/// se puede programar y agrupar; la frase cambia, el código no (misma lección que hub#139).
pub const BOOTSTRAP_FAILED_CODE: &str = "bootstrap_blueprint_failed";

/// Reintentos por defecto del arranque. Pocos y cortos a propósito: el hub que más necesita esto
/// vive 60 minutos, y un lazo largo solo retrasa la rendición — que ya es una respuesta válida.
const DEFAULT_ATTEMPTS: u32 = 3;
const DEFAULT_BACKOFF: Duration = Duration::from_secs(5);

/// El blueprint que el SaaS declaró para este hub: **identidad**, nunca el artefacto.
///
/// Viajan `slug` + `locale` porque la URL prefirmada lleva credencial, acaba en un log de deploy y
/// caduca en 1 h — menos de lo que vive una task que se reprograma.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct BootstrapBlueprint {
    /// Slug del catálogo (`restaurante`). Único **por idioma**.
    pub slug: String,
    /// Idioma del bundle (`es`). Sin él, un slug que existe en dos idiomas da **400** en el SaaS.
    pub locale: Option<String>,
}

impl BootstrapBlueprint {
    /// Lee las dos claves de env (`HUB_BOOTSTRAP_BLUEPRINT` / `HUB_BOOTSTRAP_BLUEPRINT_LOCALE`).
    ///
    /// Slug ausente o en blanco ⇒ `None`: el mecanismo es genérico y el SaaS decide quién lo recibe.
    /// Un slug **sin locale** SÍ es una declaración: desactivarlo en silencio sería exactamente el
    /// contrato muerto que este issue viene a evitar (`HUB_COUNTRY`), y un slug ambiguo lo dice el
    /// SaaS con un 400 que aquí se reporta.
    pub fn from_env_values(slug: Option<&str>, locale: Option<&str>) -> Option<Self> {
        let slug = slug.map(str::trim).filter(|s| !s.is_empty())?;
        Some(Self {
            slug: slug.to_string(),
            locale: locale
                .map(str::trim)
                .filter(|l| !l.is_empty())
                .map(str::to_string),
        })
    }

    /// Marcador que se guarda cuando este blueprint queda aplicado: `slug@version`.
    fn marker(&self, version: &str) -> String {
        format!("{}@{version}", self.slug)
    }
}

/// Cuántas veces se intenta y cuánto se espera entre intentos.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct RetryPolicy {
    /// Intentos TOTALES (1 = un solo intento, sin reintento).
    pub attempts: u32,
    /// Espera base entre intentos; crece linealmente con el número de intento.
    pub backoff: Duration,
}

impl Default for RetryPolicy {
    fn default() -> Self {
        Self {
            attempts: DEFAULT_ATTEMPTS,
            backoff: DEFAULT_BACKOFF,
        }
    }
}

/// En qué acabó el import de arranque. Lo devuelve la task para que el log —y los tests— puedan
/// distinguir «no había nada que hacer» de «ya estaba» de «se intentó y no pudo».
#[derive(Debug, Clone, PartialEq)]
pub enum BootstrapOutcome {
    /// El SaaS no declaró blueprint para este hub: no se toca el Cloud.
    NotDeclared,
    /// Ya se aplicó en un arranque anterior (marcador en la BD del hub).
    AlreadyApplied { slug: String, version: String },
    /// Aplicado ahora, con el informe del import (secciones + `installed_modules`).
    Imported {
        slug: String,
        version: String,
        report: Value,
    },
    /// Se agotaron los intentos. El hub sigue sirviendo, degradado.
    GaveUp { attempts: u32, error: String },
}

/// Lanza el import de arranque **en su propia task** y devuelve su handle, o `None` si el SaaS no
/// declaró nada.
///
/// 🔴 Esta firma es la garantía: no hay `Result` que `serve()` pueda propagar con `?`, así que un
/// blueprint roto **no puede** abortar el arranque. El hub escucha mientras esto ocurre por detrás.
pub fn spawn_declared_blueprint_import(st: &AppState) -> Option<JoinHandle<BootstrapOutcome>> {
    st.config.bootstrap_blueprint.as_ref()?;
    let st = st.clone();
    Some(tokio::spawn(async move {
        let outcome = import_declared_blueprint(&st, RetryPolicy::default()).await;
        log_outcome(&outcome);
        outcome
    }))
}

/// Reconcilia el blueprint declarado: marcador → resolver → descargar → verificar → importar.
///
/// Nunca devuelve `Err`: todo camino acaba en un [`BootstrapOutcome`], porque el llamador es el
/// arranque y ahí un error no tiene a quién subir.
pub async fn import_declared_blueprint(st: &AppState, retry: RetryPolicy) -> BootstrapOutcome {
    let Some(blueprint) = st.config.bootstrap_blueprint.clone() else {
        return BootstrapOutcome::NotDeclared;
    };

    // El marcador se mira ANTES de la red: un redespliegue no debe ni resolver otra vez.
    match applied_marker(st).await {
        Ok(Some(marker)) => {
            if let Some((slug, version)) = marker.split_once('@') {
                if slug == blueprint.slug {
                    return BootstrapOutcome::AlreadyApplied {
                        slug: slug.to_string(),
                        version: version.to_string(),
                    };
                }
            }
        }
        Ok(None) => {}
        // Sin marcador legible se sigue: perder el catálogo de una demo es peor que aplicarlo dos
        // veces, y las guardas `NOT EXISTS` del propio SQL del bundle amortiguan la repetición.
        Err(e) => tracing::warn!(error = %e, "bootstrap: no se pudo leer el marcador de import"),
    }

    let mut last_error = String::new();
    for attempt in 1..=retry.attempts {
        match try_import_once(st, &blueprint).await {
            Ok((version, report)) => {
                if let Err(e) = write_marker(st, &blueprint.marker(&version)).await {
                    // El dato YA está aplicado; lo que se pierde es la idempotencia del próximo
                    // arranque. Se dice fuerte en vez de fingir que no pasó.
                    tracing::error!(error = %e, "bootstrap: el blueprint se importó pero el marcador no se pudo escribir — un reinicio podría reimportarlo");
                }
                return BootstrapOutcome::Imported {
                    slug: blueprint.slug.clone(),
                    version,
                    report,
                };
            }
            Err(e) => {
                last_error = e;
                tracing::warn!(
                    slug = %blueprint.slug,
                    attempt,
                    attempts = retry.attempts,
                    error = %last_error,
                    "bootstrap: el import del blueprint declarado falló"
                );
                if attempt < retry.attempts {
                    tokio::time::sleep(retry.backoff * attempt).await;
                }
            }
        }
    }

    report_give_up(&blueprint, retry.attempts, &last_error);
    BootstrapOutcome::GaveUp {
        attempts: retry.attempts,
        error: last_error,
    }
}

/// Un intento: credencial de máquina → resolver+descargar+verificar → importar.
async fn try_import_once(
    st: &AppState,
    blueprint: &BootstrapBlueprint,
) -> Result<(String, Value), String> {
    // Se pide dentro del intento a propósito: la celda del token es viva (hot-reload), así que un
    // enrolamiento posterior habilita el siguiente reintento sin reiniciar el hub.
    let Some(auth) = crate::auth::machine_auth(st) else {
        return Err("hub sin token de máquina: no puede resolver el blueprint declarado".into());
    };

    let fetched = crate::fetch_blueprint(st, &auth, &blueprint.slug, blueprint.locale.as_deref())
        .await
        .map_err(|e| e.message())?;

    // Selección: módulos + settings + media. `users`/`fiscal` FUERA — ADR-0195 los prohíbe en una
    // plantilla y el motor los descarta igual; pedirlos aquí sería pedir que el motor diga que no.
    let selection = ImportSelection {
        users: false,
        settings: true,
        fiscal: false,
        media: true,
        modules: manifest_module_ids(&fetched.zip)?,
    };

    let data_hub_id = st.hub_id();
    match crate::export_import::run_import(st, Some(auth), &fetched.zip, selection, &data_hub_id)
        .await
    {
        Ok(report) => Ok((fetched.version, report)),
        Err(resp) => Err(response_message(resp).await),
    }
}

/// Ids de los módulos que el manifest declara: es lo que `ImportSelection.modules` espera, y aquí
/// no hay formulario que los marque — se importa lo que el bundle trae.
fn manifest_module_ids(zip: &[u8]) -> Result<Vec<String>, String> {
    let manifest = crate::export_import::read_manifest(zip)?;
    Ok(manifest.modules.into_iter().map(|m| m.id).collect())
}

/// Marcador ya escrito en la BD de ESTE hub, si lo hay.
async fn applied_marker(st: &AppState) -> Result<Option<String>, String> {
    let arc = st
        .runtime_for(&st.hub_id())
        .await
        .map_err(|e| e.to_string())?;
    let rt = arc.lock().await;
    erplora_runtime::hub_meta::get(rt.db(), BOOTSTRAP_MARKER_KEY)
        .await
        .map_err(|e| e.to_string())
}

/// Deja constancia de qué blueprint quedó aplicado. Se escribe SOLO tras un import que devolvió
/// informe: un rechazo duro (integridad) no toca la BD y debe poder reintentarse.
async fn write_marker(st: &AppState, marker: &str) -> Result<(), String> {
    let arc = st
        .runtime_for(&st.hub_id())
        .await
        .map_err(|e| e.to_string())?;
    let rt = arc.lock().await;
    erplora_runtime::hub_meta::set(rt.db(), BOOTSTRAP_MARKER_KEY, marker)
        .await
        .map_err(|e| e.to_string())
}

/// Mensaje legible de la `Response` de error que devuelve `run_import` (contrato
/// `{ ok: false, error }`). El arranque no responde a nadie: lo que necesita es la frase, para el
/// log y para el reporte al Cloud.
async fn response_message(resp: axum::response::Response) -> String {
    let status = resp.status();
    match extract_error_text(resp).await {
        Some(text) => format!("import rechazado ({status}): {text}"),
        None => format!("import rechazado ({status})"),
    }
}

async fn extract_error_text(resp: axum::response::Response) -> Option<String> {
    let bytes = axum::body::to_bytes(resp.into_body(), 64 * 1024)
        .await
        .ok()?;
    let value: Value = serde_json::from_slice(&bytes).ok()?;
    value["error"].as_str().map(str::to_string)
}

/// Reporta la rendición por el embudo único de errores del runtime (`error_sink` → Cloud).
/// Best-effort por contrato: sin sink instalado se descarta en silencio y el hub sigue.
fn report_give_up(blueprint: &BootstrapBlueprint, attempts: u32, error: &str) {
    tracing::error!(
        slug = %blueprint.slug,
        attempts,
        error,
        "bootstrap: se abandona el import del blueprint declarado — el hub sigue sirviendo, sin catálogo"
    );
    ErrorRegistry::global().report(
        ErrorEvent::new(
            source::HUB,
            BOOTSTRAP_FAILED_CODE,
            format!(
                "no se pudo importar el blueprint declarado «{}» tras {attempts} intento(s): {error}",
                blueprint.slug
            ),
            severity::UNEXPECTED,
        )
        .with_context(json!({
            "slug": blueprint.slug,
            "locale": blueprint.locale,
            "attempts": attempts,
        })),
    );
}

/// Traza del desenlace: es lo que dirá, en el log del contenedor, si un hub nació vacío porque
/// nadie se lo declaró, porque ya estaba, o porque el import no pudo.
fn log_outcome(outcome: &BootstrapOutcome) {
    match outcome {
        BootstrapOutcome::NotDeclared => {}
        BootstrapOutcome::AlreadyApplied { slug, version } => {
            tracing::info!(%slug, %version, "bootstrap: el blueprint declarado ya estaba aplicado")
        }
        BootstrapOutcome::Imported {
            slug,
            version,
            report,
        } => {
            // El informe por módulo es lo que distingue un fallo de entitlement de uno de
            // artefacto: `installed` / `already_installed` / `blocked` / `failed`.
            tracing::info!(
                %slug, %version,
                modules = %report["installed_modules"],
                "bootstrap: blueprint declarado importado"
            )
        }
        BootstrapOutcome::GaveUp { .. } => {} // ya reportado en report_give_up
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Las dos claves se leen como hermanas de `HUB_SECTOR`: en blanco ⇒ nada declarado.
    #[test]
    fn a_blank_slug_declares_nothing() {
        assert_eq!(BootstrapBlueprint::from_env_values(None, Some("es")), None);
        assert_eq!(
            BootstrapBlueprint::from_env_values(Some(""), Some("es")),
            None
        );
        assert_eq!(BootstrapBlueprint::from_env_values(Some("   "), None), None);
    }

    /// Un slug SIN locale sigue siendo una declaración: apagarlo en silencio es lo que convirtió a
    /// `HUB_COUNTRY` en un contrato muerto. Ambiguo lo dirá el SaaS con un 400, que sí se reporta.
    #[test]
    fn a_slug_without_locale_is_still_a_declaration() {
        let bp = BootstrapBlueprint::from_env_values(Some("restaurante"), None)
            .expect("un slug declarado no se ignora por no traer idioma");
        assert_eq!(bp.slug, "restaurante");
        assert_eq!(bp.locale, None);
    }

    /// El env llega con espacios de sobra más veces de las que parece (un `.env` copiado a mano).
    #[test]
    fn both_halves_are_trimmed() {
        let bp = BootstrapBlueprint::from_env_values(Some(" restaurante "), Some(" es "))
            .expect("declarado");
        assert_eq!(bp.slug, "restaurante");
        assert_eq!(bp.locale.as_deref(), Some("es"));
    }

    /// El marcador lleva la versión aplicada, y la comparación de idempotencia es por SLUG: una
    /// versión nueva del mismo blueprint NO se reimporta (duplicaría el catálogo), un slug distinto
    /// sí es un estado declarado distinto.
    #[test]
    fn the_marker_carries_slug_and_version() {
        let bp = BootstrapBlueprint::from_env_values(Some("restaurante"), Some("es")).unwrap();
        assert_eq!(bp.marker("1.4.0"), "restaurante@1.4.0");
        let (slug, version) = bp
            .marker("1.4.0")
            .split_once('@')
            .map(|(s, v)| (s.to_string(), v.to_string()))
            .unwrap();
        assert_eq!(slug, "restaurante");
        assert_eq!(version, "1.4.0");
    }

    /// Por defecto: acotado. Un lazo infinito contra un Cloud caído es un hub que no se rinde nunca
    /// en un host que vive una hora.
    #[test]
    fn the_default_retry_is_bounded() {
        let policy = RetryPolicy::default();
        assert!(policy.attempts >= 1 && policy.attempts <= 5, "{policy:?}");
        assert!(policy.backoff > Duration::ZERO);
    }
}
