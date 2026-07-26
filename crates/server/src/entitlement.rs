//! Revalidación híbrida del entitlement de módulos de pago (UX + defensa en profundidad).
//!
//! El enforcement REAL es server-side: el proxy del SaaS corta las llamadas de pago al
//! instante. Este módulo añade la capa local del hub, deliberadamente **laxa**:
//!
//!  1. Un job periódico (default 24h, env `HUB_ENTITLEMENT_REVALIDATE_SECS`) refresca el
//!     entitlement **firmado RS256** del Cloud con la credencial de máquina del hub
//!     (`X-Hub-Token`) y actualiza este estado compartido.
//!  2. Un módulo queda **bloqueado** si:
//!     - (a) el ÚLTIMO refresh EXITOSO no lo incluye en `claims.modules` (verdad del servidor:
//!       revocado/no comprado → inmediato, sea cual sea su tier), O
//!     - (b) es **DE PAGO** (`tier` fuera de los gratuitos `free`/`basic`/`essential`, ADR-0006)
//!       y acumulamos [`MAX_CONSECUTIVE_FAILURES`] fallos seguidos de refresh **Y** ya pasó la
//!       ventana de gracia del último token válido: la de pago (`paid_grace_until`, claim
//!       ADITIVO del SaaS de 5 días, 2026-07-12) si el token la trae, o si no la global
//!       (`grace_until`, 7 días, la del gate de la app) como hasta ahora.
//!  3. Sin ningún refresh exitoso previo (dev/local sin enrolar, hub recién arrancado) NUNCA
//!     se bloquea (fail-open): la autoridad es el SaaS, no este gate.
//!
//! Decisión del fundador: «si el módulo es de pago deja de funcionar» — y SOLO el de pago. Los
//! módulos gratuitos son locales por diseño (offline-first, ADR-0040: sin sync) y siguen
//! funcionando SIEMPRE, incluso con el hub incomunicado más allá de la gracia; el de pago en
//! cambio depende del entitlement que emite el SaaS. Un tier desconocido se trata como de pago
//! (fail-closed solo en la rama (b), ver [`is_paid_tier`]).
//!
//! El gate solo corta `execute_query`/`execute_command` con el error estable
//! `module_entitlement_blocked` (ver `entitlement_blocked_response` en `lib.rs`); **NUNCA**
//! desinstala módulos ni toca datos. El estado se expone de forma aditiva en el proxy
//! `GET /api/entitlement` (bloque `revalidation`) para que la UI pueda pintar
//! «funcionará hasta {fecha}».

use std::sync::{Arc, RwLock};

use cloud_client::EntitlementClaims;
use serde_json::Value;

/// Intervalo por defecto del job de revalidación: 24h (override: `HUB_ENTITLEMENT_REVALIDATE_SECS`).
pub const DEFAULT_REVALIDATE_SECS: u64 = 86_400;

/// Nº de fallos CONSECUTIVOS de refresh a partir del cual (junto con la gracia vencida) se
/// bloquean los módulos del último token válido.
pub const MAX_CONSECUTIVE_FAILURES: u32 = 3;

/// Estado de la revalidación periódica. Vive en [`crate::AppState`] tras un `RwLock` (mismo
/// patrón que `MachineToken`): lo escribe el job de background y lo leen los handlers
/// `query`/`command` (gate) y el proxy `/api/entitlement` (UI).
#[derive(Debug, Default)]
pub struct RevalidationState {
    /// Claims del último token **verificado** (firma RS256 OK) traído con éxito del Cloud.
    /// `None` = nunca hubo refresh exitoso → fail-open (no se bloquea nada).
    pub last_claims: Option<EntitlementClaims>,
    /// Unix-ts del último refresh EXITOSO.
    pub last_refresh_ok_at: Option<i64>,
    /// Unix-ts del último INTENTO de refresh (éxito o fallo) — `last_check` para la UI.
    pub last_check_at: Option<i64>,
    /// Fallos consecutivos de refresh; se resetea a 0 en cada éxito.
    pub consecutive_failures: u32,
}

