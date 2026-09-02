//! Helpers para los e2e del runtime que necesitan los módulos REALES (`modules-workspace`).
//!
//! **El problema que cierra esto** (ERPlora/hub#253): los ~170 e2e arrancaban con un guard
//! copiado en cada test:
//!
//! ```ignore
//! if !std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
//!     .join("../../../modules-workspace/modules").exists()
//! { eprintln!("SKIP: modules-workspace not present (CI)"); return; }
//! ```
//!
//! Cuando la ruta no resolvía, el test **retornaba sin ejecutar nada y contaba como `ok`**.
//! El runner mostraba una suite entera en verde que no había ejercido ni una línea. El caso real:
//! un worktree creado fuera del árbol del monorepo (`git worktree add /tmp/...`) deja los e2e en
//! VERDE VACÍO sin avisar — y `cargo test` miente sobre lo que realmente corrió.
//!
//! # Política (recomendación 1+4 del issue)
//!
//! `modules-workspace` es un repo hermano NO clonado en CI (ver `test-hub.yml`: solo se hace
//! `checkout` del hub). Ahí el skip es legítimo. Pero **en local los módulos están al lado del
//! hub**: si faltan, casi siempre es un error de configuración (worktree fuera del árbol), no una
//! omisión intencionada.
//!
//! Así que [`require_modules_workspace`] aplica una política única y centralizada:
//!
//!   * **Fuera de CI** (lo normal en local): si los módulos no están, **`panic!` ruidoso**. El
//!     desarrollador se entera al instante en vez de creer que todo pasa. No hay forma de que un
//!     worktree mal montado deje la suite ciega.
//!   * **En CI** (`CI=true`, lo que GitHub Actions inyecta): el skip es legítimo y se imprime con
//!     un mensaje **visible** (no un `eprintln!` enterrado que se confunde con `ok`).
//!
//!   * **Con `ERPLORA_E2E_REQUIRE_MODULES=1`** (hub#1216): los módulos son **obligatorios** en este
//!     entorno y su ausencia es **fatal**, gane quien gane — ni `CI=true` ni
//!     `ERPLORA_E2E_ALLOW_SKIP` abren el skip. Lo pone el job de CI que sí clona el catálogo de
//!     módulos. Sin esto, un fallo al traerlos dejaría los 238 e2e saltándose solos y el job
//!     saldría **verde sin haber probado nada** — el agujero exacto que ese job cierra, y el mismo
//!     modo de fallo que este fichero describe arriba, solo que en CI.
//!
//! Override explícito: `ERPLORA_E2E_ALLOW_SKIP=1` permite el skip silencioso-legítimo en cualquier
//! entorno (p.ej. un worktree temporal donde uno sabe que no va a correr e2e) **salvo donde los
//! módulos se hayan declarado obligatorios**, y `ERPLORA_MODULES_DIR` apunta la raíz de módulos
//! manualmente para que un worktree fuera del monorepo pueda resolverlos sin tocar el código.

use std::path::PathBuf;

/// Raíz canónica de los módulos: `$ERPLORA_MODULES_DIR` si está definida, si no
/// `<CARGO_MANIFEST_DIR>/../../../modules-workspace/modules` (relativa al monorepo).
///
/// Pública para que los tests puedan construir rutas de módulo con la MISMA resolución que usa el
/// guard, evitando divergencias.
pub fn modules_root() -> PathBuf {
    resolve_root(
        std::env::var("ERPLORA_MODULES_DIR").ok(),
        default_modules_root,
    )
}

/// La política «override si lo hay, si no el default», factorizada para poder probarla sin mutar el
/// entorno —que es del PROCESO y provocaría carreras entre tests—, igual que [`decide`].
fn resolve_root(override_dir: Option<String>, default: fn() -> PathBuf) -> PathBuf {
    match override_dir {
        Some(dir) => PathBuf::from(dir),
        None => default(),
    }
}

/// The monorepo-relative default, WITHOUT the `$ERPLORA_MODULES_DIR` override.
///
/// Split out so a test can assert what the default resolves to without going through the function
/// the environment is allowed to override — asserting on [`modules_root`] made the test contradict
/// the very override this module documents, and it went red for anyone pointing the variable at a
/// directory of their own.
fn default_modules_root() -> PathBuf {
    // `env!` se evalúa al compilar el crate `erplora-runtime`, cuyo MANIFEST_DIR es
    // `crates/runtime`. `../../../modules-workspace/modules` sube tres niveles hasta la raíz del
    // monorepo (donde vive `modules-workspace` como repo hermano del hub).
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../../modules-workspace/modules")
}

