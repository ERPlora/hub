//! Registro persistente de dispositivos (JSON) + resolución MAC vía ARP + watchdog de
//! auto-recuperación.
//!
//! Porta:
//!   - `hardware/network.py` → `DeviceRegistry` + `get_mac_for_ip` + `_normalize_mac`.
//!   - `hardware/watchdog.py` → `Watchdog` (health-check periódico + recovery scan por MAC
//!     cuando la IP cambia por DHCP).

use std::collections::HashMap;
use std::path::PathBuf;
use std::process::Command;
use std::sync::RwLock;
use std::time::{Duration, Instant};

use crate::discovery::local_subnet_prefix;
use crate::protocol::Device;
use crate::{Result, ESCPOS_NETWORK_PORT};

/// Resuelve la MAC de una IP usando la tabla ARP del sistema (ping para poblar caché + `arp`).
/// Porta `get_mac_for_ip`. Nunca lanza: devuelve `None` ante fallo. Multiplataforma.
pub fn get_mac_for_ip(ip: &str) -> Option<String> {
    let is_windows = std::env::consts::OS == "windows";

    // Ping para poblar la caché ARP (un paquete). Ignoramos cualquier fallo (espejo del try/except).
    let ping = if is_windows {
        Command::new("ping").args(["-n", "1", "-w", "1000", ip]).output()
    } else {
        Command::new("ping").args(["-c", "1", "-W", "1", ip]).output()
    };
    if let Err(exc) = ping {
        tracing::warn!("ping a {ip} falló: {exc}");
    }

    // Leer la tabla ARP.
    let arp = if is_windows {
        Command::new("arp").args(["-a", ip]).output()
    } else {
        Command::new("arp").args(["-n", ip]).output()
    };

    let output = match arp {
        Ok(o) => o,
        Err(exc) => {
            tracing::warn!("comando arp para {ip} falló: {exc}");
            return None;
        }
    };

    if !output.status.success() {
        tracing::warn!(
            "consulta ARP para {ip} falló (rc={:?}): {}",
            output.status.code(),
            String::from_utf8_lossy(&output.stderr).trim()
        );
        return None;
    }

    let stdout = String::from_utf8_lossy(&output.stdout);
    match find_mac(&stdout) {
        Some(mac) => Some(normalize_mac(&mac)),
        None => {
            tracing::warn!("no se encontró MAC en la salida ARP para {ip}: {}", stdout.trim());
            None
        }
    }
}

/// Busca un token con forma de MAC (6 grupos hex separados por `:` o `-`) en un texto arbitrario.
/// Sustituye al regex `_MAC_RE` de Python (este crate no tiene `regex`).
fn find_mac(text: &str) -> Option<String> {
    // La salida de `arp` separa columnas por espacios; la MAC es un token completo.
    for token in text.split(|c: char| c.is_whitespace()) {
        if is_mac_token(token) {
            return Some(token.to_string());
        }
    }
    None
}

/// `true` si `token` tiene forma de MAC: 6 grupos de 1-2 dígitos hex separados consistentemente
/// por `:` o `-`.
/// `true` if `token` is a well-formed MAC address. Public face of [`is_mac_token`] for the
/// `bluetooth:{mac}` printer_id variant (ADR-0204): the contract validates the MAC at the parsing
/// edge, with the same rule the registry itself uses to recognise one.
pub fn is_mac(token: &str) -> bool {
    is_mac_token(token)
}

fn is_mac_token(token: &str) -> bool {
    let sep = if token.contains(':') {
        ':'
    } else if token.contains('-') {
        '-'
    } else {
        return false;
    };

    let groups: Vec<&str> = token.split(sep).collect();
    if groups.len() != 6 {
        return false;
    }
    groups
        .iter()
        .all(|g| (1..=2).contains(&g.len()) && g.chars().all(|c| c.is_ascii_hexdigit()))
}

/// Normaliza una MAC a mayúsculas separada por `:` con octetos de 2 dígitos. Porta `_normalize_mac`.
pub fn normalize_mac(mac: &str) -> String {
    let unified = mac.replace(['-', '.'], ":").to_uppercase();
    unified
        .split(':')
        .map(|part| format!("{:0>2}", part))
        .collect::<Vec<_>>()
        .join(":")
}

