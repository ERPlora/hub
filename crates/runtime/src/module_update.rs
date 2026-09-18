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

/// Una actualización que **ocurrió**: de dónde venía y a dónde fue.
///
/// Es lo único que el dueño ve de todo esto (ADR-0269 §3.5, hub#564): *«qué me habéis cambiado y
/// desde qué versión»*. Por eso viaja el `from` y no solo la versión nueva — «inventory 1.1.2» no
/// dice nada; «1.1.1 → 1.1.2» sí.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ModuleUpdate {
    pub module_id: String,
    pub from: String,
    pub to: String,
}

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
    Update {
        from: String,
        to: String,
    },
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
        .filter_map(|candidate| {
            parse(&candidate.version).map(|parsed| (parsed, &candidate.version))
        })
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

/// Las versiones que se le pueden **ofrecer** a este hub, de la más nueva a la más vieja.
///
/// Es la lista del desplegable de versión (hub#675): instalar y actualizar dejan de tener una sola
/// opción implícita —«lo que el resolutor decida»— y pasan a poder elegir. `installed = None` es el
/// caso de instalar por primera vez.
///
/// **Elegir no relaja ninguna regla de [`resolve`]**, y esa es la parte que importa: si la lista
/// tuviera su propia política, el desplegable sería una segunda puerta por la que entra justo lo
/// que la primera impide.
///
/// - **Un pin de soporte no deja nada que elegir.** Si hemos clavado a un cliente en `sales@3.1`
///   mientras se arregla la `3.2`, un desplegable que ofrezca la `3.2` es la forma de saltárselo.
/// - **Nada en cuarentena.** Es literalmente para lo que se marca rota una versión.
/// - **Nada hacia atrás, ni la instalada.** Bajar ejecutaría migraciones ya pasadas sobre datos que
///   la nueva escribió, y no hay `down` (ADR-0269 §3.4). Bajar a un cliente sigue siendo la palanca
///   de soporte —versión explícita contra la ruta de update—, no una opción del dueño.
/// - **Lo que no se puede ordenar, no se ofrece**; y si la ilegible es la instalada, no se ofrece
///   nada: sin poder comparar no se sabe qué sería «hacia delante».
///
/// Devolver la lista vacía es una respuesta legítima y frecuente —el hub ya corre lo último, o el
/// Cloud no contestó—: no hay nada que elegir, y la pantalla no debe abrir un desplegable.
pub fn offer(
    installed: Option<&str>,
    pinned: Option<&str>,
    available: &[Available],
) -> Vec<String> {
    if pinned.is_some() {
        return Vec::new();
    }

    let floor = match installed {
        Some(version) => match parse(version) {
            Some(parsed) => Some(parsed),
            // La instalada no se puede comparar: no se ofrece a ciegas.
            None => return Vec::new(),
        },
        None => None,
    };

    let mut ordered: Vec<((u64, u64, u64), &str)> = available
        .iter()
        .filter(|candidate| candidate.is_active)
        .filter_map(|candidate| {
            parse(&candidate.version).map(|parsed| (parsed, candidate.version.as_str()))
        })
        .filter(|(parsed, _)| floor.is_none_or(|current| *parsed > current))
        .collect();

    ordered.sort_by(|a, b| b.0.cmp(&a.0));
    ordered
        .into_iter()
        .map(|(_, version)| version.to_string())
        .collect()
}

