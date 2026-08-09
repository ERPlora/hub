//! Qué versión de cada módulo debe correr este hub (hub#516).
//!
//! Los módulos se actualizan **solos**, como el hub. La re-descarga del arranque ya existía —el
//! `module_cache` es `/tmp` en el contrato stateless de Swarm, así que se vacía en cada redeploy—;
//! lo único que faltaba es que **resuelva la última versión instalable en vez de la pineada**.
//!
//! ## Por qué solos, y no «alerta + botón»
//!
//! Si el hub se actualiza solo porque *el usuario nunca actualiza por miedo a romper*, con los
//! módulos ese problema se multiplica **por 24**. Una lista de «tienes 7 módulos pendientes»
//! produce fragmentación al cuadrado: 24 módulos × N versiones es un espacio de combinaciones que
//! no se puede probar ni soportar, y convierte la primera pregunta de cada incidencia en «¿qué
//! combinación tienes?».
//!
//! ## Lo que hace seguro hacerlo solo
//!
//! Tres cosas que **ya están** (eran los bloqueantes duros de esta issue):
//!
//! - **hub#542** — el SQL de una migración de módulo se valida antes de aplicarse, y su `DROP` se
//!   traduce a `RENAME TO _deprecated_*`: nada de lo que aplique una versión nueva destruye datos.
//! - **hub#517** — expand/contract, así que al revertir no hay nada que deshacer.
//! - **hub#538** — un módulo que no carga deja `/readyz` en `DOWN`, y Swarm revierte el despliegue
//!   entero en vez de dejar el hub «sano» con el TPV roto.
//!
//! Este módulo es solo la decisión: **qué versión**. El cómo lo aplica es el instalador.

/// Una versión que el marketplace ofrece.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Available {
    pub version: String,
    /// `false` = **en cuarentena** (`ModuleVersion.is_active` del Cloud: «marked as broken»).
    pub is_active: bool,
}

/// Qué debe correr este hub tras resolver.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Target {
    Update { from: String, to: String },
    /// Se queda donde está — y eso incluye el caso en que el Cloud no dijo nada. **Nunca «sin
    /// módulo»**: un hub con la versión de ayer funciona; uno sin el módulo, no.
    StayPut(String),
}

impl Target {
    pub fn version(&self) -> &str {
        match self {
            Target::Update { to, .. } => to,
            Target::StayPut(version) => version,
        }
    }

    pub fn is_update(&self) -> bool {
        matches!(self, Target::Update { .. })
    }
}

/// Decide la versión que toca.
///
/// - **Un pin de soporte gana sobre todo**, incluida una versión más nueva y la cuarentena. No es
///   una opción de producto —el dueño no elige— sino una herramienta nuestra: dejar a un cliente en
///   `sales@3.1` mientras se arregla la `3.2`, sin tocar a los demás.
/// - **Las versiones en cuarentena no se eligen jamás.** Es justo lo que la cuarentena existe para
///   impedir: que una versión rota se instale sola en toda la flota.
/// - **Nunca hacia atrás.** Bajar ejecutaría migraciones ya pasadas sobre datos que la nueva
///   escribió, y no hay `down` (ADR-0269): retroceder no es una operación que exista.
/// - **Lo que no se puede comparar, no se mueve.** Una versión con formato raro se ignora, y si la
///   ilegible es la instalada, el hub se queda donde está: mover a ciegas es peor que no mover.
pub fn resolve(installed: &str, pinned: Option<&str>, available: &[Available]) -> Target {
    if let Some(pin) = pinned {
        return Target::StayPut(pin.to_string());
    }

    let Some(current) = parse(installed) else {
        return Target::StayPut(installed.to_string());
    };

    let best = available
        .iter()
        .filter(|candidate| candidate.is_active)
        .filter_map(|candidate| parse(&candidate.version).map(|parsed| (parsed, &candidate.version)))
        .filter(|(parsed, _)| *parsed > current)
        .max_by_key(|(parsed, _)| *parsed);

    match best {
        Some((_, version)) => Target::Update {
            from: installed.to_string(),
            to: version.clone(),
        },
        None => Target::StayPut(installed.to_string()),
    }
}

