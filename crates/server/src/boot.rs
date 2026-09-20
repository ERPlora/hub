//! Composition root: serve() wires config, DB, native plugins and background services — split out of `lib.rs` verbatim (hub#1404).

use crate::*;

/// Trae la clave pública RSA del Cloud (`GET /api/v1/auth/public-key/`) para verificar los JWT de
/// usuario offline. `None` si el Cloud no responde o no la trae.
pub(crate) async fn fetch_jwt_public_key(cloud_base_url: &str) -> Option<String> {
    let url = format!(
        "{}/api/v1/auth/public-key/",
        cloud_base_url.trim_end_matches('/')
    );
    // Timeout ACOTADO: esta llamada corre ANTES de bindear el listener en `serve()`. Sin límite, una
    // red hostil (captive portal / DNS lento / host inalcanzable) retrasaría el arranque del servidor
    // mucho más que el `wait_for_runtime` del shell Tauri → la ventana cargaría un loopback que aún no
    // escucha (ADR-0050). El login cloud degrada a "no disponible" si no llega; el PIN no la necesita.
    let client = match reqwest::Client::builder()
        .connect_timeout(std::time::Duration::from_secs(3))
        .timeout(std::time::Duration::from_secs(5))
        .build()
    {
        Ok(c) => c,
        Err(_) => return None,
    };
    let resp = client.get(&url).send().await.ok()?;
    if !resp.status().is_success() {
        return None;
    }
    let v: Value = resp.json().await.ok()?;
    v.get("public_key")
        .and_then(|k| k.as_str())
        .filter(|s| !s.is_empty())
        .map(|s| s.to_string())
}

/// Resuelve el SQL de seed de configuración inicial desde el entorno (hub#36):
///  - `HUB_SEED_SQL` — SQL inline (gana si está presente y no vacío). Lo usa ECS/terraform.
///  - `HUB_SEED_SQL_PATH` — ruta a un fichero `.sql` (alternativa para local/dev).
///
/// `Ok(None)` si no se configura ninguno (arranque normal sin seed). Un `HUB_SEED_SQL_PATH` que
/// no se puede leer es un error de configuración → aborta el arranque con un mensaje claro.
pub(crate) fn load_seed_sql() -> Result<Option<String>, Box<dyn std::error::Error>> {
    if let Some(sql) = std::env::var("HUB_SEED_SQL")
        .ok()
        .filter(|s| !s.trim().is_empty())
    {
        return Ok(Some(sql));
    }
    if let Some(path) = std::env::var("HUB_SEED_SQL_PATH")
        .ok()
        .filter(|s| !s.trim().is_empty())
    {
        let sql = std::fs::read_to_string(&path)
            .map_err(|e| format!("HUB_SEED_SQL_PATH={path}: no se pudo leer el seed: {e}"))?;
        return Ok(Some(sql));
    }
    Ok(None)
}

