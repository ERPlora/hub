//! Código máquina de los handlers, compilado UNA vez por versión de módulo (hub#926).
//!
//! El `.wasm` de un módulo no lo ejecuta la CPU: wasmtime lo traduce con Cranelift primero, y esa
//! traducción es la parte cara. El runtime la pedía dentro de CADA comando y tiraba el resultado.
//!
//! Medido en **hardware de producción** (amd64, la imagen que corre la flota, 512 MiB / 0,25 vCPU),
//! que es lo que de verdad describe el problema:
//!
//!  * Extism ya trae una caché **en disco** de wasmtime (`$HOME/.cache/wasmtime`), así que la
//!    segunda llamada a un handler no vuelve a pasar por Cranelift: por eso una venta cuesta
//!    ~50 ms y no lo que cuesta compilar. Esta caché en memoria se ahorra además la
//!    deserialización y el montaje del plugin: **−23 % de CPU por venta** (44 → 34 ms, medido A/B
//!    con dos imágenes compiladas igual).
//!  * Pero la caché en disco vive en el contenedor, y **un deploy estrena contenedor**: tras cada
//!    despliegue las dos primeras ventas costaron **8,2 s y 5,7 s** (de la tercera en adelante,
//!    75-91 ms). Ese es el coste que paga el cajero con un cliente delante, y para eso está
//!    [`warm_up`].
//!
//! Aquí se guarda el resultado de esa traducción. Lo que se comparte es **código inmutable**; el
//! estado nunca: cada llamada sigue instanciando su propio sandbox (memoria lineal, fuel y epoch
//! nuevos — ver `CompiledModule::instantiate`).
//!
//! **La clave incluye la versión** porque servir el código de la versión anterior tras actualizar
//! un módulo sería peor que recompilar siempre: el hub ejecutaría lógica que ya nadie tiene. Y por
//! si un hub de desarrollo reinstala la MISMA versión con bytes distintos, la entrada se tira
//! explícitamente al desregistrar el módulo (`Registry::remove_module`), que es por donde pasa
//! toda actualización.

use std::collections::HashMap;
use std::sync::{Arc, Mutex};

use erplora_wasm_host::{CompiledModule, WasmLimits};

/// Reexportado para que el host (server/Tauri) pueda armar los topes sin depender del crate del
/// sandbox: el precalentado del arranque es su único usuario.
pub use erplora_wasm_host::WasmLimits as Limits;

use crate::errors::{Result, RuntimeError};

/// Identidad del código compilado: el módulo, su versión y los topes con los que se compiló
/// (los límites viajan dentro del artefacto; servir uno compilado con otro tope sería mentir).
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct CacheKey {
    pub module_id: String,
    pub version: String,
    limits: WasmLimitsKey,
}

/// `WasmLimits` no es `Hash`: esta es su proyección para la clave.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
struct WasmLimitsKey {
    memory_max_mb: u32,
    fuel: u64,
    timeout_ms: u64,
}

impl CacheKey {
    pub fn new(
        module_id: impl Into<String>,
        version: impl Into<String>,
        limits: WasmLimits,
    ) -> Self {
        CacheKey {
            module_id: module_id.into(),
            version: version.into(),
            limits: WasmLimitsKey {
                memory_max_mb: limits.memory_max_mb,
                fuel: limits.fuel,
                timeout_ms: limits.timeout_ms,
            },
        }
    }
}

/// Los módulos ya compilados, vivos mientras el módulo esté instalado.
#[derive(Debug, Default)]
pub struct WasmCache {
    entries: Mutex<HashMap<CacheKey, Arc<CompiledModule>>>,
}

