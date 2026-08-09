//! Descubrimiento de impresoras en red + parseo de `printer_id`.
//! Porta `bridge/ERPlora-Bridge-desktop/erplora_bridge/hardware/discovery.py`, **solo la rama
//! de red** (USB/Bluetooth descartados, §2.7).
//!
//! Métodos: escaneo de subred /24 al puerto 9100 + mDNS (`_pdl-datastream._tcp`,`_ipp._tcp`),
//! deduplicado, y enriquecido con MAC/ARP para registrar en `registry::DeviceRegistry`.

use std::collections::HashSet;
use std::net::SocketAddr;
use std::time::Duration;

use serde::{Deserialize, Serialize};
use tokio::net::TcpStream;
use tokio::task::JoinSet;

use crate::protocol::PrinterInfo;
use crate::registry::DeviceRegistry;
use crate::{Result, ESCPOS_NETWORK_PORT};

/// Timeout del `connect` TCP durante el escaneo de subred.
///
/// Eran 300 ms, heredados del `timeout=0.3` del Python. Un `connect` a una impresora encendida en
/// la misma LAN tarda milisegundos, así que 300 parecía de sobra — y no lo es: el margen no lo come
/// la impresora, lo come la CONTENCIÓN. Con el barrido compitiendo consigo mismo (el watchdog de
/// `registry` barre esta misma subred) o con la máquina cargada, el `connect` a la impresora REAL
/// se pasa de 300 ms y se descarta **sin un solo error**: «no hay impresoras».
///
/// Medido el 2026-08-09 contra una térmica encendida, dos barridos en paralelo: con 300 ms la
/// perdía 3 de 3; acotando la concurrencia a [`SCAN_MAX_IN_FLIGHT`] bajó a 1 de 3; con 1 s, 0 de 3.
/// Las dos mitades hacen falta.
///
/// El coste es el peor caso de un barrido sin nadie al otro lado: 254 direcciones en tandas de 64 →
/// 4 tandas × 1 s ≈ 4 s. Un descubrimiento se pide a mano y de tarde en tarde; perder la impresora
/// sale mucho más caro que esperar cuatro segundos.
const SCAN_CONNECT_TIMEOUT: Duration = Duration::from_millis(1000);
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

/// What the OS lets this process do on the local network — the one thing printer discovery cannot
/// work around, and the one every platform gates somewhere else: an Android runtime permission
/// (`ACCESS_LOCAL_NETWORK`, API 37+) or the macOS 15 local-network consent. This library cannot ask
/// the OS itself, so the shell that *can* states it here, on the way in.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum LocalNetworkAccess {
    /// Granted, or the platform has no such gate at all. The scan runs.
    Granted,
    /// The OS refused. The scan is deliberately NOT run: it could only ever come back empty, and
    /// an empty list reads exactly like "this venue has no printers".
    Denied { permission: String },
}

impl LocalNetworkAccess {
    /// The permission standing between us and the printers, if any. `None` = go ahead and look.
    pub fn blocked_by(&self) -> Option<&str> {
        match self {
            Self::Granted => None,
            Self::Denied { permission } => Some(permission),
        }
    }
}

/// Outcome of a discovery run.
///
/// It exists because `Vec<PrinterInfo>` cannot answer the only question that matters when it comes
/// back empty: did we look and find nothing, or were we never allowed to look? Those two need
/// **opposite** things from the user — plug a printer in, versus grant the app a permission — so
/// the difference has to survive all the way to the screen. Logging it is not enough.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(tag = "status", rename_all = "snake_case")]
pub enum PrinterDiscovery {
    /// The scan ran. `printers` is the honest answer, empty or not.
    Scanned { printers: Vec<PrinterInfo> },
    /// The scan never ran: the OS denied the permission it needs. `permission` names it so the
    /// screen can point at the exact toggle instead of guessing.
    #[serde(rename = "local_network_permission_denied")]
    PermissionDenied { permission: String },
}