/// Arranca el runtime completo y **sirve Axum** en `cfg.bind` hasta que termina. Punto de entrada
/// único del binario y del shell Tauri (in-process, §11): abre SQLite, instala los módulos del dir
/// si se indica, resuelve la clave pública del Cloud si falta, monta el [`AppState`], lanza el
/// **relay del outbox** (poll 1s + backoff, §5.4) y sirve. La credencial de máquina viaja en
/// `cfg.hub.cloud_api_token` (Tauri la inyecta desde el keychain; ECS desde el env).
pub async fn serve(mut cfg: ServeConfig) -> Result<(), Box<dyn std::error::Error>> {
    use erplora_runtime::Runtime;

    // Logging del hub → consola + `media/_logs/` (rotación diaria, retención 6 meses, ADR-0047).
    // Se monta lo primero para capturar el arranque. El guard se mantiene vivo toda la función
    // (al soltarlo se pierden los logs en cola del appender no-bloqueante).
    let _log_guard = logging::init(&cfg.hub.media_dir);

    // hub#1279 — a dev/bench process (`HUB_DEV_MODE=1`) with no explicit `HUB_CLOUD_API_URL`
    // silently inherits the PRODUCTION default (see `HubConfig::from_env_with_auth`). A deployed
    // hub never hits this — provisioning always injects the var — so this only ever fires for a
    // process started outside it: a Playwright bench, a CI job, `pnpm dev`. `pnpm dev` keeps
    // pointing at production on purpose (`/hub-local`), so only `CI` — nobody at the terminal to
    // read a warning — turns this into a hard refusal. Checked before the DSN below: it needs
    // neither Postgres nor the log guard's side effects, just the cheapest fail-fast available.
    match state::cloud_url_guard(
        cfg.hub.dev_mode,
        &cfg.hub.cloud_base_url,
        std::env::var_os("CI").is_some(),
    ) {
        state::CloudUrlGuard::Ok => {}
        state::CloudUrlGuard::Warn => eprintln!(
            "cloud: HUB_CLOUD_API_URL not set → defaulting to {} (PRODUCTION). HUB_DEV_MODE=1, so \
             this runtime keeps starting, but a dev/bench process with no explicit \
             HUB_CLOUD_API_URL talks to production by default (hub#1279) — set it explicitly.",
            state::PRODUCTION_CLOUD_BASE_URL,
        ),
        state::CloudUrlGuard::Refuse => {
            return Err(format!(
                "HUB_CLOUD_API_URL is not set and HUB_DEV_MODE=1 while running in CI (CI is \
                 set): a CI dev/bench run must never default to {} (PRODUCTION, hub#1279). Set \
                 HUB_CLOUD_API_URL explicitly (e.g. a closed loopback address).",
                state::PRODUCTION_CLOUD_BASE_URL,
            )
            .into());
        }
    }

    // Backend de datos: **Postgres-only** (ADR-0154). `HUB_DATABASE_URL` es obligatoria — sin ella
    // el arranque falla con un error claro (fail-fast). El Cloud lo inyecta en forma SQLAlchemy
    // (`postgresql+asyncpg://…`); sqlx quiere `postgresql://…` → se normaliza (`normalize_pg_dsn`).
    let dsn = normalize_pg_dsn(cfg.database_url.trim());
    if dsn.is_empty() {
        return Err(
            "HUB_DATABASE_URL es obligatoria (Hub Cloud es Postgres-only, ADR-0154): \
                    define el DSN Postgres del hub"
                .into(),
        );
    }
    eprintln!("db: backend Postgres vía HUB_DATABASE_URL");
    let db: Box<dyn erplora_db::DatabaseAdapter> =
        Box::new(erplora_db::PgAdapter::connect(&dsn).await?);
    // Identidad viva: en Cloud nace del deployment; en el primer arranque Tauri la aporta el
    // shell y puede pasar del placeholder al UUID registrado sin reiniciar.
    let hub_id_cell = cfg
        .hub_id_cell
        .take()
        .unwrap_or_else(|| std::sync::Arc::new(std::sync::RwLock::new(cfg.hub.hub_id.clone())));
    if let Ok(hub_id) = hub_id_cell.read() {
        cfg.hub.hub_id = hub_id.clone();
    }

    // El runtime se construye con el `hub_id` del despliegue (config, no spoofable): scope del
    // estado de módulos (`hub_module`) y de las migraciones de sistema (hub#31 / hub#37).
    let mut runtime = Runtime::with_hub_id(db, cfg.hub.hub_id.clone());

    // DEMO efímera (ADR-0197, hub#376): se sella ya, antes incluso de instalar módulos o aplicar
    // migraciones, para que los cierres estén puestos durante TODO el arranque. `AppState` vuelve a
    // sellarlo (mismo valor, idempotente) porque su constructor es el embudo de todos los hosts.
    runtime.set_demo_hub(cfg.hub.demo);
    if cfg.hub.demo {
        eprintln!(
            "demo: hub efímero (ADR-0197) — entorno fiscal clavado a `testing`, certificado \
             propio e identidad fiscal cerrados"
        );
    }

    // El mismo backend de ficheros sirve a TODOS los módulos, con el mismo contrato lógico
    // (`media/modules/<folder>/`). Se inyecta antes de instalar para que cada manifest con
    // `static_files.folder` materialice su carpeta al activarse.
    let machine_token_cell = cfg.machine_token_cell.take().unwrap_or_else(|| {
        std::sync::Arc::new(std::sync::RwLock::new(cfg.hub.cloud_api_token.clone()))
    });
    // Cuál de los dos lo decide `backend_for`, con el MISMO interruptor que decide si se escanea
    // `HUB_MODULES_DIR` (más abajo): si el hub instala módulos de disco, sus ficheros también van a
    // disco. Este comentario prometía el backend de disco desde el principio y no existía
    // (hub#1477) — y como `verifactu` es el único módulo del catálogo con `static_files`, era el
    // único que no se podía instalar sin Cloud.
    let module_storage: std::sync::Arc<dyn erplora_runtime::module_storage::ModuleStorage> =
        match module_storage::backend_for(cfg.hub.dev_mode) {
            module_storage::Backend::Disk => {
                let media_dir = state::media_dir_from_env();
                eprintln!(
                    "módulos: ficheros de `static_files` en disco ({}/modules) — modo desarrollo",
                    media_dir.display()
                );
                std::sync::Arc::new(module_storage::ModuleDiskStorage::new(media_dir))
            }
            // Producción: proxy autenticado Hub→Cloud→Object Storage (ADR-0154), sin credenciales
            // de almacenamiento en el Hub. Sin token de máquina falla, y debe fallar: un hub real
            // sin token tiene un problema de despliegue que caer a disco solo taparía.
            module_storage::Backend::Cloud => {
                std::sync::Arc::new(module_storage::ModuleMediaStorage::cloud(
                    cfg.hub.cloud_base_url.clone(),
                    cfg.hub.hub_id.clone(),
                    machine_token_cell.clone(),
                ))
            }
        };
    runtime.set_module_storage(module_storage);

    // Plugins nativos first-party (ADR-0009): motores compliance-crítico horneados en el
    // runtime. Hoy solo `verifactu` (cadena fiscal + transmisión AEAT TLS-mutua).
    runtime.register_native(
        "verifactu",
        std::sync::Arc::new(erplora_verifactu::VerifactuEngine),
    );

    // Escaneo de `HUB_MODULES_DIR` al arrancar: SOLO en modo desarrollo explícito (hub#239). En
    // producción ese dir es `/tmp/modules` (contenedor stateless) y se instalaba todo subdirectorio
    // con un `module.json` sin verificar nada — un dir escribible convertido en cargador de código.
    // Los módulos de un hub real vienen del marketplace (grant + SHA256, ADR-0015).
    match install_guard::boot_scan_dir(cfg.hub.dev_mode, cfg.modules_dir.as_deref()) {
        Some(dir) => {
            // Instala los módulos del dir resolviendo el orden de `depends_on` por topo-sort (hub#16):
            // una dependencia se instala antes que quien la declara, sin depender del orden del FS.
            // `install_all_from_dir` es tolerante (loguea ✓/✗ por módulo y salta los rotos); aquí solo
            // registramos un error externo (read_dir fallido o ciclo de dependencias del conjunto).
            eprintln!("dev: instalando módulos de HUB_MODULES_DIR={dir} (modo desarrollo)");
            if let Err(e) = runtime
                .install_all_from_dir(std::path::Path::new(dir))
                .await
            {
                eprintln!("✗ instalación de módulos: {e}");
            }
        }
        None => {
            if let Some(ignored) = &cfg.modules_dir {
                eprintln!(
                    "módulos: HUB_MODULES_DIR={ignored} IGNORADO (sin HUB_DEV_MODE): en producción \
                     los módulos se instalan desde el marketplace, con SHA256 verificado"
                );
            }
        }
    }

    // En `HUB_AUTH=session` el login cloud necesita la clave pública RSA del Cloud; el PIN no. Si no
    // se logra traer, se arranca igual (login cloud quedará no disponible).
    if cfg.hub.auth_mode == AuthMode::Session && cfg.hub.jwt_public_key.is_none() {
        cfg.hub.jwt_public_key = fetch_jwt_public_key(&cfg.hub.cloud_base_url).await;
        if cfg.hub.jwt_public_key.is_none() {
            eprintln!("auth: sin clave pública del Cloud → login cloud no disponible (PIN sí)");
        }
    }
    eprintln!("auth: modo {:?}", cfg.hub.auth_mode);

    // **Y en qué modo de firma se ha quedado este hub** (hub#1754). Una línea, siempre, tenga
    // módulos o no: INFO si verifica, WARN si no hay anillo desplegado, ERROR si la variable viene
    // puesta y no parsea (hub#870). Antes solo se sabía como efecto lateral de instalar algo, así
    // que el hub recién aprovisionado —el que acaba de estrenar la clave— arrancaba callado y el
    // fallo aparecía después, en otra persona, como una instalación que no pasaba.
    //
    // 🔑 Va AQUÍ, en el resumen de configuración del arranque y ANTES de que nada instale: si el
    // anillo está roto, la causa se lee por encima de sus consecuencias, no por debajo.
    cfg.hub.announce_signature_policy();

    // Índice vectorial del asistente (§9.2b routing + §9.6 ingestión) — Postgres + pgvector
    // (hub#204 / pm#29). Con los 24 módulos instalados el catálogo de tools que viaja en CADA
    // turno son ~58k tokens; el router lo recorta a los módulos relevantes, y para eso necesita
    // este índice.
    //
    // **Nunca aborta el arranque.** Si pgvector no está disponible en esta BD (la imagen no lo
    // trae, o el rol del hub no puede crear la extensión — ADR-0201 da a cada hub su BD y su rol),
    // se queda en `None` y el asistente degrada a ofrecer todos los tools (§9.5), que es
    // exactamente lo que hacía antes. Más caro de prompt, nunca roto. Lo que el asistente SABE del
    // hub no depende de esto: el mapa de módulos va en el system prompt
    // (`assistant::build_instructions`). Los embeddings siguen saliendo por el Cloud (§9.3).
    let vector_store: Option<state::SharedVectorStore> = match erplora_db::PgAdapter::connect(&dsn)
        .await
    {
        Ok(vdb) => {
            let store = erplora_vector::PgVectorStore::new(
                std::sync::Arc::new(vdb),
                erplora_vector::DEFAULT_DIMS,
            );
            match erplora_vector::VectorStore::ensure_schema(&store).await {
                Ok(()) => {
                    eprintln!("asistente: índice vectorial pgvector listo (router §9.2b activo)");
                    Some(std::sync::Arc::new(store) as state::SharedVectorStore)
                }
                Err(e) => {
                    eprintln!(
                        "asistente: sin índice vectorial ({e}); se ofrecen TODOS los tools (§9.5). \
                         Instala pgvector en esta BD para abaratar el prompt."
                    );
                    None
                }
            }
        }
        Err(e) => {
            eprintln!(
                "asistente: sin índice vectorial (pool: {e}); se ofrecen todos los tools (§9.5)"
            );
            None
        }
    };

    // Celda del token de máquina: externa (compartida con el shell Tauri para hot-reload) o propia.
    let mut state = AppState::with_config_cells(runtime, cfg.hub, machine_token_cell, hub_id_cell);
    if let Some(vs) = vector_store {
        state = state.with_vector(vs);
    }
    // Tablas de sistema del runtime (outbox + scheduler) — para el caso de hub vacío sin módulos.
    state.runtime.read().await.ensure_system_tables().await?;

    // Marca de actividad de usuario (hub#670): se ADOPTA la que dejó el proceso anterior, y a
    // partir de aquí se escribe sola cada `HUB_ACTIVITY_PERSIST_SECS`.
    //
    // Va justo después de las migraciones (su tabla nace en la v39) y ANTES de que arranquen el
    // latido y el router: el latido manda `pending()` en su PRIMER tick, y sin la marca adoptada
    // ese tick diría «aquí no ha entrado nadie» de un hub que sí se usa. Perderla no es cosmético
    // — es el reloj con el que el Cloud apaga (60d) y BORRA (120d) un hub free, y borrar no se
    // deshace. Ambas llamadas son best-effort: un hub cuya marca no se pueda leer o escribir tiene
    // que arrancar igual, con el reloj empezado de nuevo, nunca quedarse sin arrancar.
    activity::restore_from_db(&state).await;
    activity::spawn_persistence(&state);

    // **¿Nos han cambiado el binario?** (hub#564, ADR-0269 §3.5). Nadie se lo dice al hub: la imagen
    // se re-resuelve FUERA del contenedor, la task se sustituye, y el binario nuevo arranca
    // reportando otro número. Compararlo con el último que anotamos es todo el mecanismo — y es
    // también lo que hace VISIBLE un rollback automático, porque Swarm revirtiendo un despliegue
    // malo, visto desde aquí dentro, es exactamente una versión que baja.
    //
    // Va justo detrás de `ensure_system_tables` porque necesita su tabla (v40) y nada más: cuanto
    // más tarde se anote, más ventana hay de que el arranque se caiga antes y el salto se pierda.
    // Best-effort: no poder escribir el historial nunca impide abrir la tienda.
    {
        let rt = state.runtime.read().await;
        match erplora_runtime::update_history::note_core_version(
            rt.db(),
            &state.hub_id(),
            version::HUB_VERSION,
        )
        .await
        {
            Ok(Some(entry)) => eprintln!(
                "✓ versión del core: {} → {} ({})",
                entry.from_version, entry.to_version, entry.outcome
            ),
            Ok(None) => {}
            Err(e) => eprintln!("✗ no se pudo anotar la versión del core (hub#564): {e}"),
        }
    }

    // **Owner sembrado del env** (ADR-0157, corrección de Ioan): el owner es el CREADOR del hub y el
    // despliegue lo trae ya inyectado por el provisioning del SaaS como `HUB_OWNER_EMAIL`. Se siembra
    // un `hub_user` role=admin (cloud_user_id NULL, sin PIN) tras las tablas de sistema —`admin` es
    // lo más alto del plano de NEGOCIO desde hub#349; la PROPIEDAD sigue siendo del plano de la
    // cuenta—; en su primer login `auth_cloud` lo enlaza por email. **Idempotente** (no duplica ni
    // pisa un rol existente),
    // así que es seguro en cada arranque. Sin el env (dev/local) es un no-op silencioso. Sustituye al
    // bootstrap «primer login = owner» (retirado): el owner ya no depende de quién entre primero.
    if let Some(owner_email) = std::env::var("HUB_OWNER_EMAIL")
        .ok()
        .map(|s| s.trim().to_string())
        .filter(|s| !s.is_empty())
    {
        match state.runtime.read().await.seed_owner(&owner_email).await {
            Ok(true) => eprintln!("auth: owner sembrado del env (HUB_OWNER_EMAIL={owner_email})"),
            Ok(false) => {} // ya existía: idempotente.
            Err(e) => eprintln!("✗ seed del owner (HUB_OWNER_EMAIL={owner_email}): {e}"),
        }
    }

    // Re-hidrata el Registry tras un reinicio: re-registra los módulos ya instalados de este hub
    // desde la caché de descargas (`module_cache/<id>/<version>/`). Sin esto, un runtime con
    // `modules_dir: None` (el caso descarga-desde-marketplace, p. ej. el shell Tauri) arrancaría
    // con el Registry vacío aunque `hub_module` + las tablas del módulo persistan → el módulo
    // "desaparecería" del runtime al reiniciar (no expondría queries/commands/nav). Tolerante.
    {
        let cache_root = state.config.module_cache.clone();
        match state
            .runtime
            .write()
            .await
            .rehydrate_installed(&cache_root)
            .await
        {
            Ok(ids) if !ids.is_empty() => eprintln!("módulos re-hidratados: {}", ids.join(", ")),
            Ok(_) => {}
            Err(e) => eprintln!("✗ re-hidratación de módulos: {e}"),
        }
    }

    // Auto-curación del contrato STATELESS (Hub Cloud): el `module_cache` es efímero (`/tmp`) y se
    // vacía en cada redeploy/reschedule, así que `rehydrate_installed` no encuentra las carpetas y
    // los módulos que `hub_module` marca instalados quedan SIN registrar → "desaparecen" del runtime.
    // El diseño stateless (reschedulable, sin volumen) implica **re-descargarlos del marketplace**:
    // el hub se auto-cura re-bajando esos módulos con su token de máquina. Best-effort — un módulo
    // que no se pueda re-bajar (red/entitlement) se omite con log, no aborta el arranque.
    // `install_from_cloud` resuelve `depends_on` en orden (nested install).
    {
        let missing = state
            .runtime
            .read()
            .await
            .installed_but_unregistered()
            .await
            .unwrap_or_default();
        if !missing.is_empty() {
            match auth::machine_auth(&state) {
                Some(machine) => {
                    let cache_root = state.config.module_cache.clone();
                    let cloud = state.config.cloud_base_url.clone();
                    eprintln!("cache vacío: re-descargando {} módulo(s) instalados del marketplace…", missing.len());
                    // Pins de soporte de este hub (hub#516): `module_id → pinned_version`.
                    let pins: std::collections::HashMap<String, String> = {
                        let rt = state.runtime.read().await;
                        erplora_runtime::installer::installed_with_pin(rt.db(), &state.hub_id())
                            .await
                            .unwrap_or_default()
                            .into_iter()
                            .filter_map(|(id, _, pin)| pin.map(|p| (id, p)))
                            .collect()
                    };

                    for (id, version) in missing {
                        // 🔄 Los módulos se actualizan SOLOS (hub#516): se resuelve la ÚLTIMA versión
                        // instalable, no la registrada. Es lo único que faltaba — la re-descarga del
                        // arranque ya existía porque el `module_cache` es `/tmp`.
                        //
                        // Seguro porque hub#542 valida el SQL de la migración y traduce sus `DROP` a
                        // rename, hub#517 garantiza que no hay nada que deshacer al revertir, y
                        // hub#538 deja `/readyz` en DOWN si el módulo no carga — así Swarm revierte
                        // el despliegue en vez de dejar el hub «sano» con el TPV roto.
                        let target = resolve_module_target(&state, &machine, &id, &version, pins.get(&id).map(String::as_str)).await;

                        let mut rt = state.runtime.write().await;
                        // El nombre que lee el dueño, capturado ANTES de tocar nada (hub#564): si el
                        // intento pierde el módulo, el registry ya no lo tiene y la entrada del
                        // historial se quedaría con el id — que es justo lo que la regla 3 prohíbe.
                        let module_name = rt
                            .registry()
                            .installed
                            .iter()
                            .find(|m| m.id == id)
                            .map(|m| m.name.clone())
                            .unwrap_or_else(|| id.clone());
                        // Progreso no-op: en el arranque aún no hay clientes WS a los que retransmitir.
                        let attempt = match install::install_from_cloud(&state.http, &cloud, &cache_root, &machine, &mut rt, &id, target.version(), &|_, _| {}, &state.config.signature_policy()).await {
                            Ok(_) if target.is_update() => {
                                eprintln!("✓ módulo actualizado: {id} {version} → {}", target.version());
                                Some(erplora_runtime::module_update::Outcome::Updated { from: version.clone(), to: target.version().to_string() })
                            }
                            Ok(_) => { eprintln!("✓ módulo re-descargado: {id}@{}", target.version()); None }
                            Err(e) if target.is_update() => {
                                // ⚠️ Una actualización que falla NO puede dejar al hub SIN el módulo:
                                // un hub con la versión de ayer funciona, uno sin el módulo no. Se
                                // cae a la que tenía registrada.
                                eprintln!("✗ actualización de {id} a {}: {e} — vuelvo a {version}", target.version());
                                let fallback = install::install_from_cloud(&state.http, &cloud, &cache_root, &machine, &mut rt, &id, &version, &|_, _| {}, &state.config.signature_policy()).await;
                                match &fallback {
                                    Ok(_) => eprintln!("✓ {id} sigue en {version}"),
                                    Err(e) => eprintln!("✗ {id}@{version} tampoco: {e}"),
                                }
                                // Y no puede ser un silencio (update-model §3.1.1): si actualizamos
                                // solos, una actualización que se cae —y más aún un hub que arranca
                                // SIN el módulo— tiene que llegar a alguien, no morir en un log del
                                // contenedor. Best-effort: sin sink (hub sin enrolar) se descarta.
                                report_failed_module_update(&id, &version, target.version(), &e.to_string(), fallback.is_ok());
                                Some(match &fallback {
                                    Ok(_) => erplora_runtime::module_update::Outcome::RolledBack { stayed_on: version.clone(), error: e.to_string() },
                                    Err(fe) => erplora_runtime::module_update::Outcome::Lost { module: id.clone(), error: format!("{e}; la vuelta atrás tampoco: {fe}") },
                                })
                            }
                            Err(e) => { eprintln!("✗ re-descarga de {id}@{version}: {e}"); None }
                        };

                        // Y tampoco puede ser un silencio PARA EL DUEÑO (hub#564): el `error_sink`
                        // de arriba nos avisa a NOSOTROS, pero quien se encuentra la caja distinta
                        // por la mañana es quien abre la tienda. La misma decisión que usa el botón
                        // —`from_module_outcome`— para que las dos puertas no cuenten lo mismo de
                        // dos maneras. Best-effort: el historial nunca impide arrancar.
                        if let Some(attempt) = attempt {
                            if let Some(change) = erplora_runtime::update_history::from_module_outcome(&id, &module_name, target.version(), &attempt) {
                                if let Err(e) = erplora_runtime::update_history::record(rt.db(), &state.hub_id(), change).await {
                                    eprintln!("✗ no se pudo anotar el historial de {id} (hub#564): {e}");
                                }
                            }
                        }
                    }
                }
                None => eprintln!(
                    "⚠ {} módulo(s) instalados sin caché y hub sin enrolar (sin token de máquina): no se re-descargan",
                    missing.len()
                ),
            }

            // 🛟 **Y si el marketplace no dio, la copia PROPIA del hub** (hub#571). Todo lo de
            // arriba depende del SaaS: un reinicio con el Cloud caído, un DNS torcido o el router
            // del cliente apagado dejaban al hub arrancando SIN un solo módulo — `/readyz` en DOWN,
            // Swarm recreando el contenedor en bucle y el bar sin TPV. Este es el único camino que
            // no pasa por la red: los bytes se guardaron en la base del propio hub al instalar y se
            // vuelven a verificar aquí igual que una descarga (SHA256 + firma según la política).
            //
            // Va DESPUÉS y no antes a propósito: la vía del marketplace es también la de la
            // actualización automática (hub#516/ADR-0269), y adelantarla convertiría cada arranque
            // en «quédate donde estás». Primero se intenta llegar a lo que toca; esto es la red que
            // impide caer por debajo de lo que ya se tenía.
            let still_missing = state
                .runtime
                .read()
                .await
                .installed_but_unregistered()
                .await
                .unwrap_or_default();
            if !still_missing.is_empty() {
                eprintln!(
                    "marketplace inalcanzable para {} módulo(s): reponiendo de la copia local…",
                    still_missing.len()
                );
                let cache_root = state.config.module_cache.clone();
                let policy = state.config.signature_policy();
                let orphans = {
                    let mut rt = state.runtime.write().await;
                    install::restore_from_local_packages(
                        &cache_root,
                        &mut rt,
                        &still_missing,
                        &policy,
                    )
                    .await;
                    rt.installed_but_unregistered().await.unwrap_or_default()
                };
                // Ni copia, ni marketplace, ni tarea vieja a la que volver: aquí la regla «nunca con
                // menos» no se puede cumplir, porque no hay ninguna alternativa que la cumpla. Lo
                // que NO puede pasar es que sea un silencio — un hub que arranca incompleto tiene
                // que llegar a alguien, no morir en el log de un contenedor.
                if !orphans.is_empty() {
                    report_incomplete_boot(&orphans);
                }
            }
        }
    }

    // Backfill del índice vectorial (§9.6): la ingesta normal corre en el hook de INSTALL, que ya
    // pasó para todo hub existente — sin esto, su índice quedaría vacío para siempre y el router
    // (§9.2b) nunca se activaría. Solo embebe la DIFERENCIA (módulos activos aún no indexados):
    // los embeddings son llamadas metered al Cloud (§9.3), así que reiniciar no cuesta nada.
    // En tarea de fondo: el arranque no espera a la red, y un fallo aquí no toca el arranque.
    if let (Some(store), Some(machine)) = (state.vector.clone(), auth::machine_auth(&state)) {
        let runtime = state.runtime.clone();
        let http = state.http.clone();
        let cloud = state.config.cloud_base_url.clone();
        let hub_id = state.hub_id();
        tokio::spawn(async move {
            let embedder = embed::CloudEmbedder::new(http, &cloud, machine);
            let rt = runtime.read().await;
            let (modules, chunks) =
                embed::backfill_index(&embedder, store.as_ref(), rt.registry(), &hub_id).await;
            if modules > 0 {
                tracing::info!(modules, chunks, "índice vectorial backfilleado (§9.6)");
            }
        });
    }

    // Seed de configuración inicial (hub#36): SQL idempotente que se aplica UNA vez al arrancar,
    // tras las tablas de sistema. Mecanismo genérico (NO "modo demo"): el host lo pasa por env —
    // `HUB_SEED_SQL` (SQL inline, p. ej. el del despliegue demo) o `HUB_SEED_SQL_PATH` (fichero).
    // Si ambos están, gana el inline. La idempotencia la garantiza el propio SQL (`WHERE NOT
    // EXISTS`/`ON CONFLICT`). Un seed roto aborta el arranque (error claro), no se traga en silencio.
    if let Some(seed_sql) = load_seed_sql()? {
        let n = state.runtime.read().await.apply_seed(&seed_sql).await?;
        eprintln!("seed: aplicadas {n} sentencia(s) de configuración inicial");
    }

    // **El PAÍS que el SaaS acuñó al aprovisionar** (`HUB_COUNTRY`, ADR-0207 — hub#69). Va AQUÍ,
    // después del seed SQL (que también puede escribir `country_code`, y quien lo escribe manda
    // sobre un default) y ANTES del perfil fiscal, que deriva el régimen del país: sembrarlo
    // después dejaría el perfil calculado sobre el país equivocado hasta el siguiente arranque.
    //
    // Se lee del entorno aquí y no en `HubConfig` por lo mismo que `HUB_SEED_SQL` o
    // `HUB_OWNER_EMAIL`: es una entrada de ARRANQUE que se consume una vez y no vuelve a hacer
    // falta — a partir de este punto la autoridad es `hub_settings.country_code`, que es lo único
    // que leen el motor de impuestos, la checklist y el filtro del marketplace.
    //
    // NUNCA pisa una respuesta que el hub ya tenga: el env es la SUGERENCIA del alta («corregible»,
    // ADR-0207), y quien la corrigió en Ajustes manda sobre ella.
    match state
        .runtime
        .read()
        .await
        .ensure_provisioned_country(&std::env::var("HUB_COUNTRY").unwrap_or_default())
        .await
    {
        Ok(true) => eprintln!("país: `country_code` sembrado desde HUB_COUNTRY (ADR-0207)"),
        Ok(false) => {}
        // No aborta el arranque: un hub que no abre es peor que un hub con el país por defecto.
        Err(e) => eprintln!("✗ país: no se pudo sembrar el país del aprovisionamiento: {e}"),
    }

    // **La DEMO arranca con su identidad fiscal ya puesta** (hub#684). Va AQUÍ, después del seed
    // (que escribe el `country_code`) y ANTES del perfil fiscal, que es quien deriva `READY` de
    // «identidad ∧ certificado»: sembrarla después dejaría el perfil calculado sobre un hub sin
    // identidad hasta el siguiente arranque.
    //
    // Es el CORE escribiendo el marcador de posición de la demo, no una puerta: los tres cierres de
    // ADR-0197 §4 siguen intactos — el visitante no puede CAMBIAR el NIF, ni subir un certificado
    // `own`, ni salir de `testing`. Lo que se arregla es que la checklist le pedía justo el dato
    // que el producto le prohibía escribir, y que su venta se cobraba sin llegar a emitir factura
    // (`invoice.create_from_sale` estampa `:business_tax_id` y el gate de ADR-0203 la rechazaba).
    match state
        .runtime
        .read()
        .await
        .ensure_demo_fiscal_identity()
        .await
    {
        Ok(true) => eprintln!("demo: identidad fiscal de la demo sembrada (hub#684)"),
        Ok(false) => {}
        // No aborta el arranque: un hub que no abre es peor que una demo con la checklist a medias.
        Err(e) => eprintln!("✗ demo: no se pudo sembrar la identidad fiscal de la demo: {e}"),
    }

    // **Perfil fiscal** (ADR-0273 D2/D4, hub#550): qué debe este hub, resuelto contra lo que hay
    // montado de verdad. Va AQUÍ y no junto a `ensure_system_tables` por dos razones que son la
    // misma: el registry ya está re-hidratado (así se sabe si queda algún proveedor del régimen) y
    // el seed ya escribió el `country_code` (así se sabe qué régimen es). Antes de este punto las
    // dos mitades de la respuesta no existen.
    //
    // **No aborta el arranque.** Un hub que no abre es una tienda que no cobra; y como `BLOCKED` es
    // DERIVADO, no hay nada que se quede mal escrito por no haber corrido: la siguiente lectura lo
    // vuelve a calcular. Aquí nada rechaza todavía (eso es hub#556).
    {
        let rt = state.runtime.read().await;
        match rt.refresh_fiscal_profile().await {
            Ok(mode) => eprintln!("fiscal: perfil del hub resuelto → {mode:?}"),
            Err(e) => eprintln!("✗ fiscal: no se pudo resolver el perfil del hub (ADR-0273): {e}"),
        }
    }

    // Transporte de `host.notify` (ADR-0012 + ADR-0283 §5 K4, hub#663): el cliente REAL. Email y
    // WhatsApp salen por el **proxy del SaaS** (`/api/v1/hub/device/notify/{email,whatsapp}/`) con
    // la credencial de máquina; el hub nunca guarda credenciales de Meta/SES (patrón del LLM).
    //
    // El mock sigue disponible, pero **hay que pedirlo por su nombre** (`HUB_NOTIFY_TRANSPORT=mock`)
    // y no se cae en él por accidente: un mock devuelve `Sent` sin enviar nada, y el outbox marca
    // entonces el evento como entregado — un recordatorio que nunca salió y del que nadie se entera.
    // Un hub sin enrolar falla RUIDOSAMENTE (reintento → dead-letter), que sí se ve.
    state
        .runtime
        .write()
        .await
        .set_notify_transport(notify_transport::build(
            state.http.clone(),
            &state.config.cloud_base_url,
            state.hub_id.clone(),
            state.machine_token.clone(),
            std::env::var(notify_transport::TRANSPORT_ENV).ok(),
        ));

    // Registro GLOBAL de errores ("todo controlado", un único embudo): instala el sink que reenvía
    // al Cloud (`POST /api/v1/hub/device/error-report/`, X-Hub-Token) cada error del runtime
    // (core + módulos), del panic hook y de la ruta local del frontend. Best-effort (spawn detached);
    // si el hub no está enrolado el sink descarta en silencio. Se hace una sola vez al arrancar.
    install_error_reporting(&state);

    // Catch-up del scheduler al arrancar (ADR-0011): un hub que estuvo apagado ejecuta UNA sola
    // vez las tareas con backlog vencido (collapse) y reprograma el resto. Se hace antes del loop.
    {
        let hub_id = state.hub_id();
        let rt = state.runtime.read().await;
        match rt.scheduler_catch_up(&hub_id).await {
            Ok(n) if n > 0 => eprintln!("scheduler: catch-up de arranque ejecutó {n} tarea(s)"),
            Ok(_) => {}
            Err(e) => eprintln!("scheduler catch-up: {e}"),
        }
    }

    // Bucle de background: relay de eventos del outbox (§5.4) + barrido del scheduler (ADR-0011).
    // Ambos comparten el mismo tick de 1s y el mismo guard de LECTURA del runtime (hub#978): un
    // tick que drena backlog ya no congela las cajas, porque los commands entran con su propio
    // guard compartido; lo único que espera a que el tick acabe es un escritor (instalar/activar).
    {
        let scheduler_state = state.clone();
        tokio::spawn(async move {
            loop {
                // I/O que el tick de flujos deja preparada (hub#662). Se recoge DENTRO del bloque
                // con lock y se despacha FUERA: el `dispatch` no debe tocar el lock que acabamos de
                // soltar, y el bucle de 1 s no puede esperar a una llamada de 30 s.
                let mut pending_io = Vec::new();
                {
                    let hub_id = scheduler_state.hub_id();
                    let rt = scheduler_state.runtime.read().await;
                    // Entrega at-least-once asíncrona del outbox a sus listeners (+ listener-host
                    // de host.notify para los eventos `*.reminder.due`).
                    if let Err(e) = rt.process_outbox().await {
                        eprintln!("relay outbox: {e}");
                    }
                    // Scheduled tasks vencidas → execute_command del propio módulo (sin usuario).
                    if let Err(e) = rt.process_scheduler(&hub_id).await {
                        eprintln!("scheduler: {e}");
                    }
                    // Kernel de automatización (ADR-0283, hub#661): dispara los triggers de reloj,
                    // despierta los `delay` vencidos y avanza los runs reclamados. Comparte este
                    // guard con los dos de arriba, y su trabajo sigue ACOTADO por tick
                    // (`MAX_RUNS_PER_TICK` × `MAX_STEPS_PER_TICK`, todos sin I/O): un step `http` o
                    // un turno de IA aquí dentro retendría el guard 30 s, y un escritor en cola
                    // (una instalación) pararía tras él a todo el TPV — el `RwLock` es justo, así
                    // que los lectores nuevos esperan al escritor pendiente. Por eso esos van por
                    // claim → I/O → complete FUERA del lock (hub#662/#665).
                    match rt.process_flows().await {
                        Ok(report) => pending_io = report.pending_io,
                        Err(e) => eprintln!("flows: {e}"),
                    }
                }
                // Ya sin el lock: cada llamada se va a su propia tarea y vuelve por
                // `complete_flow_io` cuando termine (crates/server/src/flow_io.rs).
                if !pending_io.is_empty() {
                    flow_io::dispatch(&scheduler_state, pending_io);
                }
                tokio::time::sleep(std::time::Duration::from_millis(1000)).await;
            }
        });
    }

    // **Retención del historial** (hub#699, `erplora_runtime::retention`): el outbox y los runs de
    // flujos eran append-only — ninguna fila se borraba nunca — y sus columnas anchas (`input`,
    // `output`, `payload`, todas TEXT) crecían de por vida en una BD que se paga por GB. A los 90
    // días se poda lo TERMINAL, y solo eso: un `pending` (aún por entregar) y un `dead` (esperando
    // decisión humana) sobreviven a cualquier edad, porque son la durabilidad, no el historial.
    //
    // Tick PROPIO y horario, no el bucle de 1s: el barrido no es urgente y el bucle de 1s sostiene
    // el lock del runtime para el relay de eventos. El lock se coge **por pasada**, no para todo el
    // barrido, así que entre dos DELETE acotados el relay entra sin esperar. Que sea horario y no
    // diario es lo que deja a un hub con un año de atraso ponerse al día en unas horas en vez de en
    // meses, sin que ninguna pasada deje de ser pequeña.
    {
        let st = state.clone();
        tokio::spawn(async move {
            let mut tick = tokio::time::interval(std::time::Duration::from_secs(3600));
            loop {
                tick.tick().await;
                let hub_id = st.hub_id();

                // **Antes de podar, cerrar lo que caducó** (hub#972). El TTL de 72 h de una
                // aprobación solo se miraba al intentar decidirla, así que una propuesta que nadie
                // contestó no se podía ni aprobar ni rechazar —las dos vías pasan por la misma
                // puerta— y su run se quedaba en `waiting_approval` PARA SIEMPRE: exento de la poda
                // de abajo, con el `payload` verbatim dentro (el nombre y el teléfono de una
                // clienta). El barrido lo pasa a `expired`, aplica la política que dice la FILA
                // (`on_expire`, defecto `reject`) y deja el run en estado terminal — que es lo que
                // lo mete en la poda de 90 días, en esta misma vuelta.
                //
                // Pasadas acotadas con el lock cogido **por pasada**, igual que la poda de abajo:
                // cerrar una propuesta no es un DELETE, es terminar (o reanudar) un run, y una
                // bandeja con un año de abandono no puede quedarse el lock un minuto entero.
                {
                    let mut swept = erplora_runtime::flows::ExpirySweepReport::default();
                    for _ in 0..erplora_runtime::retention::MAX_PASSES {
                        let runtime = st.runtime.read().await;
                        let pass = runtime.sweep_expired_flow_approvals().await;
                        drop(runtime);
                        match pass {
                            Ok(p) if p.is_empty() => break,
                            Ok(p) => swept.merge(p),
                            Err(e) => {
                                tracing::warn!(error = %e, "flows: el barrido de aprobaciones caducadas falló");
                                break;
                            }
                        }
                    }
                    if !swept.is_empty() {
                        tracing::info!(
                            expired = swept.expired,
                            runs_stopped = swept.runs_stopped,
                            runs_resumed = swept.runs_resumed,
                            stranded = swept.stranded,
                            "flows: propuestas caducadas cerradas"
                        );
                    }
                }

                // Dos relojes, uno por tabla (hub#903): el historial a 90 días y el RECIBO de una
                // aprobación humana a cuatro años. Se calculan juntos al principio de la vuelta
                // para que todas las pasadas de este tick midan contra el mismo instante.
                let cutoffs = erplora_runtime::retention::Cutoffs::now();
                let mut total = erplora_runtime::retention::PruneReport::default();
                for _ in 0..erplora_runtime::retention::MAX_PASSES {
                    let runtime = st.runtime.read().await;
                    let pass =
                        erplora_runtime::retention::prune_once(runtime.db(), &hub_id, &cutoffs)
                            .await;
                    drop(runtime);
                    match pass {
                        Ok(p) if p.is_empty() => break,
                        Ok(p) => total.merge(p),
                        Err(e) => {
                            tracing::warn!(error = %e, "retention: la poda de historial falló");
                            break;
                        }
                    }
                }
                // Solo si borró algo: una poda silenciosa es indistinguible de una pérdida de datos
                // el día que alguien busca un evento viejo y no está, pero "borradas 0 filas" cada
                // hora es ruido que enseña a no leer el log.
                if !total.is_empty() {
                    tracing::info!(
                        events = total.events,
                        delivery_markers = total.delivery_markers,
                        runs = total.runs,
                        run_steps = total.run_steps,
                        approvals = total.approvals,
                        receipts = total.receipts,
                        retention_days = erplora_runtime::retention::RETENTION_DAYS,
                        approval_audit_days = erplora_runtime::retention::APPROVAL_AUDIT_DAYS,
                        "retention: historial terminal podado"
                    );
                }
            }
        });
    }

    // **WhatsApp entrante** (ADR-0283 K1c, `architecture/hub/flows.md` §6): el hub POLLEA su
    // bandeja en el SaaS y convierte cada mensaje en el evento core
    // `hub.whatsapp.message_received`. El SaaS no puede llamar a un hub (ADR-0213) y los hubs
    // viven tras NAT, así que la única dirección posible es esta.
    //
    // Tick PROPIO y no el bucle de 1s de arriba, por dos razones: su periodo es otro (5s) y, sobre
    // todo, hace **I/O de red** — meterlo en el bucle del relay tendría el lock del runtime
    // cogido durante un round-trip HTTP y pararía la entrega de eventos de todo el hub.
    // `poll_once` coge el lock solo para el gate y para las escrituras (ver su doc).
    //
    // El propio tick se auto-gatea: sin el módulo `whatsapp_inbox` activo y con entitlement, no
    // sale ni una petición (720 GET/hora por hub que sí lo usa).
    {
        let poll_state = state.clone();
        let poller = inbound_poll::InboundPoller::new(
            state.http.clone(),
            &state.config.cloud_base_url,
            state.hub_id.clone(),
            state.machine_token.clone(),
        );
        let secs =
            inbound_poll::interval_secs(std::env::var(inbound_poll::INTERVAL_ENV).ok().as_deref());
        tokio::spawn(async move {
            let mut tick = tokio::time::interval(std::time::Duration::from_secs(secs));
            tick.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Delay);
            loop {
                tick.tick().await;
                match poller
                    .poll_once(&poll_state.runtime, &poll_state.entitlement)
                    .await
                {
                    Ok(report) if report.ingested > 0 => tracing::info!(
                        ingested = report.ingested,
                        acked = report.acked,
                        // Lo que el SaaS sirvió y este runtime no entendió (hub#1612): cero es
                        // lo normal, y un número aquí dice que falta release de runtime para
                        // aprovechar algo que el SaaS ya está entregando.
                        unexpected = report.unexpected,
                        "whatsapp entrante: mensajes ingeridos como evento core"
                    ),
                    Ok(_) => {}
                    // Un fallo de red aquí NO es fatal: los mensajes siguen pendientes en el SaaS
                    // y el siguiente tick los recoge (nada se pierde por no haber podido leer).
                    Err(e) => tracing::warn!("whatsapp entrante: {e}"),
                }
            }
        });
    }

    // Job de **revalidación híbrida del entitlement** (crate::entitlement): refresca el token
    // firmado del Cloud cada `HUB_ENTITLEMENT_REVALIDATE_SECS` (default 24h) con la credencial
    // de máquina y actualiza el estado que leen el gate de query/command y `/api/entitlement`.
    // Primer tick al arrancar (siembra el estado cuanto antes). Sin token de máquina (dev/local
    // sin enrolar) el tick se salta SIN contar fallo → el gate queda fail-open, como hoy.
    //
    // 🪦 El latido era además el **segundo disparador del refetch del certificado delegado**
    // (ADR-0202 §2 punto 4): subía la versión instalada y bajaba la que servía el plano de control,
    // de modo que una rotación central convergía por la llamada que ya se hacía. Se fue con el slot
    // (hub#1435) — no hay clave que rotar: la celda fiscal transmite con un Sello que nunca sale de
    // la plataforma (ADR-0320) — y el SaaS retiró su mitad en saas#1435 fase 2.
    {
        let st = state.clone();
        let secs = entitlement::interval_secs(
            std::env::var("HUB_ENTITLEMENT_REVALIDATE_SECS")
                .ok()
                .as_deref(),
        );
        tokio::spawn(async move {
            let mut tick = tokio::time::interval(std::time::Duration::from_secs(secs));
            loop {
                tick.tick().await;
                let Some(auth) = auth::machine_auth(&st) else {
                    continue;
                };
                // Same 24h tick, no second scheduler: report canonical daily business usage.
                // Collection happens before network I/O, then both Cloud calls run independently:
                // an entitlement failure must not suppress business-usage retention (or vice versa).
                let now = entitlement::now_unix();
                let now_iso = chrono::Utc::now().to_rfc3339();
                let mut usage = {
                    let runtime = st.runtime.read().await;
                    // Lo que cada motor instalado debe a su autoridad (hub#326/hub#1406) — la
                    // pregunta va al REGISTRO, no a un motor con nombre; mismo lock barato que
                    // el resto del snapshot.
                    let pending = runtime.pending_obligations().await;
                    daily_usage::collect_daily_usage(
                        runtime.db(),
                        runtime.hub_id(),
                        &now_iso,
                        &pending,
                    )
                    .await
                };
                // ADR-0175: la actividad de usuario viaja en ESTE heartbeat, y solo si la hubo.
                // Un hub encendido que nadie toca no manda la marca — que es exactamente lo que el
                // Cloud tiene que observar para poder apagarlo.
                let pending_activity = st.activity.pending();
                usage.last_user_activity_at = pending_activity.map(activity::to_iso8601);
                // hub#975: la telemetría de recursos viaja en el MISMO latido, del sampler único
                // de `system_metrics` (fuera del lock de arriba: el muestreo de CPU duerme 100 ms).
                // Best-effort: fuera de contenedor los campos viajan ausentes, nunca un 0 falso.
                daily_usage::sample_resource_metrics()
                    .await
                    .apply_to(&mut usage);
                let entitlement_request = entitlement::fetch_verified_claims(
                    &st.http,
                    &st.config.cloud_base_url,
                    &auth,
                    now,
                );
                let heartbeat_request =
                    daily_usage::send_heartbeat(&st.http, &st.config.cloud_base_url, &auth, &usage);
                let (outcome, heartbeat_result) =
                    tokio::join!(entitlement_request, heartbeat_request);
                entitlement::record_outcome(&st.entitlement, outcome, now);
                // La cuota del canal de WhatsApp se refleja en el medidor del módulo (hub#1089).
                // Se lee EN VIVO de `whatsapp/plan/` con esta MISMA credencial de máquina, no de
                // un claim del token: ese endpoint devuelve tier + consumo, y el consumo es un
                // contador que se mueve con cada mensaje. Si el Cloud no contesta no se escribe
                // nada — el medidor conserva lo que ya medía, porque en este canal `0` significa
                // «sin tope» y un fallo de red no es un plan. Un hub sin el módulo ni pregunta.
                match whatsapp_quota::sync_once(
                    &st.runtime,
                    &st.http,
                    &st.config.cloud_base_url,
                    &auth,
                )
                .await
                {
                    whatsapp_quota::QuotaSync::Written {
                        monthly_limit,
                        monthly_usage,
                    } => {
                        tracing::debug!(
                            monthly_limit,
                            monthly_usage,
                            "cuota de WhatsApp al día"
                        )
                    }
                    // Los demás casos ya se han contado donde tocaba (o son el no-op esperado
                    // en la flota que no compró el canal): aquí no se repite el ruido.
                    other => tracing::trace!(?other, "sincronización de cuota de WhatsApp"),
                }
                match heartbeat_result {
                    // Confirmar SOLO tras un envío correcto: si se diera por reportada una marca
                    // que no llegó, el Cloud seguiría contando días y adelantaría el apagado.
                    Ok(_) => {
                        // Lo mismo, un escalón más abajo (saas#2129): los EVENTOS que viajaron en
                        // este latido ya están en el Cloud, así que se pueden soltar. Un latido
                        // fallido los deja donde están — este dato no se recupera hacia atrás.
                        {
                            let runtime = st.runtime.read().await;
                            daily_usage::confirm_activity(
                                runtime.db(),
                                runtime.hub_id(),
                                &usage.activity,
                            )
                            .await;
                        }
                        if let Some(ts) = pending_activity {
                            st.activity.mark_reported(ts);
                        }
                    }
                    Err(error) => tracing::warn!(%error, "daily usage heartbeat failed"),
                }
            }
        });
    }

    // ⛔ Aquí iba el import del blueprint DECLARADO por el SaaS (ADR-0212 / hub#406), y ya no va:
    // **un hub nace VACÍO** (ADR-0293). Era el único paso del arranque que instalaba módulos por su
    // cuenta —`ImportSelection.modules` = todos los del manifest de la plantilla—, así que un hub
    // recién provisionado amanecía con el vertical entero puesto (13 apps con el blueprint
    // `restaurante` de la demo).
    //
    // ERPlora es un **ERP genérico, no un POS**: el vertical lo elige el usuario. Un hub nuevo trae
    // su configuración y nada más, y la primera pantalla le ofrece los blueprints para que importe
    // el suyo. Sembrárselo al nacer decide por él justo lo que el producto le deja elegir.
    //
    // Las dos claves de env (`HUB_BOOTSTRAP_BLUEPRINT`, `HUB_BOOTSTRAP_BLUEPRINT_LOCALE`) siguen
    // llegando en el despliegue de las demos y **se ignoran a propósito**; `HubConfig::from_env` ya
    // no las lee. Lo vigila `tests/newborn_hub_is_empty.rs`, que arranca el hub de verdad con ellas
    // puestas y comprueba que no se le pide un solo blueprint al Cloud.

    // hub#1457: el alta de la identidad de MÁQUINA converge sola. Mira un dato LOCAL en cada
    // tick —clave sin certificado, o sea «alguien pidió el CSR en este hub»— y solo entonces
    // gasta una llamada, así que una flota de hubs que firman con su propio certificado no le
    // cuesta nada al plano de control ni llena de revisiones el escritorio del operador.
    gateway_enrolment::spawn_enrolment_service(&state);

    // «Llama a MI nube con MI credencial de máquina» (hub#1459): el primitivo genérico con el
    // que un motor first-party pide algo al plano de control sin sostener jamás el `X-Hub-Token`.
    // El host pone destino y credencial; el motor pone método, ruta y cuerpo — y qué significa la
    // respuesta (caché, 409, reintento) es del motor, no del core.
    erplora_runtime::cloud_call::CloudCallerCell::global()
        .install(cloud_call::HubCloudCaller::installed(&state));

    // Router de API + (opcional) frontend estático en el MISMO origen (`cfg.web_dir`). En ECS/binario
    // lo vuelca `from_env` desde `HUB_WEB_DIR`; en Tauri (Hub Local, ADR-0050) lo fija el shell con la
    // ruta del `dist/` empaquetado (`resource_dir()`), para que el webview cargue front + datos del
    // mismo origen. `None` ⇒ solo API (dev con Vite, que proxya).
    if let Some(dir) = cfg.web_dir.as_deref() {
        eprintln!("sirviendo frontend estático desde {dir} (fallback SPA → index.html)");
    }
    // El router consume el `state`; el aviso de arranque de más abajo necesita el suyo, y el
    // apagado el suyo (hub#670: el último flush de la marca de actividad).
    let announce_state = state.clone();
    let shutdown_state = state.clone();
    // hub#926: el precalentado de handlers también necesita el suyo (el router consume `state`).
    let warm_state = state.clone();
    // CSP (ADR-0050, hub#708): con el doc servido por Axum —que es SIEMPRE, también en la app
    // instalada, cuya ventana navega aquí— la de `tauri.conf` no alcanza al documento. Sin rama:
    // la política se emite siempre, y `cfg.csp` es `String` para que "sin CSP" ni se pueda escribir.
    let router = build_serving_router(state, cfg.web_dir.as_deref(), &cfg.csp);

    let listener = tokio::net::TcpListener::bind(&cfg.bind).await?;
    eprintln!("erplora-server escuchando en http://{}", cfg.bind);
    tracing::info!(bind = %cfg.bind, "erplora-server arrancado");

    // «Ya atiendo» (hub#712): en cuanto el agregado de `/readyz` diga `UP`, un latido al Cloud
    // para que un hub recién desplegado pase a `active` sin esperar al sondeo del SaaS.
    //
    // 🔑 Va AQUÍ, después de bindear: el socket ya escucha, así que el aviso no puede adelantar
    // al hub que anuncia. Antes de este punto marcaríamos listo un hub que todavía no atiende, y
    // eso es peor que tardar. En su propia task y best-effort, como el import de blueprint y el
    // refetch del certificado: un plano de control inalcanzable deja un hub que FUNCIONA.
    boot_announce::spawn(&announce_state);
    // Precalentar los handlers WASM (hub#926). La caché en disco de wasmtime vive DENTRO del
    // contenedor, así que un deploy la estrena vacía: medido en producción, las dos primeras ventas
    // tras desplegar costaron 8,2 s y 5,7 s, y las siguientes 75-91 ms. Compilar hay que compilar;
    // lo que se elige aquí es hacerlo mientras nadie espera, no en el primer cobro del día.
    //
    // En su propia task y DESPUÉS de bindear, como el resto del arranque: el hub ya atiende, y si
    // el precalentado tarda —o un módulo trae bytes rotos— no retrasa ni tumba nada.
    {
        tokio::spawn(async move {
            // Se toma la caché (un `Arc` compartido con el registro) y se SUELTA el candado del
            // runtime antes de compilar: calentar no puede bloquear a quien esté cobrando.
            let (cache, modules) = {
                let rt = warm_state.runtime.read().await;
                (
                    std::sync::Arc::clone(&rt.registry().wasm_cache),
                    rt.registry().handlers_to_warm_up(),
                )
            };
            if modules.is_empty() {
                return;
            }
            let total = modules.len();
            // `spawn_blocking`: compilar es trabajo de CPU y no debe ocupar un worker async.
            match tokio::task::spawn_blocking(move || {
                erplora_runtime::wasm_cache::warm_up(
                    &cache,
                    &modules,
                    erplora_runtime::wasm_cache::Limits::from_env(),
                )
            })
            .await
            {
                Ok(warmed) => eprintln!("wasm: {warmed}/{total} handler(s) precalentados"),
                Err(e) => eprintln!("wasm: precalentado abortado: {e}"),
            }
        });
    }

    // Apagado limpio (ECS/Tauri): Ctrl-C o SIGTERM → deja de aceptar conexiones y drena las en
    // vuelo antes de salir, en vez de cortar a mitad (importante para ECS al desescalar/desplegar).
    axum::serve(listener, router)
        .with_graceful_shutdown(shutdown_signal(shutdown_state))
        .await?;
    Ok(())
}

