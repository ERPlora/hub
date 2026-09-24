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
//! ## Y el CONSUMO viaja en el mismo cuerpo (hub#1953)
//!
//! Un cupo, un contador. El cupo se vende —y Meta nos lo cobra— por los mensajes que el negocio
//! **manda**, que es la cuenta que ya lleva la plataforma (`usage.billable_messages`, el mismo
//! número que `check_quota` hace cumplir allí antes de gastar dinero, sumado sobre todas las
//! grafías de la métrica desde saas#1963). El medidor del módulo contaba otra cosa —los mensajes
//! que la clienta **escribe**—, así que bajo un mismo «30 al mes» había dos números que no se
//! parecen y el dueño no tenía forma de saber cuál le iba a cortar primero. Aquí se baja el gasto
//! junto al tope y el módulo pasa de contar a **reflejar**.
//!
//! ## Por qué se pregunta ANTES si el módulo lo acepta
//!
//! 🔴 La versión del módulo **no se mueve con la del hub**: un `whatsapp_inbox` más viejo sigue
//! instalando en un hub nuevo (ADR-0286 §3), y el carril del marketplace no promociona solo. El
//! `_quota.set` publicado hoy declara su schema con `additionalProperties: false`, así que mandarle
//! [`USAGE_FIELD`] a ciegas no es «un campo que se ignora»: es un `invalid_payload` que tumba el
//! command entero y deja de escribir **también el tope** — y un tope que no llega es, en este
//! medidor, un canal facturando por mensaje sin límite. Por eso el campo sólo viaja cuando el
//! command instalado lo **declara** ([`declares_usage`]), que es una pregunta al registro en
//! memoria: ni una llamada más, ni un código de error que interpretar.
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

/// El campo del payload de [`QUOTA_COMMAND`] que lleva el consumo del mes (whatsapp_inbox#155).
///
/// Es el nombre del contrato entre los dos repos: el módulo lo declara en
/// `schemas/quota_set.json` y aquí se pregunta por él literalmente. Si una de las dos mitades lo
/// escribiese distinto, el campo dejaría de viajar **en silencio** — de ahí que sea una constante
/// y no una cadena suelta, y que [`declares_usage`] tenga su propio test.
pub const USAGE_FIELD: &str = "monthly_usage";

/// Dónde vive el consumo del mes en el cuerpo de `whatsapp/plan/`: `usage.billable_messages`.
pub const PLAN_USAGE_KEYS: [&str; 2] = ["usage", "billable_messages"];

/// Qué hizo un tick de sincronización. Explícito a propósito: un resultado que se pueda ignorar es
/// como un límite acaba fallando en silencio.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum QuotaSync {
    /// Se escribió en el medidor. `monthly_usage` es el consumo que viajó con el tope: `None`
    /// cuando la plataforma no declaró uno utilizable **o** cuando el módulo instalado todavía no
    /// declara el campo — en los dos casos el gasto que ya midiera sigue midiendo, porque «no sé»
    /// nunca es «cero gastado».
    Written {
        monthly_limit: i64,
        monthly_usage: Option<i64>,
    },
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

/// Resuelve el consumo del mes a partir del cuerpo de `whatsapp/plan/`. `None` = este cuerpo no
/// declara uno utilizable, que **no** es lo mismo que decir cero.
///
/// 🔴 La regla es la del tope, pero el umbral es **distinto y a propósito**: aquí `0` SÍ es un
/// dato. En el tope `0` significa «sin límite», así que no se escribe; en el consumo significa
/// «este mes no has gastado nada» — es lo que ve el dueño el día 1, y tratarlo como «no sé» le
/// dejaría en pantalla el gasto del mes pasado. Lo que no se escribe es la **ausencia** (un cuerpo
/// de un SaaS anterior, o ilegible) y el **negativo**, que es un dato corrupto: los dos son «no
/// sé», y «no sé» regalaría el mes entero.
///
/// No se compara con el tope: gastar por encima es legítimo (un tier `is_metered` cobra el exceso,
/// `overage_price`), así que recortarlo aquí escondería justo la factura que el dueño necesita ver.
pub fn monthly_usage_from_plan(plan: &Value) -> Option<i64> {
    PLAN_USAGE_KEYS
        .iter()
        .try_fold(plan, |node, key| node.get(*key))
        .and_then(Value::as_i64)
        .filter(|value| *value >= 0)
}

/// ¿Declara el `_quota.set` **instalado** el campo del consumo?
///
/// `schema` es el JSON crudo del schema del command tal y como lo publicó el módulo (`None` = el
/// command no declara ninguno, y un command que no declara contrato no ha declarado este campo).
///
/// Se pregunta por las `properties` y no por la versión del módulo porque la versión es una
/// promesa y el schema es el contrato que el dispatcher va a hacer cumplir dentro de un instante:
/// es literalmente el mismo documento contra el que [`crate::state::SharedRuntime`] validará el
/// payload, así que las dos respuestas no pueden divergir.
pub fn declares_usage(schema: Option<&Value>) -> bool {
    schema
        .and_then(|schema| schema.get("properties"))
        .and_then(Value::as_object)
        .is_some_and(|properties| properties.contains_key(USAGE_FIELD))
}