/// Qué versión instalar por la que un BUNDLE anotó (`manifest.modules[].version`, hub#751/#752).
///
/// La versión de un blueprint **no es un requisito, es una foto**: el exportador escribe lo que el
/// hub de origen tenía puesto ese día. El marketplace, en cambio, **borra** las versiones viejas al
/// publicar (se queda con las últimas N), así que a los pocos meses el zip pineado ya no existe y
/// una plantilla por lo demás perfecta deja al negocio sin poder vender — que es lo que tumbó a la
/// vez a las cuatro plantillas publicadas (`sales@2.12.8`, `verifactu@1.4.1`).
///
/// Exigir la versión exacta convierte el pin en una **fecha de caducidad silenciosa**; instalar
/// cualquier cosa lo convierte en un adorno. En medio está lo que hace esta función:
///
/// - **Si el pin sigue publicado, gana el pin.** La sustitución es un rescate, nunca una subida de
///   versión por la espalda: dos hubs que importan la misma plantilla el mismo día tienen que
///   acabar igual.
/// - **Si no está, la más nueva COMPATIBLE.** Compatible = mismo *major* (y, con *major* `0`,
///   también mismo *minor*: en `0.x` cada minor puede romper — es la regla del `^` de Cargo/npm).
///   Cruzar un major sí es una sorpresa de las caras: las filas del bundle se escribieron contra
///   ese contrato, y ninguna migración de módulo sabe traducirlas.
/// - **Nunca hacia atrás.** Igual que [`resolve`]: no hay `down` (ADR-0269), bajar ejecutaría
///   migraciones ya pasadas.
/// - **Nada en cuarentena**, ni siquiera cuando la cuarentena es el propio pin. `is_active = false`
///   es «esta versión está rota»: servirla porque la pidió una plantilla sería la segunda puerta
///   por la que entra justo lo que la primera impide.
/// - **Lo que no se puede comparar, no se sustituye.** Un pin con formato raro solo se resuelve si
///   está publicado tal cual; adivinar a qué línea pertenece sería inventar.
///
/// `None` = no hay nada instalable, y eso **sigue siendo un fallo que hay que contar**: es la
/// diferencia entre «te he puesto la siguiente» y «esta plantilla ya no se puede importar».
pub fn resolve_bundle_version(requested: &str, available: &[Available]) -> Option<String> {
    let installable = |candidate: &&Available| candidate.is_active;

    // El pin vivo manda — incluso si no se puede parsear (un id de versión exótico publicado tal
    // cual es instalable aunque no sea ordenable).
    if let Some(exact) = available
        .iter()
        .filter(installable)
        .find(|candidate| candidate.version == requested)
    {
        return Some(exact.version.clone());
    }

    let pinned = parse(requested)?;
    available
        .iter()
        .filter(installable)
        .filter_map(|candidate| {
            parse(&candidate.version).map(|parsed| (parsed, &candidate.version))
        })
        .filter(|(parsed, _)| *parsed > pinned && compatible(pinned, *parsed))
        .max_by_key(|(parsed, _)| *parsed)
        .map(|(_, version)| version.clone())
}

/// Which version a TEMPLATE bundle (`purpose: template`) installs for the one it recorded (hub#1904).
///
/// A published template starts a **new** business, and a new business starts on what the store
/// offers **today**: the version in `manifest.modules[].version` is the day the template was
/// exported, and honouring it while it is still published is how «Peluquería» kept opening salons
/// on `sales@2.16.1` with `2.16.67` out — a charge button off-screen that was already fixed. The
/// hub would move it forward on its next boot anyway ([`resolve`], hub#516); until then the owner
/// runs on stale code.
///
/// What the pin still decides is the **contract**, and that is the part that does not move:
///
/// - **The newest COMPATIBLE, the pin included** — same *major* (and same *minor* under `0.x`),
///   exactly as [`resolve_bundle_version`] substitutes a pruned pin. The template's rows were
///   written against that major; a newer one is the boot auto-update's job, with its migrations.
/// - **Never backwards, nothing in quarantine**, the same rules as every other resolver here.
/// - **An unparseable pin resolves only to itself**, published as is: it cannot be placed on a line.
///
/// A **backup** (`purpose: backup`) does not come through here: restoring your own hub reinstalls
/// what it ran, and [`resolve_bundle_version`] keeps that rule (ADR-0303). `None` = nothing
/// installable in the recorded line, which the caller still has to report.
pub fn resolve_template_version(requested: &str, available: &[Available]) -> Option<String> {
    let installable = |candidate: &&Available| candidate.is_active;

    let Some(pinned) = parse(requested) else {
        return available
            .iter()
            .filter(installable)
            .find(|candidate| candidate.version == requested)
            .map(|exact| exact.version.clone());
    };

    available
        .iter()
        .filter(installable)
        .filter_map(|candidate| {
            parse(&candidate.version).map(|parsed| (parsed, &candidate.version))
        })
        .filter(|(parsed, _)| *parsed >= pinned && compatible(pinned, *parsed))
        .max_by_key(|(parsed, _)| *parsed)
        .map(|(_, version)| version.clone())
}

