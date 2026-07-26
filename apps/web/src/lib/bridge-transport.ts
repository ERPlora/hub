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
  type BridgeTransport,
  type TauriBridge,
} from '@erplora/module-sdk';

import { getBridgeToken } from './bridge-client';
import { invokeTauri, isTauri } from './device';

/** Adaptador del shell Tauri al contrato `TauriBridge` del SDK (inyectable en tests). */
const tauriShell: TauriBridge = {
  invoke: (cmd, args) => invokeTauri(cmd, args) as Promise<unknown>,
  // El shell aún no emite eventos de hardware hacia la UI (los outcomes van al log del shell);
  // el contrato exige `listen`, así que se entrega una suscripción vacía.
  listen: async () => () => {},
};

/** Transporte de hardware correcto para el entorno actual. */
export function makeBridgeTransport(): BridgeTransport {
  return isTauri() ? new IpcBridgeTransport(tauriShell) : new BridgeClient(undefined, { token: getBridgeToken });
}
