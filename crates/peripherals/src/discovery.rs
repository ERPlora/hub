//! Descubrimiento de impresoras en red + parseo de `printer_id`.
//! Porta `bridge/ERPlora-Bridge-desktop/erplora_bridge/hardware/discovery.py`, **solo la rama
//! de red** (USB/Bluetooth descartados, §2.7).
//!
//! Métodos: escaneo de subred /24 al puerto 9100 + mDNS (`_pdl-datastream._tcp`,`_ipp._tcp`),
//! deduplicado, y enriquecido con MAC/ARP para registrar en `registry::DeviceRegistry`.

use std::collections::HashSet;
use std::net::SocketAddr;
use std::time::Duration;

use tokio::net::TcpStream;
use tokio::task::JoinSet;

use crate::protocol::PrinterInfo;
use crate::registry::DeviceRegistry;
use crate::{Result, ESCPOS_NETWORK_PORT};

/// Timeout del `connect` TCP durante el escaneo de subred (espejo de `timeout=0.3` en Python).
const SCAN_CONNECT_TIMEOUT: Duration = Duration::from_millis(300);
/// Ventana de escucha mDNS (espejo de `time.sleep(1.5)` en Python).
const MDNS_BROWSE_WINDOW: Duration = Duration::from_millis(1500);
/// Tipos de servicio mDNS sondeados (espejo de la lista de `_discover_mdns`).
const MDNS_SERVICE_TYPES: [&str; 2] = ["_pdl-datastream._tcp.local.", "_ipp._tcp.local."];

/// Destino de impresión por red. Sustituye al tuple `('network', {host, port})` de Python.
#[derive(Debug, Clone)]
pub struct NetworkTarget {
    pub host: String,
    pub port: u16,
}

impl NetworkTarget {
    /// Para `tokio::net::TcpStream::connect`.
    pub fn socket_addr(&self) -> String {
        format!("{}:{}", self.host, self.port)
    }
}

/// Parsea un `printer_id` `network:{ip}:{port}` → `NetworkTarget`.
/// Porta `parse_printer_id`, restringido a la rama `network` (rechaza `usb:`/`bluetooth:`).
pub fn parse_printer_id(printer_id: &str) -> Result<NetworkTarget> {
    // `split(':', 1)` de Python: separa el esquema del resto por el PRIMER ':'.
    let (scheme, rest) = match printer_id.split_once(':') {
        Some((s, r)) => (s, r),
        None => (printer_id, ""),
    };

    if scheme != "network" {
        return Err(crate::PeripheralError::InvalidPrinterId(format!(
            "tipo de impresora no soportado (red-only): {scheme}"
        )));
    }

    // `rsplit(':', 1)` de Python: host puede contener ':' (p.ej. IPv6); el puerto es lo último.
    let (host, port) = match rest.rsplit_once(':') {
        Some((h, p)) => {
            let port = p.parse::<u16>().map_err(|_| {
                crate::PeripheralError::InvalidPrinterId(format!("puerto inválido en: {printer_id}"))
            })?;
            (h.to_string(), port)
        }
        None => (rest.to_string(), ESCPOS_NETWORK_PORT),
    };

    if host.is_empty() {
        return Err(crate::PeripheralError::InvalidPrinterId(format!(
            "host vacío en: {printer_id}"
        )));
    }

    Ok(NetworkTarget { host, port })
}

/// Descubre todas las impresoras de red (mDNS + escaneo de subred), deduplica, enriquece con
/// MAC y registra en `registry`. Porta `discover_all(registry)`.
pub async fn discover_printers(registry: &DeviceRegistry) -> Result<Vec<PrinterInfo>> {
    // mDNS gana ante colisión de IP → se inserta primero y el escaneo solo añade IDs nuevos.
    let mut printers = discover_mdns().await?;

    let mut seen_ids: HashSet<String> = printers.iter().map(|p| p.id.clone()).collect();
    for p in discover_subnet_scan(ESCPOS_NETWORK_PORT).await? {
        if seen_ids.insert(p.id.clone()) {
            printers.push(p);
        }
    }

    // Enriquece cada impresora de red con su MAC (ARP) y la registra. Espejo del bucle final de
    // `discover_all`: cualquier fallo de resolución/registro se ignora, no rompe el descubrimiento.
    for p in printers.iter_mut() {
        if p.kind != "network" {
            continue;
        }
        // `network:IP:PORT` → IP es el 2º segmento.
        let (ip, port) = match parse_printer_id(&p.id) {
            Ok(t) => (t.host, t.port),
            Err(_) => continue,
        };

        if let Some(mac) = crate::registry::get_mac_for_ip(&ip) {
            p.mac = Some(mac.clone());
            // El registro puede aún ser `todo!()` en desarrollo paralelo; ignoramos su `Result`.
            let _ = registry.register(&mac, &ip, port, &p.name, "network");
        }
    }

    Ok(printers)
}

