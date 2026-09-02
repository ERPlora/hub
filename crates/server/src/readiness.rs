//! `/readyz` — «¿puedo atender?», y es un AGREGADOR, no una comprobación (hub#538).
//!
//! La forma es la de `/actuator/health` de Spring Boot: cada parte aporta su chequeo y el
//! resultado global es verde **solo si todos lo son**.
//!
//! ## Por qué existe, y por qué `/healthz` no vale
//!
//! `/healthz` es `async fn healthz() -> "ok"`: un literal. No mira la BD, ni las migraciones, ni
//! si algún módulo llegó a registrarse. Da igual mientras nadie decida nada con él — pero con el
//! blue/green de [ADR-0269] el healthcheck es el **único** criterio de `failure_action: rollback`.
//! Un hub que arranca sin BD responde `ok`, Swarm lo da por sano, **no revierte**, y mata la tarea
//! vieja que sí funcionaba. Activar el rollback antes de arreglar esto es peor que no activarlo:
//! añade una red que no atrapa nada y automatiza matar la versión buena.
//!
//! Por eso son **dos rutas distintas**, y mezclarlas es el bug de hoy:
//!
//! | | Pregunta | Quién mira | Si falla |
//! |---|---|---|---|
//! | `/healthz` | ¿el proceso responde? | supervisión | reiniciar |
//! | `/readyz`  | ¿puedo atender de verdad? | Swarm (`HEALTHCHECK`), Traefik | no mandar tráfico, **no dar la versión por buena** |
//!
//! ## Los módulos se comprueban solos
//!
//! No hace falta que ningún módulo aporte un `HealthIndicator`: el runtime ya tiene las dos
//! listas — `hub_module` (qué **debería** tener este hub) y el `Registry` (cuáles **cargaron**).
//! El chequeo es compararlas, y de paso implementa la regla sin mantener ninguna lista de
//! «módulos críticos» que alguien tendría que ir actualizando:
//!
//! > **No salgas peor de como entraste.** `hub_module` ES el estado anterior: persiste entre
//! > arranques.
//!
//! **El readiness es DURO: no hay válvula.** Se propuso «tras N arranques fallando el módulo se
//! marca degradado y deja de bloquear»; se retiró, porque eso es arrancar con menos de lo que se
//! tenía. Y no deja a nadie sin hub: con `order: start-first` la tarea vieja sigue viva hasta que
//! la nueva demuestre estar completa, así que un readiness duro no le quita el hub al cliente —
//! le deja **el de antes**.
//!
//! ## Solo dependencias LOCALES
//!
//! Nada de lo que se mira aquí sale del hub. Si `/readyz` dependiera del SaaS, una caída del Cloud
//! tumbaría **la flota entera** por rollback en cascada. Los dos casos que sí necesitan red —el
//! pre-flight y los zips de módulo— viven fuera de aquí (saas#1269, hub#571).
//!
//! [ADR-0269]: ../../../architecture/00-overview/update-model.md

use std::collections::BTreeMap;

use axum::extract::State;
use axum::http::StatusCode;
use axum::response::{IntoResponse, Response};
use axum::Json;
use serde_json::{json, Value};

use crate::AppState;

/// Estado de una parte, y del conjunto.
///
/// `Unknown` no es un adorno: es «no pude comprobarlo», que **no** es «está bien» ni «está roto».
/// Sin ese tercer estado, un fallo de red al mirar algo se pintaría de verde o de rojo, y las dos
/// mentiras cuestan — una promociona una versión rota, la otra revierte una sana.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Health {
    Up,
    Down,
    Unknown,
}

impl Health {
    fn as_str(self) -> &'static str {
        match self {
            Health::Up => "UP",
            Health::Down => "DOWN",
            Health::Unknown => "UNKNOWN",
        }
    }
}

/// Una parte del agregado: su estado y lo que haga falta para diagnosticarlo sin entrar al hub.
#[derive(Debug, Clone)]
pub struct Check {
    pub status: Health,
    pub detail: Value,
}

impl Check {
    pub fn new(status: Health) -> Self {
        Self {
            status,
            detail: json!({}),
        }
    }

    fn with(status: Health, detail: Value) -> Self {
        Self { status, detail }
    }

    fn to_json(&self) -> Value {
        let mut out = json!({ "status": self.status.as_str() });
        if let (Some(target), Some(extra)) = (out.as_object_mut(), self.detail.as_object()) {
            for (key, value) in extra {
                target.insert(key.clone(), value.clone());
            }
        }
        out
    }
}

