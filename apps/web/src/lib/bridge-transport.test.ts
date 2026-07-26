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
