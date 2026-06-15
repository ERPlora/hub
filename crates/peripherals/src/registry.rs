//! Registro persistente de dispositivos (JSON) + resolución MAC vía ARP + watchdog de
//! auto-recuperación.
//!
//! Porta:
//!   - `hardware/network.py` → `DeviceRegistry` + `get_mac_for_ip` + `_normalize_mac`.
//!   - `hardware/watchdog.py` → `Watchdog` (health-check periódico + recovery scan por MAC
//!     cuando la IP cambia por DHCP).

use std::collections::HashMap;
use std::net::SocketAddr;
use std::path::PathBuf;
use std::process::Command;
use std::sync::RwLock;
use std::time::{Duration, Instant};

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

/// Marca de tiempo ISO con resolución de segundos. Espejo de `datetime.now().isoformat(timespec='seconds')`.
fn now_iso() -> String {
    chrono::Local::now().format("%Y-%m-%dT%H:%M:%S").to_string()
}

/// Registro persistente MAC → dispositivo, respaldado por `devices.json` en el dir de config.
/// Porta `DeviceRegistry`. (Persistencia con `RwLock` síncrono + escritura al disco.)
pub struct DeviceRegistry {
    path: PathBuf,
    /// Mapa en memoria MAC → dispositivo. `RwLock` síncrono: las operaciones son rápidas y no
    /// se mantiene el lock a través de un `await`.
    devices: RwLock<HashMap<String, Device>>,
}

impl DeviceRegistry {
    /// Carga el registro desde `path` (vacío si no existe o está corrupto). Porta `__init__`/`load`.
    pub fn load(path: PathBuf) -> Self {
        let devices = if path.exists() {
            match std::fs::read_to_string(&path) {
                Ok(text) => match serde_json::from_str::<DevicesFile>(&text) {
                    Ok(file) => file.devices,
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

    /// Alta/actualización por MAC; preserva `first_seen` y `role`. Porta `register`.
    pub fn register(&self, mac: &str, ip: &str, port: u16, name: &str, kind: &str) -> Result<Device> {
        let mac = normalize_mac(mac);
        let now = now_iso();

        let device = {
            let mut map = self.devices.write().expect("registry lock envenenado");
            match map.get_mut(&mac) {
                Some(existing) => {
                    existing.ip = ip.to_string();
                    existing.port = port;
                    existing.name = name.to_string();
                    existing.kind = kind.to_string();
                    existing.last_seen = now;
                    existing.clone()
                }
                None => {
                    let device = Device {
                        mac: mac.clone(),
                        ip: ip.to_string(),
                        port,
                        name: name.to_string(),
                        role: None,
                        kind: kind.to_string(),
                        first_seen: now.clone(),
                        last_seen: now,
                        status: "online".to_string(),
                    };
                    map.insert(mac.clone(), device.clone());
                    device
                }
            }
        };

        self.save()?;
        Ok(device)
    }

    pub fn get_by_mac(&self, mac: &str) -> Option<Device> {
        let mac = normalize_mac(mac);
        let map = self.devices.read().expect("registry lock envenenado");
        map.get(&mac).cloned()
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

    pub fn set_role(&self, mac: &str, role: &str) -> Result<()> {
        let mac = normalize_mac(mac);
        let mutated = {
            let mut map = self.devices.write().expect("registry lock envenenado");
            match map.get_mut(&mac) {
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

    pub fn set_status(&self, mac: &str, status: &str) -> Result<()> {
        let mac = normalize_mac(mac);
        let mutated = {
            let mut map = self.devices.write().expect("registry lock envenenado");
            match map.get_mut(&mac) {
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

    pub fn set_name(&self, mac: &str, name: &str) -> Result<()> {
        let mac = normalize_mac(mac);
        let mutated = {
            let mut map = self.devices.write().expect("registry lock envenenado");
            match map.get_mut(&mac) {
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
    pub fn update_ip(&self, mac: &str, new_ip: &str) -> Result<()> {
        let mac = normalize_mac(mac);
        let mutated = {
            let mut map = self.devices.write().expect("registry lock envenenado");
            match map.get_mut(&mac) {
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

    pub fn remove(&self, mac: &str) -> Result<()> {
        let mac = normalize_mac(mac);
        let mutated = {
            let mut map = self.devices.write().expect("registry lock envenenado");
            map.remove(&mac).is_some()
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

    /// Comprueba la alcanzabilidad de todos los dispositivos conocidos. Porta `_check_devices`.
    async fn check_devices(&self, registry: &DeviceRegistry) {
        for device in registry.get_all() {
            if device.ip.is_empty() || device.mac.is_empty() {
                continue;
            }

            let port = if device.port == 0 { ESCPOS_NETWORK_PORT } else { device.port };
            let reachable = tcp_check(&device.ip, port, self.config.connect_timeout_ms).await;

            if reachable && device.status != "online" {
                if let Err(e) = registry.set_status(&device.mac, "online") {
                    tracing::warn!("no se pudo persistir status online de {}: {e}", device.mac);
                }
                tracing::info!(
                    "dispositivo {} ({}) de nuevo online en {}:{}",
                    device.name,
                    device.mac,
                    device.ip,
                    port
                );
                let recovered = registry.get_by_mac(&device.mac).unwrap_or_else(|| device.clone());
                self.emit(WatchdogEvent::Recovered(recovered));
            } else if !reachable && device.status == "online" {
                if let Err(e) = registry.set_status(&device.mac, "offline") {
                    tracing::warn!("no se pudo persistir status offline de {}: {e}", device.mac);
                }
                tracing::warn!(
                    "dispositivo {} ({}) pasó a offline en {}:{}",
                    device.name,
                    device.mac,
                    device.ip,
                    port
                );
                let lost = registry.get_by_mac(&device.mac).unwrap_or_else(|| device.clone());
                self.emit(WatchdogEvent::Lost(lost));
            }
        }
    }

    /// Escaneo de recuperación completo: por cada dispositivo offline, barre la subred buscándolo
    /// por MAC en una IP nueva. Porta `_recovery_scan`.
    async fn recovery_scan(&self, registry: &DeviceRegistry) {
        let mut mac_lookup: HashMap<String, Device> = registry
            .get_all()
            .into_iter()
            .filter(|d| d.status == "offline")
            .map(|d| (d.mac.clone(), d))
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

/// Detecta el prefijo /24 de la subred local (p.ej. `192.168.1`). Réplica local de
/// `discovery::local_subnet_prefix` (que es privado): UDP "connect" a 8.8.8.8:80 sin enviar nada.
fn local_subnet_prefix() -> Option<String> {
    let sock = std::net::UdpSocket::bind("0.0.0.0:0").ok()?;
    sock.connect("8.8.8.8:80").ok()?;
    let local: SocketAddr = sock.local_addr().ok()?;
    let ip = local.ip().to_string();
    let mut parts = ip.split('.');
    let a = parts.next()?;
    let b = parts.next()?;
    let c = parts.next()?;
    parts.next()?; // Solo IPv4 tiene 4 octetos.
    Some(format!("{a}.{b}.{c}"))
}