/// Identidad estable de un dispositivo en el registro.
///
/// La MAC normalizada cuando el sistema pudo resolverla por ARP; si no, el `printer_id`
/// (`network:{ip}:{port}`). Sin este fallback, un dispositivo sin MAC no llegaba a registrarse y
/// por tanto **no se le podía asignar un rol** (cocina/barra/caja) — que es justo lo que el módulo
/// `printing` necesita. Ocurre siempre en Android y con VPN/contenedores/firewall en escritorio.
pub fn device_key(mac: Option<&str>, ip: &str, port: u16) -> String {
    match mac {
        Some(m) if !m.trim().is_empty() => normalize_mac(m.trim()),
        _ => format!("network:{ip}:{port}"),
    }
}

/// Marca de tiempo ISO con resolución de segundos. Espejo de `datetime.now().isoformat(timespec='seconds')`.
fn now_iso() -> String {
    chrono::Local::now().format("%Y-%m-%dT%H:%M:%S").to_string()
}

/// Registro persistente clave → dispositivo, respaldado por `devices.json` en el dir de config.
/// Porta `DeviceRegistry`. (Persistencia con `RwLock` síncrono + escritura al disco.)
///
/// La clave es [`device_key`]: la MAC normalizada cuando se conoce y el `printer_id`
/// (`network:{ip}:{port}`) cuando no. Antes se indexaba solo por MAC, así que las impresoras sin
/// ARP resoluble —todas en Android— no llegaban a entrar y no admitían rol.
pub struct DeviceRegistry {
    path: PathBuf,
    /// Mapa en memoria clave → dispositivo. `RwLock` síncrono: las operaciones son rápidas y no
    /// se mantiene el lock a través de un `await`.
    devices: RwLock<HashMap<String, Device>>,
}

impl DeviceRegistry {
    /// Carga el registro desde `path` (vacío si no existe o está corrupto). Porta `__init__`/`load`.
    pub fn load(path: PathBuf) -> Self {
        let devices = if path.exists() {
            match std::fs::read_to_string(&path) {
                Ok(text) => match serde_json::from_str::<DevicesFile>(&text) {
                    Ok(file) => Self::backfill_keys(file.devices),
                    Err(exc) => {
                        tracing::warn!("fallo al parsear el registro de dispositivos {path:?}: {exc}");
                        HashMap::new()
                    }
                },
                Err(exc) => {
                    tracing::warn!("fallo al leer el registro de dispositivos {path:?}: {exc}");
                    HashMap::new()
                }
            }
        } else {
            HashMap::new()
        };

        Self { path, devices: RwLock::new(devices) }
    }

    /// Rellena `key` en los ficheros escritos antes de que el campo existiera (estaban indexados
    /// por MAC, así que la clave del mapa **es** la identidad). `devices.json` es dato de usuario:
    /// un cliente con roles ya asignados no puede perderlos al actualizar.
    fn backfill_keys(devices: HashMap<String, Device>) -> HashMap<String, Device> {
        devices
            .into_iter()
            .map(|(map_key, mut device)| {
                if device.key.trim().is_empty() {
                    device.key = map_key.clone();
                }
                (device.key.clone(), device)
            })
            .collect()
    }

    /// Persiste a disco. Porta `save`.
    pub fn save(&self) -> Result<()> {
        let payload = {
            let map = self.devices.read().expect("registry lock envenenado");
            serde_json::to_string_pretty(&serde_json::json!({ "devices": &*map }))?
        };

        if let Some(parent) = self.path.parent() {
            std::fs::create_dir_all(parent)?;
        }
        std::fs::write(&self.path, payload)?;
        Ok(())
    }

