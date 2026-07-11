//! Revalidación híbrida del entitlement de módulos de pago (UX + defensa en profundidad).
//!
//! El enforcement REAL es server-side: el proxy del SaaS corta las llamadas de pago al
//! instante. Este módulo añade la capa local del hub, deliberadamente **laxa**:
//!
//!  1. Un job periódico (default 24h, env `HUB_ENTITLEMENT_REVALIDATE_SECS`) refresca el
//!     entitlement **firmado RS256** del Cloud con la credencial de máquina del hub
//!     (`X-Hub-Token`) y actualiza este estado compartido.
//!  2. Un módulo queda **bloqueado** si:
//!     - el ÚLTIMO refresh EXITOSO no lo incluye en `claims.modules` (verdad del servidor:
//!       revocado/no comprado → inmediato), O
//!     - acumulamos [`MAX_CONSECUTIVE_FAILURES`] fallos seguidos de refresh **Y** ya pasó la
//!       ventana de gracia (`grace_until`) del último token válido — la misma semántica de
//!       gracia que el gate de arranque de la app Tauri (`verify_entitlement`).
//!  3. Sin ningún refresh exitoso previo (dev/local sin enrolar, hub recién arrancado) NUNCA
//!     se bloquea (fail-open): la autoridad es el SaaS, no este gate.
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
        // Verdad del servidor: el último refresh OK no lo incluye → bloqueado inmediato.
        if !claims.allows(module_id) {
            return true;
        }
        // Entitled según el último token válido: solo se bloquea si llevamos demasiados fallos
        // seguidos Y además venció su ventana de gracia (misma semántica que el gate Tauri).
        self.consecutive_failures >= MAX_CONSECUTIVE_FAILURES && now > claims.grace_until
    }

    /// `grace_until` del último token válido (para la UI: «funcionará hasta {fecha}»).
    pub fn grace_until(&self) -> Option<i64> {
        self.last_claims.as_ref().map(|c| c.grace_until)
    }

    /// Filtra de `installed` los módulos bloqueados a fecha `now` (para el proxy de entitlement).
    pub fn blocked_modules(&self, installed: &[String], now: i64) -> Vec<String> {
        installed.iter().filter(|id| self.is_blocked(id, now)).cloned().collect()
    }

    /// Bloque JSON **aditivo** `revalidation` que el proxy `/api/entitlement` añade a la
    /// respuesta del Cloud (no rompe el contrato actual; la UI lo consume si está).
    pub fn revalidation_json(&self, installed: &[String], now: i64) -> Value {
        serde_json::json!({
            "blocked_modules": self.blocked_modules(installed, now),
            "grace_until": self.grace_until(),
            "last_check": self.last_check_at,
            "last_refresh_ok_at": self.last_refresh_ok_at,
            "consecutive_failures": self.consecutive_failures,
        })
    }
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
            deployment_mode: "cloud".into(),
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
        }
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
        assert_eq!(st.blocked_modules(&installed, 2_000), vec!["pos".to_string()]);
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
    fn revalidation_json_sin_estado_es_nulo_y_vacio() {
        // Estado inicial (fail-open): sin bloqueos y campos a null — la UI no pinta aviso.
        let st = RevalidationState::default();
        let v = st.revalidation_json(&["pos".to_string()], 1_000);
        assert_eq!(v["blocked_modules"], serde_json::json!([]));
        assert_eq!(v["grace_until"], Value::Null);
        assert_eq!(v["last_check"], Value::Null);
    }
}