// There was a `blueprints_root()` here (plus `$ERPLORA_BLUEPRINTS_DIR`), because
// `sector_packs_pg_e2e` read its sector seeds out of the sibling `blueprints` checkout. That was
// the hand-written catalogue model ADR-0121 retired, and the hub was its only live consumer
// (hub#1050): the seeds are now fixtures of this repo, resolved from the crate's own
// `CARGO_MANIFEST_DIR`, so there is no second sibling repo left to locate. `modules-workspace` is
// still one, and keeps its resolver below.

/// ¿Estamos corriendo en CI? GitHub Actions (y la mayoría de runners) inyectan `CI=true`.
fn running_in_ci() -> bool {
    std::env::var_os("CI").is_some()
}

/// ¿Se ha permitido explícitamente el skip legítimo vía `ERPLORA_E2E_ALLOW_SKIP=1`?
fn allow_skip_override() -> bool {
    std::env::var_os("ERPLORA_E2E_ALLOW_SKIP")
        .map(|v| v == "1" || v == "true" || v == "TRUE")
        .unwrap_or(false)
}

/// ¿Se ha declarado que en ESTE entorno los módulos son OBLIGATORIOS
/// (`ERPLORA_E2E_REQUIRE_MODULES=1`)?
///
/// Lo pone el job de CI que sí se los trae (hub#1216). Ahí «no encuentro los módulos» no es un skip
/// legítimo: es el job entero fallando en su única razón de existir.
fn require_modules_override() -> bool {
    std::env::var_os("ERPLORA_E2E_REQUIRE_MODULES")
        .map(|v| v == "1" || v == "true" || v == "TRUE")
        .unwrap_or(false)
}

/// Decisión pura del guard (sin tocar el FS ni el entorno) — factorizada para que la política sea
/// testable de forma determinista, sin carreras entre tests que muten variables de entorno.
///
/// * `modules_present` — ¿resolvió `modules_root()` a un directorio que existe?
/// * `in_ci` — equivalente a `running_in_ci()`.
/// * `allow_skip` — equivalente a `allow_skip_override()`.
#[derive(Debug, PartialEq, Eq, Clone, Copy)]
pub enum GuardDecision {
    /// Los módulos están → el test corre de verdad.
    Run,
    /// El skip es legítimo y explícito (CI / override): el test se omite, pero de forma visible.
    LegitSkip,
    /// Fuera de CI y sin override: el test DEBE fallar ruidosamente (no un verde vacío).
    FailLoud,
}

#[doc(hidden)]
pub fn decide(
    modules_present: bool,
    in_ci: bool,
    allow_skip: bool,
    require_modules: bool,
) -> GuardDecision {
    if modules_present {
        GuardDecision::Run
    } else if require_modules {
        // hub#1216: quien declara los módulos OBLIGATORIOS en su entorno (el job de CI que se los
        // trae) no admite skip, ni por `CI=true` ni por `ERPLORA_E2E_ALLOW_SKIP`. Si aquí faltan,
        // el job saldría verde sin ejecutar los 238 e2e — el agujero que vino a cerrar.
        GuardDecision::FailLoud
    } else if in_ci || allow_skip {
        GuardDecision::LegitSkip
    } else {
        // El caso que motiva el issue (ERPlora/hub#253): módulos ausentes en local casi siempre es
        // un worktree fuera del monorepo. Verde vacío → FAIL LOUD.
        GuardDecision::FailLoud
    }
}