    /// Alta/actualización por [`device_key`]; preserva `first_seen` y `role`. Porta `register`.
    ///
    /// `mac` es `Option` a propósito: cuando ARP no la resuelve el dispositivo **igualmente se
    /// registra**, identificado por su `printer_id`. Antes se salía sin registrar nada.
    pub fn register(
        &self,
        mac: Option<&str>,
        ip: &str,
        port: u16,
        name: &str,
        kind: &str,
    ) -> Result<Device> {
        let key = device_key(mac, ip, port);
        let mac = mac
            .map(str::trim)
            .filter(|m| !m.is_empty())
            .map(normalize_mac);
        let now = now_iso();

        let device = {
            let mut map = self.devices.write().expect("registry lock envenenado");
            match map.get_mut(&key) {
                Some(existing) => {
                    existing.ip = ip.to_string();
                    existing.port = port;
                    existing.name = name.to_string();
                    existing.kind = kind.to_string();
                    existing.last_seen = now;
                    // Una MAC que aparece más tarde (p. ej. el ARP responde en el 2º escaneo)
                    // enriquece la entrada, pero nunca la borra si ya se conocía.
                    if mac.is_some() {
                        existing.mac = mac;
                    }
                    existing.clone()
                }
                None => {
                    let device = Device {
                        key: key.clone(),
                        mac,
                        ip: ip.to_string(),
                        port,
                        name: name.to_string(),
                        role: None,
                        kind: kind.to_string(),
                        first_seen: now.clone(),
                        last_seen: now,
                        status: "online".to_string(),
                    };
                    map.insert(key.clone(), device.clone());
                    device
                }
            }
        };

        self.save()?;
        Ok(device)
    }

    /// Resuelve una entrada a partir de su clave **o** de su MAC.
    ///
    /// El protocolo JSON llama `mac` a este parámetro (`SetDeviceRole { mac }`) y los llamadores
    /// existentes le pasan lo que tengan a mano, así que se aceptan las dos formas: primero tal
    /// cual (será un `printer_id`), luego normalizada como MAC.
    fn resolve_key(&self, key_or_mac: &str) -> Option<String> {
        let map = self.devices.read().expect("registry lock envenenado");
        if map.contains_key(key_or_mac) {
            return Some(key_or_mac.to_string());
        }
        let normalized = normalize_mac(key_or_mac);
        map.contains_key(&normalized).then_some(normalized)
    }

    /// Dispositivo por clave o MAC.
    pub fn get(&self, key_or_mac: &str) -> Option<Device> {
        let key = self.resolve_key(key_or_mac)?;
        let map = self.devices.read().expect("registry lock envenenado");
        map.get(&key).cloned()
    }

    /// Alias histórico de [`Self::get`]; acepta igualmente clave o MAC.
    pub fn get_by_mac(&self, mac: &str) -> Option<Device> {
        self.get(mac)
    }

    pub fn get_by_ip(&self, ip: &str) -> Option<Device> {
        let map = self.devices.read().expect("registry lock envenenado");
        map.values().find(|d| d.ip == ip).cloned()
    }

    /// Todos los dispositivos, ordenados por `last_seen` desc. Porta `get_all`.
    pub fn get_all(&self) -> Vec<Device> {
        let map = self.devices.read().expect("registry lock envenenado");
        let mut devices: Vec<Device> = map.values().cloned().collect();
        devices.sort_by(|a, b| b.last_seen.cmp(&a.last_seen));
        devices
    }

    /// Asigna el rol (`receipt`/`kitchen`/`bar`…). Acepta clave o MAC.
    pub fn set_role(&self, key_or_mac: &str, role: &str) -> Result<()> {
        let Some(key) = self.resolve_key(key_or_mac) else {
            return Ok(());
        };
        let mutated = {
            let mut map = self.devices.write().expect("registry lock envenenado");
            match map.get_mut(&key) {
                Some(device) => {
                    device.role = Some(role.to_string());
                    true
                }
                None => false,
            }
        };
        if mutated {
            self.save()?;
        }
        Ok(())
    }

    /// Marca online/offline. Acepta clave o MAC.
    pub fn set_status(&self, key_or_mac: &str, status: &str) -> Result<()> {
        let Some(key) = self.resolve_key(key_or_mac) else {
            return Ok(());
        };
        let mutated = {
            let mut map = self.devices.write().expect("registry lock envenenado");
            match map.get_mut(&key) {
                Some(device) => {
                    device.status = status.to_string();
                    true
                }
                None => false,
            }
        };
        if mutated {
            self.save()?;
        }
        Ok(())
    }

