//! Guardarraíl de la superficie de instalación **local** del Hub (ERPlora/hub#239).
//!
//! `POST /api/modules/install {dir}` instala un módulo desde una carpeta del disco: es la vía de
//! DESARROLLO (la carpeta ya extraída) y esquiva a propósito el pipeline del marketplace
//! (grant + verificación SHA256 obligatoria, ADR-0015 / `module-system.md` §5). Sin guardarraíl,
//! el `dir` viajaba tal cual a `Path::new` → cualquiera con sesión admin podía apuntar a
//! CUALQUIER ruta del contenedor (`/etc`, `/tmp/loquesea`, `../..`) y ejecutar sus migraciones y
//! su SQL como código del hub.
//!
//! Dos barreras, ambas obligatorias (y en este orden):
//!  1. **Modo desarrollo explícito** (`HUB_DEV_MODE`): en producción la vía entera está apagada
//!     y el endpoint responde un error estable, sin tocar el disco. **Fail-closed**: si la
//!     variable no está, NO hay modo dev (el provisioning del SaaS nunca la inyecta).
//!  2. **Confinamiento en staging**: el `dir` se canonicaliza (resuelve `..` y symlinks) y debe
//!     caer DENTRO de una raíz conocida — la caché de descargas (`HUB_MODULE_CACHE`, donde
//!     `erplora-source` extrae los zips verificados) o, en dev, `HUB_MODULES_DIR`.
//!
//! El mismo flag gobierna el **escaneo de `HUB_MODULES_DIR` al arrancar** ([`boot_scan_dir`]):
//! en producción ese dir apunta a `/tmp/modules` (contenedor stateless) y se instalaba TODO
//! subdirectorio con un `module.json` — un directorio escribible por cualquier proceso del
//! contenedor era, de facto, un cargador de código.

use std::path::{Path, PathBuf};

/// Por qué se rechaza una instalación por directorio. Cada variante tiene un **código estable**
/// (contrato con el cliente) y un mensaje legible.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum InstallDirRejection {
    /// La vía «instalar desde carpeta» está apagada (no hay modo desarrollo explícito).
    DevModeRequired,
    /// El directorio no existe (o no se puede canonicalizar).
    NotFound,
    /// La ruta existe pero no es un directorio.
    NotADirectory,
    /// El directorio real (tras resolver `..`/symlinks) cae fuera de toda raíz de staging.
    OutsideStaging,
}

impl InstallDirRejection {
    /// Código estable para el cliente (`{ ok:false, error:{ code } }`).
    pub fn code(&self) -> &'static str {
        match self {
            Self::DevModeRequired => "dev_mode_required",
            Self::NotFound => "install_dir_not_found",
            Self::NotADirectory => "install_dir_not_a_directory",
            Self::OutsideStaging => "install_dir_outside_staging",
        }
    }

    /// Mensaje legible (español, como el resto de errores del server).
    pub fn message(&self) -> &'static str {
        match self {
            Self::DevModeRequired => {
                "instalar desde carpeta es una vía de desarrollo: deshabilitada en producción \
                 (usa el marketplace, que verifica el SHA256 del módulo)"
            }
            Self::NotFound => "el directorio indicado no existe",
            Self::NotADirectory => "la ruta indicada no es un directorio",
            Self::OutsideStaging => {
                "el directorio queda fuera del staging de módulos del hub (ruta no permitida)"
            }
        }
    }
}

/// ¿El despliegue declara **modo desarrollo**? Fail-closed: solo `1`/`true`/`yes`/`on`
/// (sin distinguir mayúsculas) activan; ausente o cualquier otra cosa = producción.
pub fn parse_dev_mode(raw: Option<&str>) -> bool {
    matches!(
        raw.map(|s| s.trim().to_ascii_lowercase()).as_deref(),
        Some("1" | "true" | "yes" | "on")
    )
}

/// Resuelve el `dir` de `POST /api/modules/install` a una ruta **confinada** en staging.
///
/// Rechaza, por este orden: sin modo dev → [`InstallDirRejection::DevModeRequired`]; ruta
/// inexistente → `NotFound`; no-directorio → `NotADirectory`; fuera de toda raíz → `OutsideStaging`.
/// La comparación se hace sobre rutas **canonicalizadas** (por eso `..` y los symlinks que
/// apuntan fuera del staging no sirven para escapar).
pub fn resolve_install_dir(
    dev_mode: bool,
    staging_roots: &[PathBuf],
    dir: &str,
) -> Result<PathBuf, InstallDirRejection> {
    if !dev_mode {
        return Err(InstallDirRejection::DevModeRequired);
    }
    let canonical =
        std::fs::canonicalize(Path::new(dir)).map_err(|_| InstallDirRejection::NotFound)?;
    if !canonical.is_dir() {
        return Err(InstallDirRejection::NotADirectory);
    }
    let inside = staging_roots
        .iter()
        .filter_map(|root| std::fs::canonicalize(root).ok())
        .any(|root| canonical.starts_with(&root));
    if !inside {
        return Err(InstallDirRejection::OutsideStaging);
    }
    Ok(canonical)
}

