//! 🔴 **El radio de explosión de una regla nueva del guard, medido sobre el catálogo ENTERO.**
//!
//! `published_contracts_still_install.rs` congela los cuatro `contract` publicados, que es lo que
//! puede correr en CI sin `modules-workspace`. Pero hub#1149 mete una regla que afecta a **todas**
//! las migraciones de todos los `kind` —un cuerpo procedimental no entra— y hub#1109 cambia cómo
//! se leen los nombres de tabla en **cualquier** sentencia. Medir eso contra cuatro ficheros no
//! mide nada: hace falta pasar el guard por las 155 migraciones que los 27 repos publican.
//!
//! El barrido a mano dice hoy «cero afectadas». Un barrido a mano no es un guardia: al mes que
//! viene nadie se acuerda de repetirlo, y el módulo que se cae lo descubre el cliente al instalar.
//! Esto lo deja permanente.
//!
//! **Se salta (a gritos) donde no hay `modules-workspace`**, como el resto de e2e — en el gate de
//! la flota, que corre con el worktree hermano del workspace, sí mide de verdad. Y como un test
//! que se salta sale tan verde como uno que pasa, lleva dos cinturones: exige un mínimo de
//! ficheros vistos cuando el catálogo está, y comprueba que la misma puerta **rechaza el
//! positivo** — si `check` empezara a devolver `Ok` siempre, este test se pone rojo.
use erplora_runtime::manifest::Manifest;
use erplora_runtime::migration_guard::{Kind, check};

/// La misma lista efectiva que aplica el instalador: `manifest ∪ migrations/postgres/*.sql`, con
/// el `kind` declarado (y `expand` para lo que el manifest no lista). Recorrer solo el manifest
/// dejaría fuera justo los ficheros que viajan en el zip sin declarar, que son los que el runtime
/// aplica como `expand` y los que más fácil se saltan una regla nueva.
fn declared_migrations(dir: &std::path::Path, manifest: &Manifest) -> Vec<(String, Kind)> {
    let mut files: Vec<(String, Kind)> = manifest
        .migrations
        .postgres
        .iter()
        .map(|entry| (entry.file().to_string(), entry.kind()))
        .collect();
    if let Ok(entries) = std::fs::read_dir(dir.join("migrations").join("postgres")) {
        for entry in entries.flatten() {
            let name = entry.file_name().to_string_lossy().into_owned();
            if !name.ends_with(".sql") {
                continue;
            }
            let rel = format!("migrations/postgres/{name}");
            if !files.iter().any(|(f, _)| f == &rel) {
                files.push((rel, Kind::Expand));
            }
        }
    }
    files.sort_by(|(a, _), (b, _)| a.cmp(b));
    files
}

#[test]
fn every_published_migration_still_passes_the_guard() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
    let root = erplora_runtime::modules_root();

    let mut modules = 0;
    let mut migrations = 0;
    for entry in std::fs::read_dir(&root).expect("modules root is readable").flatten() {
        let dir = entry.path();
        if !dir.join("module.json").is_file() {
            continue;
        }
        let module = dir.file_name().unwrap_or_default().to_string_lossy().to_string();
        // Un manifest que no parsea es asunto de otro test, no de este.
        let Ok(manifest) = Manifest::load(&dir) else {
            continue;
        };
        modules += 1;

        for (file, kind) in declared_migrations(&dir, &manifest) {
            let Ok(sql) = std::fs::read_to_string(dir.join(&file)) else {
                continue; // Declarada y no presente: se queja el instalador, no esta red.
            };
            check(&manifest.id, &file, &sql, kind).unwrap_or_else(|e| {
                panic!(
                    "🔴 `{module}/{file}` ({kind:?}) está PUBLICADO y el guard lo rechaza: {e}\n\
                     Una regla nueva no puede poner en rojo lo que la flota ya tiene instalado. \
                     Si la regla es correcta, el que cambia es el módulo — y antes de mergear."
                )
            });
            migrations += 1;
        }
    }

    // 🔴 Cinturón 1: sin esto, un `modules_root` mal resuelto recorrería cero ficheros y el test
    // saldría verde sin haber mirado nada. Los umbrales van por debajo de lo medido (27 repos,
    // 155 migraciones el 2026-08-26) para que publicar no ponga esto en rojo por crecer.
    assert!(
        modules >= 20 && migrations >= 100,
        "el catálogo publicado son ~27 módulos y ~155 migraciones; solo se vieron {modules} \
         módulos y {migrations} migraciones en {} — esta red no estaba midiendo nada",
        root.display()
    );
}

/// 🔴 **Cinturón 2: la puerta rechaza el positivo.** Un guard que no valida su payload no deniega:
/// queda ABIERTO y aparenta funcionar. Si `check` empezara a devolver `Ok` siempre —o si la regla
/// de hub#1149 se cayera en un refactor—, el test de arriba seguiría verde mientras la puerta está
/// abierta de par en par. Estos tres casos son los que NO pueden pasar, por la misma puerta y con
/// las mismas formas que usa el catálogo.
#[test]
fn the_same_door_still_refuses_what_it_must() {
    let must_be_refused = [
        // hub#1149: el borrado escondido en un cuerpo que el lint no puede leer.
        ("sales", "DO $$\nBEGIN\n  DELETE FROM sales_line WHERE legacy = 'yes';\nEND\n$$", Kind::Expand),
        ("sales", "DO $limpia$ BEGIN EXECUTE 'DROP TABLE sales_line'; END $limpia$", Kind::Backfill),
        // hub#542/#1109: la tabla de otro módulo sigue sin tocarse, upsert o no.
        (
            "taxes",
            "INSERT INTO sales_sale (id) VALUES (1) ON CONFLICT (id) DO UPDATE SET id = EXCLUDED.id",
            Kind::Backfill,
        ),
        // hub#1145: un `contract` no destruye filas.
        ("sales", "TRUNCATE sales_line", Kind::Contract),
    ];

    for (module_id, sql, kind) in must_be_refused {
        let refused = check(module_id, "migrations/postgres/099_probe.sql", sql, kind);
        assert!(
            refused.is_err(),
            "🔴 la puerta dejó pasar lo que no puede pasar ({kind:?}): {sql}"
        );
    }
}