    /// Renombra el dispositivo. Acepta clave o MAC.
    pub fn set_name(&self, key_or_mac: &str, name: &str) -> Result<()> {
        let Some(key) = self.resolve_key(key_or_mac) else {
            return Ok(());
        };
        let mutated = {
            let mut map = self.devices.write().expect("registry lock envenenado");
            match map.get_mut(&key) {
                Some(device) => {
                    device.name = name.to_string();
                    true
                }
                None => false,
            }
        };
        if mutated {
            self.save()?;
        }
        Ok(())
    }

    /// Actualiza la IP (auto-recuperación tras cambio DHCP). Porta `update_ip`.
    /// Acepta clave o MAC — pero solo tiene sentido con MAC: sin ella no se puede reconocer al
    /// dispositivo en una IP nueva (y la clave, que ES la IP, ya no valdría).
    pub fn update_ip(&self, key_or_mac: &str, new_ip: &str) -> Result<()> {
        let Some(key) = self.resolve_key(key_or_mac) else {
            return Ok(());
        };
        let mutated = {
            let mut map = self.devices.write().expect("registry lock envenenado");
            match map.get_mut(&key) {
                Some(device) => {
                    device.ip = new_ip.to_string();
                    device.last_seen = now_iso();
                    true
                }
                None => false,
            }
        };
        if mutated {
            self.save()?;
        }
        Ok(())
    }

    /// Borra el dispositivo del registro. Acepta clave o MAC.
    pub fn remove(&self, key_or_mac: &str) -> Result<()> {
        let Some(key) = self.resolve_key(key_or_mac) else {
            return Ok(());
        };
        let mutated = {
            let mut map = self.devices.write().expect("registry lock envenenado");
            map.remove(&key).is_some()
        };
        if mutated {
            self.save()?;
        }
        Ok(())
    }
}

/// Envoltorio para (de)serializar el fichero `{ "devices": { MAC: Device } }`.
#[derive(serde::Deserialize)]
struct DevicesFile {
    #[serde(default)]
    devices: HashMap<String, Device>,
}

/// Eventos que el watchdog comunica al consumidor (mapean a `device_recovered`/`device_lost`).
#[derive(Debug, Clone)]
pub enum WatchdogEvent {
    Recovered(Device),
    Lost(Device),
}

/// Intervalos del watchdog (porta las constantes de `watchdog.py`).
#[derive(Debug, Clone, Copy)]
pub struct WatchdogConfig {
    pub check_interval_s: u64,
    pub recovery_interval_s: u64,
    pub connect_timeout_ms: u64,
}

impl Default for WatchdogConfig {
    fn default() -> Self {
        Self { check_interval_s: 30, recovery_interval_s: 120, connect_timeout_ms: 1000 }
    }
}

/// Watchdog en segundo plano: comprueba salud de los dispositivos conocidos y, para los offline,
/// re-escanea la red para localizarlos por MAC en una IP nueva. Porta `DeviceWatchdog`.
pub struct Watchdog {
    config: WatchdogConfig,
    /// Canal opcional hacia el consumidor (bridge#8): los `WatchdogEvent` se publican aquí
    /// además de por `tracing`. Sin canal, el comportamiento es solo-log como antes.
    events: Option<tokio::sync::mpsc::UnboundedSender<WatchdogEvent>>,
}

impl Watchdog {
    pub fn new(config: WatchdogConfig) -> Self {
        Self { config, events: None }
    }

    /// Cablea el canal de eventos hacia el consumidor (estilo builder; la firma de `run`
    /// permanece intacta).
    pub fn with_events(mut self, events: tokio::sync::mpsc::UnboundedSender<WatchdogEvent>) -> Self {
        self.events = Some(events);
        self
    }

    /// Publica un evento al consumidor si hay canal cableado.
    fn emit(&self, event: WatchdogEvent) {
        if let Some(tx) = &self.events {
            let _ = tx.send(event);
        }
    }

