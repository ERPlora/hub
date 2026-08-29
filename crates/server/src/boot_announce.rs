//! «Ya atiendo» — el aviso que el hub manda al Cloud en cuanto empieza a servir (hub#712).
//!
//! ## El problema que resuelve
//!
//! El SaaS decide que un hub pasa de `deploying` a `active` **preguntando**: sondea la URL del
//! hub cada pocos segundos durante diez minutos. No es un capricho — Dokploy no está en el camino
//! del tráfico y no emite eventos, y lo que emitiría sería «build hecho», que no es «acepta
//! tráfico». Pero preguntar tiene dos costes: el visitante espera con su hub ya listo, y un fallo
//! del sondeo deja marcado `deploying` para siempre a un hub que está perfectamente vivo.
//!
//! El hub, en cambio, **sabe** cuándo empieza a atender. Y ya tiene abierto el canal para decirlo:
//! `POST /api/v1/hub/device/heartbeat/` con la credencial de máquina (hub#199, ADR-0003). Lo único
//! que faltaba era mandar un latido **al arrancar**, en vez de solo en el tick de 24 h.
//!
//! ## El orden es TODO
//!
//! Un aviso que sale antes de tiempo es peor que no mandarlo: marcaría `active` un hub que
//! todavía no atiende, y el visitante se encontraría un error en vez de una espera. Por eso el
//! aviso está atado a [`crate::readiness::is_ready`] — **el mismo agregado que publica `/readyz`**
//! y que mira el `HEALTHCHECK` de Swarm— y no a un criterio propio que pudiera desincronizarse.
//! Se lanza además después de bindear el listener, así que cuando sale el aviso el hub ya está
//! aceptando conexiones.
//!
//! ## Y es *best-effort*, de verdad
//!
//! Si el aviso falla —hub sin enrolar, red caída, Cloud caído— **el hub arranca igual**. Esta
//! tarea vive fuera del camino de arranque y no propaga nada. El sondeo del SaaS sigue existiendo
//! exactamente para eso: aquí se convierte en el respaldo en vez de ser el mecanismo.
//!
//! Quien decide de verdad sigue siendo el SaaS, que al recibir el latido de un hub en `deploying`
//! confirma con `/readyz` antes de marcarlo. Este aviso adelanta la pregunta; no la contesta.

use std::future::Future;
use std::time::Duration;

use crate::{auth, daily_usage, readiness, AppState};

/// Cuánto se espera a que el hub esté listo antes de rendirse y dejarlo en manos del sondeo.
///
/// Generoso a propósito: lo que hay detrás de un arranque lento es una BD que tarda o una
/// migración larga, y en ambos casos el aviso sigue siendo útil cuando llegue. Rendirse aquí no
/// rompe nada — solo devuelve al hub al camino de antes.
pub const READY_TIMEOUT: Duration = Duration::from_secs(300);

/// Cada cuánto se vuelve a mirar. Es una consulta local (la misma de `/readyz`), no red.
pub const READY_POLL: Duration = Duration::from_millis(250);

/// Lanza el aviso en su propia tarea. Lo llama [`crate::serve`] **después de bindear** el
/// listener: cuando esta tarea llegue a mandar el latido, el hub ya acepta conexiones.
pub fn spawn(state: &AppState) {
    let state = state.clone();
    tokio::spawn(async move { announce_when_ready(state, READY_TIMEOUT, READY_POLL).await });
}

/// Espera a que el hub esté listo y manda **un** latido. Nunca falla hacia fuera.
///
/// `timeout`/`poll` son parámetros para que los tests no tengan que esperar cinco minutos a un
/// hub que jamás va a estar listo; en producción son [`READY_TIMEOUT`] y [`READY_POLL`].
pub async fn announce_when_ready(state: AppState, timeout: Duration, poll: Duration) {
    // Sin credencial de máquina no hay a quién avisar: un hub creado fuera del aprovisionamiento
    // (un `pnpm dev`) no existe para el Cloud. Se comprueba ANTES de esperar a nada — no tiene
    // sentido vigilar el readiness de un hub que no va a poder decírselo a nadie.
    let Some(auth) = auth::machine_auth(&state) else {
        return;
    };

    if !wait_until(timeout, poll, || readiness::is_ready(&state)).await {
        // No es un error del arranque: el hub sigue sirviendo lo que pueda servir y `/readyz`
        // sigue contando la verdad a quien pregunte. Simplemente nadie se ha enterado por esta vía.
        tracing::warn!(
            timeout_secs = timeout.as_secs(),
            "el hub no estuvo listo a tiempo: no se avisa al Cloud (queda el sondeo)"
        );
        return;
    }

    let mut usage = {
        let runtime = state.runtime.read().await;
        let now = chrono::Utc::now().to_rfc3339();
        daily_usage::collect_daily_usage(runtime.db(), runtime.hub_id(), &now).await
    };
    // hub#975: el latido de arranque lleva la misma telemetría de recursos que el diario —
    // fuera del lock del runtime (el sampler de CPU duerme 100 ms) y best-effort igual que él.
    daily_usage::sample_resource_metrics().await.apply_to(&mut usage);

    match daily_usage::send_heartbeat(&state.http, &state.config.cloud_base_url, &auth, &usage).await
    {
        Ok(_) => tracing::info!("arranque: avisado al Cloud de que este hub ya atiende"),
        // Best-effort literal: el sondeo del SaaS es exactamente el respaldo de este caso.
        Err(error) => {
            tracing::warn!(%error, "arranque: no se pudo avisar al Cloud (queda el sondeo)")
        }
    }
}