/// Instala el **registro global de errores** del runtime: el sink que reenvía al Cloud + el panic
/// hook. Idempotente en la práctica (el `OnceLock` interno ignora un segundo `install`; el hook se
/// re-encadena al anterior). Lo llama [`serve`] una vez al arrancar, con el `AppState` ya montado.
pub(crate) fn install_error_reporting(state: &AppState) {
    use erplora_runtime::error_registry::{ErrorEvent, ErrorRegistry};

    // El sink lee el token de máquina VIVO (hot-reload) de la celda del state, así que un enrol
    // posterior habilita el reporte sin reiniciar. La versión del hub = la del build del server.
    let sink = error_sink::CloudErrorSink::new(
        &state.config.cloud_base_url,
        state.hub_id.clone(),
        state.machine_token.clone(),
        state.http.clone(),
        version::display(),
    );
    ErrorRegistry::install(std::sync::Arc::new(sink));

    // Panic hook: convierte cualquier `panic!` del proceso en un `ErrorEvent` (source=hub,
    // code=panic, severity=unexpected) y lo reporta al registro global ANTES de delegar en el hook
    // por defecto (que sigue logueando/abortando). `report` es seguro desde aquí (no hace panic!).
    let previous = std::panic::take_hook();
    std::panic::set_hook(Box::new(move |info| {
        // Mensaje: el payload del panic (str/String) si es legible.
        let message = info
            .payload()
            .downcast_ref::<&str>()
            .map(|s| s.to_string())
            .or_else(|| info.payload().downcast_ref::<String>().cloned())
            .unwrap_or_else(|| "panic (payload no legible)".to_string());
        // Stack: ubicación del panic + backtrace si está habilitado (RUST_BACKTRACE).
        let location = info
            .location()
            .map(|l| format!("{}:{}:{}", l.file(), l.line(), l.column()))
            .unwrap_or_default();
        let backtrace = std::backtrace::Backtrace::capture().to_string();
        let stack = if backtrace.is_empty() || backtrace.contains("disabled backtrace") {
            location
        } else {
            format!("{location}\n{backtrace}")
        };

        let event = ErrorEvent::new(
            erplora_runtime::error_registry::source::HUB,
            "panic",
            message,
            erplora_runtime::error_registry::severity::UNEXPECTED,
        )
        .with_stack(stack);
        ErrorRegistry::global().report(event);

        // Conserva el comportamiento previo (log a stderr / abort según config).
        previous(info);
    }));
}