    /// Bucle principal: `check_devices` cada `check_interval`, `recovery_scan` cada
    /// `recovery_interval`. Porta `_run`.
    pub async fn run(&self, registry: &DeviceRegistry) {
        let check_interval = Duration::from_secs(self.config.check_interval_s);
        let recovery_interval = Duration::from_secs(self.config.recovery_interval_s);

        // Espera inicial para dejar estabilizar el sistema (espejo de `_stop_event.wait(5)`).
        tokio::time::sleep(Duration::from_secs(5)).await;

        let mut last_recovery = Instant::now() - recovery_interval;

        loop {
            self.check_devices(registry).await;

            if last_recovery.elapsed() >= recovery_interval {
                self.recovery_scan(registry).await;
                last_recovery = Instant::now();
            }

            tokio::time::sleep(check_interval).await;
        }
    }

    /// Does the watchdog watch over this device at all? (ADR-0204, hub#388)
    ///
    /// Only NETWORK devices: the whole toolbox here is IP-shaped — a TCP probe for health, an ARP
    /// sweep for recovery. A Bluetooth SPP printer has neither an IP to probe nor a subnet to be
    /// found on, so "monitoring" it could only mark it offline forever, and the recovery sweep —
    /// which hunts by MAC, the one thing a BT printer always has — would happily "recover" it
    /// onto some LAN device's IP. Phase 1 gives BT devices no health path on purpose.
    pub fn monitors(device: &Device) -> bool {
        device.kind == "network"
    }

    /// Comprueba la alcanzabilidad de todos los dispositivos conocidos. Porta `_check_devices`.
    async fn check_devices(&self, registry: &DeviceRegistry) {
        for device in registry.get_all() {
            if !Self::monitors(&device) {
                continue;
            }
            // El chequeo de salud solo necesita IP: se hace por `key`, así que las impresoras sin
            // MAC (todas en Android) también se vigilan. La MAC solo hace falta para el recovery
            // scan, más abajo.
            if device.ip.is_empty() {
                continue;
            }

            let port = if device.port == 0 { ESCPOS_NETWORK_PORT } else { device.port };
            let reachable = tcp_check(&device.ip, port, self.config.connect_timeout_ms).await;

            if reachable && device.status != "online" {
                if let Err(e) = registry.set_status(&device.key, "online") {
                    tracing::warn!("no se pudo persistir status online de {}: {e}", device.key);
                }
                tracing::info!(
                    "dispositivo {} ({}) de nuevo online en {}:{}",
                    device.name,
                    device.key,
                    device.ip,
                    port
                );
                let recovered = registry.get(&device.key).unwrap_or_else(|| device.clone());
                self.emit(WatchdogEvent::Recovered(recovered));
            } else if !reachable && device.status == "online" {
                if let Err(e) = registry.set_status(&device.key, "offline") {
                    tracing::warn!("no se pudo persistir status offline de {}: {e}", device.key);
                }
                tracing::warn!(
                    "dispositivo {} ({}) pasó a offline en {}:{}",
                    device.name,
                    device.key,
                    device.ip,
                    port
                );
                let lost = registry.get(&device.key).unwrap_or_else(|| device.clone());
                self.emit(WatchdogEvent::Lost(lost));
            }
        }
    }