/// Sondea `ready` hasta que diga que sí o se agote `timeout`. `true` = llegó a estar listo.
///
/// **El primer vistazo es inmediato**, y no es un detalle: cuando esto corre, el arranque ya hizo
/// todo su trabajo (migraciones, re-hidratación y re-descarga de módulos), así que lo normal es
/// acertar a la primera. Dormir antes de mirar sería regalar el retardo que este trabajo viene a
/// quitar — exactamente el defecto que tenía el sondeo del SaaS.
async fn wait_until<F, Fut>(timeout: Duration, poll: Duration, mut ready: F) -> bool
where
    F: FnMut() -> Fut,
    Fut: Future<Output = bool>,
{
    let deadline = tokio::time::Instant::now() + timeout;
    loop {
        if ready().await {
            return true;
        }
        // Se para ANTES de dormir de más: una espera que se pasa del plazo es una espera que
        // nadie pidió, y aquí se paga en el arranque de cada hub.
        if tokio::time::Instant::now() + poll >= deadline {
            return false;
        }
        tokio::time::sleep(poll).await;
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::cell::Cell;

    /// Lo normal: cuando esto corre el hub YA está listo, y mirar cuesta una consulta local.
    /// Dormir «por si acaso» antes del primer vistazo añadiría ese retardo al arranque de todos
    /// los hubs para no ganar nada.
    #[tokio::test]
    async fn the_first_look_happens_before_any_sleep() {
        let looks = Cell::new(0);

        let ready = wait_until(Duration::from_secs(60), Duration::from_secs(30), || {
            looks.set(looks.get() + 1);
            async { true }
        })
        .await;

        assert!(ready);
        assert_eq!(looks.get(), 1, "un hub ya listo no puede costar más de un vistazo");
    }

    /// Un hub que tarda en abrir su BD no se pierde el aviso: se vuelve a mirar.
    #[tokio::test]
    async fn a_hub_that_takes_a_moment_is_still_caught() {
        let looks = Cell::new(0);

        let ready = wait_until(Duration::from_millis(500), Duration::from_millis(5), || {
            looks.set(looks.get() + 1);
            async { looks.get() >= 3 }
        })
        .await;

        assert!(ready);
        assert_eq!(looks.get(), 3);
    }

    /// **Rendirse es una opción, colgarse no.** Si el hub nunca llega a estar listo, esta tarea
    /// termina y deja el trabajo al sondeo del SaaS — que es quien cubre ese caso.
    #[tokio::test]
    async fn it_gives_up_instead_of_waiting_forever() {
        let started = std::time::Instant::now();

        let ready = wait_until(Duration::from_millis(100), Duration::from_millis(10), || async {
            false
        })
        .await;

        assert!(!ready);
        assert!(
            started.elapsed() < Duration::from_secs(2),
            "se rindió tarde: {:?}",
            started.elapsed()
        );
    }

    /// Y no se pasa del plazo por dormir una última vez: el `poll` puede ser más largo que lo que
    /// queda, y esperar de más en el arranque es justo lo que aquí no se puede hacer.
    #[tokio::test]
    async fn it_never_sleeps_past_the_deadline() {
        let started = std::time::Instant::now();

        wait_until(Duration::from_millis(30), Duration::from_secs(30), || async { false }).await;

        assert!(
            started.elapsed() < Duration::from_secs(1),
            "durmió un ciclo entero de más: {:?}",
            started.elapsed()
        );
    }
}
