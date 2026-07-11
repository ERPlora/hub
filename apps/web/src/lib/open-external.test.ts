// Tests del helper `openExternal` (deep-link de compra, Fase 4): en web abre pestaña nueva con
// `noopener`; dentro de Tauri delega en el plugin opener (navegador del SISTEMA, no el WebView).
// Entorno node puro: se stubbea `window`, igual que el global `__TAURI__` que usa lib/device.ts.
import { afterEach, describe, expect, it, vi } from 'vitest';

// Mock del plugin de Tauri (hoisted: vi.mock se iza por encima de los imports). En el test no hay
// runtime Rust; solo se comprueba la delegación al plugin.
const { openUrl } = vi.hoisted(() => ({ openUrl: vi.fn(async () => undefined) }));
vi.mock('@tauri-apps/plugin-opener', () => ({ openUrl }));

import { openExternal } from './open-external';

describe('openExternal', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    openUrl.mockClear();
  });

  it('en web abre la URL en pestaña nueva con noopener', async () => {
    const open = vi.fn();
    vi.stubGlobal('window', { open });

    await openExternal('https://erplora.com/dashboard/billing/modules/pos/?hub=h1&utm_source=hub');

    expect(open).toHaveBeenCalledWith(
      'https://erplora.com/dashboard/billing/modules/pos/?hub=h1&utm_source=hub',
      '_blank',
      'noopener',
    );
    expect(openUrl).not.toHaveBeenCalled();
  });

  it('en Tauri delega en el plugin opener (navegador del sistema)', async () => {
    const open = vi.fn();
    // Detección de Tauri idéntica a lib/device.ts: window.__TAURI__.core.invoke presente.
    vi.stubGlobal('window', { open, __TAURI__: { core: { invoke: vi.fn() } } });

    await openExternal('https://erplora.com/x');

    expect(openUrl).toHaveBeenCalledWith('https://erplora.com/x');
    expect(open).not.toHaveBeenCalled();
  });
});
