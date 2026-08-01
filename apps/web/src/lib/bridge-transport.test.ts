// ADR-0159 (cliente fino): la PWA elige el transporte de HARDWARE por entorno.
//   - Web pura (navegador / WebView Android) → `BridgeClient` (WS a localhost:12321, el bridge
//     standalone Rust o el bridge Kotlin de la app Android).
//   - Shell Tauri de escritorio → `IpcBridgeTransport` (invoke in-process: el shell ES el bridge,
//     sin servidor WS ni token de emparejamiento).
// Antes de 0159 la selección NUNCA estuvo cableada: getClient() construía siempre el WS.
import { describe, expect, it, vi } from 'vitest';

const { tauriMode, invokeSpy } = vi.hoisted(() => ({
  tauriMode: { value: false },
  invokeSpy: vi.fn(async () => ({ version: 'test' })),
}));

vi.mock('./device', () => ({
  isTauri: () => tauriMode.value,
  invokeTauri: invokeSpy,
}));

import { BridgeClient, IpcBridgeTransport } from '@erplora/module-sdk';

import { makeBridgeTransport } from './bridge-transport';

describe('ADR-0159: selección del transporte de hardware', () => {
  it('web pura → BridgeClient (WS a localhost:12321)', () => {
    tauriMode.value = false;
    expect(makeBridgeTransport()).toBeInstanceOf(BridgeClient);
  });

  it('shell Tauri → IpcBridgeTransport (invoke, sin WS ni token)', () => {
    tauriMode.value = true;
    expect(makeBridgeTransport()).toBeInstanceOf(IpcBridgeTransport);
  });

  it('el transporte Ipc delega en invokeTauri (detect → erplora_bridge_status)', async () => {
    tauriMode.value = true;
    const transport = makeBridgeTransport();
    const status = await transport.detect();
    expect(invokeSpy).toHaveBeenCalledWith('erplora_bridge_status', {});
    expect(status.online).toBe(true);
  });
});

// ── Notificaciones ──────────────────────────────────────────────────────────────────────────
// El protocolo declara `send_notification` desde el principio y SOLO lo implementaba el binario
// suelto `apps/bridge` (escritorio, vía notify_rust). Ni el shell Tauri ni el SDK lo exponían, así
// que un módulo NO PODÍA avisar de nada: cuando entra una comanda, cocina no se entera.
//
// El contrato es el mismo por los dos transportes para que el módulo no sepa dónde corre.
describe('notificaciones: el mismo contrato por los dos transportes', () => {
  it('el shell Tauri las manda por invoke', async () => {
    tauriMode.value = true;
    const transport = makeBridgeTransport();

    await transport.notify('Nueva comanda', 'Mesa 4 · 3 platos');

    expect(invokeSpy).toHaveBeenCalledWith('erplora_notify', {
      title: 'Nueva comanda',
      body: 'Mesa 4 · 3 platos',
    });
  });

  it('el transporte WS las manda con la acción `send_notification` del protocolo', async () => {
    const enviados: unknown[] = [];
    const ws = new BridgeClient(undefined, { token: () => null });
    // El WS real no está levantado en el test: se intercepta el envío, que es el contrato.
    (ws as unknown as { request: unknown }).request = async (payload: unknown) => {
      enviados.push(payload);
      return {};
    };

    await ws.notify('Nueva comanda', 'Mesa 4 · 3 platos');

    expect(enviados[0]).toEqual({
      action: 'send_notification',
      title: 'Nueva comanda',
      body: 'Mesa 4 · 3 platos',
    });
  });
});