/// Escaneo de subred: prueba TCP `connect` al puerto 9100 en `{prefix}.1..=254`.
/// Porta `_discover_network_scan` + `_get_local_subnet`.
pub async fn discover_subnet_scan(port: u16) -> Result<Vec<PrinterInfo>> {
    let subnet_prefix = match local_subnet_prefix() {
        Some(p) => p,
        None => return Ok(Vec::new()),
    };

    tracing::info!("escaneando subred {subnet_prefix}.0/24 buscando impresoras en :{port}");

    // 254 sondas concurrentes: `tokio::time::timeout` sobre `TcpStream::connect`.
    let mut set: JoinSet<Option<String>> = JoinSet::new();
    for i in 1u8..=254 {
        let ip = format!("{subnet_prefix}.{i}");
        set.spawn(async move {
            let addr = format!("{ip}:{port}");
            match tokio::time::timeout(SCAN_CONNECT_TIMEOUT, TcpStream::connect(&addr)).await {
                Ok(Ok(_stream)) => Some(ip),
                _ => None,
            }
        });
    }

    let mut printers = Vec::new();
    while let Some(joined) = set.join_next().await {
        if let Ok(Some(ip)) = joined {
            tracing::debug!("impresora de red encontrada en {ip}:{port}");
            printers.push(PrinterInfo {
                id: format!("network:{ip}:{port}"),
                name: format!("Network Printer ({ip})"),
                kind: "network".into(),
                status: "ready".into(),
                paper_width: 80,
                mac: None,
            });
        }
    }

    Ok(printers)
}

/// Descubrimiento mDNS/Bonjour. Porta `_discover_mdns`.
/// Robusto: ante cualquier error devuelve `Vec` vacío en lugar de propagar (espejo del try/except).
pub async fn discover_mdns() -> Result<Vec<PrinterInfo>> {
    // El daemon de `mdns-sd` usa canales `flume` síncronos; lo ejecutamos en un hilo bloqueante
    // para no acaparar el runtime async durante la ventana de escucha.
    let result = tokio::task::spawn_blocking(browse_mdns_blocking).await;

    match result {
        Ok(printers) => Ok(printers),
        Err(e) => {
            tracing::error!("error en descubrimiento mDNS (join): {e}");
            Ok(Vec::new())
        }
    }
}

/// Lógica bloqueante de mDNS: arranca el daemon, navega los tipos de servicio, escucha la ventana
/// y mapea cada `ServiceResolved` a `PrinterInfo`. Nunca falla: ante error registra y sigue.
fn browse_mdns_blocking() -> Vec<PrinterInfo> {
    use mdns_sd::{ServiceDaemon, ServiceEvent};

    let mut printers: Vec<PrinterInfo> = Vec::new();
    let mut seen_ids: HashSet<String> = HashSet::new();

    let daemon = match ServiceDaemon::new() {
        Ok(d) => d,
        Err(e) => {
            tracing::error!("no se pudo crear el daemon mDNS: {e}");
            return printers;
        }
    };

    let mut receivers = Vec::new();
    for service_type in MDNS_SERVICE_TYPES {
        match daemon.browse(service_type) {
            Ok(rx) => receivers.push(rx),
            Err(e) => tracing::debug!("no se pudo navegar {service_type}: {e}"),
        }
    }

    let deadline = std::time::Instant::now() + MDNS_BROWSE_WINDOW;
    loop {
        let now = std::time::Instant::now();
        if now >= deadline {
            break;
        }
        let remaining = deadline - now;

        // Recorre todos los receptores con un timeout corto; al expirar la ventana, salimos.
        let mut progressed = false;
        for rx in &receivers {
            let slice = remaining.min(Duration::from_millis(100));
            match rx.recv_timeout(slice) {
                Ok(ServiceEvent::ServiceResolved(info)) => {
                    progressed = true;
                    if let Some(printer) = service_to_printer(&info) {
                        if seen_ids.insert(printer.id.clone()) {
                            tracing::debug!(
                                "impresora mDNS encontrada: {} ({})",
                                printer.name,
                                printer.id
                            );
                            printers.push(printer);
                        }
                    }
                }
                Ok(_) => {
                    progressed = true;
                }
                Err(_) => {
                    // timeout/desconexión de este receptor: probar el siguiente.
                }
            }
        }

        if !progressed {
            // Nada pendiente; evita busy-loop hasta agotar la ventana.
            std::thread::sleep(Duration::from_millis(50));
        }
    }

    let _ = daemon.shutdown();
    printers
}

/// Mapea un `ServiceInfo` resuelto a `PrinterInfo` de red. `None` si no tiene direcciones.
fn service_to_printer(info: &mdns_sd::ServiceInfo) -> Option<PrinterInfo> {
    let ip = info.get_addresses().iter().next()?.to_string();
    let port = match info.get_port() {
        0 => ESCPOS_NETWORK_PORT,
        p => p,
    };
    // Nombre = primer segmento del fullname (espejo de `info.name.split('.')[0]`).
    let fullname = info.get_fullname();
    let name = match fullname.split('.').next() {
        Some(n) if !n.is_empty() => n.to_string(),
        _ => format!("mDNS Printer ({ip})"),
    };

    Some(PrinterInfo {
        id: format!("network:{ip}:{port}"),
        name,
        kind: "network".into(),
        status: "ready".into(),
        paper_width: 80,
        mac: None,
    })
}

/// Detecta el prefijo /24 de la subred local (p.ej. `192.168.1`). Porta `_get_local_subnet`:
/// abre un socket UDP "conectado" a 8.8.8.8:80 y lee la IP local de salida (sin enviar nada).
fn local_subnet_prefix() -> Option<String> {
    let sock = std::net::UdpSocket::bind("0.0.0.0:0").ok()?;
    sock.connect("8.8.8.8:80").ok()?;
    let local: SocketAddr = sock.local_addr().ok()?;
    let ip = local.ip().to_string();
    let mut parts = ip.split('.');
    let a = parts.next()?;
    let b = parts.next()?;
    let c = parts.next()?;
    // Solo IPv4 tiene 4 octetos; si no, no es una subred /24 escaneable.
    parts.next()?;
    Some(format!("{a}.{b}.{c}"))
}
