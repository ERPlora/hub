//! Load shedding: inflight cap and 503-on-overload — split out of `lib.rs` verbatim (hub#1404).

use crate::*;

/// Env que fija el techo de peticiones EN VUELO en la superficie de negocio antes de que el
/// runtime empiece a soltar carga (hub#1401). Por encima de este número, el exceso recibe un `503`
/// inmediato en vez de encolarse hasta que el origen se satura.
pub const MAX_INFLIGHT_ENV: &str = "HUB_MAX_INFLIGHT_REQUESTS";

/// Default del techo de peticiones en vuelo cuando [`MAX_INFLIGHT_ENV`] no está configurado.
///
/// **512** es un tope de SEGURIDAD, no de latencia: protege al origen del apilamiento sin límite
/// que provoca la tormenta de `502` de Cloudflare y la recuperación de decenas de segundos
/// (medido: a 1000 concurrentes el origen colapsaba). Un hub sirve a UN negocio, así que su
/// concurrencia real es de unas pocas decenas de peticiones a la vez —muy por debajo de 512—,
/// mientras que 512 queda holgadamente por debajo del punto de colapso observado. El SaaS puede
/// ajustarlo por plan vía [`MAX_INFLIGHT_ENV`]. El cuello real está en el pool de Postgres
/// (`HUB_DB_MAX_CONNECTIONS`, 10 por defecto): este techo solo evita que el resto se acumule.
pub const DEFAULT_MAX_INFLIGHT_REQUESTS: usize = 512;

/// Segundos sugeridos en `Retry-After` al soltar una petición. La sobrecarga es transitoria —el
/// presupuesto en vuelo se drena en mucho menos de un segundo en cuanto deja de crecer—, así que
/// se pide un backoff corto en lugar de martillear un origen saturado.
pub(crate) const OVERLOADED_RETRY_AFTER_SECS: u32 = 1;

/// Interpreta el valor crudo de [`MAX_INFLIGHT_ENV`]: entero `>= 1`, o el default ante ausencia,
/// vacío, no numérico o `0` (un techo de 0 dejaría al hub sin atender nada).
pub(crate) fn resolve_max_inflight(raw: Option<&str>) -> usize {
    match raw.map(str::trim).filter(|s| !s.is_empty()) {
        None => DEFAULT_MAX_INFLIGHT_REQUESTS,
        Some(s) => match s.parse::<usize>() {
            Ok(n) if n >= 1 => n,
            _ => {
                eprintln!(
                    "{MAX_INFLIGHT_ENV} inválido ({s:?}): se esperaba un entero >= 1; \
                     usando el default {DEFAULT_MAX_INFLIGHT_REQUESTS}"
                );
                DEFAULT_MAX_INFLIGHT_REQUESTS
            }
        },
    }
}

/// Lee [`MAX_INFLIGHT_ENV`] del entorno en el punto de construcción del router.
pub(crate) fn max_inflight_from_env() -> usize {
    resolve_max_inflight(std::env::var(MAX_INFLIGHT_ENV).ok().as_deref())
}

/// Mapea el rechazo de `LoadShed` al sobre de error del runtime (ADR-0412) como un `503 Service
/// Unavailable` inmediato con `Retry-After`. Lo que NO sea la señal de sobrecarga es un fallo real
/// del propio stack de capas y sale como `500` con su mensaje —nunca un cuerpo vacío mudo, nunca un
/// `500` genérico para la sobrecarga.
pub(crate) async fn handle_overloaded(err: tower::BoxError) -> Response {
    if err.is::<tower::load_shed::error::Overloaded>() {
        let mut response = (
            StatusCode::SERVICE_UNAVAILABLE,
            Json(json!({
                "ok": false,
                "error": {
                    "code": "service_overloaded",
                    "message": "el hub está recibiendo demasiadas peticiones a la vez; reintenta en unos segundos"
                }
            })),
        )
            .into_response();
        if let Ok(value) = HeaderValue::from_str(&OVERLOADED_RETRY_AFTER_SECS.to_string()) {
            response.headers_mut().insert(header::RETRY_AFTER, value);
        }
        response
    } else {
        (
            StatusCode::INTERNAL_SERVER_ERROR,
            Json(json!({
                "ok": false,
                "error": { "code": "load_shed_layer_error", "message": err.to_string() }
            })),
        )
            .into_response()
    }
}

