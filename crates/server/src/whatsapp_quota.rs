//! Sincronización de la **cuota del plan de WhatsApp** hacia el medidor del módulo (hub#1089).
//!
//! `whatsapp_inbox_settings.free_tier_monthly_limit` es el contador de la facturación del canal:
//! las dos guardas de ingesta del módulo (`commands/message_ingest_msg.sql`,
//! `commands/inbound_message_insert.sql`) sólo cuentan mensajes entrantes mientras sea `> 0`.
//! Hasta hub#1089 **nadie lo escribía nunca**, así que valía `0` en toda la flota: el plan gratuito
//! no tenía tope, en silencio, y el módulo se cobra por mensaje.
//!
//! **El dueño del número es billing, en el Cloud** (`apps/whatsapp_inbox/services/billing.py` +
//! `apps/public/modules/usage.py`, ADR-0013/ADR-0032). Aquí sólo se refleja.
//!
//! **La dirección la fija ADR-0213**: no existe plano SaaS→hub —los hubs viven tras NAT y no hay
//! credencial con la que empujarles nada—, así que el número llega como llega cualquier otro hecho
//! del Cloud: **el hub tira**. Y tira en el tick que ya existe, el del entitlement (24 h), en vez
//! de abrir un tercer poller: cambiar de plan no es un evento de segundos, y una llamada más al
//! SaaS la paga toda la flota, que comparte cubo de tasa (saas#1640, hub#1167).
//!
//! ## De dónde sale el número: el endpoint, EN VIVO, con la credencial de MÁQUINA
//!
//! `GET /api/v1/hub/device/whatsapp/plan/` con `X-Hub-Token` + `X-Hub-Id` — el plano que ADR-0003
//! asigna a lo hub-scoped **sin usuario**, que es exactamente lo que es un tick de background: no
//! hay nadie logueado de quien tomar prestado un JWT. Es la misma credencial con la que el hub ya
//! drena su bandeja (`inbound_poll`) y manda mensajes (`notify_whatsapp`).
//!
//! No viaja como claim firmado dentro del entitlement, y la razón es que ese endpoint devuelve
//! **tier + consumo**: el consumo es un contador vivo que se mueve con cada mensaje, así que un
//! claim de 24 h nacería rancio. Un claim sirve para el **límite** del plan, no para el gasto — y
//! tener el mismo número en dos sitios es como los dos acaban divergiendo.
//!
//! El tope llega ya resuelto por el SaaS (`max_billable_messages`, con su alias
//! `max_conversations`): la precedencia entre las tres claves de cuota la aplica él, que es quien
//! conoce sus propios tiers, y aquí no se replica.
//!
//! ## La regla que no se negocia
//!
//! **Si no hay una cuota buena, no se escribe.** Ni `0`, ni un valor «por defecto». Un fallo de
//! red, un `tier: null` o un tope de `0` significan *no sé*, y en el medidor `0` significa *sin
//! tope*: son cosas opuestas, y confundirlas es facturar por mensaje sin límite. Por eso
//! [`sync_once`] tiene un resultado explícito y ninguna rama silenciosa.

use erplora_db::Params;
use erplora_runtime::RequestContext;
use serde_json::{json, Value};

use crate::state::SharedRuntime;

/// El módulo cuyo canal se mide (el mismo que poletea `crate::inbound_poll`).
pub const MODULE_ID: &str = "whatsapp_inbox";

/// El command **interno** que es el único escritor del medidor (whatsapp_inbox#37/#38). Es
/// `internal: true`, así que sólo lo alcanza el runtime: por la puerta pública, por una API key o
/// por el asistente responde `internal_command`. Ésa es justamente la razón de que exista — antes
/// lo escribía `settings.upsert` desde su payload y cualquiera con `manage_settings` podía poner
/// su propio medidor a cero.
pub const QUOTA_COMMAND: &str = "whatsapp_inbox._quota.set";

/// Campos de `tier` que traen el tope mensual, **en orden de precedencia**, tal y como los arma
/// `whatsapp_plan` (`saas/apps/whatsapp_inbox/api/views.py`). El primero es el nombre de después
/// de la migración de Meta al precio por mensaje entregado; el segundo es el alias que el propio
/// SaaS mantiene para hubs anteriores a ella. Los dos llevan el mismo número.
pub const PLAN_LIMIT_KEYS: [&str; 2] = ["max_billable_messages", "max_conversations"];