/// Directorio de módulos a escanear **al arrancar** (`HUB_MODULES_DIR`): solo en modo desarrollo.
/// En producción devuelve `None` aunque el env esté puesto (el llamador lo registra en el log).
pub fn boot_scan_dir<'a>(dev_mode: bool, modules_dir: Option<&'a str>) -> Option<&'a str> {
    if dev_mode {
        modules_dir
    } else {
        None
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Crea un árbol temporal `<tmp>/<tag>/{staging/mod-a, fuera/mod-b}` y lo devuelve.
    fn tree(tag: &str) -> PathBuf {
        let base = std::env::temp_dir().join(format!(
            "erplora-install-guard-{}-{tag}",
            std::process::id()
        ));
        let _ = std::fs::remove_dir_all(&base);
        std::fs::create_dir_all(base.join("staging/mod-a")).unwrap();
        std::fs::create_dir_all(base.join("fuera/mod-b")).unwrap();
        base
    }

    #[test]
    fn dev_mode_solo_con_valor_explicito() {
        assert!(!parse_dev_mode(None), "ausente = producción (fail-closed)");
        assert!(!parse_dev_mode(Some("")), "vacío = producción");
        assert!(!parse_dev_mode(Some("0")));
        assert!(!parse_dev_mode(Some("false")));
        assert!(!parse_dev_mode(Some("session")), "otro valor = producción");
        assert!(parse_dev_mode(Some("1")));
        assert!(parse_dev_mode(Some("true")));
        assert!(parse_dev_mode(Some(" TRUE ")));
        assert!(parse_dev_mode(Some("yes")));
    }

    /// (b) del contrato: en producción la vía entera está apagada, aunque el dir sea legítimo.
    #[test]
    fn en_produccion_no_se_instala_desde_carpeta() {
        let base = tree("prod");
        let staging = vec![base.join("staging")];
        let dir = base.join("staging/mod-a");
        let err = resolve_install_dir(false, &staging, dir.to_str().unwrap()).unwrap_err();
        assert_eq!(err, InstallDirRejection::DevModeRequired);
        assert_eq!(err.code(), "dev_mode_required");
        let _ = std::fs::remove_dir_all(&base);
    }

    /// (a) del contrato: rutas absolutas fuera del staging y travesías `..` se rechazan.
    #[test]
    fn fuera_del_staging_se_rechaza() {
        let base = tree("fuera");
        let staging = vec![base.join("staging")];

        // Ruta absoluta del sistema.
        assert_eq!(
            resolve_install_dir(true, &staging, "/etc").unwrap_err(),
            InstallDirRejection::OutsideStaging
        );
        // Hermano del staging (mismo padre, otro subárbol).
        let hermano = base.join("fuera/mod-b");
        assert_eq!(
            resolve_install_dir(true, &staging, hermano.to_str().unwrap()).unwrap_err(),
            InstallDirRejection::OutsideStaging
        );
        // Travesía explícita desde dentro del staging.
        let travesia = base.join("staging/../fuera/mod-b");
        assert_eq!(
            resolve_install_dir(true, &staging, travesia.to_str().unwrap()).unwrap_err(),
            InstallDirRejection::OutsideStaging
        );
        // Prefijo de cadena que NO es prefijo de ruta (`staging-evil` no está en `staging`).
        std::fs::create_dir_all(base.join("staging-evil/mod-c")).unwrap();
        let vecino = base.join("staging-evil/mod-c");
        assert_eq!(
            resolve_install_dir(true, &staging, vecino.to_str().unwrap()).unwrap_err(),
            InstallDirRejection::OutsideStaging
        );
        let _ = std::fs::remove_dir_all(&base);
    }

    /// Un symlink DENTRO del staging que apunta fuera no sirve para escapar (se canonicaliza).
    #[cfg(unix)]
    #[test]
    fn symlink_que_sale_del_staging_se_rechaza() {
        let base = tree("symlink");
        let staging = vec![base.join("staging")];
        let link = base.join("staging/escape");
        std::os::unix::fs::symlink(base.join("fuera/mod-b"), &link).unwrap();
        assert_eq!(
            resolve_install_dir(true, &staging, link.to_str().unwrap()).unwrap_err(),
            InstallDirRejection::OutsideStaging
        );
        let _ = std::fs::remove_dir_all(&base);
    }

    /// (c) del contrato: en modo dev, un dir dentro del staging se acepta (ruta canonicalizada).
    #[test]
    fn dentro_del_staging_en_modo_dev_se_acepta() {
        let base = tree("ok");
        let staging = vec![base.join("staging")];
        let dir = base.join("staging/mod-a");
        let resolved = resolve_install_dir(true, &staging, dir.to_str().unwrap()).unwrap();
        assert_eq!(resolved, std::fs::canonicalize(&dir).unwrap());
        let _ = std::fs::remove_dir_all(&base);
    }

    #[test]
    fn dir_inexistente_o_fichero_se_distinguen() {
        let base = tree("missing");
        let staging = vec![base.join("staging")];
        assert_eq!(
            resolve_install_dir(true, &staging, base.join("staging/nope").to_str().unwrap())
                .unwrap_err(),
            InstallDirRejection::NotFound
        );
        let file = base.join("staging/mod-a/module.json");
        std::fs::write(&file, b"{}").unwrap();
        assert_eq!(
            resolve_install_dir(true, &staging, file.to_str().unwrap()).unwrap_err(),
            InstallDirRejection::NotADirectory
        );
        let _ = std::fs::remove_dir_all(&base);
    }

    /// Sin raíces de staging configuradas no se instala nada (deny-all).
    #[test]
    fn sin_raices_de_staging_no_se_instala() {
        let base = tree("noroots");
        let dir = base.join("staging/mod-a");
        assert_eq!(
            resolve_install_dir(true, &[], dir.to_str().unwrap()).unwrap_err(),
            InstallDirRejection::OutsideStaging
        );
        let _ = std::fs::remove_dir_all(&base);
    }

    /// (g) del contrato: `HUB_MODULES_DIR` solo se escanea al arrancar en modo desarrollo.
    #[test]
    fn el_escaneo_de_arranque_es_solo_dev() {
        assert_eq!(boot_scan_dir(true, Some("/tmp/modules")), Some("/tmp/modules"));
        assert_eq!(boot_scan_dir(false, Some("/tmp/modules")), None);
        assert_eq!(boot_scan_dir(true, None), None);
    }
}