/// Espera Ctrl-C o (en Unix) SIGTERM. ECS envía SIGTERM al desescalar/desplegar; al recibirla,
/// `axum::serve` deja de aceptar conexiones nuevas y drena las en vuelo antes de cerrar.
pub(crate) async fn shutdown_signal(state: AppState) {
    let ctrl_c = async {
        tokio::signal::ctrl_c()
            .await
            .expect("instalar handler de Ctrl-C");
    };
    #[cfg(unix)]
    let terminate = async {
        tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate())
            .expect("instalar handler de SIGTERM")
            .recv()
            .await;
    };
    #[cfg(not(unix))]
    let terminate = std::future::pending::<()>();
    tokio::select! {
        _ = ctrl_c => {},
        _ = terminate => {},
    }
    // 🔑 Seguir ACEPTANDO antes de cerrar (hub#646). `with_graceful_shutdown` empieza a apagar en
    // cuanto este future resuelve, así que retrasarlo es lo que mantiene el listener abierto —
    // justo el tiempo que Traefik tarda en dejar de mandarnos tráfico. Sin esto, cada actualización
    // devuelve 502 a quien llegue en esa ventana.
    let drain = shutdown::drain_delay();
    if !drain.is_zero() {
        eprintln!(
            "apagado: señal recibida — sigo aceptando {}s para que Traefik deje de enrutar aquí…",
            drain.as_secs()
        );
        tokio::time::sleep(drain).await;
    }
    // Último flush de la marca de actividad (hub#670) antes de cerrar. El write-behind ya la
    // escribe cada minuto, así que esto solo cierra el último minuto — pero el SIGTERM de un
    // blue/green (ADR-0269) llega en CADA actualización, y ese minuto es justo el que contiene la
    // visita de quien estaba usando el hub cuando se desplegó.
    activity::flush(&state).await;
    eprintln!("apagado: cierro el listener y dreno las conexiones en vuelo…");
}

