//! Señal de **actividad de usuario** del hub → Cloud (ciclo de vida de hubs free).
//!
//! El Cloud apaga un hub free en el que **nadie entra** durante 60 días, lo marca inactivo a los
//! 90 y lo borra a los 120 (`free_hub_lifecycle_task`). Para eso necesita saber cuándo entró
//! alguien por última vez, y solo el hub lo sabe.
//!
//! **Por qué no vale el heartbeat de liveness**: un hub encendido late para siempre, lo use
//! alguien o no. Si el reloj de inactividad se llevara con el heartbeat, ningún hub vencería
//! jamás; y si se lleva con `created_at` (lo que hacía el Cloud antes de esto), vencen TODOS a
//! los 120 días de creados, se usen o no. Por eso van separadas: `last_heartbeat` = el contenedor
//! está vivo, `last_user_activity_at` = un humano ha entrado.
//!
//! **Coste**: cero I/O por petición. Cada request con sesión válida hace un `fetch_max` sobre un
//! `AtomicI64` ([`ActivityState::touch`]); un job de fondo (cada `HUB_ACTIVITY_REPORT_SECS`, 15
//! min por defecto) envía el heartbeat **solo si** hubo actividad nueva desde el último envío.
//! Si nadie entra, no sale nada — que es exactamente lo que el Cloud debe observar.

use std::sync::atomic::{AtomicI64, Ordering};

/// Cadencia por defecto del job de reporte: 15 min. Suficientemente fino frente a un umbral de
/// 60 DÍAS, y suficientemente grueso para que un hub ocupado no genere tráfico apreciable.
pub const DEFAULT_REPORT_SECS: u64 = 900;

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
    /// Es la decisión completa del job: sin actividad nueva no se manda nada, así que un hub
    /// dormido no genera tráfico ni resetea el reloj del Cloud.
    pub fn pending(&self) -> Option<i64> {
        let last = self.last_activity.load(Ordering::Relaxed);
        if last > 0 && last > self.last_reported.load(Ordering::Relaxed) {
            Some(last)
        } else {
            None
        }
    }

    /// Confirma que `ts` llegó al Cloud. Solo se llama tras un 2xx: si el envío falla, `pending`
    /// sigue devolviéndolo y el siguiente tick reintenta.
    pub fn mark_reported(&self, ts: i64) {
        self.last_reported.fetch_max(ts, Ordering::Relaxed);
    }
}

/// Intervalo del job en segundos: el valor de `HUB_ACTIVITY_REPORT_SECS` si es un entero > 0;
/// si no (ausente, vacío, no numérico o 0), [`DEFAULT_REPORT_SECS`]. Espejo de
/// `entitlement::interval_secs`.
pub fn interval_secs(env_value: Option<&str>) -> u64 {
    env_value
        .and_then(|v| v.trim().parse::<u64>().ok())
        .filter(|v| *v > 0)
        .unwrap_or(DEFAULT_REPORT_SECS)
}

/// Epoch en segundos → ISO-8601 UTC, el formato que parsea el Cloud (`_coerce_datetime`).
pub fn to_iso8601(ts: i64) -> String {
    chrono::DateTime::from_timestamp(ts, 0)
        .unwrap_or_else(|| chrono::DateTime::from_timestamp(0, 0).expect("epoch"))
        .to_rfc3339_opts(chrono::SecondsFormat::Secs, true)
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

/// Cuerpo del `POST /api/v1/hub/device/heartbeat/`.
///
/// Se manda SIEMPRE `last_user_activity_at` (es el motivo del envío) y `uptime_seconds` como
/// cortesía para el panel. El resto de métricas las cubre el reporte de recursos.
pub fn heartbeat_payload(activity_ts: i64, uptime_secs: Option<i64>) -> serde_json::Value {
    let mut body = serde_json::json!({ "last_user_activity_at": to_iso8601(activity_ts) });
    if let Some(up) = uptime_secs {
        body["uptime_seconds"] = serde_json::json!(up);
    }
    body
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
        // `mark_reported` solo se llama tras un 2xx; sin él, el tick siguiente reintenta.
        let st = ActivityState::new();
        st.touch(1_000);
        assert_eq!(st.pending(), Some(1_000));
        assert_eq!(st.pending(), Some(1_000));
    }

    #[test]
    fn intervalo_del_job_default_y_override() {
        assert_eq!(interval_secs(None), DEFAULT_REPORT_SECS);
        assert_eq!(interval_secs(Some("60")), 60);
        assert_eq!(interval_secs(Some(" 120 ")), 120);
        assert_eq!(interval_secs(Some("0")), DEFAULT_REPORT_SECS);
        assert_eq!(interval_secs(Some("")), DEFAULT_REPORT_SECS);
        assert_eq!(interval_secs(Some("no-numero")), DEFAULT_REPORT_SECS);
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

    #[test]
    fn el_payload_lleva_la_actividad_y_el_uptime_opcional() {
        let body = heartbeat_payload(1_700_000_000, Some(42));
        assert_eq!(body["last_user_activity_at"], "2023-11-14T22:13:20Z");
        assert_eq!(body["uptime_seconds"], 42);

        let sin_uptime = heartbeat_payload(1_700_000_000, None);
        assert!(sin_uptime.get("uptime_seconds").is_none());
    }
}
