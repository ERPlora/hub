//! Señal de **actividad de usuario** del hub → Cloud (ciclo de vida de hubs free, ADR-0175).
//!
//! El Cloud apaga un hub free en el que **nadie entra** durante 60 días, lo marca inactivo a los 90
//! y lo borra a los 120 (`free_hub_lifecycle_task`). Quién ha entrado solo lo sabe el hub.
//!
//! **Por qué no basta el heartbeat que ya existe** (`daily_usage`, hub#199): ese mide *liveness y
//! negocio* — el contenedor está vivo, y hoy se han hecho N ventas. Un hub encendido late para
//! siempre, lo use alguien o no, así que con esa señal ningún hub vencería jamás; y con `created_at`
//! (lo que hacía el Cloud antes de ADR-0175) vencen todos por igual. Ninguna de las dos dice «nadie
//! entra aquí». Esta sí: `last_user_activity_at` viaja **solo si alguien ha entrado**, dentro del
//! mismo heartbeat — sin abrir otro camino de red ni otro job.
//!
//! **Coste**: cero I/O por petición. Cada request con credencial válida hace un `fetch_max` sobre un
//! `AtomicI64` ([`ActivityState::touch`]) desde un middleware único del router.

use std::sync::atomic::{AtomicI64, Ordering};

/// Marca de actividad de usuario compartida por el server (vive en el `AppState`).
///
/// Ambos instantes son epoch en segundos; `0` = "nunca".
#[derive(Debug, Default)]
pub struct ActivityState {
    last_activity: AtomicI64,
    last_reported: AtomicI64,
}

impl ActivityState {
    pub fn new() -> Self {
        Self::default()
    }

    /// Registra actividad de usuario en el instante `now`. Monótona: una petición que llega
    /// desordenada (o un reloj que retrocede) nunca hace retroceder la marca.
    pub fn touch(&self, now: i64) {
        self.last_activity.fetch_max(now, Ordering::Relaxed);
    }

    /// Último instante con actividad conocida (`None` si nadie ha entrado desde el arranque).
    pub fn last_activity(&self) -> Option<i64> {
        match self.last_activity.load(Ordering::Relaxed) {
            0 => None,
            v => Some(v),
        }
    }

    /// Instante a reportar, o `None` si no hay nada nuevo desde el último envío.
    ///
    /// Es la decisión completa: sin actividad nueva no se manda nada, así que un hub dormido no
    /// resetea el reloj del Cloud.
    pub fn pending(&self) -> Option<i64> {
        let last = self.last_activity.load(Ordering::Relaxed);
        if last > 0 && last > self.last_reported.load(Ordering::Relaxed) {
            Some(last)
        } else {
            None
        }
    }

    /// Confirma que `ts` llegó al Cloud. Solo se llama tras un heartbeat correcto: si el envío
    /// falla, `pending` sigue devolviéndolo y el siguiente tick reintenta (perder el reporte
    /// adelantaría el apagado del hub).
    pub fn mark_reported(&self, ts: i64) {
        self.last_reported.fetch_max(ts, Ordering::Relaxed);
    }
}

/// ¿Cuenta esta petición como "alguien está usando el hub"?
///
/// Dos condiciones, ambas necesarias:
/// - **Trae credencial** (`X-Hub-Session` de un humano logueado, o una API key de una integración
///   viva). Sin credencial es un anónimo: la pantalla de login, un health-check del balanceador o
///   un bot — nada de eso debe mantener vivo un hub que nadie usa.
/// - **No fue rechazada** (401/403). Una sesión caducada o un token inválido son justo lo que se
///   ve cuando NADIE vuelve; contarlos como uso dejaría el hub encendido para siempre.
pub fn is_user_activity(has_credential: bool, status: u16) -> bool {
    has_credential && status != 401 && status != 403
}

/// Epoch en segundos → ISO-8601 UTC, el formato que parsea el Cloud (`_coerce_datetime`).
pub fn to_iso8601(ts: i64) -> String {
    chrono::DateTime::from_timestamp(ts, 0)
        .unwrap_or_else(|| chrono::DateTime::from_timestamp(0, 0).expect("epoch"))
        .to_rfc3339_opts(chrono::SecondsFormat::Secs, true)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn sin_actividad_no_hay_nada_que_reportar() {
        let st = ActivityState::new();
        assert_eq!(st.pending(), None);
        assert_eq!(st.last_activity(), None);
    }

    #[test]
    fn una_visita_queda_pendiente_hasta_confirmarse() {
        let st = ActivityState::new();
        st.touch(1_000);
        assert_eq!(st.pending(), Some(1_000));
        st.mark_reported(1_000);
        assert_eq!(st.pending(), None, "ya reportado: no se reenvía");
    }

    #[test]
    fn actividad_nueva_tras_reportar_vuelve_a_quedar_pendiente() {
        let st = ActivityState::new();
        st.touch(1_000);
        st.mark_reported(1_000);
        st.touch(2_000);
        assert_eq!(st.pending(), Some(2_000));
    }

    #[test]
    fn la_marca_no_retrocede_con_peticiones_desordenadas() {
        let st = ActivityState::new();
        st.touch(2_000);
        st.touch(1_000);
        assert_eq!(st.pending(), Some(2_000));
    }

    #[test]
    fn un_envio_fallido_se_reintenta() {
        // `mark_reported` solo se llama tras un heartbeat OK; sin él, el tick siguiente reintenta.
        let st = ActivityState::new();
        st.touch(1_000);
        assert_eq!(st.pending(), Some(1_000));
        assert_eq!(st.pending(), Some(1_000));
    }

    #[test]
    fn solo_cuenta_la_peticion_autenticada_y_aceptada() {
        assert!(is_user_activity(true, 200));
        assert!(is_user_activity(true, 404), "404 de una ruta = uso real");
        assert!(is_user_activity(true, 500), "el hub falla, pero alguien hay");
    }

    #[test]
    fn no_cuenta_el_anonimo_ni_el_rechazado() {
        assert!(!is_user_activity(false, 200), "sin credencial: login/bot/LB");
        assert!(!is_user_activity(true, 401), "sesión caducada = nadie vuelve");
        assert!(!is_user_activity(true, 403));
    }

    #[test]
    fn timestamp_en_iso8601_utc() {
        assert_eq!(to_iso8601(1_700_000_000), "2023-11-14T22:13:20Z");
    }
}