/// Celda compartida del estado (job de background ↔ handlers), como `MachineToken`.
pub type SharedRevalidation = Arc<RwLock<RevalidationState>>;

/// Crea la celda compartida vacía (estado inicial fail-open).
pub fn new_shared() -> SharedRevalidation {
    Arc::new(RwLock::new(RevalidationState::default()))
}

/// ¿Es `tier` un módulo DE PAGO? Los tiers gratuitos (ADR-0006: `basic` + `essential`; `free`
/// por robustez) quedan EXENTOS de la rama (b) del bloqueo: los módulos free son locales por
/// diseño (offline-first, ADR-0040) y deben seguir funcionando aunque el hub quede incomunicado.
/// Un tier ausente/desconocido se trata como de pago — fail-closed SOLO en la rama (b), que ya
/// exige `MAX_CONSECUTIVE_FAILURES` fallos consecutivos Y la gracia vencida.
fn is_paid_tier(tier: &str) -> bool {
    !matches!(
        tier.trim().to_ascii_lowercase().as_str(),
        "free" | "basic" | "essential"
    )
}

impl RevalidationState {
    /// Registra un refresh EXITOSO: guarda las claims verificadas y resetea el contador.
    pub fn apply_success(&mut self, claims: EntitlementClaims, now: i64) {
        self.last_claims = Some(claims);
        self.last_refresh_ok_at = Some(now);
        self.last_check_at = Some(now);
        self.consecutive_failures = 0;
    }

    /// Registra un refresh FALLIDO (red/HTTP/firma): incrementa el contador de fallos.
    pub fn apply_failure(&mut self, now: i64) {
        self.last_check_at = Some(now);
        self.consecutive_failures = self.consecutive_failures.saturating_add(1);
    }

    /// Regla de bloqueo por módulo (ver doc del módulo). `now` lo pasa el llamador para
    /// mantener la función pura y testeable sin reloj real (como `verify_entitlement`).
    pub fn is_blocked(&self, module_id: &str, now: i64) -> bool {
        // Sin refresh exitoso previo no hay verdad conocida → fail-open (la autoridad es el SaaS).
        let Some(claims) = &self.last_claims else {
            return false;
        };
        // (a) Verdad del servidor: el último refresh OK no lo incluye (revocado/no comprado)
        // → bloqueado inmediato, sea cual sea su tier (que ni siquiera conocemos).
        let Some(entry) = claims.modules.iter().find(|m| m.module_id == module_id) else {
            return true;
        };
        // (b) Entitled según el último token válido: solo un módulo DE PAGO se bloquea, y solo
        // si llevamos demasiados fallos seguidos Y además venció su ventana de gracia — la DE
        // PAGO (`paid_grace_until`, claim aditivo) si el token la trae; si no, la global
        // (`grace_until`). Los tiers gratuitos siguen funcionando SIEMPRE (offline-first).
        is_paid_tier(&entry.tier)
            && self.consecutive_failures >= MAX_CONSECUTIVE_FAILURES
            && now > claims.paid_grace_until.unwrap_or(claims.grace_until)
    }

    /// `grace_until` del último token válido (para la UI: «funcionará hasta {fecha}»).
    pub fn grace_until(&self) -> Option<i64> {
        self.last_claims.as_ref().map(|c| c.grace_until)
    }

    /// Nº máximo de **dispositivos activos** del plan según el último token válido (ADR-0154).
    /// `0` = ilimitado, y también el default fail-open cuando aún no hubo refresh exitoso (la
    /// autoridad del límite es el SaaS; sin claim conocido, el hub no aplica takeover local).
    /// Lo lee `mint_session` para desalojar sesiones de otros dispositivos al abrir una nueva.
    pub fn max_devices(&self) -> u32 {
        self.last_claims.as_ref().map(|c| c.max_devices).unwrap_or(0)
    }