/// Guard centralizado para los e2e que requieren `modules-workspace`.
///
/// Llamar al inicio de cada test:
///
/// ```ignore
/// #[tokio::test]
/// async fn mi_e2e() {
///     if !erplora_runtime::require_modules_workspace() { return; }
///     // ... resto del test ...
/// }
/// ```
///
/// - Devuelve `true` si los módulos están presentes → continuar el test.
/// - Devuelve `false` únicamente cuando el skip es **legítimo y explícito** (CI, o
///   `ERPLORA_E2E_ALLOW_SKIP=1`): imprime un aviso visible y el test retorna sin ejecutarse.
/// - **Fuera de CI y sin override, si faltan los módulos → `panic!` ruidoso.** Es el modo de fallo
///   que más se enmascara (worktree fuera del monorepo): lo convertimos en error en vez de dejarlo
///   pasar como verde vacío (ERPlora/hub#253).
pub fn require_modules_workspace() -> bool {
    let root = modules_root();
    let present = root.is_dir();
    match decide(present, running_in_ci(), allow_skip_override(), require_modules_override()) {
        GuardDecision::Run => true,
        GuardDecision::LegitSkip => {
            // Aviso VISIBLE: el resumen de `cargo test` no menciona los skips, así que destacamos
            // que este test no corrió realmente. Sigue siendo un skip legítimo (CI sin los repos
            // hermanos, o override explícito).
            println!(
                "⏭  SKIP e2e: modules-workspace no encontrado en {} (CI/allow-skip). \
                 Este test NO se ejecutó.",
                root.display()
            );
            false
        }
        // Con los módulos declarados OBLIGATORIOS (hub#1216) el diagnóstico es OTRO: no es un
        // worktree mal montado, es el job de CI que no consiguió traerse los módulos. Y el consejo
        // de `ERPLORA_E2E_ALLOW_SKIP` de abajo sería falso aquí — ya no abre el skip.
        GuardDecision::FailLoud if require_modules_override() => panic!(
            "modules-workspace NO encontrado en {}\n\
             \n\
             ERPLORA_E2E_REQUIRE_MODULES=1 declara que en este entorno los módulos son\n\
             OBLIGATORIOS, así que esto NO es un skip legítimo: es el fallo del propio job.\n\
             Aquí `ERPLORA_E2E_ALLOW_SKIP` NO abre el skip, a propósito.\n\
             \n\
             En CI la causa habitual es que el paso que clona el catálogo de módulos falló o quedó\n\
             a medias (token caducado o sin acceso, repo renombrado, red). Revisa ese paso: si\n\
             siguiera adelante, los 238 e2e se saltarían solos y el job saldría VERDE sin haber\n\
             probado nada — que es exactamente el agujero que hub#1216 cierra.",
            root.display()
        ),
        // Fuera de CI, los módulos DEBERÍAN estar al lado del hub. Si faltan es casi seguro un
        // worktree fuera del árbol del monorepo (el caso exacto del issue): FAIL LOUD en vez de
        // verde vacío. La pista del `0.00s` era la única señal y pasaba desapercibida.
        GuardDecision::FailLoud => panic!(
            "modules-workspace NO encontrado en {}\n\
             \n\
             Este e2e requiere los módulos reales y NO se puede saltar en silencio (ERPlora/hub#253).\n\
             Causa habitual: el worktree está fuera del árbol del monorepo, así que la ruta relativa\n\
             `crates/runtime/../../../modules-workspace/modules` no resuelve. Opciones:\n\
               • corre los tests desde un checkout dentro del monorepo (junto a modules-workspace/),\n\
               • apunta la raíz manualmente:  ERPLORA_MODULES_DIR=/path/to/modules-workspace/modules \\\n\
                   cargo test -p erplora-runtime --test <suite>\n\
               • si el skip es intencionado (p.ej. trabajo temporal sin e2e): \\\n\
                   ERPLORA_E2E_ALLOW_SKIP=1 cargo test ...\n\
             Sin módulos, el test reportaría `ok` sin ejecutar NADA — y eso es justo lo que evitamos.",
            root.display()
        ),
    }
}

/// ¿La versión `found` cubre lo que un test necesita (`needed`)?
///
/// Comparación por NÚMERO, componente a componente. Como texto, `"2.3.9" > "2.3.27"` — y por ahí
/// se cuela un falso verde. Una versión ilegible (vacía, con letras) devuelve `false`: un
/// `module.json` que no se puede leer no es permiso para asegurar nada. Las formas cortas se
/// completan con ceros (`"3"` = `3.0.0`).
fn version_is_at_least(found: &str, needed: &str) -> bool {
    fn parts(v: &str) -> Option<(u64, u64, u64)> {
        let mut it = v.trim().split('.');
        let mut next = || -> Option<u64> {
            match it.next() {
                None => Some(0),
                Some(x) => x.trim().parse::<u64>().ok(),
            }
        };
        let (a, b, c) = (next()?, next()?, next()?);
        Some((a, b, c))
    }
    match (parts(found), parts(needed)) {
        (Some(f), Some(n)) => f >= n,
        _ => false,
    }
}