/// `true` si `candidate` puede sustituir a `pinned` sin cambiar el contrato con el que se
/// escribieron las filas del bundle: mismo *major*, y con *major* `0` también mismo *minor*
/// (semántica `^`: en `0.x` el minor es el eje que rompe).
fn compatible(pinned: (u64, u64, u64), candidate: (u64, u64, u64)) -> bool {
    if pinned.0 != candidate.0 {
        return false;
    }
    pinned.0 != 0 || pinned.1 == candidate.1
}

/// Cómo acabó un intento de actualización.
#[derive(Debug)]
pub enum Outcome {
    /// Ya estaba en esa versión: no se descargó nada ni se migró nada.
    AlreadyThere(String),
    Updated {
        from: String,
        to: String,
    },
    /// La nueva falló y **la vieja volvió a quedar instalada y funcionando**.
    RolledBack {
        stayed_on: String,
        error: String,
    },
    /// La nueva falló **y la vuelta atrás también**. El hub se queda sin el módulo, y por eso este
    /// caso no puede pasar en silencio: con el readiness duro de hub#538 el arranque siguiente no
    /// dará `UP`, y Swarm revertirá el despliegue entero.
    Lost {
        module: String,
        error: String,
    },
}

/// Actualiza, y si falla **deja la versión anterior puesta**.
///
/// Un hub con la versión de ayer funciona; uno sin el módulo, no. Antes el arranque omitía con un
/// log el módulo que no podía bajar, y el módulo **dejaba de existir** para el hub — era el cuarto
/// punto de hub#516 y el que más duele.
///
/// `install` recibe la versión y la instala (descarga, verifica firma y aplica migraciones por el
/// guard de hub#542). Se pasa como closure para que esta secuencia —que es la parte con reglas— se
/// pueda probar sin red.
pub async fn update_with_fallback<F, Fut>(from: &str, to: &str, install: F) -> Outcome
where
    F: Fn(String) -> Fut,
    Fut: std::future::Future<Output = Result<(), String>>,
{
    if from == to {
        return Outcome::AlreadyThere(to.to_string());
    }

    match install(to.to_string()).await {
        Ok(()) => Outcome::Updated {
            from: from.to_string(),
            to: to.to_string(),
        },
        Err(error) => match install(from.to_string()).await {
            Ok(()) => Outcome::RolledBack {
                stayed_on: from.to_string(),
                error,
            },
            Err(second) => Outcome::Lost {
                module: from.to_string(),
                error: format!("{error}; y la vuelta a {from} tampoco: {second}"),
            },
        },
    }
}