    /// Escaneo de recuperación completo: por cada dispositivo offline, barre la subred buscándolo
    /// por MAC en una IP nueva. Porta `_recovery_scan`.
    async fn recovery_scan(&self, registry: &DeviceRegistry) {
        // Solo entran los que TIENEN MAC: reconocer una impresora en una IP nueva exige una
        // identidad que no dependa de la IP, y la clave de las que no tienen MAC *es* la IP.
        // Sin ARP no hay recuperación posible tras un cambio de DHCP — es un límite real, no una
        // omisión: en Android el usuario tendrá que volver a descubrir la impresora.
        let mut mac_lookup: HashMap<String, Device> = registry
            .get_all()
            .into_iter()
            // A Bluetooth printer always has a MAC and never has an IP — the perfect FALSE
            // candidate for an ARP-based recovery. It is not lost on the LAN; it was never there.
            .filter(Self::monitors)
            .filter(|d| d.status == "offline")
            .filter_map(|d| d.mac.clone().map(|mac| (mac, d)))
            .collect();

        if mac_lookup.is_empty() {
            return;
        }

        tracing::info!("recovery scan: buscando {} dispositivo(s) offline", mac_lookup.len());

        let subnet = match local_subnet_prefix() {
            Some(s) => s,
            None => {
                tracing::warn!("recovery scan: no se pudo determinar la subred local");
                return;
            }
        };

        for i in 1u8..=254 {
            if mac_lookup.is_empty() {
                break; // Todos los offline recuperados.
            }

            let ip = format!("{subnet}.{i}");

            // Comprobación TCP rápida en el puerto 9100.
            if !tcp_check(&ip, ESCPOS_NETWORK_PORT, self.config.connect_timeout_ms).await {
                continue;
            }

            // Algo responde en 9100: resolver su MAC.
            let mac = match get_mac_for_ip(&ip) {
                Some(m) => m,
                None => continue,
            };

            if let Some(device) = mac_lookup.remove(&mac) {
                tracing::info!(
                    "RECUPERADO dispositivo {} ({}): {} -> {}",
                    device.name,
                    mac,
                    device.ip,
                    ip
                );
                if let Err(e) = registry.update_ip(&mac, &ip) {
                    tracing::warn!("no se pudo actualizar IP de {mac}: {e}");
                }
                if let Err(e) = registry.set_status(&mac, "online") {
                    tracing::warn!("no se pudo marcar online {mac}: {e}");
                }
                let recovered = registry.get_by_mac(&mac).unwrap_or(device);
                self.emit(WatchdogEvent::Recovered(recovered));
            }
        }

        let still_offline = mac_lookup.len();
        if still_offline > 0 {
            tracing::info!("recovery scan completo: {still_offline} dispositivo(s) siguen offline");
        }
    }
}