pub type Checks = BTreeMap<String, Check>;

/// Verde **solo si todos** lo son. Un agregado vacío tampoco es verde: no haber comprobado nada no
/// es haber comprobado que todo va bien.
pub fn aggregate(checks: &Checks) -> Health {
    if checks.is_empty() {
        return Health::Unknown;
    }
    if checks.values().all(|check| check.status == Health::Up) {
        return Health::Up;
    }
    if checks.values().any(|check| check.status == Health::Down) {
        return Health::Down;
    }
    Health::Unknown
}

/// El código HTTP es el contrato con Swarm y con Traefik. Solo `UP` es 200: cualquier otra cosa
/// —incluido «no lo sé»— significa no me mandes tráfico y no des esta versión por buena.
pub fn status_code(health: Health) -> StatusCode {
    match health {
        Health::Up => StatusCode::OK,
        _ => StatusCode::SERVICE_UNAVAILABLE,
    }
}

/// Compara lo que `hub_module` dice que debería estar con lo que el `Registry` tiene cargado.
///
/// Solo mira lo que **falta**. Lo que sobra no es un fallo: los plugins nativos horneados en el
/// runtime (ADR-0009) están en el Registry sin estar en `hub_module`, y tratarlos como fallo
/// dejaría todo hub `DOWN` para siempre.
pub fn modules_check(expected: &[String], registered: &[String]) -> Check {
    let mut missing: Vec<&String> = expected
        .iter()
        .filter(|id| !registered.contains(id))
        .collect();
    missing.sort();

    let detail = json!({
        "expected": expected.len(),
        "registered": registered.len(),
        "missing": missing,
    });

    Check::with(
        if missing.is_empty() {
            Health::Up
        } else {
            Health::Down
        },
        detail,
    )
}

/// Avisa al Cloud de los switchovers de BD que el hub ha sobrevivido desde el último aviso.
///
/// Va aquí y no en [`snapshot`] a propósito: el snapshot solo describe el estado (lo consulta
/// también el aviso de arranque), mientras que esto **consume** el contador. `/readyz` es el latido
/// que Swarm ya trae, así que no hace falta un temporizador propio para sacar el dato.
///
/// Se cuenta una vez por switchover, no una por sondeo: una alerta que se repite cada 10 segundos
/// para siempre es una alerta que todo el mundo aprende a ignorar — el mismo silencio, más ruidoso.
async fn report_recovered_switchovers(st: &AppState) {
    use erplora_runtime::error_registry::{severity, source, ErrorEvent, ErrorRegistry};

    let pending = {
        let runtime = st.runtime.read().await;
        runtime.db().take_unreported_read_only_rejections()
    };
    if pending == 0 {
        return;
    }
    tracing::warn!(
        rejections = pending,
        "the database switched over: writes were rejected by the replica and the pool recycled \
         its connections"
    );
    ErrorRegistry::global().report(
        ErrorEvent::new(
            source::HUB,
            "db_read_only_rejected",
            format!(
                "{pending} write(s) rejected by a read-only replica (25006): the database \
                 switched over and the pool recycled the connections pinned to the ex-leader"
            ),
            severity::UNEXPECTED,
        )
        .with_context(json!({ "rejections": pending })),
    );
}

/// `GET /readyz`.
pub async fn readyz(State(st): State<AppState>) -> Response {
    let checks = snapshot(&st).await;
    report_recovered_switchovers(&st).await;
    let status = aggregate(&checks);
    let body = json!({
        "status": status.as_str(),
        "version": crate::version::HUB_VERSION,
        "checks": checks
            .iter()
            .map(|(name, check)| (name.clone(), check.to_json()))
            .collect::<serde_json::Map<_, _>>(),
    });

    (status_code(status), Json(body)).into_response()
}

