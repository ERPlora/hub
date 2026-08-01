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
    if let Ok(dir) = std::env::var("ERPLORA_MODULES_DIR") {
        return PathBuf::from(dir);
    }
    // `env!` se evalúa al compilar el crate `erplora-runtime`, cuyo MANIFEST_DIR es
    // `crates/runtime`. `../../../modules-workspace/modules` sube tres niveles hasta la raíz del
    // monorepo (donde vive `modules-workspace` como repo hermano del hub).
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../../modules-workspace/modules")
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
        // por defecto siempre termina en el segmento canónico del repo hermano. El runner de
        // contratos puede reemplazarla para ensamblar módulos de varios worktrees: en ese caso el
        // test comprueba que el override se respeta, sin mutar el entorno de forma racy.
        let root = modules_root();
        if let Ok(override_dir) = std::env::var("ERPLORA_MODULES_DIR") {
            assert_eq!(root, PathBuf::from(override_dir));
        } else {
            assert!(root.ends_with("modules-workspace/modules"));
        }
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