/// `X.Y.Z` → comparable. Devuelve `None` para cualquier otra cosa, que el llamante trata como
/// «no se puede comparar» en vez de como cero.
fn parse(version: &str) -> Option<(u64, u64, u64)> {
    let mut parts = version.split('.');
    let major = parts.next()?.parse().ok()?;
    let minor = parts.next()?.parse().ok()?;
    let patch = parts.next()?.parse().ok()?;
    if parts.next().is_some() {
        return None;
    }
    Some((major, minor, patch))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn v(version: &str, is_active: bool) -> Available {
        Available { version: version.into(), is_active }
    }

    // ── Se actualizan solos ──────────────────────────────────────────────────────────

    #[test]
    fn a_newer_version_is_picked_up_without_anyone_asking() {
        let target = resolve("1.0.0", None, &[v("1.0.0", true), v("1.1.0", true)]);

        assert_eq!(target, Target::Update { from: "1.0.0".into(), to: "1.1.0".into() });
    }

    #[test]
    fn the_highest_wins_not_the_last_in_the_list() {
        let target = resolve("1.0.0", None, &[v("1.10.0", true), v("1.9.0", true), v("1.2.0", true)]);

        assert_eq!(target.version(), "1.10.0", "1.10 > 1.9: se compara por número, no por texto");
    }

    #[test]
    fn already_on_the_latest_is_not_an_update() {
        let target = resolve("2.0.0", None, &[v("1.9.0", true), v("2.0.0", true)]);

        assert_eq!(target, Target::StayPut("2.0.0".into()));
    }

    // ── La cuarentena manda ──────────────────────────────────────────────────────────

    /// `ModuleVersion.is_active = false` es la cuarentena. Una versión marcada rota **no se
    /// instala sola en toda la flota** — que es justo lo que la cuarentena existe para impedir.
    #[test]
    fn a_version_marked_broken_is_never_chosen() {
        let target = resolve("1.0.0", None, &[v("1.1.0", true), v("2.0.0", false)]);

        assert_eq!(target.version(), "1.1.0", "la 2.0.0 está en cuarentena");
    }

    /// Y si la que el hub TIENE es la que se marcó rota, sigue avanzando: sacarlo de ahí es
    /// exactamente para lo que se pone la cuarentena.
    #[test]
    fn a_hub_stuck_on_a_quarantined_version_still_moves_forward() {
        let target = resolve("2.0.0", None, &[v("2.0.0", false), v("2.0.1", true)]);

        assert_eq!(target.version(), "2.0.1");
    }

    // ── El pin de soporte ────────────────────────────────────────────────────────────

    /// **No es una opción de producto** —el dueño no elige— sino una herramienta nuestra: cuando un
    /// cliente tiene un problema con `sales@3.2`, dejarlo en `3.1` mientras se arregla, sin tocar a
    /// los demás. Por eso gana sobre todo lo demás, incluida una versión más nueva.
    #[test]
    fn a_support_pin_beats_a_newer_version() {
        let target = resolve("3.1.0", Some("3.1.0"), &[v("3.1.0", true), v("3.2.0", true)]);

        assert_eq!(target, Target::StayPut("3.1.0".into()));
    }

    #[test]
    fn a_support_pin_also_beats_the_quarantine() {
        // Si lo hemos clavado ahí a propósito, es porque sabemos lo que hacemos.
        let target = resolve("3.1.0", Some("3.1.0"), &[v("3.1.0", false), v("3.2.0", true)]);

        assert_eq!(target.version(), "3.1.0");
    }

    // ── Nunca hacia atrás, y nunca a ciegas ──────────────────────────────────────────

    /// Bajar de versión ejecutaría migraciones que ya pasaron sobre datos que la nueva escribió.
    /// No hay `down` (ADR-0269): retroceder no es una operación que exista.
    #[test]
    fn it_never_goes_backwards() {
        let target = resolve("2.0.0", None, &[v("1.0.0", true), v("1.5.0", true)]);

        assert_eq!(target, Target::StayPut("2.0.0".into()));
    }

    #[test]
    fn an_empty_catalogue_leaves_the_hub_exactly_as_it_was() {
        // El Cloud no contestó, o el módulo se despublicó entero: se queda con lo que tiene y
        // funciona. Nunca «sin módulo».
        assert_eq!(resolve("1.0.0", None, &[]), Target::StayPut("1.0.0".into()));
    }

    /// Una versión con formato raro no puede tumbar el arranque de un hub: se ignora.
    #[test]
    fn a_version_that_is_not_semver_is_ignored_not_fatal() {
        let target = resolve("1.0.0", None, &[v("latest", true), v("1.1.0", true)]);

        assert_eq!(target.version(), "1.1.0");
    }

    #[test]
    fn an_unparseable_installed_version_does_not_update_blindly() {
        // Si no se puede comparar, no se toca: mover a ciegas es peor que no mover.
        let target = resolve("no-semver", None, &[v("1.0.0", true)]);

        assert_eq!(target, Target::StayPut("no-semver".into()));
    }
}