impl WasmCache {
    /// Devuelve el código compilado de este módulo, compilándolo si es la primera vez.
    ///
    /// `build` es la compilación de verdad; entra como cierre para poder ejercitar la caché en los
    /// tests sin depender de un `.wasm` real, y porque el llamante es quien sabe de dónde salen
    /// los bytes.
    ///
    /// El candado **no** se sostiene mientras se compila: dos llamadas simultáneas que fallen la
    /// caché compilarán las dos. Es deliberado — sostenerlo serializaría todos los cobros del hub
    /// detrás de una compilación, que es exactamente lo que se viene a quitar. Compilar dos veces
    /// una vez es barato; bloquear la caja, no.
    pub fn get_or_compile_with<F>(&self, key: CacheKey, build: F) -> Result<Arc<CompiledModule>>
    where
        F: FnOnce() -> Result<CompiledModule>,
    {
        if let Some(hit) = self.get(&key) {
            return Ok(hit);
        }
        let compiled = Arc::new(build()?);
        let mut entries = self.lock();
        // `entry` en vez de `insert`: si otra llamada se adelantó, se usa la suya y se descarta la
        // nuestra, así todas las instancias vivas salen del mismo artefacto.
        Ok(entries.entry(key).or_insert(compiled).clone())
    }

    /// Igual, compilando de verdad desde los bytes del handler.
    pub fn get_or_compile(
        &self,
        key: CacheKey,
        wasm: &[u8],
        limits: WasmLimits,
    ) -> Result<Arc<CompiledModule>> {
        self.get_or_compile_with(key, || {
            CompiledModule::compile(wasm, limits).map_err(|e| RuntimeError::Wasm(e.to_string()))
        })
    }

    fn get(&self, key: &CacheKey) -> Option<Arc<CompiledModule>> {
        self.lock().get(key).cloned()
    }

    /// Tira lo compilado de un módulo. Lo llama `Registry::remove_module`, que es el paso previo
    /// de toda actualización y de toda desinstalación (hub#516).
    pub fn forget_module(&self, module_id: &str) {
        self.lock().retain(|k, _| k.module_id != module_id);
    }

    /// Cuántos módulos hay compilados ahora mismo (observabilidad y tests).
    pub fn len(&self) -> usize {
        self.lock().len()
    }

    pub fn is_empty(&self) -> bool {
        self.len() == 0
    }

    /// Un candado envenenado no puede tumbar el TPV: la caché es un acelerador, no una fuente de
    /// verdad, así que se sigue adelante con lo que haya dentro.
    fn lock(&self) -> std::sync::MutexGuard<'_, HashMap<CacheKey, Arc<CompiledModule>>> {
        self.entries.lock().unwrap_or_else(|e| e.into_inner())
    }
}

/// Compila por adelantado los handlers de los módulos instalados (hub#926).
///
/// Medido en hardware de producción (amd64, imagen de la flota, 512 MiB / 0,25 vCPU): tras un
/// **deploy** —que estrena contenedor, y con él la caché en disco de wasmtime— las dos primeras
/// ventas costaron **8,2 s y 5,7 s**, y de la tercera en adelante 75-91 ms. La compilación hay que
/// pagarla igual; lo que se elige aquí es **cuándo**: al arrancar, cuando no hay nadie esperando
/// en el mostrador, en vez de en el primer cobro del día.
///
/// Devuelve cuántos handlers quedaron compilados. **No falla nunca**: un módulo con bytes rotos se
/// salta —su comando dará error cuando alguien lo llame, con su mensaje, no antes— porque arrancar
/// es justo lo que no se puede permitir que se caiga.
pub fn warm_up(
    cache: &WasmCache,
    modules: &[(String, String, Option<Vec<u8>>)],
    limits: WasmLimits,
) -> usize {
    let mut warmed = 0;
    for (module_id, version, wasm) in modules {
        let Some(bytes) = wasm else { continue };
        let key = CacheKey::new(module_id.clone(), version.clone(), limits);
        match cache.get_or_compile(key, bytes, limits) {
            Ok(_) => warmed += 1,
            Err(e) => eprintln!("wasm: no se pudo precalentar `{module_id}`: {e}"),
        }
    }
    warmed
}
