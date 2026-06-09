//! Cajón portamonedas: comando kick ESC/POS enviado por el socket TCP de la impresora.
//! Porta `bridge/ERPlora-Bridge-desktop/erplora_bridge/hardware/drawer.py`.

use crate::discovery::NetworkTarget;
use crate::Result;

/// `ESC p 0 25 50` — pulso por el pin 2 del conector DK (por defecto).
pub const KICK_PIN_2: &[u8] = &[0x1b, 0x70, 0x00, 0x19, 0x32];

/// `ESC p 1 25 50` — pulso por el pin 5.
pub const KICK_PIN_5: &[u8] = &[0x1b, 0x70, 0x01, 0x19, 0x32];

/// Bytes del kick según el pin (2 → pin 2; cualquier otro → pin 5, igual que Python).
pub fn kick_command(pin: u8) -> &'static [u8] {
    if pin == 2 {
        KICK_PIN_2
    } else {
        KICK_PIN_5
    }
}

/// Abre el cajón conectado a la impresora: abre socket al `target` y envía el kick.
/// Porta `open_drawer(printer_id, pin)`.
pub async fn open_drawer(target: &NetworkTarget, pin: u8) -> Result<()> {
    let stream = tokio::net::TcpStream::connect(target.socket_addr()).await?;
    let mut buf = kick_command(pin);
    while !buf.is_empty() {
        stream.writable().await?;
        match stream.try_write(buf) {
            Ok(n) => buf = &buf[n..],
            Err(e) if e.kind() == std::io::ErrorKind::WouldBlock => continue,
            Err(e) => return Err(e.into()),
        }
    }
    Ok(())
}
