//! El hub tira de la cuota del plan de WhatsApp y la escribe en el medidor (hub#1089).
//!
//! `whatsapp_inbox_settings.free_tier_monthly_limit` es el contador de la facturación del canal:
//! las dos guardas de ingesta del módulo sólo cuentan mensajes entrantes mientras sea `> 0`. Hasta
//! aquí **nadie lo escribía nunca**, así que valía `0` en toda la flota y el plan gratuito no tenía
//! tope — en silencio, que es la peor manera de que falle un límite.
//!
//! El dueño del número es **billing, en el Cloud**; el hub sólo lo refleja. Y la dirección la fija
//! ADR-0213: no existe plano SaaS→hub (los hubs viven tras NAT y no hay credencial para empujarles
//! nada), así que el número llega como llega cualquier otro hecho del Cloud — **el hub tira**, en
//! el mismo tick de 24 h que ya refresca el entitlement, sin abrir un tercer poller.
//!
//! **De dónde sale el número: `GET /api/v1/hub/device/whatsapp/plan/`, EN VIVO y con la credencial
//! de MÁQUINA** (`X-Hub-Token` + `X-Hub-Id`) — el plano que ADR-0003 asigna a lo hub-scoped sin
//! usuario, que es lo que es un tick de background. No viaja como claim firmado dentro del
//! entitlement porque ese endpoint devuelve *tier + consumo*, y el consumo es un contador vivo que
//! se mueve con cada mensaje: un claim de 24 h nace rancio. Un número en dos sitios es un número
//! que acaba divergiendo.
//!
//! Lo que estos tests fijan es lo que es del hub: **cuándo** se pregunta, **qué** se escribe y
//! —sobre todo— **cuándo NO**. Un `0` escrito por un fallo de red es un canal sin tope facturando
//! por mensaje, así que el silencio nunca puede confundirse con «plan sin límite».

use std::path::PathBuf;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Arc;
use std::sync::Mutex as StdMutex;

use axum::extract::Request;
use axum::http::{HeaderMap, StatusCode};
use axum::routing::get;
use axum::{Json, Router};
use erplora_db::testutil::fresh_db;
use erplora_db::Params;
use erplora_runtime::Runtime;
use erplora_server::whatsapp_quota::{self, QuotaSync};
use serde_json::{json, Value};
use tokio::sync::RwLock;

/// `Params` es un `Map<String, Json>`; este envoltorio evita repetir la construcción en cada test.
fn params<const N: usize>(pairs: [(&str, Value); N]) -> Params {
    let mut p = Params::new();
    for (k, v) in pairs {
        p.insert(k.to_string(), v);
    }
    p
}

const HUB: &str = "hub-wa";
const MACHINE_TOKEN: &str = "machine-secret";
/// La ruta real del SaaS (`cloud_client::CloudClient::whatsapp_plan`).
const CLOUD_PATH: &str = "/api/v1/hub/device/whatsapp/plan/";

/// El módulo tal y como está PUBLICADO hoy: su `_quota.set` sólo declara `monthly_limit`, y su
/// schema es `additionalProperties: false` como el de verdad.
fn fixture() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixture_wa_quota")
}

/// El módulo DESPUÉS de whatsapp_inbox#155: su `_quota.set` declara además `monthly_usage` y la
/// fila de ajustes tiene dónde guardarlo.
fn fixture_con_consumo() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixture_wa_quota_usage")
}

/// Un hub cuyo registro lleva de verdad `whatsapp_inbox`, instalado por la ÚNICA puerta que
/// registra algo (`install_from_dir`) — no un mapa de estado tocado a mano.
async fn hub(installed: bool) -> Arc<RwLock<Runtime>> {
    hub_con(if installed { Some(fixture()) } else { None }).await
}

/// El mismo hub, eligiendo QUÉ VERSIÓN del módulo está instalada. Es la diferencia que importa en
/// esta issue: la versión del módulo no se mueve con la del hub (ADR-0286 §3), así que el tick
/// tiene que sostener las dos.
async fn hub_con(fixture: Option<PathBuf>) -> Arc<RwLock<Runtime>> {
    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), HUB);
    rt.ensure_system_tables().await.unwrap();
    if let Some(dir) = fixture {
        rt.install_from_dir(&dir).await.unwrap();
    }
    Arc::new(RwLock::new(rt))
}