/// Los chequeos, sin HTTP: lo que `/readyz` publica y lo que consulta el aviso de arranque
/// (`crate::boot_announce`).
///
/// Existe como función aparte para que **no haya dos respuestas** a la misma pregunta. El aviso
/// que le dice al Cloud «ya atiendo» es lo que hace que un hub pase a `active` sin esperar al
/// sondeo, así que tiene que salir exactamente cuando esta ruta diría `UP` — ni antes (marcaría
/// listo un hub que no atiende, que es peor que tardar) ni con un criterio propio que se
/// desincronice del que mira Swarm.
pub async fn snapshot(st: &AppState) -> Checks {
    let mut checks = Checks::new();
    let runtime = st.runtime.read().await;
    let db = runtime.db();

    // ── 1. La base de datos responde ─────────────────────────────────────────────────
    let database = match db.query("SELECT 1 AS ok", &Default::default()).await {
        // Un switchover del que el hub se recuperó solo (hub#1376) **no** baja el estado: la BD
        // atiende, y marcar `DOWN` por algo ya resuelto dispararía el rollback de Swarm. Pero sale
        // en el detalle, porque un hub que sobrevivió a un cambio de líder es justo lo que hay que
        // mirar cuando alguien pregunta por qué se cortó el cobro un momento.
        Ok(_) => match db.read_only_rejections() {
            0 => Check::new(Health::Up),
            rejections => Check::with(Health::Up, json!({ "read_only_rejections": rejections })),
        },
        Err(error) => Check::with(Health::Down, json!({ "error": error.to_string() })),
    };
    let database_up = database.status == Health::Up;
    checks.insert("database".into(), database);

    // ── 2. Las migraciones de sistema están aplicadas ────────────────────────────────
    //
    // Sin BD no se puede saber: `UNKNOWN`, no `DOWN`. El fallo ya lo canta el chequeo de arriba, y
    // duplicarlo como si fuera un segundo problema manda a buscar dos causas donde hay una.
    let migrations = if database_up {
        match db
            .query(
                "SELECT COUNT(*) AS applied FROM _hub_migrations",
                &Default::default(),
            )
            .await
        {
            Ok(result) => {
                let applied = result
                    .rows
                    .first()
                    .and_then(|row| {
                        row["applied"]
                            .as_u64()
                            .or_else(|| row["applied"].as_str()?.parse().ok())
                    })
                    .unwrap_or(0);
                Check::with(Health::Up, json!({ "applied": applied }))
            }
            Err(error) => Check::with(Health::Down, json!({ "error": error.to_string() })),
        }
    } else {
        Check::new(Health::Unknown)
    };
    checks.insert("migrations".into(), migrations);

    // ── 3. Los módulos que debería tener, cargados ───────────────────────────────────
    let modules = if database_up {
        match expected_modules(db, &st.hub_id()).await {
            Ok(expected) => {
                let registered: Vec<String> = runtime
                    .registry()
                    .installed
                    .iter()
                    .map(|manifest| manifest.id.clone())
                    .collect();
                modules_check(&expected, &registered)
            }
            // No poder LEER la lista no es que falte un módulo: es no saberlo.
            Err(error) => Check::with(Health::Unknown, json!({ "error": error.to_string() })),
        }
    } else {
        Check::new(Health::Unknown)
    };
    checks.insert("modules".into(), modules);

    checks
}

/// ¿Puede atender este hub **ahora mismo**? La misma respuesta que da `/readyz`.
pub async fn is_ready(st: &AppState) -> bool {
    aggregate(&snapshot(st).await) == Health::Up
}