    /// `paid_grace_until` del último token válido: gracia ESPECÍFICA de los módulos de pago
    /// (claim aditivo del SaaS). `None` = el token no la trae → aplica `grace_until`.
    pub fn paid_grace_until(&self) -> Option<i64> {
        self.last_claims.as_ref().and_then(|c| c.paid_grace_until)
    }

    /// Filtra de `installed` los módulos bloqueados a fecha `now` (para el proxy de entitlement).
    pub fn blocked_modules(&self, installed: &[String], now: i64) -> Vec<String> {
        installed
            .iter()
            .filter(|id| self.is_blocked(id, now))
            .cloned()
            .collect()
    }

    /// Bloque JSON **aditivo** `revalidation` que el proxy `/api/entitlement` añade a la
    /// respuesta del Cloud (no rompe el contrato actual; la UI lo consume si está).
    pub fn revalidation_json(&self, installed: &[String], now: i64) -> Value {
        serde_json::json!({
            "blocked_modules": self.blocked_modules(installed, now),
            "grace_until": self.grace_until(),
            "paid_grace_until": self.paid_grace_until(),
            "last_check": self.last_check_at,
            "last_refresh_ok_at": self.last_refresh_ok_at,
            "consecutive_failures": self.consecutive_failures,
        })
    }
}

/// Registra en la celda compartida el resultado de UN tick del job de revalidación.
/// Separado del fetch de red para poder testearlo con estado/clock inyectados.
pub fn record_outcome(
    cell: &SharedRevalidation,
    outcome: Result<EntitlementClaims, String>,
    now: i64,
) {
    // Si el lock está envenenado (panic de otro hilo) se degrada a no-op: este estado es
    // UX/defensa en profundidad, nunca debe tumbar el server.
    let Ok(mut guard) = cell.write() else { return };
    match outcome {
        Ok(claims) => guard.apply_success(claims, now),
        Err(e) => {
            tracing::warn!(error = %e, fallos = guard.consecutive_failures + 1, "revalidación de entitlement fallida");
            guard.apply_failure(now);
        }
    }
}

/// Intervalo del job en segundos: el valor del env `HUB_ENTITLEMENT_REVALIDATE_SECS` si es un
/// entero > 0; si no (ausente, vacío, no numérico o 0), el default de 24h.
pub fn interval_secs(env_value: Option<&str>) -> u64 {
    env_value
        .and_then(|v| v.trim().parse::<u64>().ok())
        .filter(|v| *v > 0)
        .unwrap_or(DEFAULT_REVALIDATE_SECS)
}

/// Baja del Cloud la clave pública + el entitlement firmado (credencial de máquina) y verifica
/// la firma RS256 y la gracia — la MISMA ruta de verificación que el gate de arranque Tauri
/// (`verify_entitlement`). Glue de red del tick: el manejo de resultado (estado/contador) vive
/// en [`record_outcome`], que es lo testeable sin red.
pub async fn fetch_verified_claims(
    http: &reqwest::Client,
    cloud_base_url: &str,
    auth: &cloud_client::Auth,
    now: i64,
) -> Result<EntitlementClaims, String> {
    let cloud = cloud_client::CloudClient::new(cloud_base_url);

    // 1) Clave pública RSA (endpoint público, sin auth).
    #[derive(serde::Deserialize)]
    struct Pk {
        public_key: String,
    }
    let pk_body = exec_get(http, cloud.public_key()).await?;
    let pk: Pk = serde_json::from_str(&pk_body).map_err(|e| format!("public-key: {e}"))?;

    // 2) Entitlement firmado del hub (X-Hub-Token + X-Hub-Id).
    let ent_body = exec_get(http, cloud.entitlement(auth)).await?;
    let ent = cloud_client::EntitlementResponse::parse(&ent_body)
        .map_err(|e| format!("entitlement: {e}"))?;

    // 3) Verificación offline-style: firma RS256 + ventana de gracia.
    cloud_client::verify_entitlement(&ent.token, &pk.public_key, now).map_err(|e| e.to_string())
}