/// La credencial de MÁQUINA del hub — la única que un tick de background puede tener.
fn machine_auth() -> cloud_client::Auth {
    cloud_client::Auth::HubToken {
        hub_id: HUB.to_string(),
        token: MACHINE_TOKEN.to_string(),
    }
}

/// Lo que el Cloud simulado ha visto: cuántas veces le preguntaron y con qué cabeceras.
#[derive(Clone, Default)]
struct Seen {
    calls: Arc<AtomicUsize>,
    headers: Arc<StdMutex<Vec<HeaderMap>>>,
}

impl Seen {
    fn calls(&self) -> usize {
        self.calls.load(Ordering::SeqCst)
    }

    fn last_headers(&self) -> HeaderMap {
        self.headers
            .lock()
            .unwrap()
            .last()
            .cloned()
            .unwrap_or_default()
    }
}

/// Cloud simulado que CUENTA las llamadas al plan y responde lo que le diga `script`.
///
/// `script(n)` recibe el número de llamada (1-based), así un test puede decir «la primera devuelve
/// 30 y la segunda 200», que es exactamente lo que hace un cambio de plan entre dos ticks.
fn mock_cloud<F>(seen: Seen, script: F) -> Router
where
    F: Fn(usize) -> (StatusCode, Value) + Clone + Send + Sync + 'static,
{
    Router::new().route(
        CLOUD_PATH,
        get(move |request: Request| {
            let seen = seen.clone();
            let script = script.clone();
            async move {
                seen.headers.lock().unwrap().push(request.headers().clone());
                let n = seen.calls.fetch_add(1, Ordering::SeqCst) + 1;
                let (status, body) = script(n);
                (status, Json(body))
            }
        }),
    )
}

/// Arranca el Cloud simulado y devuelve su URL base y lo que va viendo.
async fn cloud<F>(script: F) -> (String, Seen)
where
    F: Fn(usize) -> (StatusCode, Value) + Clone + Send + Sync + 'static,
{
    let seen = Seen::default();
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    let router = mock_cloud(seen.clone(), script);
    tokio::spawn(async move { axum::serve(listener, router).await.unwrap() });
    (format!("http://{address}"), seen)
}

/// La respuesta del SaaS tal y como la arma `whatsapp_plan`: el tope YA resuelto por él (con su
/// precedencia de claves) más el consumo del mes, que es lo que obliga a leerlo en vivo.
fn plan_body(max_billable_messages: Value) -> Value {
    plan_body_con_consumo(max_billable_messages, json!(7))
}

/// El mismo cuerpo, eligiendo el consumo que declara el SaaS. `usage.billable_messages` es el
/// gasto del mes en curso en la MISMA unidad que el tope, sumado por el SaaS sobre todas las
/// grafías de la métrica (saas#1963), y es el número que `check_quota` hace cumplir allí.
fn plan_body_con_consumo(max_billable_messages: Value, billable_messages: Value) -> Value {
    let mut usage = json!({ "conversations": 7, "month": "2026-08" });
    if !billable_messages.is_null() {
        usage["billable_messages"] = billable_messages;
    }
    json!({
        "tier": {
            "slug": "free",
            "name": "WhatsApp Free",
            "price_monthly": "0.00",
            "max_billable_messages": max_billable_messages,
            "max_conversations": max_billable_messages,
            "is_metered": false,
            "overage_price": "0.00",
        },
        "usage": usage,
        "available_tiers": [],
    })
}

/// Un tick completo contra el Cloud simulado.
async fn sync(runtime: &Arc<RwLock<Runtime>>, base_url: &str) -> QuotaSync {
    whatsapp_quota::sync_once(runtime, &reqwest::Client::new(), base_url, &machine_auth()).await
}

/// El medidor tal y como está guardado. `None` = la fila singleton ni siquiera existe.
async fn stored_limit(runtime: &Arc<RwLock<Runtime>>) -> Option<i64> {
    let rt = runtime.read().await;
    let rows = rt
        .db()
        .query(
            "SELECT free_tier_monthly_limit FROM whatsapp_inbox_settings \
             WHERE hub_id = :hub_id AND is_deleted = 0",
            &params([("hub_id", Value::from(HUB))]),
        )
        .await
        .unwrap()
        .rows;
    rows.first()
        .and_then(|r| r.get("free_tier_monthly_limit"))
        .and_then(Value::as_i64)
}