/// UN tick de sincronización: mira si el canal está activo, pregunta al Cloud por el plan y, si
/// trae un tope bueno, lo escribe por la puerta interna del dispatcher — con el consumo al lado
/// cuando la plataforma lo declara y el módulo instalado sabe recibirlo.
pub async fn sync_once(
    runtime: &SharedRuntime,
    http: &reqwest::Client,
    cloud_base_url: &str,
    auth: &cloud_client::Auth,
) -> QuotaSync {
    // 1) ¿Está el canal instalado y activo? Mismo gate que `inbound_poll`. Va ANTES de la red a
    //    propósito: la flota que no compró el módulo no puede gastar cupo del cubo compartido.
    // También se mira aquí, bajo el MISMO lock, qué declara el `_quota.set` de la versión
    // instalada: son dos hechos del registro y tomarlos juntos evita un segundo `read()` que
    // podría ver otro módulo (una instalación entra entre medias) y decidir sobre un schema que
    // no es el que va a validar.
    let (hub_id, module_takes_usage) = {
        let rt = runtime.read().await;
        if !rt.registry().is_active(MODULE_ID) {
            return QuotaSync::ModuleNotActive;
        }
        let takes_usage = declares_usage(
            rt.registry()
                .get_command(QUOTA_COMMAND)
                .and_then(|command| command.schema.as_ref())
                .map(|schema| schema.raw.as_ref()),
        );
        (rt.hub_id().to_string(), takes_usage)
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

    // El consumo, sólo si se sabe Y el módulo instalado lo declara. Una rama explícita por caso: el
    // que no viaja deja el gasto anterior midiendo, que es lo correcto en los dos — nunca un `0`.
    let usage = match (monthly_usage_from_plan(&plan), module_takes_usage) {
        (Some(usage), true) => {
            payload.insert(USAGE_FIELD.to_string(), Value::from(usage));
            Some(usage)
        }
        (Some(usage), false) => {
            // La mitad del módulo (whatsapp_inbox#155) todavía no ha llegado a este hub. No es un
            // fallo —es la flota, y el tope sigue su curso—, pero el dueño sigue viendo dos cupos,
            // así que queda dicho. En el log, no en el registro de errores: se repetiría cada 24 h
            // en cada hub con el módulo anterior, y un aviso que sale siempre deja de leerse.
            tracing::info!(
                module = MODULE_ID,
                monthly_usage = usage,
                "el `_quota.set` instalado todavía no declara el consumo: se refleja sólo el tope"
            );
            None
        }
        (None, _) => None,
    };

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
                monthly_usage = usage,
                "cuota del canal sincronizada"
            );
            QuotaSync::Written {
                monthly_limit: limit,
                monthly_usage: usage,
            }
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

    /// El consumo sale de `usage.billable_messages`, y su umbral NO es el del tope: aquí `0` es un
    /// dato («este mes no has gastado nada»), porque el medidor guarda gasto, no permiso.
    #[test]
    fn el_consumo_sale_del_cuerpo_y_un_cero_si_es_un_dato() {
        assert_eq!(
            monthly_usage_from_plan(&json!({ "usage": { "billable_messages": 12 } })),
            Some(12)
        );
        assert_eq!(
            monthly_usage_from_plan(&json!({ "usage": { "billable_messages": 0 } })),
            Some(0),
            "«nada gastado» es el número que ve el dueño el día 1, no una ausencia"
        );
        assert_eq!(
            monthly_usage_from_plan(&json!({ "usage": { "conversations": 9 } })),
            None,
            "el alias de la unidad vieja no es esta métrica: el SaaS manda las dos y sólo una es la del cupo"
        );
        assert_eq!(
            monthly_usage_from_plan(&json!({ "tier": { "max_billable_messages": 30 } })),
            None,
            "sin `usage` no hay gasto que reflejar"
        );
        assert_eq!(
            monthly_usage_from_plan(&json!({ "usage": { "billable_messages": -3 } })),
            None,
            "un negativo es un dato corrupto: se conserva lo que ya medía"
        );
        assert_eq!(
            monthly_usage_from_plan(&json!({ "usage": { "billable_messages": "12" } })),
            None,
            "una cifra en texto no es una cifra"
        );
    }

    /// 🔴 El predicado que impide la regresión: el campo sólo viaja si el command instalado lo
    /// DECLARA. Un módulo anterior a whatsapp_inbox#155 lo rechazaría con `additionalProperties:
    /// false` y se llevaría el tope por delante.
    #[test]
    fn el_consumo_solo_viaja_si_el_command_instalado_lo_declara() {
        let publicado_hoy = json!({
            "type": "object",
            "additionalProperties": false,
            "properties": { "monthly_limit": { "type": "integer" } }
        });
        let tras_la_issue_hermana = json!({
            "type": "object",
            "additionalProperties": false,
            "properties": {
                "monthly_limit": { "type": "integer" },
                "monthly_usage": { "type": "integer" }
            }
        });

        assert!(
            !declares_usage(Some(&publicado_hoy)),
            "el de hoy no lo declara"
        );
        assert!(declares_usage(Some(&tras_la_issue_hermana)));
        assert!(
            !declares_usage(None),
            "un command sin schema no ha declarado este campo"
        );
        assert!(
            !declares_usage(Some(&json!({ "type": "object" }))),
            "sin `properties` no hay nada declarado"
        );
        assert!(
            !declares_usage(Some(
                &json!({ "properties": { "monthly_usage_extra": {} } })
            )),
            "el nombre se compara entero: un parecido no es el contrato"
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
