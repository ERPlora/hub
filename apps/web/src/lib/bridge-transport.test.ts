// ADR-0159 (cliente fino): la PWA elige el transporte de HARDWARE por entorno.
//   - Web pura (navegador / WebView Android) → `BridgeClient` (WS a localhost:12321, el bridge
//     standalone Rust o el bridge Kotlin de la app Android).
//   - Shell Tauri de escritorio → `IpcBridgeTransport` (invoke in-process: el shell ES el bridge,
//     sin servidor WS ni token de emparejamiento).
// Antes de 0159 la selección NUNCA estuvo cableada: getClient() construía siempre el WS.
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { tauriMode, invokeSpy } = vi.hoisted(() => ({
  tauriMode: { value: false },
  invokeSpy: vi.fn<(cmd: string, args?: Record<string, unknown>) => Promise<unknown>>(
    async () => ({ version: 'test' }),
  ),
}));

vi.mock('./device', () => ({
  isTauri: () => tauriMode.value,
  invokeTauri: invokeSpy,
}));

import {
  BridgeClient,
  IpcBridgeTransport,
  LOCAL_NETWORK_PERMISSION_DENIED,
  LocalNetworkPermissionDeniedError,
} from '@erplora/module-sdk';

import { makeBridgeTransport } from './bridge-transport';
import { printerDiscoveryMessage } from './printer-discovery';

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

// ── Permisos de Android ─────────────────────────────────────────────────────────────────────
// Declarar un permiso en el manifest NO basta: `ACCESS_LOCAL_NETWORK` (API 37+) y
// `POST_NOTIFICATIONS` (API 33+) se conceden en runtime, y su ausencia falla EN SILENCIO —
// el descubrimiento devuelve [] y las notificaciones no salen, sin un solo error.
// Verificado en el emulador API 37: `discover_printers` daba [] hasta concederlo con `adb`.
describe('permisos de runtime antes de tocar el hardware', () => {
  it('pide permisos antes de descubrir impresoras', async () => {
    tauriMode.value = true;
    invokeSpy.mockClear();
    const transport = makeBridgeTransport();

    await transport.discoverPrinters();

    const llamadas = invokeSpy.mock.calls.map((c) => c[0]);
    expect(llamadas).toContain('plugin:erplora-android|request_permissions');
    expect(llamadas.indexOf('plugin:erplora-android|request_permissions')).toBeLessThan(
      llamadas.indexOf('erplora_discover_printers'),
    );
  });

  it('pide permisos antes de notificar', async () => {
    tauriMode.value = true;
    invokeSpy.mockClear();
    const transport = makeBridgeTransport();

    await transport.notify('Nueva comanda', 'Mesa 4');

    const llamadas = invokeSpy.mock.calls.map((c) => c[0]);
    expect(llamadas).toContain('plugin:erplora-android|request_permissions');
    expect(llamadas.indexOf('plugin:erplora-android|request_permissions')).toBeLessThan(
      llamadas.indexOf('erplora_notify'),
    );
  });

  it('si el usuario DENIEGA, la operación sigue — no revienta', async () => {
    // Un «no» es una respuesta, no un error. Sin impresora el TPV tiene que seguir cobrando.
    tauriMode.value = true;
    invokeSpy.mockClear();
    invokeSpy.mockImplementation(async (cmd: string) => {
      if (cmd === 'plugin:erplora-android|request_permissions') throw new Error('denegado');
      return { status: 'scanned', printers: [] };
    });
    const transport = makeBridgeTransport();

    await expect(transport.discoverPrinters()).resolves.toEqual([]);
  });
});

// ── hub#338: el shell le pone PALABRAS al estado ────────────────────────────────────────────
//
// El runtime ya distingue «no hay impresoras» de «no me dejan buscarlas», pero eso solo sirve si
// llega a la pantalla como una frase que dice qué HACER. El shell es quien tiene i18n, así que es
// quien la pone: cualquier módulo que ya enseñaba `error.message` acierta sin tocar una línea.
describe('el escaneo bloqueado llega al usuario como una frase, no como una lista vacía', () => {
  beforeEach(() => {
    tauriMode.value = true;
    invokeSpy.mockClear();
    invokeSpy.mockImplementation(async () => ({ status: 'scanned', printers: [] }));
  });

  it('permiso denegado → rechaza con la frase de «dale permiso», no con []', async () => {
    invokeSpy.mockImplementation(async (cmd: string) => {
      if (cmd === 'erplora_discover_printers') {
        return {
          status: LOCAL_NETWORK_PERMISSION_DENIED,
          permission: 'android.permission.ACCESS_LOCAL_NETWORK',
        };
      }
      return {};
    });
    const transport = makeBridgeTransport();

    await expect(transport.discoverPrinters()).rejects.toThrow(LocalNetworkPermissionDeniedError);
    await expect(transport.discoverPrinters()).rejects.toThrow(
      printerDiscoveryMessage('permission_denied'),
    );
  });

  it('el permiso denegado conserva su nombre: la frase señala UN interruptor', async () => {
    invokeSpy.mockImplementation(async () => ({
      status: LOCAL_NETWORK_PERMISSION_DENIED,
      permission: 'android.permission.ACCESS_LOCAL_NETWORK',
    }));
    const transport = makeBridgeTransport();

    await transport.discoverPrinters().then(
      () => expect.fail('un escaneo bloqueado no puede resolver'),
      (e: unknown) => {
        expect(e).toBeInstanceOf(LocalNetworkPermissionDeniedError);
        expect((e as LocalNetworkPermissionDeniedError).permission).toBe(
          'android.permission.ACCESS_LOCAL_NETWORK',
        );
      },
    );
  });

  it('cero impresoras CON permiso sigue resolviendo []: es una respuesta, no un fallo', async () => {
    const transport = makeBridgeTransport();
    await expect(transport.discoverPrinters()).resolves.toEqual([]);
  });

  it('envolver el transporte no cambia cuál es (sigue siendo el de Tauri)', async () => {
    // El contrato de ADR-0159 se decide por `instanceof`; ponerle copy no puede romperlo.
    expect(makeBridgeTransport()).toBeInstanceOf(IpcBridgeTransport);
  });
});