/// Los módulos que `hub_module` dice que este hub debería tener cargados.
///
/// Lee y ya está — **no** llama a `installer::installed_status`, que de paso aplica las migraciones
/// de sistema: un healthcheck que corre cada 30 s no puede tener efectos secundarios sobre el
/// esquema, y menos mientras dos runtimes se solapan.
///
/// Los `inactive` no cuentan: están instalados y apagados a propósito, así que no cargan y su
/// ausencia del Registry es lo correcto.
async fn expected_modules(
    db: &dyn erplora_db::DatabaseAdapter,
    hub_id: &str,
) -> Result<Vec<String>, String> {
    let mut params = erplora_db::Params::new();
    params.insert("hub_id".into(), json!(hub_id));
    let result = db
        .query(
            "SELECT module_id FROM hub_module WHERE hub_id = :hub_id AND status = 'active'",
            &params,
        )
        .await
        .map_err(|error| error.to_string())?;
    Ok(result
        .rows
        .iter()
        .filter_map(|row| row["module_id"].as_str().map(str::to_owned))
        .collect())
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn checks(pairs: &[(&str, Health)]) -> Checks {
        pairs
            .iter()
            .map(|(name, status)| ((*name).to_string(), Check::new(*status)))
            .collect()
    }

    // ── El agregado ──────────────────────────────────────────────────────────────────

    #[test]
    fn ready_only_when_every_part_is_up() {
        let all_up = checks(&[("database", Health::Up), ("modules", Health::Up)]);

        assert_eq!(aggregate(&all_up), Health::Up);
    }

    #[test]
    fn one_part_down_takes_the_whole_thing_down() {
        let one_down = checks(&[("database", Health::Up), ("modules", Health::Down)]);

        assert_eq!(aggregate(&one_down), Health::Down);
    }

    /// **«No pude comprobarlo» no es «está bien».**
    ///
    /// Es la regla que `apps/web/src/lib/system-health.ts` (hub#375) ya defiende del lado del
    /// shell: un estado que miente es peor que no tener estado. Aquí importa el doble, porque el
    /// consumidor es Swarm: si un chequeo que no se pudo evaluar contase como `UP`, la tarea nueva
    /// se daría por buena y **mataría a la vieja que sí funcionaba**.
    #[test]
    fn a_part_that_could_not_be_checked_is_never_counted_as_up() {
        let unknown = checks(&[("database", Health::Up), ("migrations", Health::Unknown)]);

        assert_ne!(aggregate(&unknown), Health::Up);
        // …y sigue diciendo que NO SE SABE, que no es lo mismo que decir que está roto.
        assert_eq!(unknown["migrations"].status, Health::Unknown);
    }

    #[test]
    fn nothing_to_check_is_not_a_pass() {
        assert_ne!(aggregate(&Checks::new()), Health::Up);
    }

    // ── Los módulos se comparan solos, sin que ninguno registre nada ──────────────────

    #[test]
    fn every_expected_module_registered_is_up() {
        let check = modules_check(
            &["sales".into(), "taxes".into()],
            &["taxes".into(), "sales".into()],
        );

        assert_eq!(check.status, Health::Up);
        assert_eq!(check.detail["expected"], json!(2));
        assert_eq!(check.detail["registered"], json!(2));
    }

    /// **No salgas peor de como entraste.** `hub_module` ES el estado anterior: persiste entre
    /// arranques. Si un módulo estaba instalado y ahora no carga, es un fallo — sea cual sea el
    /// módulo, sin listas de «críticos» que alguien tendría que mantener.
    #[test]
    fn a_module_that_should_be_there_and_is_not_is_down_and_named() {
        let check = modules_check(&["sales".into(), "taxes".into()], &["taxes".into()]);

        assert_eq!(check.status, Health::Down);
        assert_eq!(check.detail["missing"], json!(["sales"]));
    }

    /// **No hay válvula, y es deliberado** (corrección de Ioan en hub#538, 2026-08-08).
    ///
    /// Se propuso «tras N arranques fallando, el módulo se marca degradado y deja de bloquear».
    /// Se retiró: eso es arrancar con menos de lo que se tenía, justo lo que el modelo prohíbe. Y
    /// no deja a nadie sin hub, porque con `order: start-first` la tarea VIEJA sigue viva hasta
    /// que la nueva demuestre estar completa — un readiness duro no le quita el hub al cliente,
    /// le deja **el de antes**.
    #[test]
    fn there_is_no_valve_that_lets_a_missing_module_through() {
        let expected = vec!["sales".to_string()];

        for attempt in 1..=10 {
            let check = modules_check(&expected, &[]);
            assert_eq!(
                check.status,
                Health::Down,
                "intento {attempt} dejó pasar el módulo que falta"
            );
        }
    }

    /// Lo que sobra no molesta: la regla es no salir con MENOS, no salir con lo mismo.
    ///
    /// Un plugin nativo horneado en el runtime (ADR-0009) está en el Registry sin estar en
    /// `hub_module`; tratarlo como fallo dejaría todo hub `DOWN` para siempre.
    #[test]
    fn a_module_registered_but_not_expected_does_not_block() {
        let check = modules_check(&["sales".into()], &["sales".into(), "printing".into()]);

        assert_eq!(check.status, Health::Up);
    }

    // ── Liveness ≠ readiness ─────────────────────────────────────────────────────────

    /// El código HTTP es el contrato con Swarm y con Traefik: 200 = mándame tráfico y da la
    /// versión por buena; 503 = ni una cosa ni la otra.
    #[test]
    fn the_status_code_says_the_same_as_the_body() {
        assert_eq!(status_code(Health::Up).as_u16(), 200);
        assert_eq!(status_code(Health::Down).as_u16(), 503);
        assert_eq!(status_code(Health::Unknown).as_u16(), 503);
    }
}
