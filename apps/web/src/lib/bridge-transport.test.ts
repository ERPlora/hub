// ADR-0196 §3: hay UN solo camino al hardware, y es la app instalada.
//   - App instalada (Tauri, escritorio · Android · iOS) → `IpcBridgeTransport`: `invoke`
//     in-process, sin servidor local, sin token de emparejamiento.
//   - Navegador a secas → NO hay hardware. Antes había un segundo camino (`BridgeClient`, WS a
//     `localhost:12321` contra el bridge standalone) y con él PNA, mixed-content y la clave
//     pública del emparejamiento; 0196 lo retira y la PWA deja de imprimir tiques térmicos.
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
  ErploraError,
  IpcBridgeTransport,
  LOCAL_NETWORK_PERMISSION_DENIED,
  LocalNetworkPermissionDeniedError,
} from '@erplora/module-sdk';

import { makeBridgeTransport } from './bridge-transport';
import { hardwareUnavailableMessage, printerDiscoveryMessage } from './printer-discovery';

describe('ADR-0196 §3: selección del transporte de hardware', () => {
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

  it('navegador a secas → sin hardware: detect() dice offline y NO sondea localhost', async () => {
    // `detect()` no puede rechazar: el módulo printing lo llama sin try/catch y enseña su propio
    // estado «bridge offline» a partir de este booleano.
    tauriMode.value = false;
    const fetchSpy = vi.spyOn(globalThis, 'fetch');

    await expect(makeBridgeTransport().detect()).resolves.toEqual({ online: false });

    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });

  it('navegador a secas → imprimir FALLA con `hardware_unavailable`, no en silencio', async () => {
    // El precio explícito de ADR-0196: la PWA no imprime tiques térmicos. Lo que no puede pasar
    // es que lo diga resolviendo — el TPV daría por impreso un tique que no ha salido.
    tauriMode.value = false;

    await makeBridgeTransport()
      .print('network:192.168.1.50:9100', 'receipt', { total: 100 })
      .then(
        () => expect.fail('imprimir sin hardware no puede resolver'),
        (e: unknown) => {
          expect(e).toBeInstanceOf(ErploraError);
          expect((e as ErploraError).code).toBe('hardware_unavailable');
        },
      );
  });

  it('navegador a secas → el mensaje va en el idioma del hub, no en inglés del log', async () => {
    // El shell es quien tiene i18n (mismo reparto que hub#338): el SDK pone el `code`, el shell
    // pone la frase. Un módulo que enseñe `error.message` acierta sin tocar una línea.
    tauriMode.value = false;

    await expect(makeBridgeTransport().testPrint('network:192.168.1.50:9100')).rejects.toThrow(
      hardwareUnavailableMessage(),
    );
  });

  it('«no hay app» NO se confunde con «no me dejan mirar la red» ni con «no hay impresoras»', () => {
    // El fallo de hub#338 fue enseñar la frase de otro estado: manda al usuario a arreglar algo
    // que nunca estuvo roto. Aquí serían los ajustes del sistema, buscando un permiso que no
    // existe porque lo que falta es la app. Las tres frases tienen que ser tres.
    const unavailable = hardwareUnavailableMessage();

    expect(unavailable).not.toBe('');
    expect(unavailable).not.toBe(printerDiscoveryMessage('permission_denied'));
    expect(unavailable).not.toBe(printerDiscoveryMessage('no_printers'));
  });

  it('la frase existe en los DOS idiomas (inglés fuente + su `es`)', async () => {
    // Sin la traducción, un hub en español enseñaría la clave cruda `hardware.unavailable`.
    const [en, es] = await Promise.all([
      import('../i18n/locales/en'),
      import('../i18n/locales/es'),
    ]);

    for (const catalogue of [en.default, es.default]) {
      expect(catalogue.hardware.unavailable).toBeTruthy();
    }
    expect(en.default.hardware.unavailable).not.toBe(es.default.hardware.unavailable);
  });
});

// ── Notificaciones ──────────────────────────────────────────────────────────────────────────
// El protocolo declara `send_notification` desde el principio y SOLO lo implementaba el binario
// suelto `apps/bridge` (escritorio, vía notify_rust). Ni el shell Tauri ni el SDK lo exponían, así
// que un módulo NO PODÍA avisar de nada: cuando entra una comanda, cocina no se entera.
//
// Best-effort por contrato: una notificación que no sale no puede tumbar la comanda que la
// provocó — ni con la app instalada ni sin ella.
describe('notificaciones', () => {
  it('el shell Tauri las manda por invoke', async () => {
    tauriMode.value = true;
    const transport = makeBridgeTransport();

    await transport.notify('Nueva comanda', 'Mesa 4 · 3 platos');

    expect(invokeSpy).toHaveBeenCalledWith('erplora_notify', {
      title: 'Nueva comanda',
      body: 'Mesa 4 · 3 platos',
    });
  });

  it('sin la app instalada NO lanzan: avisar es best-effort, imprimir no', async () => {
    // Es la única operación del contrato que degrada callando. Las que mueven papel o dinero
    // rechazan (arriba): dar por hecho un tique que no ha salido sería el fallo caro.
    tauriMode.value = false;

    await expect(
      makeBridgeTransport().notify('Nueva comanda', 'Mesa 4 · 3 platos'),
    ).resolves.toBeUndefined();
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
