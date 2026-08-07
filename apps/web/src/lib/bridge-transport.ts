// Selección del transporte de HARDWARE por entorno (ADR-0159, cliente fino).
//
//   - Web pura (navegador / WebView Android): `BridgeClient` — WS a `localhost:12321`, servido por
//     el bridge standalone Rust (desktop) o el bridge Kotlin embebido en la app Android. Presenta
//     el token de emparejamiento (fail-closed del bridge standalone, ADR-0050 §seguridad).
//   - Shell Tauri de escritorio: `IpcBridgeTransport` — `invoke` in-process (el shell ES el
//     bridge, §2.7): sin servidor WS, sin token, sin device-code.
//
// Los módulos consumen `erplora.peripherals` sin distinguir el transporte (mismo contrato).
import {
  BridgeClient,
  IpcBridgeTransport,
  LocalNetworkPermissionDeniedError,
  type BridgeTransport,
  type TauriBridge,
} from '@erplora/module-sdk';

import { getBridgeToken } from './bridge-client';
import { invokeTauri, isTauri } from './device';
import { printerDiscoveryMessage } from './printer-discovery';

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

/** Transporte de hardware correcto para el entorno actual. */
export function makeBridgeTransport(): BridgeTransport {
  return withLocalisedDiscovery(
    isTauri() ? new IpcBridgeTransport(tauriShell) : new BridgeClient(undefined, { token: getBridgeToken }),
  );
}
