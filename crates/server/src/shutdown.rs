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

/// Lo que Swarm espera desde el SIGTERM hasta el SIGKILL.
///
/// **Este número NO se decide aquí**: lo pone el service spec, y el service spec lo escribe el
/// SaaS al desplegar (`stopGracePeriodSwarm` en el provider de Hetzner). Aquí está copiado para
/// poder afirmarlo en un test, porque es un acoplamiento entre dos repos que no tiene quien lo
/// vigile: si allí baja a 20 s y aquí nadie se entera, el drenaje muere a mitad y el síntoma —un
/// 502 esporádico durante los despliegues— no apunta a este fichero ni de lejos.
///
/// Si cambia allí, cambia aquí y el test de abajo dice si el techo sigue cabiendo.
pub const SWARM_STOP_GRACE: Duration = Duration::from_secs(40);

/// Techo duro. Drenar más de lo que Swarm espera antes de SIGKILL no drena: solo garantiza morir a
/// mitad de una petición, que es peor que no drenar.
///
/// 30 s = holgadamente por encima de los 15 de Traefik y holgadamente por debajo de los 40 de
/// `SWARM_STOP_GRACE`, con margen para que el proceso termine de cerrar después de drenar.
pub const MAX_DRAIN: Duration = Duration::from_secs(30);

/// Cuánto seguir aceptando tras la señal. `HUB_SHUTDOWN_DRAIN_SECONDS` lo ajusta.
///
/// **Cero es legítimo**: en local no hay Traefik delante y esperar 20 s en cada Ctrl-C es una
/// tortura. Lo que no puede ser es el default.
pub fn drain_delay() -> Duration {
    drain_from(std::env::var("HUB_SHUTDOWN_DRAIN_SECONDS").ok().as_deref())
}

/// La decisión, sin tocar el entorno.
///
/// Está separada de `drain_delay()` por los tests. La versión anterior los hacía leer y escribir
/// `HUB_SHUTDOWN_DRAIN_SECONDS` —una variable del **proceso**, compartida— y cargo los corre en
/// paralelo dentro del mismo binario: cada test pisaba el valor del vecino. El resultado no era
/// «a veces falla», era peor: **fallaba un subconjunto distinto en cada ejecución**, así que el
/// fallo parecía venir de lo último que hubieras tocado. Se descubrió justo así, cambiando
/// `MAX_DRAIN` y viendo cómo fallaban los tres tests que NO tenían nada que ver.
///
/// Sin entorno de por medio no hay estado compartido y no hay carrera.
fn drain_from(raw: Option<&str>) -> Duration {
    match raw {
        Some(raw) => match raw.trim().parse::<u64>() {
            Ok(seconds) => Duration::from_secs(seconds).min(MAX_DRAIN),
            // Un valor absurdo no puede colgar el apagado ni saltarse el drenaje en silencio.
            Err(_) => DEFAULT_DRAIN,
        },
        None => DEFAULT_DRAIN,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Lo que valdría `HUB_SHUTDOWN_DRAIN_SECONDS`, **sin tocar el entorno del proceso**.
    fn con(valor: Option<&str>) -> std::time::Duration {
        drain_from(valor)
    }

    /// El puente entre la función pura y la que lee el entorno: si alguien desconecta una de otra,
    /// todo lo de abajo seguiría verde probando código que ya no se usa.
    #[test]
    fn the_env_reader_delegates_to_the_pure_decision() {
        // Sin la variable puesta —el caso de producción— las dos tienen que coincidir.
        std::env::remove_var("HUB_SHUTDOWN_DRAIN_SECONDS");
        assert_eq!(drain_delay(), drain_from(None));
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

    /// El valor de ejemplo va por debajo de `MAX_DRAIN` a propósito: si se pusiera uno por encima,
    /// este test estaría midiendo el recorte del techo en lugar de que el entorno se lea.
    #[test]
    fn it_can_be_tuned_from_the_environment() {
        assert!(Duration::from_secs(25) < MAX_DRAIN, "25 s debe caber bajo el techo");
        assert_eq!(con(Some("25")), std::time::Duration::from_secs(25));
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

    /// **El techo tiene que caber dentro de lo que Swarm espera.**
    ///
    /// El test que había aquí antes comparaba el drenaje contra `MAX_DRAIN`… que es justo lo que
    /// acababa de recortarlo en `drain_delay()`. Era una tautología: verde por construcción,
    /// pasara lo que pasara con el service spec. Y tapaba un fallo real —`MAX_DRAIN` eran 60 s
    /// contra un `stopGracePeriodSwarm` de 40—, así que un `HUB_SHUTDOWN_DRAIN_SECONDS=50` se
    /// aceptaba tan ricamente y luego moría de SIGKILL a los 40, a mitad del drenaje: exactamente
    /// lo que el techo existía para impedir.
    ///
    /// Ahora se compara contra el número de verdad.
    #[test]
    fn the_cap_fits_inside_the_grace_period_swarm_gives_us() {
        assert!(
            MAX_DRAIN < SWARM_STOP_GRACE,
            "el techo del drenaje ({MAX_DRAIN:?}) no cabe en el stopGracePeriod de Swarm \
             ({SWARM_STOP_GRACE:?}): un valor entre los dos se acepta y muere de SIGKILL a mitad"
        );
    }

    /// Y lo mismo por el otro lado: ningún valor del entorno, por bestia que sea, puede acabar
    /// durando más de lo que Swarm aguanta.
    #[test]
    fn no_environment_value_can_outlast_the_grace_period() {
        assert!(
            con(Some("9999")) < SWARM_STOP_GRACE,
            "un valor absurdo del entorno se ha colado por encima del stopGracePeriod"
        );
    }
}