/// Guard de VERSIÓN para un e2e que asegura algo de un módulo concreto.
///
/// Hermano de [`require_modules_workspace`], y por el mismo motivo. Los e2e cargan los módulos de
/// `modules-workspace/modules/<id>`, que es un checkout **compartido** por la flota: casi siempre
/// está en la rama de otro y varias releases por detrás de lo publicado. Un test que asegura algo
/// que llegó en una versión nueva se pone rojo ahí — y no en el worktree de quien lo escribió,
/// sino en el **gate pre-push de todo el que empuje después**. Ha puesto el gate de la flota en
/// rojo dos veces esta semana.
///
/// - `true` → el módulo del disco cubre la versión: el test corre.
/// - `false` → se OMITE, imprimiendo **las dos versiones y el módulo**. Visible a propósito: un
///   skip mudo es un verde vacío, que es justo lo que `require_modules_workspace` ya rechaza.
///
/// ```ignore
/// if !erplora_runtime::require_module_version("kitchen", "2.3.27") { return; }
/// ```
pub fn require_module_version(module_id: &str, needed: &str) -> bool {
    let manifest = modules_root().join(module_id).join("module.json");
    let found = std::fs::read_to_string(&manifest)
        .ok()
        .and_then(|raw| serde_json::from_str::<serde_json::Value>(&raw).ok())
        .and_then(|v| v.get("version").and_then(|x| x.as_str()).map(str::to_owned))
        .unwrap_or_default();

    if version_is_at_least(&found, needed) {
        return true;
    }
    println!(
        "⏭  SKIP e2e: `{module_id}` en disco es {} y este test necesita >= {needed}. \
         Este test NO se ejecutó.\n   {} \n   \
         El checkout de módulos lo comparte toda la flota y suele ir por detrás: \
         actualízalo (`git -C <ese checkout> fetch && git checkout main`) o apunta a otro con \
         ERPLORA_MODULES_DIR=... para ejecutarlo de verdad.",
        if found.is_empty() {
            "ilegible/ausente".to_string()
        } else {
            found
        },
        manifest.display(),
    );
    false
}

#[cfg(test)]
mod tests {
    use super::*;

    // ── Política determinista (decide): sin tocar FS ni entorno → sin carreras en paralelo ──
    //
    // Estos tests fijan la matriz de decisión del guard. Son la prueba de que el modo de fallo
    // silencioso (ERPlora/hub#253) es ahora ruidoso: en local, módulos ausentes → FailLoud (nunca
    // Run, nunca un LegitSkip encubierto). Solo CI u override explícito permiten el skip.

    // ── El módulo DEL DISCO puede ir por detrás de lo que el test asegura ──────────────────
    //
    // Los e2e cargan los módulos de `modules-workspace/modules/<id>`, que es un checkout
    // COMPARTIDO por toda la flota y que a menudo está en la rama de otro, varias releases por
    // detrás de lo publicado. Un test que asegura algo de una versión nueva se pone rojo ahí — y
    // no en su propio worktree, sino en el gate pre-push de TODO el que empuje después.
    //
    // Ha pasado dos veces esta semana. La política: si el módulo del disco es más viejo que lo que
    // el test necesita, se OMITE, pero nombrando las dos versiones — nunca en silencio, que es lo
    // que convierte un guard en un verde vacío.

    #[test]
    fn una_version_igual_o_mayor_corre_el_test() {
        assert!(version_is_at_least("2.3.27", "2.3.27"));
        assert!(version_is_at_least("2.3.28", "2.3.27"));
        assert!(version_is_at_least("2.4.0", "2.3.27"));
        assert!(version_is_at_least("3.0.0", "2.3.27"));
    }

    #[test]
    fn una_version_mas_vieja_no_corre_el_test() {
        // El caso real: el checkout compartido en 2.3.20 mientras lo publicado es 2.3.27.
        assert!(!version_is_at_least("2.3.20", "2.3.27"));
        assert!(!version_is_at_least("2.2.99", "2.3.27"));
        assert!(!version_is_at_least("1.9.9", "2.3.27"));
    }

    #[test]
    fn se_compara_por_numero_y_no_por_texto() {
        // `"2.3.9" > "2.3.27"` como CADENA, y por ahí se cuela un falso verde.
        assert!(!version_is_at_least("2.3.9", "2.3.27"));
        assert!(version_is_at_least("2.10.0", "2.9.0"));
    }

    #[test]
    fn una_version_ilegible_no_se_da_por_buena() {
        // Un `module.json` que no se puede leer no es permiso para asegurar nada.
        assert!(!version_is_at_least("", "2.3.27"));
        assert!(!version_is_at_least("no-soy-una-version", "2.3.27"));
        // Y las formas cortas se completan con ceros en vez de reventar.
        assert!(version_is_at_least("3", "2.3.27"));
        assert!(!version_is_at_least("2.3", "2.3.27"));
    }

    #[test]
    fn decide_run_cuando_los_modulos_existen() {
        // Presente manda sobre todo lo demás: el test corre siempre que haya módulos.
        assert_eq!(decide(true, false, false, false), GuardDecision::Run);
        assert_eq!(decide(true, true, false, false), GuardDecision::Run);
        assert_eq!(decide(true, false, true, false), GuardDecision::Run);
    }