/// The one wire string that means "the OS blocked the scan": the `status` of the outcome on the
/// invoke path and the `code` of the bridge's WS error frame. One literal for both transports, so
/// a screen only has to learn to branch once.
pub const LOCAL_NETWORK_PERMISSION_DENIED: &str = "local_network_permission_denied";

impl PrinterDiscovery {
    /// The printers found — `None` when the scan never ran, so an empty list can never be mistaken
    /// for "there are no printers here". That `Some(&[]) != None` is the whole point of the type.
    pub fn scanned_printers(&self) -> Option<&[PrinterInfo]> {
        match self {
            Self::Scanned { printers } => Some(printers),
            Self::PermissionDenied { .. } => None,
        }
    }

    /// The permission the OS refused, if that is what happened.
    pub fn denied_permission(&self) -> Option<&str> {
        match self {
            Self::Scanned { .. } => None,
            Self::PermissionDenied { permission } => Some(permission),
        }
    }
}

/// Discovers every network printer (mDNS + subnet sweep), deduplicates, enriches with the MAC and
/// registers them in `registry`. Ports `discover_all(registry)`.
///
/// `access` is not decoration: with the permission denied the sweep is 254 silent timeouts and an
/// mDNS window that resolves nothing, so it is skipped and the caller is told **why** there is no
/// list — instead of being handed an empty one it cannot tell from an empty venue.
pub async fn discover_printers(
    registry: &DeviceRegistry,
    access: LocalNetworkAccess,
) -> Result<PrinterDiscovery> {
    if let LocalNetworkAccess::Denied { permission } = access {
        tracing::warn!(
            %permission,
            "printer discovery skipped: the OS denies this app access to the local network"
        );
        return Ok(PrinterDiscovery::PermissionDenied { permission });
    }

    Ok(PrinterDiscovery::Scanned {
        printers: scan_network(registry).await?,
    })
}

/// The scan itself: mDNS + subnet sweep, deduplicated, MAC-enriched and registered.
async fn scan_network(registry: &DeviceRegistry) -> Result<Vec<PrinterInfo>> {
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

        // La MAC es un ENRIQUECIMIENTO, no un requisito: el registro se hace siempre. Antes el
        // `register` colgaba del `if let Some(mac)`, así que en Android —donde ARP nunca resuelve,
        // no existe el binario `arp` y `/proc/net/arp` está restringido desde Android 10— ninguna
        // impresora llegaba a `devices.json`: `get_devices` devolvía `[]` y no se podía asignar
        // ningún rol de cocina/barra/caja.
        p.mac = crate::registry::get_mac_for_ip(&ip);
        let _ = registry.register(p.mac.as_deref(), &ip, port, &p.name, "network");
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

    let ips: Vec<String> = (1u8..=254).map(|i| format!("{subnet_prefix}.{i}")).collect();
    let found = sweep_addresses(ips, move |ip| async move {
        let addr = format!("{ip}:{port}");
        matches!(
            tokio::time::timeout(SCAN_CONNECT_TIMEOUT, TcpStream::connect(&addr)).await,
            Ok(Ok(_))
        )
    })
    .await;

    let mut printers = Vec::new();
    {
        for ip in found {
            tracing::debug!("impresora de red encontrada en {ip}:{port}");
            printers.push(PrinterInfo {
                id: format!("network:{ip}:{port}"),
                name: format!("Network Printer ({ip})"),
                kind: "network".into(),
                // Responder al 9100 no dice qué idioma habla: una láser A4 de oficina también
                // escucha ahí. Sin más evidencia no se clasifica.
                category: crate::protocol::default_printer_category(),
                status: "ready".into(),
                paper_width: 80,
                mac: None,
            });
        }
    }

    Ok(printers)
}