/// El consumo tal y como está guardado en el medidor del módulo (sólo existe en la versión
/// posterior a whatsapp_inbox#155). `None` = la fila singleton ni siquiera existe.
async fn stored_usage(runtime: &Arc<RwLock<Runtime>>) -> Option<i64> {
    let rt = runtime.read().await;
    let rows = rt
        .db()
        .query(
            "SELECT monthly_usage FROM whatsapp_inbox_settings \
             WHERE hub_id = :hub_id AND is_deleted = 0",
            &params([("hub_id", Value::from(HUB))]),
        )
        .await
        .unwrap()
        .rows;
    rows.first()
        .and_then(|r| r.get("monthly_usage"))
        .and_then(Value::as_i64)
}

/// ⓵ El caso que la issue pide literalmente: un hub con el módulo instalado y un tier de **30**
/// acaba con `free_tier_monthly_limit = 30` **sin que nadie abra la pantalla de ajustes** — el
/// command siembra la fila singleton, porque la ingesta tampoco espera a que nadie la abra.
#[tokio::test]
async fn un_tier_de_30_deja_el_medidor_en_30_sin_abrir_los_ajustes() {
    let runtime = hub(true).await;
    assert_eq!(
        stored_limit(&runtime).await,
        None,
        "de partida no hay ni fila"
    );
    let (base_url, seen) = cloud(|_| (StatusCode::OK, plan_body(json!(30)))).await;

    let outcome = sync(&runtime, &base_url).await;

    assert_eq!(
        outcome,
        QuotaSync::Written {
            monthly_limit: 30,
            // `hub(true)` instala el módulo PUBLICADO, que todavía no declara el consumo: el
            // tope viaja igual y el gasto no, que es justo la tolerancia de versión de hub#1953.
            monthly_usage: None,
        }
    );
    assert_eq!(stored_limit(&runtime).await, Some(30));
    assert_eq!(seen.calls(), 1, "un tick, una llamada");
}

/// ⓶ **La credencial.** El tick pregunta con el token de MÁQUINA del hub y con NINGÚN JWT de
/// usuario, porque no hay ninguno que pedir prestado. Es el contrato que sostiene todo lo demás:
/// mientras el endpoint fue `IsHubMember` esta llamada era imposible de hacer.
#[tokio::test]
async fn el_tick_pregunta_con_la_credencial_de_maquina_y_sin_usuario() {
    let runtime = hub(true).await;
    let (base_url, seen) = cloud(|_| (StatusCode::OK, plan_body(json!(30)))).await;

    sync(&runtime, &base_url).await;

    let headers = seen.last_headers();
    assert_eq!(
        headers.get("x-hub-token").and_then(|v| v.to_str().ok()),
        Some(MACHINE_TOKEN),
        "sin el token de máquina el SaaS no tiene con qué autenticar al hub"
    );
    assert_eq!(
        headers.get("x-hub-id").and_then(|v| v.to_str().ok()),
        Some(HUB),
        "el token es POR HUB: sin `X-Hub-Id` no hay contra quién compararlo"
    );
    assert!(
        headers.get("authorization").is_none(),
        "un tick de background no tiene sesión de la que sacar un JWT de usuario"
    );
}

/// ⓷ Un cambio de plan (30 → 200) se refleja en el siguiente tick, y **sin pisar** lo que es del
/// comerciante: el `ON CONFLICT` sólo mueve el medidor.
#[tokio::test]
async fn un_cambio_de_plan_se_refleja_en_el_siguiente_tick_sin_pisar_los_ajustes() {
    let runtime = hub(true).await;
    let (base_url, _seen) = cloud(|n| {
        let limit = if n == 1 { 30 } else { 200 };
        (StatusCode::OK, plan_body(json!(limit)))
    })
    .await;
    sync(&runtime, &base_url).await;
    // El comerciante escribe su saludo entre los dos ticks.
    {
        let rt = runtime.read().await;
        rt.db()
            .execute(
                "UPDATE whatsapp_inbox_settings SET greeting = :g WHERE hub_id = :hub_id",
                &params([("g", Value::from("Hola!")), ("hub_id", Value::from(HUB))]),
            )
            .await
            .unwrap();
    }

    let outcome = sync(&runtime, &base_url).await;

    assert_eq!(
        outcome,
        QuotaSync::Written {
            monthly_limit: 200,
            monthly_usage: None,
        }
    );
    assert_eq!(stored_limit(&runtime).await, Some(200));
    let greeting = {
        let rt = runtime.read().await;
        rt.db()
            .query(
                "SELECT greeting FROM whatsapp_inbox_settings WHERE hub_id = :hub_id",
                &params([("hub_id", Value::from(HUB))]),
            )
            .await
            .unwrap()
            .rows
            .first()
            .and_then(|r| r.get("greeting"))
            .and_then(|v| v.as_str().map(str::to_string))
    };
    assert_eq!(
        greeting.as_deref(),
        Some("Hola!"),
        "un cambio de plan no puede borrar el saludo del comerciante"
    );
}