/// Envuelve `router` para que nunca haya más de `max_inflight` peticiones en vuelo a la vez: el
/// exceso se suelta INMEDIATAMENTE como `503` (ver [`handle_overloaded`]) en lugar de encolarse
/// hasta que el origen se satura y Cloudflare responde `502` a cualquiera que llegue (hub#1401).
///
/// Patrón Tower canónico: un límite de concurrencia GLOBAL (un único semáforo compartido entre
/// cada clon por conexión) acota el trabajo en vuelo; `LoadShed` convierte la contrapresión
/// resultante en un rechazo rápido; `HandleErrorLayer` mapea ese rechazo al sobre de error del
/// runtime y vuelve a dejar el servicio infalible. Salud/liveness (`/healthz`, `/readyz`) se dejan
/// FUERA de esta capa a propósito —ver [`app`]—: un chequeo de salud debe responder incluso bajo
/// sobrecarga, y un `503` en el healthcheck haría que Swarm reprogramara el contenedor en plena
/// punta transitoria, convirtiendo la contrapresión en una caída real. Las rutas de streaming
/// (`/ws`, `/ws/print`, SSE) SÍ pasan por aquí sin peligro: el permiso de concurrencia se libera
/// cuando el handler devuelve la respuesta (el `Sse`/upgrade), no mientras dura el stream.
pub fn with_load_shedding<S>(router: Router<S>, max_inflight: usize) -> Router<S>
where
    S: Clone + Send + Sync + 'static,
{
    use axum::error_handling::HandleErrorLayer;
    use tower::limit::GlobalConcurrencyLimitLayer;
    use tower::ServiceBuilder;

    let shed = ServiceBuilder::new()
        // La más externa: convierte el rechazo en el sobre de error del runtime, así el servicio
        // vuelve a ser infalible (nunca el cuerpo vacío por defecto de tower).
        .layer(HandleErrorLayer::new(handle_overloaded))
        // Convierte la contrapresión del límite de concurrencia en un `Overloaded` inmediato en
        // lugar de esperar en cola.
        .load_shed()
        // Un único semáforo compartido entre cada clon por conexión = presupuesto GLOBAL.
        .layer(GlobalConcurrencyLimitLayer::new(max_inflight))
        .into_inner();
    router.layer(shed)
}

#[cfg(test)]
mod load_shed_config_tests {
    //! hub#1401 — the in-flight budget parses env safely: a valid integer is honoured, and
    //! anything that would leave the hub unable to serve (absent, empty, non-numeric, or `0`)
    //! falls back to the production default instead of shedding everything.
    use super::{resolve_max_inflight, DEFAULT_MAX_INFLIGHT_REQUESTS};

    #[test]
    fn absent_or_blank_uses_the_default() {
        assert_eq!(resolve_max_inflight(None), DEFAULT_MAX_INFLIGHT_REQUESTS);
        assert_eq!(resolve_max_inflight(Some("")), DEFAULT_MAX_INFLIGHT_REQUESTS);
        assert_eq!(resolve_max_inflight(Some("   ")), DEFAULT_MAX_INFLIGHT_REQUESTS);
    }

    #[test]
    fn a_valid_positive_integer_is_honoured() {
        assert_eq!(resolve_max_inflight(Some("2")), 2);
        assert_eq!(resolve_max_inflight(Some("1024")), 1024);
        assert_eq!(resolve_max_inflight(Some("  64 ")), 64);
    }

    #[test]
    fn zero_and_garbage_fall_back_to_the_default_never_choke_the_hub() {
        // A ceiling of 0 would shed every request forever — clamp it to the default.
        assert_eq!(resolve_max_inflight(Some("0")), DEFAULT_MAX_INFLIGHT_REQUESTS);
        assert_eq!(resolve_max_inflight(Some("-5")), DEFAULT_MAX_INFLIGHT_REQUESTS);
        assert_eq!(resolve_max_inflight(Some("abc")), DEFAULT_MAX_INFLIGHT_REQUESTS);
        assert_eq!(resolve_max_inflight(Some("1.5")), DEFAULT_MAX_INFLIGHT_REQUESTS);
    }
}