/// Comprueba si un puerto TCP está abierto. Porta `_tcp_check`.
pub async fn tcp_check(host: &str, port: u16, timeout_ms: u64) -> bool {
    matches!(
        tokio::time::timeout(
            Duration::from_millis(timeout_ms),
            tokio::net::TcpStream::connect((host, port)),
        )
        .await,
        Ok(Ok(_))
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Ruta aislada por test bajo el temp del sistema (el registro escribe a disco).
    fn temp_registry(name: &str) -> (DeviceRegistry, PathBuf) {
        let dir = std::env::temp_dir().join(format!("erplora-registry-test-{name}"));
        let _ = std::fs::remove_dir_all(&dir);
        let path = dir.join("devices.json");
        (DeviceRegistry::load(path.clone()), path)
    }

    // ── tcp_check: la sonda de alcanzabilidad del watchdog ──────────────────────────────────────

    /// **La sonda distingue viva de apagada, y es lo único que lo hace.** El watchdog marca
    /// `offline` y dispara el barrido de recuperación a partir de esta respuesta: si dijera
    /// siempre `true`, una impresora que cambió de IP por DHCP se quedaría marcada online para
    /// siempre y los tiques se irían a una dirección que ya no es suya.
    #[tokio::test]
    async fn the_probe_says_reachable_only_while_something_is_listening() {
        let mock = crate::test_support::MockPrinter::start().await;
        assert!(
            tcp_check(&mock.target.host, mock.target.port, 500).await,
            "con un listener arriba la sonda tiene que ver la impresora"
        );

        let dead = crate::test_support::unreachable_target();
        assert!(
            !tcp_check(&dead.host, dead.port, 500).await,
            "un puerto cerrado es una impresora apagada, no una viva"
        );
    }

    /// Un destino que ni siquiera resuelve/enruta no puede colgar la sonda: el watchdog barre 254
    /// direcciones en serie, así que una sola espera sin techo congela la recuperación entera.
    #[tokio::test]
    async fn the_probe_gives_up_within_its_timeout() {
        // `192.0.2.0/24` es TEST-NET-1 (RFC 5737): no se enruta, así que el connect no responde.
        let started = Instant::now();
        assert!(!tcp_check("192.0.2.1", ESCPOS_NETWORK_PORT, 120).await);
        assert!(
            started.elapsed() < Duration::from_millis(2_000),
            "la sonda debe rendirse con su timeout, no con el del SO (tardó {:?})",
            started.elapsed()
        );
    }

    // ── ADR-0204 / hub#388: the watchdog is a NETWORK mechanism, and says so ───────────────────
    //
    // Its whole toolbox is IP-shaped: a TCP probe to decide alive/dead and an ARP sweep to find a
    // printer that DHCP moved. A Bluetooth SPP printer has neither an IP to probe nor a subnet to
    // be found on — running either against it can only produce noise (a permanent "offline") or a
    // false recovery onto some LAN device that happens to share the MAC. Phase 1 of ADR-0204 gives
    // BT devices NO health path on purpose; this predicate is where that decision lives.

    fn device_of_kind(kind: &str, ip: &str) -> Device {
        Device {
            key: "AA:BB:CC:DD:EE:FF".into(),
            mac: Some("AA:BB:CC:DD:EE:FF".into()),
            ip: ip.into(),
            port: 0,
            name: "Printer".into(),
            role: None,
            kind: kind.into(),
            first_seen: "2026-08-13T00:00:00".into(),
            last_seen: "2026-08-13T00:00:00".into(),
            status: "online".into(),
        }
    }

    #[test]
    fn the_watchdog_monitors_network_devices_and_leaves_bluetooth_alone() {
        assert!(Watchdog::monitors(&device_of_kind("network", "10.0.0.5")));
        assert!(
            !Watchdog::monitors(&device_of_kind("bluetooth", "")),
            "a BT printer has no IP to probe: 'monitoring' it can only mark it offline forever"
        );
    }

    #[test]
    fn a_bluetooth_device_never_enters_the_recovery_sweep() {
        // The recovery sweep hunts offline devices BY MAC across the local subnet — and a BT
        // printer always HAS a MAC, so without this gate it is the perfect false candidate: any
        // LAN device answering 9100 with a matching-looking MAC would "recover" it onto an IP it
        // never had.
        let bt = {
            let mut d = device_of_kind("bluetooth", "");
            d.status = "offline".into();
            d
        };
        assert!(!Watchdog::monitors(&bt));
    }

    // ── device_key: la identidad estable ────────────────────────────────────────────────────────

    #[test]
    fn la_clave_es_la_mac_normalizada_cuando_se_conoce() {
        assert_eq!(device_key(Some("aa-bb-cc-dd-ee-f1"), "10.0.0.5", 9100), "AA:BB:CC:DD:EE:F1");
    }

    #[test]
    fn la_clave_cae_al_printer_id_cuando_no_hay_mac() {
        // En Android NUNCA hay MAC (no existe el binario `arp` y /proc/net/arp está restringido
        // desde Android 10), y en escritorio falla con VPN, contenedores o firewall.
        assert_eq!(device_key(None, "10.0.0.5", 9100), "network:10.0.0.5:9100");
        assert_eq!(device_key(Some("   "), "10.0.0.5", 9100), "network:10.0.0.5:9100");
    }

    // ── El bug: sin MAC no se podía registrar ni asignar rol ────────────────────────────────────

    #[test]
    fn registra_una_impresora_sin_mac() {
        let (registry, _) = temp_registry("registra-sin-mac");
        let device = registry.register(None, "10.0.0.5", 9100, "Caja", "network").unwrap();

        assert_eq!(device.key, "network:10.0.0.5:9100");
        assert_eq!(device.mac, None, "sin ARP no se inventa una MAC");
        assert_eq!(registry.get_all().len(), 1, "la impresora DEBE entrar en el registro");
    }

    #[test]
    fn asigna_rol_a_una_impresora_sin_mac() {
        // Este es el defecto que bloqueaba el módulo `printing` en Android: sin MAC el
        // dispositivo no llegaba a `devices.json`, `get_devices` devolvía [] y no se podía
        // marcar ninguna impresora como cocina/barra/caja.
        let (registry, _) = temp_registry("rol-sin-mac");
        let device = registry.register(None, "10.0.0.7", 9100, "Cocina", "network").unwrap();

        registry.set_role(&device.key, "kitchen").unwrap();

        let stored = registry.get(&device.key).expect("el dispositivo sigue en el registro");
        assert_eq!(stored.role.as_deref(), Some("kitchen"));
    }

    // ── Compatibilidad hacia atrás: con MAC todo sigue igual ────────────────────────────────────

    #[test]
    fn con_mac_la_clave_sigue_siendo_la_mac_normalizada() {
        let (registry, _) = temp_registry("clave-es-mac");
        let device = registry
            .register(Some("aa-bb-cc-dd-ee-f2"), "10.0.0.8", 9100, "Barra", "network")
            .unwrap();

        assert_eq!(device.key, "AA:BB:CC:DD:EE:F2");
        assert_eq!(device.mac.as_deref(), Some("AA:BB:CC:DD:EE:F2"));
    }

    #[test]
    fn las_mutaciones_aceptan_indistintamente_la_mac_o_la_clave() {
        // El protocolo JSON llama `mac` a este parámetro (`SetDeviceRole { mac }`) y los
        // llamadores existentes (apps/tauri) le pasan lo que tengan a mano.
        let (registry, _) = temp_registry("mac-o-clave");
        registry
            .register(Some("AA:BB:CC:DD:EE:F3"), "10.0.0.9", 9100, "Caja", "network")
            .unwrap();

        registry.set_role("aa-bb-cc-dd-ee-f3", "receipt").unwrap();
        assert_eq!(
            registry.get("AA:BB:CC:DD:EE:F3").unwrap().role.as_deref(),
            Some("receipt"),
            "una MAC sin normalizar debe resolver al mismo dispositivo"
        );

        registry.set_name("AA:BB:CC:DD:EE:F3", "Caja principal").unwrap();
        assert_eq!(registry.get("AA:BB:CC:DD:EE:F3").unwrap().name, "Caja principal");
    }

    #[test]
    fn re_registrar_preserva_first_seen_y_el_rol() {
        let (registry, _) = temp_registry("preserva");
        let first = registry.register(None, "10.0.0.10", 9100, "Caja", "network").unwrap();
        registry.set_role(&first.key, "receipt").unwrap();

        let again = registry.register(None, "10.0.0.10", 9100, "Caja renombrada", "network").unwrap();

        assert_eq!(again.first_seen, first.first_seen, "first_seen no se pisa");
        assert_eq!(again.role.as_deref(), Some("receipt"), "el rol asignado sobrevive");
        assert_eq!(registry.get_all().len(), 1, "no se duplica la entrada");
    }

    // ── Datos ya persistidos en casa de clientes ────────────────────────────────────────────────

    #[test]
    fn carga_un_devices_json_antiguo_sin_campo_key() {
        // `devices.json` es dato de usuario: los ficheros escritos antes de esta versión están
        // indexados por MAC y no traen `key`. Deben seguir cargando y quedar operativos.
        let (_, path) = temp_registry("legacy");
        std::fs::create_dir_all(path.parent().unwrap()).unwrap();
        std::fs::write(
            &path,
            r#"{"devices":{"AA:BB:CC:DD:EE:F4":{"mac":"AA:BB:CC:DD:EE:F4","ip":"10.0.0.11",
               "port":9100,"name":"Cocina","role":"kitchen","type":"network",
               "first_seen":"2026-01-01T00:00:00","last_seen":"2026-01-01T00:00:00",
               "status":"online"}}}"#,
        )
        .unwrap();

        let registry = DeviceRegistry::load(path);
        let device = registry.get("AA:BB:CC:DD:EE:F4").expect("el dispositivo legacy carga");

        assert_eq!(device.key, "AA:BB:CC:DD:EE:F4", "la clave se rellena desde la MAC");
        assert_eq!(device.role.as_deref(), Some("kitchen"), "el rol asignado no se pierde");
    }
}