/// **Liveness**: ¿el proceso responde? Nada más — y por eso es un literal.
///
/// La pregunta que de verdad importa al desplegar («¿puedo atender?») la contesta
/// [`readiness::readyz`], y es la que mira el `HEALTHCHECK`. Mezclarlas fue el bug: durante meses
/// esto FUE el healthcheck del contenedor, así que un hub sin BD, con las migraciones a medias o
/// sin un solo módulo cargado pasaba por sano.
/// Manda al Cloud que una actualización automática de módulo se cayó (hub#516).
///
/// Si actualizamos solos y sin preguntar (ADR-0269), una actualización que falla no puede quedarse
/// en un `eprintln!` del contenedor: `outcome` distingue el caso tolerable —el hub siguió con la
/// versión de ayer— del que no lo es: **el hub arrancó sin el módulo**, que es el único desenlace
/// que este modelo prohíbe. Best-effort por contrato del registro: sin sink (hub sin enrolar) se
/// descarta en silencio.
pub(crate) fn report_failed_module_update(
    module_id: &str,
    from: &str,
    to: &str,
    error: &str,
    fell_back: bool,
) {
    use erplora_runtime::error_registry::{ErrorEvent, ErrorRegistry};

    ErrorRegistry::global().report(
        ErrorEvent::new(
            erplora_runtime::error_registry::source::HUB,
            "module_update_failed",
            format!("no se pudo actualizar `{module_id}` de {from} a {to}: {error}"),
            erplora_runtime::error_registry::severity::UNEXPECTED,
        )
        .with_module(module_id.to_string())
        .with_context(json!({
            "from": from,
            "to": to,
            // `stayed_on_previous` = el hub sirve; `no_module` = arrancó incompleto.
            "outcome": if fell_back { "stayed_on_previous" } else { "no_module" },
        })),
    );
}

