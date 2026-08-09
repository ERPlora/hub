//! Cuánto sigue aceptando el hub tras recibir SIGTERM (hub#646).
//!
//! ## El fallo que cierra
//!
//! Con `order: start-first` (ADR-0269), Swarm manda **SIGTERM** a la tarea vieja en cuanto la nueva
//! pasa el healthcheck. Y `with_graceful_shutdown` hace lo correcto **a medias**: cierra el listener
//! **en el acto** y drena lo que hay en vuelo. Las peticiones en vuelo se salvan; **las nuevas, no**.
//!
//! Y siguen llegando, porque **Traefik no descubre backends por DNS**: con el provider Swarm usa la
//! API de Docker y la consulta cada `refreshSeconds` — **15 s por defecto**. Durante esa ventana
//! sigue mandando tráfico a un socket que ya no acepta → **502 al cliente, en cada actualización**.
//!
//! ⚠️ Ojo con la intuición: el riesgo **no** es que Traefik tarde en descubrir la tarea nueva (por
//! defecto filtra las no sanas, así que no le manda nada hasta que pasa su healthcheck). El riesgo
//! es el contrario: que tarde en **dejar de** mandar a la vieja.
//!
//! ## La solución, y por qué no es `stopGracePeriod` a secas
//!
//! Alargar el `stopGracePeriod` **no arregla nada por sí solo**: el proceso ya cerró el listener al
//! recibir la señal, así que darle más tiempo solo alarga una agonía en la que sigue rechazando.
//! Lo que hace falta es **seguir aceptando** hasta que Traefik haya dejado de mandar — el patrón
//! `preStop sleep` de Kubernetes.
//!
//! Las dos piezas van juntas: aquí se espera, y el service spec (`stopGracePeriodSwarm`, saas) tiene
//! que dar margen suficiente o Swarm mata con SIGKILL a mitad del drenaje.

use std::time::Duration;

/// Cada cuánto consulta Traefik la API de Docker con el provider Swarm. **Es el número que manda**:
/// el drenaje tiene que durar más que esto o la ventana sigue abierta.
pub const TRAEFIK_REFRESH: Duration = Duration::from_secs(15);

/// 20 s = los 15 de Traefik más margen. No sale de una medición: sale de un valor **documentado y
/// configurado**, así que no hace falta ensayar nada para justificarlo (a diferencia de `Monitor`
/// y `start_period`, que sí — hub#520).
pub const DEFAULT_DRAIN: Duration = Duration::from_secs(20);

/// Techo duro. Drenar más de lo que Swarm espera antes de SIGKILL no drena: solo garantiza morir a
/// mitad de una petición, que es peor que no drenar. Tiene que ir por debajo del
/// `stopGracePeriodSwarm` que pide el service spec.
pub const MAX_DRAIN: Duration = Duration::from_secs(60);

/// Cuánto seguir aceptando tras la señal. `HUB_SHUTDOWN_DRAIN_SECONDS` lo ajusta.
///
/// **Cero es legítimo**: en local no hay Traefik delante y esperar 20 s en cada Ctrl-C es una
/// tortura. Lo que no puede ser es el default.
pub fn drain_delay() -> Duration {
    match std::env::var("HUB_SHUTDOWN_DRAIN_SECONDS") {
        Ok(raw) => match raw.trim().parse::<u64>() {
            Ok(seconds) => Duration::from_secs(seconds).min(MAX_DRAIN),
            // Un valor absurdo no puede colgar el apagado ni saltarse el drenaje en silencio.
            Err(_) => DEFAULT_DRAIN,
        },
        Err(_) => DEFAULT_DRAIN,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn con(valor: Option<&str>) -> std::time::Duration {
        match valor {
            Some(v) => std::env::set_var("HUB_SHUTDOWN_DRAIN_SECONDS", v),
            None => std::env::remove_var("HUB_SHUTDOWN_DRAIN_SECONDS"),
        }
        drain_delay()
    }

    /// **El valor por defecto tiene que sobrevivir al polling de Traefik.**
    ///
    /// Traefik no descubre backends por DNS: usa la API de Docker y la consulta cada
    /// `refreshSeconds` — **15 s por defecto**. Si el hub deja de aceptar antes, Traefik sigue
    /// mandándole tráfico a un socket cerrado durante lo que le quede de ventana → **502 al
    /// cliente**, en cada actualización.
    #[test]
    fn the_default_outlasts_traefiks_polling_window() {
        assert!(
            con(None) > TRAEFIK_REFRESH,
            "el drenaje por defecto ({:?}) no cubre los {:?} de polling de Traefik",
            con(None),
            TRAEFIK_REFRESH
        );
    }

    #[test]
    fn it_can_be_tuned_from_the_environment() {
        assert_eq!(con(Some("45")), std::time::Duration::from_secs(45));
    }

    /// **Cero es legítimo** — en local no hay Traefik delante y esperar 20 s en cada Ctrl-C es una
    /// tortura. Lo que no puede es ser el default.
    #[test]
    fn zero_is_allowed_for_local_development() {
        assert_eq!(con(Some("0")), std::time::Duration::ZERO);
    }

    /// Un valor absurdo no puede colgar el apagado para siempre: Swarm mataría con SIGKILL a mitad
    /// de una petición, que es peor que no drenar.
    #[test]
    fn a_nonsense_value_falls_back_to_the_default() {
        assert_eq!(con(Some("no-soy-un-numero")), DEFAULT_DRAIN);
    }

    #[test]
    fn it_never_outlasts_the_grace_period_swarm_gives_us() {
        // `stopGracePeriodSwarm` es lo que Swarm espera antes de SIGKILL. Drenar más que eso no
        // drena: solo garantiza morir a mitad.
        assert!(
            con(Some("9999")) <= MAX_DRAIN,
            "el drenaje debe caber dentro del stopGracePeriod que pide el service spec"
        );
    }
}
