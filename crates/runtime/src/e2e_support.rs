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
//! Override explícito: `ERPLORA_E2E_ALLOW_SKIP=1` permite el skip silencioso-legítimo en cualquier
//! entorno (p.ej. un worktree temporal donde uno sabe que no va a correr e2e), y
//! `ERPLORA_MODULES_DIR` apunta la raíz de módulos manualmente para que un worktree fuera del
//! monorepo pueda resolverlos sin tocar el código.

use std::path::PathBuf;

/// Raíz canónica de los módulos: `$ERPLORA_MODULES_DIR` si está definida, si no
/// `<CARGO_MANIFEST_DIR>/../../../modules-workspace/modules` (relativa al monorepo).
///
/// Pública para que los tests puedan construir rutas de módulo con la MISMA resolución que usa el
/// guard, evitando divergencias.
pub fn modules_root() -> PathBuf {
    resolve_root(std::env::var("ERPLORA_MODULES_DIR").ok(), default_modules_root)
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

/// Canonical root of the blueprint catalogues: `$ERPLORA_BLUEPRINTS_DIR` when set, otherwise
/// `<CARGO_MANIFEST_DIR>/../../../blueprints` (relative to the monorepo).
///
/// Same policy as [`modules_root`], for the same reason (hub#540/#541): `blueprints/` is another
/// sibling repo, so a worktree created OUTSIDE the monorepo tree cannot resolve it by a relative
/// path. Without one shared resolver, a test that hardcodes the relative path fails with a bare
/// `NotFound` in exactly the setup the override exists for.
pub fn blueprints_root() -> PathBuf {
    resolve_root(std::env::var("ERPLORA_BLUEPRINTS_DIR").ok(), default_blueprints_root)
}

/// The monorepo-relative default, WITHOUT the `$ERPLORA_BLUEPRINTS_DIR` override
/// (same split, same reason, as [`default_modules_root`]).
fn default_blueprints_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../../blueprints")
}

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
pub fn decide(modules_present: bool, in_ci: bool, allow_skip: bool) -> GuardDecision {
    if modules_present {
        GuardDecision::Run
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
    match decide(present, running_in_ci(), allow_skip_override()) {
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

#[cfg(test)]
mod tests {
    use super::*;

    // ── Política determinista (decide): sin tocar FS ni entorno → sin carreras en paralelo ──
    //
    // Estos tests fijan la matriz de decisión del guard. Son la prueba de que el modo de fallo
    // silencioso (ERPlora/hub#253) es ahora ruidoso: en local, módulos ausentes → FailLoud (nunca
    // Run, nunca un LegitSkip encubierto). Solo CI u override explícito permiten el skip.

    #[test]
    fn decide_run_cuando_los_modulos_existen() {
        // Presente manda sobre todo lo demás: el test corre siempre que haya módulos.
        assert_eq!(decide(true, false, false), GuardDecision::Run);
        assert_eq!(decide(true, true, false), GuardDecision::Run);
        assert_eq!(decide(true, false, true), GuardDecision::Run);
    }

    #[test]
    fn decide_fail_loud_cuando_faltan_en_local() {
        // El corazón del issue: worktree fuera del monorepo, sin CI, sin override → FAIL LOUD.
        assert_eq!(decide(false, false, false), GuardDecision::FailLoud);
    }

    #[test]
    fn decide_skip_legitimo_en_ci() {
        // CI no tiene los repos hermanos (test-hub.yml): el skip es legítimo y explícito.
        assert_eq!(decide(false, true, false), GuardDecision::LegitSkip);
    }

    #[test]
    fn decide_skip_legitimo_con_override_explicito() {
        // ERPLORA_E2E_ALLOW_SKIP=1: el dev declara que hoy no quiere e2e. Skip explícito.
        assert_eq!(decide(false, false, true), GuardDecision::LegitSkip);
    }

    #[test]
    fn decide_ci_y_override_son_equivalentes_para_el_skip() {
        // Ambos canales llevan al mismo LegitSkip: no hay jerarquía entre ellos.
        assert_eq!(decide(false, true, true), GuardDecision::LegitSkip);
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
        assert!(default_blueprints_root().ends_with("blueprints"));
    }

    #[test]
    fn la_variable_de_entorno_gana_al_default() {
        // La otra mitad del contrato, que no probaba nadie: el override existe PARA pisar. Es lo
        // que permite correr los e2e desde un worktree fuera del monorepo, donde la ruta relativa
        // no resuelve (hub#253/#541). Sin esto, romper el override no rompe ningún test.
        //
        // Se ejerce `resolve_root`, que es LA función que usan `modules_root`/`blueprints_root` —
        // no una copia de su lógica en el test. Mismo motivo que `decide()`: la política se factoriza
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