/// Ejecuta un GET de una `PreparedRequest` del `CloudClient` y devuelve el body si es 2xx.
async fn exec_get(
    http: &reqwest::Client,
    req: cloud_client::PreparedRequest,
) -> Result<String, String> {
    let mut r = http.get(&req.url);
    for (k, v) in req.headers {
        r = r.header(k, v);
    }
    let resp = r.send().await.map_err(|e| e.to_string())?;
    let status = resp.status();
    if !status.is_success() {
        return Err(format!("{}: status {status}", req.url));
    }
    resp.text().await.map_err(|e| e.to_string())
}

/// Unix-ts actual (segundos). `0` si el reloj está antes de EPOCH (imposible en la práctica).
pub fn now_unix() -> i64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs() as i64)
        .unwrap_or(0)
}

#[cfg(test)]
mod tests {
    use super::*;
    use cloud_client::EntitledModule;

    /// Claims de prueba: construidas a mano (los campos son `pub`), sin firmar — la regla de
    /// bloqueo opera sobre claims YA verificadas (la firma la cubre `verify_entitlement`).
    fn claims(modules: &[&str], grace_until: i64) -> EntitlementClaims {
        EntitlementClaims {
            hub_id: "h1".into(),
            modules: modules
                .iter()
                .map(|id| EntitledModule {
                    module_id: (*id).to_string(),
                    tier: "premium".into(),
                    version: "1.0.0".into(),
                })
                .collect(),
            iat: 1_000,
            exp: 2_000,
            grace_until,
            paid_grace_until: None,
            plan: None,
            max_devices: 0,
        }
    }

    /// Como [`claims`] pero con `tier` explícito por módulo (regla (b): solo los DE PAGO).
    fn claims_tiered(modules: &[(&str, &str)], grace_until: i64) -> EntitlementClaims {
        EntitlementClaims {
            hub_id: "h1".into(),
            modules: modules
                .iter()
                .map(|(id, tier)| EntitledModule {
                    module_id: (*id).to_string(),
                    tier: (*tier).to_string(),
                    version: "1.0.0".into(),
                })
                .collect(),
            iat: 1_000,
            exp: 2_000,
            grace_until,
            paid_grace_until: None,
            plan: None,
            max_devices: 0,
        }
    }

    #[test]
    fn tras_fallos_y_gracia_vencida_los_tiers_free_no_se_bloquean() {
        // Decisión del fundador: solo el módulo DE PAGO deja de funcionar. Los free son
        // locales por diseño (offline-first, ADR-0040) y siguen SIEMPRE, incluso con el
        // hub incomunicado más allá de la gracia.
        let mut st = RevalidationState::default();
        st.apply_success(
            claims_tiered(
                &[
                    ("pos", "premium"),
                    ("caja", "basic"),
                    ("agenda", "essential"),
                    ("notas", "free"),
                ],
                5_000,
            ),
            1_500,
        );
        for i in 0..3 {
            st.apply_failure(6_000 + i);
        }
        assert!(st.is_blocked("pos", 9_000)); // de pago → bloquea (fallos>=3 AND gracia vencida)
        assert!(!st.is_blocked("caja", 9_000)); // basic → gratis (ADR-0006), nunca por la rama (b)
        assert!(!st.is_blocked("agenda", 9_000)); // essential → gratis
        assert!(!st.is_blocked("notas", 9_000)); // free → gratis
    }

    #[test]
    fn tier_desconocido_o_vacio_cuenta_como_de_pago_en_la_rama_b() {
        // Fail-closed SOLO en la rama (b) (que ya exige 3 fallos + gracia vencida): un tier
        // que no sabemos que sea gratuito se trata como premium.
        let mut st = RevalidationState::default();
        st.apply_success(claims_tiered(&[("x", "pro"), ("y", "")], 5_000), 1_500);
        for i in 0..3 {
            st.apply_failure(6_000 + i);
        }
        assert!(st.is_blocked("x", 9_000)); // tier desconocido → como de pago
        assert!(st.is_blocked("y", 9_000)); // tier vacío → como de pago
    }