/// ⓸ **Lo más importante.** Si el SaaS no declara un tope utilizable, NO se escribe nada. Escribir
/// `0` es exactamente el bug de hub#1089 visto desde el otro lado: en el medidor `0` significa
/// «sin tope», así que sería abrir el canal de par en par creyendo que se cierra.
#[tokio::test]
async fn sin_una_cuota_buena_del_saas_no_se_escribe_nada() {
    // (a) El hub no tiene tier resuelto (nunca compró, o el SaaS no lo sabe): `tier: null`.
    let runtime = hub(true).await;
    let (base_url, _seen) = cloud(|_| {
        (
            StatusCode::OK,
            json!({ "tier": Value::Null, "usage": {}, "available_tiers": [] }),
        )
    })
    .await;
    let outcome = sync(&runtime, &base_url).await;
    assert_eq!(outcome, QuotaSync::NoQuotaKnown);
    assert_eq!(stored_limit(&runtime).await, None, "no se siembra un 0");

    // (b) Hay tier pero su cuota es `0` — que es lo que el SaaS manda cuando el tier no declara
    //     ninguna de sus claves (`… or 0`). Ausencia de dato NO es dato «sin límite».
    let runtime = hub(true).await;
    let (base_url, _seen) = cloud(|_| (StatusCode::OK, plan_body(json!(0)))).await;
    let outcome = sync(&runtime, &base_url).await;
    assert_eq!(outcome, QuotaSync::NoQuotaKnown);
    assert_eq!(stored_limit(&runtime).await, None);

    // (c) Un número imposible es un dato corrupto, no una instrucción.
    let runtime = hub(true).await;
    let (base_url, _seen) = cloud(|_| (StatusCode::OK, plan_body(json!(-1)))).await;
    assert_eq!(sync(&runtime, &base_url).await, QuotaSync::NoQuotaKnown);
    assert_eq!(stored_limit(&runtime).await, None);
}

/// ⓹ Un valor previo NO se degrada porque el Cloud deje de contestar: el número que ya medía sigue
/// midiendo. Volver a `0` por un 500 o por un timeout abriría el canal de par en par — y un fallo
/// de red no es un plan.
#[tokio::test]
async fn un_cloud_que_no_contesta_no_borra_la_cuota_que_ya_media() {
    let runtime = hub(true).await;
    let (base_url, _seen) = cloud(|n| {
        if n == 1 {
            (StatusCode::OK, plan_body(json!(30)))
        } else {
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                json!({ "detail": "boom" }),
            )
        }
    })
    .await;
    sync(&runtime, &base_url).await;
    assert_eq!(stored_limit(&runtime).await, Some(30));

    let outcome = sync(&runtime, &base_url).await;

    assert!(
        matches!(outcome, QuotaSync::CloudUnreachable(_)),
        "un 500 se cuenta como «no pude preguntar», no como «no hay tope»: {outcome:?}"
    );
    assert_eq!(
        stored_limit(&runtime).await,
        Some(30),
        "el valor previo sigue midiendo"
    );
}