/// `X.Y.Z` → comparable. Devuelve `None` para cualquier otra cosa, que el llamante trata como
/// «no se puede comparar» en vez de como cero.
/// `pub(crate)` because the update history compares the CORE's versions with the same rule
/// (hub#564): the number that decides "this is a rollback, not an update" cannot be a second,
/// slightly different parser, or the two would eventually disagree about the same jump.
pub(crate) fn parse(version: &str) -> Option<(u64, u64, u64)> {
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
        Available {
            version: version.into(),
            is_active,
        }
    }

    // ── Se actualizan solos ──────────────────────────────────────────────────────────

    #[test]
    fn a_newer_version_is_picked_up_without_anyone_asking() {
        let target = resolve("1.0.0", None, &[v("1.0.0", true), v("1.1.0", true)]);

        assert_eq!(
            target,
            Target::Update {
                from: "1.0.0".into(),
                to: "1.1.0".into()
            }
        );
    }

    #[test]
    fn the_highest_wins_not_the_last_in_the_list() {
        let target = resolve(
            "1.0.0",
            None,
            &[v("1.10.0", true), v("1.9.0", true), v("1.2.0", true)],
        );

        assert_eq!(
            target.version(),
            "1.10.0",
            "1.10 > 1.9: se compara por número, no por texto"
        );
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
        let target = resolve(
            "3.1.0",
            Some("3.1.0"),
            &[v("3.1.0", true), v("3.2.0", true)],
        );

        assert_eq!(target, Target::StayPut("3.1.0".into()));
    }

    #[test]
    fn a_support_pin_also_beats_the_quarantine() {
        // Si lo hemos clavado ahí a propósito, es porque sabemos lo que hacemos.
        let target = resolve(
            "3.1.0",
            Some("3.1.0"),
            &[v("3.1.0", false), v("3.2.0", true)],
        );

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

    // ── Qué versiones se le pueden OFRECER a alguien ─────────────────────────────────

    /// Instalar por primera vez: no hay nada instalado contra lo que comparar, así que valen
    /// todas las publicadas — y la primera de la lista es la última, que es la que se ofrece.
    #[test]
    fn a_first_install_can_choose_among_every_published_version_newest_first() {
        let offered = offer(
            None,
            None,
            &[v("1.0.0", true), v("2.0.0", true), v("1.5.0", true)],
        );

        assert_eq!(offered, vec!["2.0.0", "1.5.0", "1.0.0"]);
    }

    /// La misma regla que `resolve`, y por el mismo motivo: la cuarentena existe para que una
    /// versión marcada rota no llegue a un hub. Un desplegable que la enseñe es una segunda puerta
    /// que la deja entrar con un clic.
    #[test]
    fn a_quarantined_version_is_never_offered() {
        let offered = offer(None, None, &[v("1.0.0", true), v("2.0.0", false)]);

        assert_eq!(offered, vec!["1.0.0"]);
    }

    /// **Elegir versión no es poder bajar de versión.** Retroceder ejecutaría migraciones ya
    /// pasadas sobre datos que la nueva escribió, y no hay `down` (ADR-0269 §3.4): no es una
    /// operación que exista. Bajar a alguien sigue siendo la palanca de soporte —versión explícita
    /// contra la ruta—, no un desplegable del dueño.
    #[test]
    fn an_installed_module_is_never_offered_a_downgrade() {
        let offered = offer(
            Some("2.0.0"),
            None,
            &[v("1.0.0", true), v("2.0.0", true), v("2.1.0", true)],
        );

        assert_eq!(
            offered,
            vec!["2.1.0"],
            "ni la instalada ni ninguna anterior"
        );
    }

    #[test]
    fn the_newest_comes_first_compared_by_number_not_by_text() {
        let offered = offer(None, None, &[v("1.9.0", true), v("1.10.0", true)]);

        assert_eq!(offered.first().map(String::as_str), Some("1.10.0"));
    }

    /// Nada que elegir es una respuesta legítima: el hub ya corre lo último. La pantalla no debe
    /// abrir un desplegable con una sola opción que no cambia nada.
    #[test]
    fn a_module_already_on_the_latest_has_nothing_to_offer() {
        assert!(offer(Some("2.0.0"), None, &[v("2.0.0", true)]).is_empty());
    }

    #[test]
    fn a_version_that_cannot_be_ordered_is_not_offered() {
        let offered = offer(None, None, &[v("latest", true), v("1.0.0", true)]);

        assert_eq!(
            offered,
            vec!["1.0.0"],
            "lo que no se puede colocar no se ofrece"
        );
    }

    /// Si la instalada no se puede comparar, no se sabe qué sería «hacia delante»: se ofrece nada
    /// en vez de ofrecer a ciegas. Misma regla que `resolve`.
    #[test]
    fn an_installed_version_that_cannot_be_compared_offers_nothing() {
        assert!(offer(Some("no-semver"), None, &[v("1.0.0", true)]).is_empty());
    }

    /// El Cloud no contestó (o el módulo se despublicó entero): no hay lista, y no hay desplegable.
    #[test]
    fn an_empty_catalogue_offers_nothing() {
        assert!(offer(None, None, &[]).is_empty());
        assert!(offer(Some("1.0.0"), None, &[]).is_empty());
    }

    /// El pin de soporte gana también aquí, y por el mismo motivo que la cuarentena: si lo hemos
    /// clavado en `3.1` mientras se arregla la `3.2`, un desplegable que ofrezca la `3.2` es
    /// exactamente la forma de saltárselo. `resolve` ya lo respeta; la lista no puede ser la
    /// excepción, o el pin dejaría de ser una garantía y pasaría a ser una sugerencia.
    #[test]
    fn a_module_pinned_by_support_has_nothing_to_choose() {
        let offered = offer(
            Some("3.1.0"),
            Some("3.1.0"),
            &[v("3.1.0", true), v("3.2.0", true)],
        );

        assert!(
            offered.is_empty(),
            "el pin no se salta desde la pantalla: {offered:?}"
        );
    }

    // ── Actualizar sin quedarse sin módulo ───────────────────────────────────────────

    async fn attempt(fails: &[&str], from: &str, to: &str) -> (Outcome, Vec<String>) {
        let intentos = std::sync::Arc::new(std::sync::Mutex::new(Vec::new()));
        let registro = intentos.clone();
        let rotas: Vec<String> = fails.iter().map(|s| s.to_string()).collect();
        let outcome = update_with_fallback(from, to, move |version: String| {
            let registro = registro.clone();
            let rotas = rotas.clone();
            async move {
                registro.lock().unwrap().push(version.clone());
                if rotas.contains(&version) {
                    Err(format!("la {version} no instala"))
                } else {
                    Ok(())
                }
            }
        })
        .await;
        let hechos = intentos.lock().unwrap().clone();
        (outcome, hechos)
    }

    #[tokio::test]
    async fn a_clean_update_lands_on_the_new_version() {
        let (outcome, intentos) = attempt(&[], "1.0.0", "1.1.0").await;

        assert!(matches!(outcome, Outcome::Updated { .. }));
        assert_eq!(intentos, vec!["1.1.0"], "no se reinstala lo que ya estaba");
    }

    /// **Una actualización que falla NO puede dejar al hub sin el módulo.**
    ///
    /// Un hub con la versión de ayer funciona; uno sin el módulo, no. Antes el arranque omitía con
    /// un log el que no podía bajar y el módulo **dejaba de existir** para el hub.
    #[tokio::test]
    async fn a_failed_update_puts_the_old_version_back() {
        let (outcome, intentos) = attempt(&["1.1.0"], "1.0.0", "1.1.0").await;

        assert!(matches!(outcome, Outcome::RolledBack { .. }), "{outcome:?}");
        assert_eq!(
            intentos,
            vec!["1.1.0", "1.0.0"],
            "se intenta la nueva y se vuelve a la vieja"
        );
    }

    /// Y si la vuelta atrás TAMBIÉN falla, se dice — no se finge que salió bien.
    ///
    /// Es el caso en que el hub sí se queda sin el módulo, y precisamente por eso no puede pasar
    /// en silencio: con readiness duro (hub#538) el arranque siguiente no dará `UP`.
    #[tokio::test]
    async fn when_even_the_rollback_fails_it_says_so() {
        let (outcome, intentos) = attempt(&["1.1.0", "1.0.0"], "1.0.0", "1.1.0").await;

        assert!(matches!(outcome, Outcome::Lost { .. }), "{outcome:?}");
        assert_eq!(intentos, vec!["1.1.0", "1.0.0"]);
    }

    /// Actualizar a lo que ya tienes no toca nada: ni descarga, ni migraciones, ni riesgo.
    #[tokio::test]
    async fn updating_to_the_version_already_installed_does_nothing() {
        let (outcome, intentos) = attempt(&[], "1.1.0", "1.1.0").await;

        assert!(matches!(outcome, Outcome::AlreadyThere(_)), "{outcome:?}");
        assert!(intentos.is_empty(), "no se reinstala por gusto");
    }

    // ── La versión que anotó un bundle (hub#751/#752) ────────────────────────────────

    /// El caso real: el marketplace podó `sales@2.12.8` y la plantilla se quedó sin ventas.
    #[test]
    fn a_pinned_version_the_marketplace_pruned_falls_back_to_the_newest_compatible() {
        let resolved = resolve_bundle_version("2.12.8", &[v("2.13.10", true), v("2.13.9", true)]);

        assert_eq!(resolved.as_deref(), Some("2.13.10"));
    }

    /// La sustitución es un rescate, no una subida de versión por la espalda.
    #[test]
    fn a_pinned_version_that_is_still_published_wins_over_a_newer_one() {
        let resolved = resolve_bundle_version("2.13.9", &[v("2.13.10", true), v("2.13.9", true)]);

        assert_eq!(resolved.as_deref(), Some("2.13.9"));
    }

    /// Cruzar un major no es sustituir: las filas del bundle se escribieron contra el contrato
    /// viejo y ninguna migración de módulo sabe traducirlas.
    #[test]
    fn a_newer_major_is_not_a_substitute() {
        let resolved = resolve_bundle_version("1.4.1", &[v("2.0.0", true)]);

        assert_eq!(resolved, None, "no se cruza un major a la brava");
    }

    /// En `0.x` el eje que rompe es el minor (semántica `^`): `printing@0.1.5` puede caer a
    /// `0.1.7`, nunca a `0.2.0`.
    #[test]
    fn below_one_point_zero_the_minor_is_the_breaking_axis() {
        assert_eq!(
            resolve_bundle_version("0.1.5", &[v("0.1.7", true)]).as_deref(),
            Some("0.1.7"),
        );
        assert_eq!(resolve_bundle_version("0.1.5", &[v("0.2.0", true)]), None);
    }

    /// **Nunca hacia atrás**, igual que `resolve`: no hay `down` (ADR-0269).
    #[test]
    fn an_older_version_is_never_a_substitute() {
        let resolved = resolve_bundle_version("2.12.8", &[v("2.11.0", true)]);

        assert_eq!(resolved, None, "bajar ejecutaría migraciones ya pasadas");
    }

    /// La cuarentena no se salta por venir de una plantilla: si se saltara, el bundle sería una
    /// segunda puerta por la que entra justo la versión que se marcó rota.
    #[test]
    fn a_quarantined_version_is_not_served_even_when_the_bundle_pins_it() {
        assert_eq!(
            resolve_bundle_version("2.12.8", &[v("2.12.8", false), v("2.13.1", true)]).as_deref(),
            Some("2.13.1"),
            "el pin en cuarentena se sustituye, no se instala",
        );
        assert_eq!(
            resolve_bundle_version("2.12.8", &[v("2.13.1", false)]),
            None,
            "sin nada sano compatible no hay sustituta",
        );
    }

    /// Un pin ilegible solo se resuelve si está publicado tal cual: adivinar a qué línea
    /// pertenece sería inventar.
    #[test]
    fn an_unparseable_pin_resolves_only_when_it_is_still_published() {
        assert_eq!(
            resolve_bundle_version("2026-07-31", &[v("2026-07-31", true)]).as_deref(),
            Some("2026-07-31"),
        );
        assert_eq!(
            resolve_bundle_version("2026-07-31", &[v("2.13.10", true)]),
            None
        );
    }

    /// Un módulo que ya no publica NADA no tiene sustituta — y el llamante debe contarlo.
    #[test]
    fn a_module_with_nothing_published_has_no_substitute() {
        assert_eq!(resolve_bundle_version("1.4.1", &[]), None);
    }

    // ── The version a TEMPLATE recorded (hub#1904) ───────────────────────────────────

    /// The real case: «Peluquería» recorded `sales@2.16.1` while the store served `2.16.67`, and
    /// the fix for the tablet's charge button only lived in the newer one. A new salon starts on
    /// what the store offers today, not on the day the template was exported.
    #[test]
    fn a_template_pin_that_is_still_published_yields_to_the_newest_compatible() {
        let resolved = resolve_template_version(
            "2.16.1",
            &[v("2.16.67", true), v("2.16.2", true), v("2.16.1", true)],
        );

        assert_eq!(resolved.as_deref(), Some("2.16.67"));
    }

    #[test]
    fn a_template_pin_that_is_already_the_newest_is_kept() {
        let resolved =
            resolve_template_version("2.16.67", &[v("2.16.67", true), v("2.16.1", true)]);

        assert_eq!(resolved.as_deref(), Some("2.16.67"));
    }

    /// Staying current never crosses a major: the template's rows were written against that
    /// contract. A newer major is the boot auto-update's job, with its migrations, not the import's.
    #[test]
    fn a_template_stays_on_its_major_even_when_a_newer_one_exists() {
        assert_eq!(
            resolve_template_version(
                "1.4.1",
                &[v("2.0.0", true), v("1.4.3", true), v("1.4.1", true)]
            )
            .as_deref(),
            Some("1.4.3"),
        );
        assert_eq!(
            resolve_template_version("1.4.1", &[v("2.0.0", true), v("1.4.1", true)]).as_deref(),
            Some("1.4.1"),
            "the recorded one is still the newest of its line",
        );
    }

    /// Below 1.0 the minor is the breaking axis (`^` semantics), as for the pruned-pin rescue.
    #[test]
    fn a_template_below_one_point_zero_stays_on_its_minor() {
        assert_eq!(
            resolve_template_version(
                "0.1.14",
                &[v("0.2.0", true), v("0.1.22", true), v("0.1.14", true)]
            )
            .as_deref(),
            Some("0.1.22"),
        );
    }

    /// Never backwards: there is no `down` (ADR-0269).
    #[test]
    fn a_template_never_goes_back_to_an_older_version() {
        assert_eq!(
            resolve_template_version("2.12.8", &[v("2.11.0", true)]),
            None
        );
    }

    /// Quarantine is not skipped for a template: neither the newest nor the recorded one is
    /// served when it is marked broken.
    #[test]
    fn a_template_skips_quarantined_versions() {
        assert_eq!(
            resolve_template_version(
                "2.13.9",
                &[v("2.13.11", false), v("2.13.10", true), v("2.13.9", true)]
            )
            .as_deref(),
            Some("2.13.10"),
            "the newest is broken: the next healthy one goes in",
        );
        assert_eq!(
            resolve_template_version("2.13.9", &[v("2.13.9", false)]),
            None,
            "nothing healthy in its line: nothing to install",
        );
    }

    /// An unparseable pin cannot be placed on a line: only its exact, published self resolves.
    #[test]
    fn a_template_with_an_unparseable_pin_resolves_only_to_itself() {
        assert_eq!(
            resolve_template_version("2026-07-31", &[v("2.13.10", true), v("2026-07-31", true)])
                .as_deref(),
            Some("2026-07-31"),
        );
        assert_eq!(
            resolve_template_version("2026-07-31", &[v("2.13.10", true)]),
            None
        );
    }

    #[test]
    fn a_template_module_with_nothing_published_resolves_to_nothing() {
        assert_eq!(resolve_template_version("1.4.1", &[]), None);
    }
}