    #[test]
    fn fuera_de_claims_bloquea_inmediato_sea_cual_sea_el_tier() {
        // La regla (a) NO cambia: fuera del último refresh OK = verdad del servidor
        // (revocado/no comprado) → bloqueo inmediato; el tier ni se conoce.
        let mut st = RevalidationState::default();
        st.apply_success(claims_tiered(&[("caja", "basic")], 50_000), 1_500);
        assert!(st.is_blocked("pos", 1_600)); // sin fallos y con gracia vigente: da igual
        assert!(!st.is_blocked("caja", 1_600));
    }

    #[test]
    fn blocked_modules_tras_gracia_solo_contiene_de_pago_o_revocados() {
        // El bloque `revalidation` del proxy hereda la regla: tras fallos+gracia solo
        // aparecen los de pago (rama b) y los fuera de claims (rama a); los free nunca.
        let mut st = RevalidationState::default();
        st.apply_success(
            claims_tiered(&[("pos", "premium"), ("caja", "basic")], 5_000),
            1_500,
        );
        for i in 0..3 {
            st.apply_failure(6_000 + i);
        }
        let installed = vec![
            "pos".to_string(),
            "caja".to_string(),
            "revocado".to_string(),
        ];
        assert_eq!(
            st.blocked_modules(&installed, 9_000),
            vec!["pos".to_string(), "revocado".to_string()]
        );
    }

    #[test]
    fn sin_refresh_exitoso_nunca_bloquea() {
        // Fail-open: dev/local sin enrolar o hub recién arrancado — la autoridad es el SaaS.
        let st = RevalidationState::default();
        assert!(!st.is_blocked("pos", 999_999));
        assert_eq!(st.grace_until(), None);
    }

    #[test]
    fn modulo_fuera_del_ultimo_refresh_exitoso_bloquea_inmediato() {
        // Verdad del servidor: el último refresh OK no incluye `pos` → bloqueado YA (sin
        // esperar fallos ni gracia). `inventory` sí está → pasa.
        let mut st = RevalidationState::default();
        st.apply_success(claims(&["inventory"], 9_000), 1_500);
        assert!(st.is_blocked("pos", 1_600));
        assert!(!st.is_blocked("inventory", 1_600));
    }

    #[test]
    fn dos_fallos_con_gracia_vencida_no_bloquea() {
        // Regla = fallos >= 3 AND now > grace: con solo 2 fallos NO bloquea aunque la gracia
        // haya vencido (el token sigue siendo la última verdad conocida).
        let mut st = RevalidationState::default();
        st.apply_success(claims(&["pos"], 5_000), 1_500);
        st.apply_failure(6_000);
        st.apply_failure(7_000);
        assert!(!st.is_blocked("pos", 8_000)); // now > grace_until (5_000), pero fallos < 3
    }

    #[test]
    fn cinco_fallos_con_gracia_vigente_no_bloquea() {
        // Muchos fallos pero la gracia del último token válido sigue vigente → no bloquea.
        let mut st = RevalidationState::default();
        st.apply_success(claims(&["pos"], 50_000), 1_500);
        for i in 0..5 {
            st.apply_failure(2_000 + i);
        }
        assert!(!st.is_blocked("pos", 10_000)); // fallos >= 3, pero now < grace_until (50_000)
    }

    #[test]
    fn tres_fallos_y_gracia_vencida_bloquea() {
        let mut st = RevalidationState::default();
        st.apply_success(claims(&["pos"], 5_000), 1_500);
        st.apply_failure(6_000);
        st.apply_failure(7_000);
        st.apply_failure(8_000);
        assert!(st.is_blocked("pos", 9_000)); // fallos == 3 AND now > grace_until
    }