/// ⓺ El alias de compatibilidad. Un SaaS anterior a la migración de Meta al precio por mensaje
/// entregado sólo manda `max_conversations`; el tope es el mismo número y se usa igual.
#[tokio::test]
async fn el_alias_de_compatibilidad_tambien_fija_el_tope() {
    let runtime = hub(true).await;
    let (base_url, _seen) = cloud(|_| {
        (
            StatusCode::OK,
            json!({
                "tier": { "slug": "free", "max_conversations": 50 },
                "usage": {},
                "available_tiers": [],
            }),
        )
    })
    .await;

    assert_eq!(
        sync(&runtime, &base_url).await,
        QuotaSync::Written {
            monthly_limit: 50,
            // Este cuerpo no trae `usage` (es el del SaaS anterior al alias): «no sé».
            monthly_usage: None,
        }
    );
    assert_eq!(stored_limit(&runtime).await, Some(50));
}

/// ⓻ Un hub **sin** el módulo instalado no hace nada: **ni siquiera pregunta**. Mismo gate que
/// `inbound_poll`, y aquí importa el doble — cada llamada evitada es cupo que no se le quita a la
/// flota, que comparte el cubo de tasa del SaaS (saas#1640).
#[tokio::test]
async fn un_hub_sin_el_modulo_ni_siquiera_pregunta_al_cloud() {
    let runtime = hub(false).await;
    let (base_url, seen) = cloud(|_| (StatusCode::OK, plan_body(json!(30)))).await;

    let outcome = sync(&runtime, &base_url).await;

    assert_eq!(outcome, QuotaSync::ModuleNotActive);
    assert_eq!(seen.calls(), 0, "el gate va ANTES de gastar una llamada");
}

/// ⓼ La puerta. El command es `internal: true`, así que sólo lo alcanza el runtime: por la puerta
/// pública sigue siendo `internal_command`. Sin esto, cualquiera con `manage_settings` podría
/// poner su propio medidor a cero — que es el agujero que whatsapp_inbox#38 cerró.
#[tokio::test]
async fn el_command_de_la_cuota_no_se_alcanza_por_la_puerta_publica() {
    let runtime = hub(true).await;
    let rt = runtime.read().await;
    let ctx = erplora_runtime::RequestContext::new(HUB, "u1", ["*".to_string()]);

    let denied = rt
        .execute_command(
            whatsapp_quota::QUOTA_COMMAND,
            &params([("monthly_limit", Value::from(0))]),
            &ctx,
        )
        .await;

    let err = denied.expect_err("la puerta pública no puede alcanzar un command interno");
    assert_eq!(
        erplora_runtime::error_registry::error_code_of(&err),
        "internal_command",
        "se afirma sobre el CÓDIGO, no sobre la frase"
    );
}

// ─────────────────────────────────────────────────────────────────────────────
// Un solo contador: el que lleva la plataforma (hub#1953)
//
// El cupo se vende —y Meta nos lo cobra— por los mensajes que el negocio MANDA, y ésa es la
// cuenta que ya lleva el SaaS. El medidor del módulo contaba los que la clienta ESCRIBE, así que
// bajo un mismo «30 al mes» había dos números que no se parecen y el dueño no podía saber cuál le
// iba a cortar. El tick que ya se baja el tope se baja también el gasto.
// ─────────────────────────────────────────────────────────────────────────────

/// ⓽ **Lo que la issue pide.** El mismo tick que fija el tope escribe el consumo que declara la
/// plataforma, así que el medidor del módulo y la cuenta de erplora.com dicen el mismo número.
#[tokio::test]
async fn el_tick_escribe_tambien_el_consumo_que_declara_la_plataforma() {
    let runtime = hub_con(Some(fixture_con_consumo())).await;
    let (base_url, seen) = cloud(|_| (StatusCode::OK, plan_body_con_consumo(json!(30), json!(12)))).await;

    sync(&runtime, &base_url).await;

    assert_eq!(stored_limit(&runtime).await, Some(30), "el tope, como siempre");
    assert_eq!(
        stored_usage(&runtime).await,
        Some(12),
        "el gasto del mes sale de la plataforma, que es quien le paga a Meta"
    );
    assert_eq!(seen.calls(), 1, "el consumo viaja en el cuerpo que ya se pedía: ni una llamada más");
}

