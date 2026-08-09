// Selección del transporte de HARDWARE por entorno (ADR-0196 §3, cliente fino).
//
//   - App instalada (Tauri: escritorio · Android · iOS): `IpcBridgeTransport` — `invoke`
//     in-process sobre `erplora-peripherals` (la app ES el acceso al hardware, §2.7): sin
//     servidor local, sin token, sin device-code.
//   - Navegador a secas: NO hay hardware — `UnavailableBridgeTransport`. Antes había aquí un
//     segundo camino (`BridgeClient`, WS a `localhost:12321` contra el bridge standalone, con su
//     token de emparejamiento); ADR-0196 §3 lo retira y con él PNA, mixed-content y la clave
//     pública del emparejamiento. El precio explícito: la PWA deja de imprimir tiques térmicos.
//
// Modules consume `erplora.peripherals` without knowing which transport they got (one contract),
// and since hub#524 the shell's own SCREENS ask at that same door ({@link detectPeripherals}).
import {
  IpcBridgeTransport,
  LocalNetworkPermissionDeniedError,
  UnavailableBridgeTransport,
  type BridgeStatus,
  type BridgeTransport,
  type TauriBridge,
} from '@erplora/module-sdk';

import { invokeTauri, isTauri } from './device';
import { hardwareUnavailableMessage, printerDiscoveryMessage } from './printer-discovery';

/** Adaptador del shell Tauri al contrato `TauriBridge` del SDK (inyectable en tests). */
const tauriShell: TauriBridge = {
  invoke: (cmd, args) => invokeTauri(cmd, args) as Promise<unknown>,
  // El shell aún no emite eventos de hardware hacia la UI (los outcomes van al log del shell);
  // el contrato exige `listen`, así que se entrega una suscripción vacía.
  listen: async () => () => {},
};

/**
 * Le pone al escaneo bloqueado la frase que el usuario entiende (hub#338).
 *
 * El SDK ya distingue «no me dejan mirar» de «no hay nada», pero su mensaje está en inglés y es
 * para el log. El shell es quien tiene i18n, así que traduce el rechazo AQUÍ, una sola vez: todo
 * módulo que ya enseñaba `error.message` pasa a decir «dale permiso a la app» sin tocar una línea.
 *
 * Se parchea la instancia en vez de envolverla en otra clase porque la selección de transporte
 * (ADR-0159) se decide por `instanceof`, y un envoltorio la rompería.
 */
function withLocalisedDiscovery<T extends BridgeTransport>(transport: T): T {
  const scan = transport.discoverPrinters.bind(transport);
  transport.discoverPrinters = async () => {
    try {
      return await scan();
    } catch (e) {
      if (e instanceof LocalNetworkPermissionDeniedError) {
        throw new LocalNetworkPermissionDeniedError(
          e.permission,
          printerDiscoveryMessage('permission_denied'),
        );
      }
      throw e;
    }
  };
  return transport;
}

export type { BridgeStatus };

/**
 * **Is there hardware on THIS device?** — one question, one door: the modules' own (hub#524).
 *
 * There used to be two ways of asking it, and the screens used the one ADR-0196 walled up:
 * `GET localhost:12321/status`, the daemon hub#340 deleted. With nobody listening there the answer
 * was `{online:false}` **everywhere, always** — including inside `com.erplora.app`, where the
 * printer is plugged in and answering. And it failed **mute**: no error, no log, just a calm
 * sentence sending the owner off to install the app they already had open.
 *
 * Delegating to the transport makes the answer honest by construction: in a browser
 * `{online:false}` IS the truth (there is no hardware there — ADR-0196 §3), and in the installed
 * app it comes from `erplora_bridge_status`, the very call the `printing` module reads.
 *
 * It never rejects. Both `detect()` implementations resolve on purpose, because whoever asks is
 * painting a state — a rejection would take down the screen instead of filling in a status.
 */
export function detectPeripherals(timeoutMs?: number): Promise<BridgeStatus> {
  return makeBridgeTransport().detect(timeoutMs);
}

/** Transporte de hardware correcto para el entorno actual. */
export function makeBridgeTransport(): BridgeTransport {
  return withLocalisedDiscovery(
    isTauri()
      ? new IpcBridgeTransport(tauriShell)
      : // La frase se resuelve AQUÍ, en cada construcción del transporte, y no en el SDK: el
        // reparto es el mismo que en el escaneo bloqueado — el SDK pone el `code`, el shell (que
        // es quien tiene i18n) pone las palabras en el idioma activo del hub.
        new UnavailableBridgeTransport(hardwareUnavailableMessage()),
  );
}