/// Qué hizo un tick de sincronización. Explícito a propósito: un resultado que se pueda ignorar es
/// como un límite acaba fallando en silencio.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum QuotaSync {
    /// Se escribió este tope mensual en el medidor.
    Written(i64),
    /// El módulo no está instalado/activo en este hub: no hay nada que medir, y **no se pregunta**.
    ModuleNotActive,
    /// El Cloud contestó, pero no declara un tope utilizable (`tier: null`, sin las claves, o un
    /// `0`). **No se escribe**: lo que ya midiera sigue midiendo.
    NoQuotaKnown,
    /// No se pudo preguntar (red, 4xx/5xx, cuerpo ilegible). Queda registrado y visible; el
    /// medidor conserva su valor anterior. Un fallo de red **no** es un plan sin tope.
    CloudUnreachable(String),
    /// El command falló. Queda registrado y visible; el medidor conserva su valor anterior.
    Failed(String),
}

/// Resuelve el tope mensual a partir del cuerpo de `whatsapp/plan/`. `None` = este plan no dice
/// nada utilizable, que **no** es lo mismo que decir cero.
///
/// Sólo vale un tope **estrictamente positivo**: el SaaS manda `0` cuando el tier no declara
/// ninguna de sus claves de cuota (`… or 0`), y en el medidor del módulo `0` desactiva el tope. Un
/// negativo es un dato corrupto. Los dos casos son «no sé», y «no sé» no se escribe.
pub fn monthly_limit_from_plan(plan: &Value) -> Option<i64> {
    let tier = plan.get("tier")?;
    PLAN_LIMIT_KEYS
        .iter()
        .find_map(|key| tier.get(*key).and_then(Value::as_i64))
        .filter(|value| *value > 0)
}

/// UN tick de sincronización: mira si el canal está activo, pregunta al Cloud por el plan y, si
/// trae un tope bueno, lo escribe por la puerta interna del dispatcher.
pub async fn sync_once(
    runtime: &SharedRuntime,
    http: &reqwest::Client,
    cloud_base_url: &str,
    auth: &cloud_client::Auth,
) -> QuotaSync {
    // 1) ¿Está el canal instalado y activo? Mismo gate que `inbound_poll`. Va ANTES de la red a
    //    propósito: la flota que no compró el módulo no puede gastar cupo del cubo compartido.
    let hub_id = {
        let rt = runtime.read().await;
        if !rt.registry().is_active(MODULE_ID) {
            return QuotaSync::ModuleNotActive;
        }
        rt.hub_id().to_string()
    };

    // 2) Preguntar. Si no se puede, NO se escribe: ésta es la rama que impide convertir un
    //    silencio de la red en un «sin tope».
    let plan = match fetch_plan(http, cloud_base_url, auth).await {
        Ok(plan) => plan,
        Err(reason) => {
            report_unreachable(&reason);
            return QuotaSync::CloudUnreachable(reason);
        }
    };
    let Some(limit) = monthly_limit_from_plan(&plan) else {
        return QuotaSync::NoQuotaKnown;
    };

    // 3) Escribir. `execute_command_internal` es la puerta del host embebedor: el mismo
    //    `Origin::Internal` con el que el relay del Outbox y el scheduler alcanzan lo interno.
    // Contexto de SISTEMA, exactamente el del scheduler (`scheduler::system_ctx`): no hay usuario
    // detrás de un tick, y el permiso comodín es el que ya usa el runtime cuando actúa por su
    // cuenta. No abre ninguna puerta nueva: el command sigue siendo `internal`.
    let ctx = RequestContext::new(hub_id, String::new(), ["*".to_string()]);
    let mut payload = Params::new();
    payload.insert("monthly_limit".to_string(), Value::from(limit));

    let result = {
        let rt = runtime.read().await;
        rt.execute_command_internal(QUOTA_COMMAND, &payload, &ctx)
            .await
    };
    match result {
        Ok(_) => {
            tracing::info!(
                module = MODULE_ID,
                monthly_limit = limit,
                "cuota del canal sincronizada"
            );
            QuotaSync::Written(limit)
        }
        Err(e) => {
            let code = erplora_runtime::error_registry::error_code_of(&e).to_string();
            report_failure(&code, limit);
            QuotaSync::Failed(code)
        }
    }
}