/// El informe de un arranque **incompleto** (hub#571), sin mandarlo todavía.
///
/// Aparte para poder fijarlo con un test: lo que importa de este evento es su **contenido** —el
/// código estable contra el que se programa y los módulos que faltan—, no que se haya llamado a un
/// sink global.
///
/// Es un fallo **del hub**, no de un módulo: lo que se cayó es el arranque, y colgárselo al primero
/// de la lista mandaría a mirar donde no es.
pub(crate) fn incomplete_boot_event(
    orphans: &[(String, String)],
) -> erplora_runtime::error_registry::ErrorEvent {
    use erplora_runtime::error_registry::{severity, source, ErrorEvent};

    let names: Vec<String> = orphans
        .iter()
        .map(|(id, version)| format!("{id}@{version}"))
        .collect();
    ErrorEvent::new(
        source::HUB,
        "module_boot_incomplete",
        format!(
            "el hub arrancó SIN {} módulo(s) instalados: {} — ni el marketplace ni la copia local \
             pudieron reponerlos",
            orphans.len(),
            names.join(", ")
        ),
        severity::UNEXPECTED,
    )
    .with_context(json!({
        "count": orphans.len(),
        "modules": orphans
            .iter()
            .map(|(id, version)| json!({ "module_id": id, "version": version }))
            .collect::<Vec<_>>(),
    }))
}