    #[test]
    fn paid_grace_until_menor_bloquea_al_de_pago_aunque_grace_until_siga_vigente() {
        // Claim ADITIVO del SaaS (2026-07-12): gracia de pago de 5 días, SEPARADA de la global
        // de 7 (`grace_until`, gate de la app). Con paid_grace_until (5_000) < grace_until
        // (50_000), el módulo DE PAGO se bloquea en cuanto fallos >= 3 AND now > paid_grace_until,
        // aunque la gracia global siga vigente. Los tiers gratuitos siguen exentos de la rama (b).
        let mut st = RevalidationState::default();
        let mut c = claims_tiered(
            &[
                ("pos", "premium"),
                ("caja", "basic"),
                ("agenda", "essential"),
                ("notas", "free"),
            ],
            50_000,
        );
        c.paid_grace_until = Some(5_000);
        st.apply_success(c, 1_500);
        for i in 0..3 {
            st.apply_failure(6_000 + i);
        }
        assert!(st.is_blocked("pos", 9_000)); // de pago: now > paid_grace (5_000), now < grace (50_000)
        assert!(!st.is_blocked("pos", 4_000)); // antes de la gracia de pago aún no bloquea
        assert!(!st.is_blocked("caja", 9_000)); // basic → gratis, nunca por la rama (b)
        assert!(!st.is_blocked("agenda", 9_000)); // essential → gratis
        assert!(!st.is_blocked("notas", 9_000)); // free → gratis
    }

    #[test]
    fn sin_paid_grace_until_el_de_pago_cae_a_grace_until_como_hoy() {
        // Retrocompat: tokens antiguos sin el claim (paid_grace_until = None, ver helpers) →
        // la rama (b) usa `grace_until` exactamente igual que antes.
        let mut st = RevalidationState::default();
        st.apply_success(claims(&["pos"], 5_000), 1_500);
        for i in 0..3 {
            st.apply_failure(6_000 + i);
        }
        assert!(st.is_blocked("pos", 9_000)); // fallos >= 3 AND now > grace_until
        assert!(!st.is_blocked("pos", 4_000)); // con la gracia global vigente no bloquea
    }

    #[test]
    fn revalidation_json_expone_paid_grace_until_ademas_de_grace_until() {
        // El bloque aditivo del proxy expone AMBAS gracias: la UI pinta «funcionará hasta
        // {fecha}» con la de pago si viene, sin perder la global existente.
        let mut st = RevalidationState::default();
        let mut c = claims(&["inventory"], 9_000);
        c.paid_grace_until = Some(4_000);
        st.apply_success(c, 1_500);
        let v = st.revalidation_json(&["inventory".to_string()], 2_500);
        assert_eq!(v["grace_until"], serde_json::json!(9_000)); // el existente no se sustituye
        assert_eq!(v["paid_grace_until"], serde_json::json!(4_000));
        assert_eq!(st.paid_grace_until(), Some(4_000));

        // Sin el claim (tokens antiguos) el campo va a null y el helper a None.
        let mut st2 = RevalidationState::default();
        st2.apply_success(claims(&["inventory"], 9_000), 1_500);
        let v2 = st2.revalidation_json(&["inventory".to_string()], 2_500);
        assert_eq!(v2["paid_grace_until"], Value::Null);
        assert_eq!(st2.paid_grace_until(), None);
    }

    #[test]
    fn exito_resetea_contador_y_desbloquea() {
        let mut st = RevalidationState::default();
        st.apply_success(claims(&["pos"], 5_000), 1_500);
        for i in 0..3 {
            st.apply_failure(6_000 + i);
        }
        assert!(st.is_blocked("pos", 9_000));

        // Un refresh exitoso posterior resetea el contador y renueva la gracia.
        st.apply_success(claims(&["pos"], 99_000), 9_500);
        assert_eq!(st.consecutive_failures, 0);
        assert_eq!(st.last_refresh_ok_at, Some(9_500));
        assert_eq!(st.grace_until(), Some(99_000));
        assert!(!st.is_blocked("pos", 10_000));
    }