    #[test]
    fn decide_fail_loud_cuando_faltan_en_local() {
        // El corazón del issue: worktree fuera del monorepo, sin CI, sin override → FAIL LOUD.
        assert_eq!(decide(false, false, false, false), GuardDecision::FailLoud);
    }

    #[test]
    fn decide_skip_legitimo_en_ci() {
        // CI no tiene los repos hermanos (test-hub.yml): el skip es legítimo y explícito.
        assert_eq!(decide(false, true, false, false), GuardDecision::LegitSkip);
    }

    #[test]
    fn decide_skip_legitimo_con_override_explicito() {
        // ERPLORA_E2E_ALLOW_SKIP=1: el dev declara que hoy no quiere e2e. Skip explícito.
        assert_eq!(decide(false, false, true, false), GuardDecision::LegitSkip);
    }

    #[test]
    fn decide_ci_y_override_son_equivalentes_para_el_skip() {
        // Ambos canales llevan al mismo LegitSkip: no hay jerarquía entre ellos.
        assert_eq!(decide(false, true, true, false), GuardDecision::LegitSkip);
    }

    /// 🔴 El job de CI que SÍ se trae los módulos (hub#1216) no puede aceptar el skip: si ahí
    /// faltan, el job saldría VERDE sin haber ejecutado ninguno de los 238 e2e — que es exactamente
    /// el agujero que ese job viene a cerrar. `ERPLORA_E2E_REQUIRE_MODULES=1` lo hace fatal.
    #[test]
    fn require_modules_gana_al_skip_de_ci() {
        assert_eq!(decide(false, true, false, true), GuardDecision::FailLoud);
    }

    /// Y gana también al override manual: quien declara que los módulos son obligatorios lo hace
    /// para este entorno concreto, y un `ERPLORA_E2E_ALLOW_SKIP` heredado del shell no puede
    /// devolver el verde vacío por la puerta de atrás.
    #[test]
    fn require_modules_gana_tambien_al_allow_skip() {
        assert_eq!(decide(false, false, true, true), GuardDecision::FailLoud);
        assert_eq!(decide(false, true, true, true), GuardDecision::FailLoud);
    }

    /// Pero si los módulos ESTÁN, `require` no cambia nada: el test corre, como siempre.
    #[test]
    fn require_modules_no_altera_el_caso_feliz() {
        assert_eq!(decide(true, true, true, true), GuardDecision::Run);
    }

    // ── Integración del guard real (sin mutar entorno de forma racy) ──────────────────────

    #[test]
    fn modules_root_por_defecto_apunta_a_monorepo() {
        // `env!` se evalúa al compilar `erplora-runtime` (MANIFEST_DIR = crates/runtime); la ruta
        // por defecto siempre termina en el segmento canónico del repo hermano.
        //
        // Contra `default_modules_root()`, NO contra `modules_root()`: esta afirmación es sobre el
        // DEFAULT, y `modules_root()` deja de serlo en cuanto hay override. Preguntándole a la
        // función que el entorno pisa, el test se ponía rojo con `ERPLORA_MODULES_DIR` apuntando a
        // cualquier ruta propia — o sea, justo al correr los e2e como el módulo dice que se corren.
        assert!(default_modules_root().ends_with("modules-workspace/modules"));
    }

    #[test]
    fn la_variable_de_entorno_gana_al_default() {
        // La otra mitad del contrato, que no probaba nadie: el override existe PARA pisar. Es lo
        // que permite correr los e2e desde un worktree fuera del monorepo, donde la ruta relativa
        // no resuelve (hub#253/#541). Sin esto, romper el override no rompe ningún test.
        //
        // Se ejerce `resolve_root`, que es LA función que usa `modules_root` — no una copia de su
        // lógica en el test. Mismo motivo que `decide()`: la política se factoriza
        // para poder probarla sin mutar el entorno, que es del PROCESO y provocaría carreras.
        assert_eq!(
            resolve_root(Some("/tmp/mis-modulos".to_string()), default_modules_root),
            PathBuf::from("/tmp/mis-modulos"),
            "con la variable puesta, el default NO se usa"
        );
        assert_eq!(
            resolve_root(None, default_modules_root),
            default_modules_root(),
            "sin la variable, manda el default del monorepo"
        );
    }

    #[test]
    fn require_modules_workspace_es_verdad_si_los_modulos_existen() {
        // En el checkout normal del monorepo los módulos están presentes → el guard devuelve true y
        // el test corre de verdad (no hay verde vacío). Desde un entorno sin módulos este test no
        // afirma nada: el caso ausente lo cubren los tests de decide() arriba.
        if !modules_root().is_dir() {
            return;
        }
        assert!(require_modules_workspace());
    }
}