/// ⓾ 🔴 **La regresión que hay que impedir.** El módulo publicado HOY declara su `_quota.set` con
/// `additionalProperties: false` y sin `monthly_usage`; las versiones de módulo no se mueven con
/// las del hub (ADR-0286 §3: un módulo viejo sigue instalando en un hub nuevo). Un tick que
/// mandase el campo a ciegas se llevaría un `invalid_payload` y dejaría de escribir **también el
/// tope** — y en este medidor un tope que no llega es un canal facturando por mensaje sin límite.
#[tokio::test]
async fn contra_el_modulo_publicado_hoy_el_tope_sigue_llegando() {
    let runtime = hub_con(Some(fixture())).await;
    let (base_url, _seen) = cloud(|_| (StatusCode::OK, plan_body_con_consumo(json!(30), json!(12)))).await;

    let outcome = sync(&runtime, &base_url).await;

    assert_eq!(
        stored_limit(&runtime).await,
        Some(30),
        "el tope no puede perderse por un campo que este módulo todavía no declara"
    );
    assert!(
        !matches!(outcome, QuotaSync::Failed(_)),
        "un módulo anterior a whatsapp_inbox#155 no es un fallo, es la flota: {outcome:?}"
    );
}

/// ⑪ **«No sé» no es «cero gastado».** Un cuerpo sin consumo utilizable no puede poner el medidor
/// a cero: eso le regalaría al hub el mes entero. El tope sí se escribe —es otro número y se sabe.
#[tokio::test]
async fn un_consumo_ausente_o_imposible_no_se_escribe_como_cero() {
    // (a) Primero un tick bueno deja 12 gastados.
    let runtime = hub_con(Some(fixture_con_consumo())).await;
    let (base_url, _seen) = cloud(|n| {
        let usage = match n {
            1 => json!(12),
            2 => Value::Null, // la clave no viene
            _ => json!(-3),   // un número imposible
        };
        (StatusCode::OK, plan_body_con_consumo(json!(30), usage))
    })
    .await;
    sync(&runtime, &base_url).await;
    assert_eq!(stored_usage(&runtime).await, Some(12));

    // (b) El consumo desaparece del cuerpo: lo que ya medía sigue midiendo.
    let sin_consumo = sync(&runtime, &base_url).await;
    assert_eq!(
        sin_consumo,
        QuotaSync::Written {
            monthly_limit: 30,
            monthly_usage: None,
        },
        "el tope sí se sabe: el tick escribe, y sólo se calla sobre el gasto"
    );
    assert_eq!(
        stored_usage(&runtime).await,
        Some(12),
        "una ausencia no puede devolverle el mes entero al hub"
    );
    assert_eq!(stored_limit(&runtime).await, Some(30), "el tope sí se sabe y sí se escribe");

    // (c) Un negativo es un dato corrupto, no una instrucción.
    //
    // 🔴 Se afirma sobre el RESULTADO del tick, no sólo sobre lo guardado, y por una razón que
    // costó medir: el `minimum: 0` del módulo también rechaza el negativo, pero lo hace tumbando
    // el command ENTERO (`invalid_payload`), así que el tope tampoco se escribiría. Mirando sólo
    // la columna, el test pasaba por casualidad —el valor ya estaba puesto del tick anterior— y
    // dejaba vivo un mutante que borra el filtro de aquí.
    let negativo = sync(&runtime, &base_url).await;
    assert_eq!(
        negativo,
        QuotaSync::Written {
            monthly_limit: 30,
            monthly_usage: None,
        },
        "el dato corrupto se descarta AQUÍ; si llega al módulo se lleva el tope por delante"
    );
    assert_eq!(stored_usage(&runtime).await, Some(12));
}

/// ⑫ **Un cero de la plataforma SÍ es un número.** Es la diferencia con el tope, donde `0`
/// significa «sin límite»: aquí significa «este mes no has gastado nada», y es lo que ve el dueño
/// el día 1. Confundirlo con «no sé» dejaría el medidor con el gasto del mes pasado.
#[tokio::test]
async fn un_consumo_de_cero_es_un_dato_y_se_escribe() {
    let runtime = hub_con(Some(fixture_con_consumo())).await;
    let (base_url, _seen) = cloud(|n| {
        let usage = if n == 1 { json!(29) } else { json!(0) };
        (StatusCode::OK, plan_body_con_consumo(json!(30), usage))
    })
    .await;
    sync(&runtime, &base_url).await;
    assert_eq!(stored_usage(&runtime).await, Some(29), "el mes que acaba");

    sync(&runtime, &base_url).await;

    assert_eq!(
        stored_usage(&runtime).await,
        Some(0),
        "el mes nuevo empieza a cero, y ese cero lo dice la plataforma"
    );
}