    #[test]
    fn apply_failure_actualiza_last_check() {
        let mut st = RevalidationState::default();
        st.apply_failure(4_000);
        assert_eq!(st.last_check_at, Some(4_000));
        assert_eq!(st.consecutive_failures, 1);
        assert_eq!(st.last_refresh_ok_at, None); // un fallo no toca el último OK
    }

    #[test]
    fn blocked_modules_filtra_instalados() {
        let mut st = RevalidationState::default();
        st.apply_success(claims(&["inventory"], 9_000), 1_500);
        let installed = vec!["inventory".to_string(), "pos".to_string()];
        assert_eq!(
            st.blocked_modules(&installed, 2_000),
            vec!["pos".to_string()]
        );
    }

    #[test]
    fn revalidation_json_expone_estado_para_la_ui() {
        // El bloque aditivo del proxy: blocked_modules + grace_until + last_check (+ extras).
        let mut st = RevalidationState::default();
        st.apply_success(claims(&["inventory"], 9_000), 1_500);
        st.apply_failure(2_000);
        let installed = vec!["inventory".to_string(), "pos".to_string()];
        let v = st.revalidation_json(&installed, 2_500);
        assert_eq!(v["blocked_modules"], serde_json::json!(["pos"]));
        assert_eq!(v["grace_until"], serde_json::json!(9_000));
        assert_eq!(v["last_check"], serde_json::json!(2_000));
        assert_eq!(v["last_refresh_ok_at"], serde_json::json!(1_500));
        assert_eq!(v["consecutive_failures"], serde_json::json!(1));
    }

    #[test]
    fn record_outcome_aplica_exito_y_fallo_sobre_la_celda() {
        // El tick del job separa red (fetch) de estado: aquí se testea el estado inyectado.
        let cell = new_shared();
        record_outcome(&cell, Ok(claims(&["pos"], 9_000)), 1_000);
        {
            let g = cell.read().unwrap();
            assert_eq!(g.consecutive_failures, 0);
            assert_eq!(g.last_refresh_ok_at, Some(1_000));
        }
        record_outcome(&cell, Err("red caída".into()), 2_000);
        let g = cell.read().unwrap();
        assert_eq!(g.consecutive_failures, 1);
        assert_eq!(g.last_check_at, Some(2_000));
        assert!(g.last_claims.is_some()); // el fallo NO borra la última verdad conocida
    }

    #[test]
    fn max_devices_viene_del_ultimo_token_o_cero_sin_estado() {
        // ADR-0154: el límite de dispositivos lo aporta el claim `max_devices` del último token
        // válido. Sin refresh exitoso previo → 0 (ilimitado, fail-open: sin takeover local, la
        // autoridad es el SaaS).
        let st = RevalidationState::default();
        assert_eq!(st.max_devices(), 0);

        let mut st2 = RevalidationState::default();
        let mut c = claims(&["pos"], 9_000);
        c.max_devices = 1;
        st2.apply_success(c, 1_500);
        assert_eq!(st2.max_devices(), 1);
    }

    #[test]
    fn intervalo_del_job_default_y_override() {
        assert_eq!(interval_secs(None), DEFAULT_REVALIDATE_SECS);
        assert_eq!(interval_secs(Some("3600")), 3_600);
        assert_eq!(interval_secs(Some("no-numero")), DEFAULT_REVALIDATE_SECS);
        assert_eq!(interval_secs(Some("0")), DEFAULT_REVALIDATE_SECS);
        assert_eq!(interval_secs(Some("")), DEFAULT_REVALIDATE_SECS);
    }

    #[test]
    fn revalidation_json_sin_estado_es_nulo_y_vacio() {
        // Estado inicial (fail-open): sin bloqueos y campos a null — la UI no pinta aviso.
        let st = RevalidationState::default();
        let v = st.revalidation_json(&["pos".to_string()], 1_000);
        assert_eq!(v["blocked_modules"], serde_json::json!([]));
        assert_eq!(v["grace_until"], Value::Null);
        assert_eq!(v["last_check"], Value::Null);
    }
}