/// Cuántas sondas pueden estar EN VUELO a la vez durante el barrido.
///
/// El barrido nació lanzando las 254 de golpe, y eso pierde impresoras de verdad: cada sonda tiene
/// [`SCAN_CONNECT_TIMEOUT`] (300 ms) para completar el `connect`, así que basta con que la máquina
/// vaya cargada —o que haya otro barrido a la vez, cosa que pasa: el watchdog de `registry` barre
/// esta misma subred— para que el `connect` a la impresora REAL se pase de 300 ms y se descarte.
///
/// Y el fallo es MUDO: el resultado es «no hay impresoras», que es exactamente lo que se ve en un
/// local sin impresora. Medido el 2026-08-09 contra una térmica encendida: con dos barridos
/// simultáneos la perdía 3 de cada 3 veces; en serie, 0 de 2.
///
/// 64 mantiene el barrido rápido (4 tandas) dando a cada `connect` una ventana que no se come la
/// contención.
pub const SCAN_MAX_IN_FLIGHT: usize = 64;

/// El barrido, separado de CÓMO se conecta.
///
/// La separación existe para poder fijarle el límite en un test sin red ni impresora: lo que hay
/// que garantizar es cuántas sondas coexisten, y eso con sockets de verdad solo se observa
/// provocando la congestión que se quiere evitar.
async fn sweep_addresses<C, F>(addresses: Vec<String>, probe: C) -> Vec<String>
where
    C: Fn(String) -> F + Clone + Send + 'static,
    F: std::future::Future<Output = bool> + Send + 'static,
{
    // El semáforo NO reduce lo que se sondea: se sondean las 254 igual, por tandas de
    // SCAN_MAX_IN_FLIGHT. Lo que acota es cuántas compiten a la vez por la red y por los 300 ms.
    let permisos = std::sync::Arc::new(tokio::sync::Semaphore::new(SCAN_MAX_IN_FLIGHT));

    let mut set: JoinSet<Option<String>> = JoinSet::new();
    for addr in addresses {
        let probe = probe.clone();
        let permisos = permisos.clone();
        set.spawn(async move {
            // `acquire_owned` solo falla si el semáforo se cierra, y aquí no se cierra nunca.
            let _permiso = permisos.acquire_owned().await.ok()?;
            probe(addr.clone()).await.then_some(addr)
        });
    }

    let mut hits = Vec::new();
    while let Some(joined) = set.join_next().await {
        if let Ok(Some(addr)) = joined {
            hits.push(addr);
        }
    }
    hits
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

    // Se conserva el tipo de servicio junto al receptor: es lo ÚNICO que permite distinguir una
    // impresora de oficina (`_ipp._tcp`) de una térmica, y se perdía al meter solo el `rx`.
    let mut receivers = Vec::new();
    for service_type in MDNS_SERVICE_TYPES {
        match daemon.browse(service_type) {
            Ok(rx) => receivers.push((service_type, rx)),
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
        for (service_type, rx) in &receivers {
            let slice = remaining.min(Duration::from_millis(100));
            match rx.recv_timeout(slice) {
                Ok(ServiceEvent::ServiceResolved(info)) => {
                    progressed = true;
                    if let Some(printer) = service_to_printer(&info, service_type) {
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
fn service_to_printer(info: &mdns_sd::ServiceInfo, service_type: &str) -> Option<PrinterInfo> {
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
        category: category_for_service(service_type).to_string(),
        status: "ready".into(),
        paper_width: 80,
        mac: None,
    })
}

/// Detecta el prefijo /24 de la subred local (p.ej. `192.168.1`). Porta `_get_local_subnet`:
/// abre un socket UDP "conectado" a 8.8.8.8:80 y lee la IP local de salida (sin enviar nada).
///
/// `pub(crate)` porque el watchdog de `registry` barre exactamente la misma subred: tenía su
/// propia copia de esta función, y dos copias de una regla es una que se queda atrás.
pub(crate) fn local_subnet_prefix() -> Option<String> {
    let sock = std::net::UdpSocket::bind("0.0.0.0:0").ok()?;
    sock.connect("8.8.8.8:80").ok()?;
    let local: SocketAddr = sock.local_addr().ok()?;
    subnet_prefix_of(&local.ip().to_string())
}

/// Los tres primeros octetos de una IPv4 (`192.168.1.42` → `192.168.1`). Cualquier otra cosa
/// —IPv6, una cadena corta— no tiene subred /24 que barrer y devuelve `None`.
fn subnet_prefix_of(ip: &str) -> Option<String> {
    let mut parts = ip.split('.');
    let a = parts.next()?;
    let b = parts.next()?;
    let c = parts.next()?;
    // Solo IPv4 tiene 4 octetos; si no, no es una subred /24 escaneable.
    parts.next()?;
    Some(format!("{a}.{b}.{c}"))
}

/// Clasifica una impresora por el servicio mDNS que la anunció.
///
/// `_ipp._tcp` lo publican las multifunción de oficina y las AirPrint, y prácticamente ninguna
/// térmica ESC/POS → es la única señal fiable de "A4". `_pdl-datastream._tcp` (impresión cruda al
/// 9100) lo anuncian **las dos familias**, así que no clasifica nada.
pub fn category_for_service(service_type: &str) -> &'static str {
    if service_type.starts_with("_ipp.") {
        crate::protocol::PRINTER_CATEGORY_A4
    } else {
        crate::protocol::PRINTER_CATEGORY_UNKNOWN
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::protocol::{PRINTER_CATEGORY_A4, PRINTER_CATEGORY_UNKNOWN};

    /// El barrido no puede lanzar las 254 sondas a la vez.
    ///
    /// Con `SCAN_CONNECT_TIMEOUT` = 300 ms, cada sonda que espera detrás de otras 253 se queda sin
    /// ventana y **la impresora real se descarta en silencio** — el usuario ve «no hay impresoras»
    /// y no hay nada en los logs que lo distinga de un local sin impresora. Medido contra hardware
    /// de verdad: dos barridos simultáneos la perdían 3 de 3.
    #[tokio::test]
    async fn el_barrido_no_abre_mas_sondas_de_las_que_puede_atender() {
        use std::sync::atomic::{AtomicUsize, Ordering};
        use std::sync::Arc;

        let en_vuelo = Arc::new(AtomicUsize::new(0));
        let pico = Arc::new(AtomicUsize::new(0));

        let direcciones: Vec<String> = (1..=254).map(|i| format!("10.0.0.{i}")).collect();
        let (v, p) = (en_vuelo.clone(), pico.clone());
        sweep_addresses(direcciones, move |_addr| {
            let (v, p) = (v.clone(), p.clone());
            async move {
                let ahora = v.fetch_add(1, Ordering::SeqCst) + 1;
                p.fetch_max(ahora, Ordering::SeqCst);
                // Sin esperar, una sonda termina antes de que arranque la siguiente y el pico nunca
                // sube: la congestión que se quiere medir necesita que se solapen.
                tokio::time::sleep(Duration::from_millis(20)).await;
                v.fetch_sub(1, Ordering::SeqCst);
                false
            }
        })
        .await;

        let pico = pico.load(Ordering::SeqCst);
        assert!(
            pico <= SCAN_MAX_IN_FLIGHT,
            "el barrido tuvo {pico} sondas en vuelo a la vez, por encima del límite de \
             {SCAN_MAX_IN_FLIGHT}: con 300 ms por sonda, las que esperan detrás se descartan y la \
             impresora se pierde SIN error"
        );
    }

    /// El límite acota, no amputa: las 254 direcciones se sondean igual, solo que por tandas. Sin
    /// esto, «arreglar» la concurrencia bajando el número de sondas dejaría medio /24 sin barrer y
    /// el test de arriba seguiría en verde.
    #[tokio::test]
    async fn el_barrido_sigue_sondeando_todas_las_direcciones() {
        use std::sync::atomic::{AtomicUsize, Ordering};
        use std::sync::Arc;

        let sondeadas = Arc::new(AtomicUsize::new(0));
        let s = sondeadas.clone();
        let encontradas = sweep_addresses(
            (1..=254).map(|i| format!("10.0.0.{i}")).collect(),
            move |addr| {
                let s = s.clone();
                async move {
                    s.fetch_add(1, Ordering::SeqCst);
                    addr.ends_with(".42")
                }
            },
        )
        .await;

        assert_eq!(sondeadas.load(Ordering::SeqCst), 254, "se dejó direcciones sin sondear");
        assert_eq!(encontradas, vec!["10.0.0.42".to_string()], "debe devolver solo los aciertos");
    }

    #[test]
    fn ipp_delata_una_impresora_de_oficina() {
        assert_eq!(category_for_service("_ipp._tcp.local."), PRINTER_CATEGORY_A4);
    }

    #[test]
    fn la_impresion_cruda_no_clasifica_nada() {
        // `_pdl-datastream._tcp` es "acepto bytes en el 9100": lo dicen tanto una térmica como una
        // láser A4. Clasificarlo como térmica sería adivinar.
        assert_eq!(
            category_for_service("_pdl-datastream._tcp.local."),
            PRINTER_CATEGORY_UNKNOWN
        );
    }

    #[test]
    fn lo_encontrado_solo_por_escaneo_de_puerto_queda_sin_clasificar() {
        // El escaneo del 9100 no aporta ninguna señal: responder ahí no dice qué idioma habla.
        assert_eq!(crate::protocol::default_printer_category(), PRINTER_CATEGORY_UNKNOWN);
    }

    #[test]
    fn parse_printer_id_sigue_rechazando_transportes_no_de_red() {
        assert!(parse_printer_id("bluetooth:AA:BB:CC:DD:EE:FF").is_err());
        assert!(parse_printer_id("usb:001:002").is_err());
        assert!(parse_printer_id("network:10.0.0.5:9100").is_ok());
    }

    /// **The /24 prefix is derived from the local IP, and that derivation is what gets tested.**
    /// The socket half (`local_subnet_prefix`) asks the OS which interface would reach the
    /// internet — untestable in CI, and the reason this rule used to live twice in the crate
    /// (here and in `registry`, copy-pasted). Splitting the pure half out gives the single
    /// implementation the sweep and the watchdog now share something to pin.
    #[test]
    fn the_subnet_prefix_is_the_first_three_octets_of_an_ipv4() {
        assert_eq!(subnet_prefix_of("192.168.1.42"), Some("192.168.1".to_string()));
        assert_eq!(subnet_prefix_of("10.0.2.15"), Some("10.0.2".to_string()));
    }

    /// A prefix that is not a /24 IPv4 must come back as `None`, never as a truncated string: the
    /// sweep builds `{prefix}.{1..=254}` out of it, so a wrong prefix means 254 connects to
    /// addresses nobody owns — a scan that finds zero printers and blames the printer.
    #[test]
    fn anything_that_is_not_an_ipv4_has_no_scannable_subnet() {
        // IPv6: no /24 to sweep.
        assert_eq!(subnet_prefix_of("fe80::1"), None);
        // Too few octets — `"10.0.2"` would otherwise be taken for a prefix as-is.
        assert_eq!(subnet_prefix_of("10.0.2"), None);
        assert_eq!(subnet_prefix_of(""), None);
    }

    // ── "No permission" is not "no printers" (hub#338) ────────────────────────────────────────
    //
    // Without local network access the sweep is 254 silent timeouts and the mDNS window resolves
    // nothing, so discovery came back with an empty list and no error whatsoever — the worst
    // failure mode a till can have. The two states send the user in OPPOSITE directions ("connect
    // a printer" vs "grant this app permission"), so they must stay apart in the return value.

    const ANDROID_LOCAL_NETWORK: &str = "android.permission.ACCESS_LOCAL_NETWORK";

    fn denied() -> LocalNetworkAccess {
        LocalNetworkAccess::Denied {
            permission: ANDROID_LOCAL_NETWORK.to_string(),
        }
    }

    /// Registry on a temp path: a test must never touch the machine's real `devices.json`.
    fn temp_registry(name: &str) -> DeviceRegistry {
        let dir = std::env::temp_dir().join(format!(
            "erplora-discovery-test-{}-{name}",
            std::process::id()
        ));
        std::fs::create_dir_all(&dir).expect("temp dir");
        DeviceRegistry::load(dir.join(format!("{name}.json")))
    }

    #[test]
    fn granted_access_blocks_nothing() {
        assert_eq!(LocalNetworkAccess::Granted.blocked_by(), None);
    }

    #[test]
    fn denied_access_names_the_permission_the_user_has_to_grant() {
        // The name is what lets the screen point at one toggle instead of listing every setting.
        assert_eq!(denied().blocked_by(), Some(ANDROID_LOCAL_NETWORK));
    }

    #[test]
    fn an_empty_scan_is_an_answer_but_a_blocked_scan_is_not() {
        // `Some(&[])` vs `None` — the ONLY difference between "we looked, nothing there" and "we
        // were never allowed to look". Collapsing both into an empty Vec is the bug.
        assert_eq!(
            PrinterDiscovery::Scanned {
                printers: Vec::new()
            }
            .scanned_printers(),
            Some(&[][..])
        );
        assert_eq!(
            PrinterDiscovery::PermissionDenied {
                permission: ANDROID_LOCAL_NETWORK.to_string(),
            }
            .scanned_printers(),
            None
        );
    }

    #[test]
    fn only_a_blocked_run_names_a_permission() {
        assert_eq!(
            PrinterDiscovery::Scanned {
                printers: Vec::new()
            }
            .denied_permission(),
            None
        );
        assert_eq!(
            PrinterDiscovery::PermissionDenied {
                permission: ANDROID_LOCAL_NETWORK.to_string(),
            }
            .denied_permission(),
            Some(ANDROID_LOCAL_NETWORK)
        );
    }

    #[test]
    fn the_wire_carries_the_status_so_the_screen_can_branch_on_it() {
        // The shell command and the module SDK read `status`. If the difference only existed in a
        // log line, the user would still be looking at the same two identical screens.
        let blocked = serde_json::to_value(PrinterDiscovery::PermissionDenied {
            permission: ANDROID_LOCAL_NETWORK.to_string(),
        })
        .expect("serializable");
        assert_eq!(blocked["status"], LOCAL_NETWORK_PERMISSION_DENIED);
        assert_eq!(blocked["permission"], ANDROID_LOCAL_NETWORK);

        let empty = serde_json::to_value(PrinterDiscovery::Scanned {
            printers: Vec::new(),
        })
        .expect("serializable");
        assert_eq!(empty["status"], "scanned");
        assert_eq!(empty["printers"], serde_json::json!([]));
        assert!(
            empty.get("permission").is_none(),
            "an honest zero must not name a permission: there is nothing to grant"
        );
    }

    #[tokio::test]
    async fn a_denied_permission_skips_the_scan_instead_of_reporting_zero_printers() {
        // Not merely a different return value: with the permission denied the sweep can ONLY come
        // back empty, so running it burns the 1.5 s mDNS window to learn nothing. Answering well
        // inside that window is the proof that we never looked.
        let registry = temp_registry("denied");

        let outcome = tokio::time::timeout(
            Duration::from_millis(200),
            discover_printers(&registry, denied()),
        )
        .await
        .expect("a blocked scan must answer at once, not after the mDNS window")
        .expect("a denied permission is a state, not a transport failure");

        assert_eq!(
            outcome,
            PrinterDiscovery::PermissionDenied {
                permission: ANDROID_LOCAL_NETWORK.to_string(),
            }
        );
        assert_eq!(
            outcome.scanned_printers(),
            None,
            "an empty list here would be the very lie this type exists to prevent"
        );
        assert!(
            registry.get_all().is_empty(),
            "a scan that never ran must not register a single device"
        );
    }
}