/// `GET /api/v1/hub/device/whatsapp/plan/` con la credencial de máquina. Devuelve el cuerpo JSON
/// o el motivo por el que no hay cuerpo — nunca un cuerpo inventado.
async fn fetch_plan(
    http: &reqwest::Client,
    cloud_base_url: &str,
    auth: &cloud_client::Auth,
) -> Result<Value, String> {
    let request = cloud_client::CloudClient::new(cloud_base_url).whatsapp_plan(auth);
    let mut builder = http.get(&request.url);
    for (key, value) in request.headers {
        builder = builder.header(key, value);
    }
    let response = builder.send().await.map_err(|e| e.to_string())?;
    let status = response.status();
    if !status.is_success() {
        return Err(format!("status {status}"));
    }
    response
        .json::<Value>()
        .await
        .map_err(|e| format!("cuerpo ilegible: {e}"))
}

/// Deja VISIBLE que no se pudo preguntar. Un medidor que no se refresca deja el canal facturando
/// con el tope viejo (o sin ninguno, si nunca hubo), así que el fallo no puede ser mudo.
fn report_unreachable(reason: &str) {
    use erplora_runtime::error_registry::{ErrorEvent, ErrorRegistry};

    tracing::error!(
        module = MODULE_ID,
        reason,
        "no se pudo leer el plan de WhatsApp del Cloud: el medidor conserva su valor anterior"
    );
    ErrorRegistry::global().report(
        ErrorEvent::new(
            erplora_runtime::error_registry::source::HUB,
            "whatsapp_quota_fetch_failed",
            format!("`whatsapp/plan/` no contestó: {reason}"),
            erplora_runtime::error_registry::severity::UNEXPECTED,
        )
        .with_module(MODULE_ID)
        .with_context(json!({ "reason": reason })),
    );
}

/// Deja el fallo VISIBLE. Es lo que separa esto de la incidencia original: un medidor que no se
/// escribe deja el canal facturando sin tope, así que no puede fallar callado. Va al log del
/// runtime **y** al registro de errores, que es el canal que llega al Cloud.
fn report_failure(code: &str, attempted_limit: i64) {
    use erplora_runtime::error_registry::{ErrorEvent, ErrorRegistry};

    tracing::error!(
        module = MODULE_ID,
        error_code = code,
        attempted_limit,
        "no se pudo escribir la cuota del canal de WhatsApp: el medidor conserva su valor anterior"
    );
    ErrorRegistry::global().report(
        ErrorEvent::new(
            erplora_runtime::error_registry::source::HUB,
            "whatsapp_quota_sync_failed",
            format!("`{QUOTA_COMMAND}` falló con `{code}` al fijar {attempted_limit}"),
            erplora_runtime::error_registry::severity::UNEXPECTED,
        )
        .with_module(MODULE_ID)
        .with_context(json!({ "error_code": code, "attempted_limit": attempted_limit })),
    );
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    /// El tope puede venir con dos nombres según la edad del hub (el SaaS manda los dos y el
    /// segundo es su alias de compatibilidad). Se resuelven con precedencia, y un plan que no
    /// declara ninguno no es un cero: es «no sé».
    #[test]
    fn el_tope_se_resuelve_con_la_precedencia_del_saas() {
        assert_eq!(
            monthly_limit_from_plan(&json!({
                "tier": { "max_conversations": 30, "max_billable_messages": 99 }
            })),
            Some(99),
            "`max_billable_messages` es el nombre nuevo y gana"
        );
        assert_eq!(
            monthly_limit_from_plan(&json!({ "tier": { "max_conversations": 30 } })),
            Some(30),
            "el alias de compatibilidad lleva el mismo número"
        );
        assert_eq!(
            monthly_limit_from_plan(&json!({ "tier": { "otra_cosa": 5 } })),
            None,
            "una cuota de otra métrica no es la de este canal"
        );
        assert_eq!(
            monthly_limit_from_plan(&json!({ "tier": Value::Null })),
            None
        );
        assert_eq!(
            monthly_limit_from_plan(&json!({ "usage": { "billable_messages": 7 } })),
            None,
            "sin tier no hay plan que reflejar"
        );
    }

    /// `0` es lo que manda el SaaS cuando el tier no declara ninguna clave de cuota (`… or 0`), y
    /// en el medidor `0` DESACTIVA el tope. Escribirlo sería el bug de hub#1089 por el otro lado.
    #[test]
    fn un_cero_o_un_negativo_no_son_un_tope() {
        assert_eq!(
            monthly_limit_from_plan(&json!({ "tier": { "max_billable_messages": 0 } })),
            None,
            "`0` en el medidor significa «sin tope»: no se escribe por no saber"
        );
        assert_eq!(
            monthly_limit_from_plan(&json!({ "tier": { "max_billable_messages": -1 } })),
            None,
            "un número imposible no se escribe: el medidor es un contador, no un capricho"
        );
    }
}