/// Manda al Cloud que este hub arrancó **sin** alguno de sus módulos (hub#571).
///
/// Es el caso que ADR-0269 no puede cumplir: no hay copia, no hay versión anterior y no hay tarea
/// vieja a la que volver. Lo único que sí está en nuestra mano es que **no sea un silencio** — un
/// hub incompleto que solo lo cuenta en el log de un contenedor es un hub que nadie arregla.
/// Best-effort por contrato del registro: sin sink (hub sin enrolar) se descarta.
pub(crate) fn report_incomplete_boot(orphans: &[(String, String)]) {
    eprintln!(
        "🔴 el hub arranca SIN {} módulo(s): {}",
        orphans.len(),
        orphans
            .iter()
            .map(|(id, v)| format!("{id}@{v}"))
            .collect::<Vec<_>>()
            .join(", ")
    );
    erplora_runtime::error_registry::ErrorRegistry::global().report(incomplete_boot_event(orphans));
}

#[cfg(test)]
mod incomplete_boot_report_tests {
    //! hub#571: un hub que arranca SIN alguno de sus módulos no puede ser un silencio.
    use super::incomplete_boot_event;

    #[test]
    fn the_report_names_every_module_that_could_not_be_mounted() {
        let event = incomplete_boot_event(&[
            ("sales".to_string(), "3.2.0".to_string()),
            ("taxes".to_string(), "1.4.0".to_string()),
        ]);

        assert_eq!(event.error_code, "module_boot_incomplete");
        assert_eq!(
            event.severity,
            erplora_runtime::error_registry::severity::UNEXPECTED
        );
        // Los módulos, con su versión, para que quien lo lea sepa QUÉ falta sin abrir el hub.
        assert_eq!(event.context["modules"][0]["module_id"], "sales");
        assert_eq!(event.context["modules"][0]["version"], "3.2.0");
        assert_eq!(event.context["modules"][1]["module_id"], "taxes");
        assert_eq!(event.context["count"], 2);
        assert!(event.message.contains("sales"), "{}", event.message);
        assert!(event.message.contains("taxes"), "{}", event.message);
    }

    /// El evento es del HUB, no de un módulo: no hay un culpable al que colgárselo — lo que falló
    /// es el arranque, y atribuirlo al primero de la lista mandaría a mirar donde no es.
    #[test]
    fn the_failure_belongs_to_the_hub_and_not_to_one_of_the_modules() {
        let event = incomplete_boot_event(&[("sales".to_string(), "3.2.0".to_string())]);
        assert_eq!(event.source, erplora_runtime::error_registry::source::HUB);
        assert_eq!(event.module_id, None);
    }
}
