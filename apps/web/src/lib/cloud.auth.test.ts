// Regresión UX-001: los planos de sesión local y Cloud son distintos.
//
// Un usuario que entra por PIN tiene una sesión válida en el runtime aunque no conserve un JWT
// Cloud fresco. Un 401 de billing debe degradar solo esa conexión Cloud; en un Hub Cloud real,
// en cambio, el fallo definitivo del refresh sigue expirando la sesión completa.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { beginRequest, endRequest } = vi.hoisted(() => ({
  beginRequest: vi.fn(),
  endRequest: vi.fn(),
}));
const { tauriMode } = vi.hoisted(() => ({ tauriMode: { value: false } }));

vi.mock('./shell', () => ({ beginRequest, endRequest }));
vi.mock('./device', () => ({
  isTauri: () => tauriMode.value,
  loginHeaders: vi.fn(async () => ({ 'X-Client-Type': 'hub' })),
}));

import {
  clearTokens,
  cloudInvoices,
  getAccessToken,
  setOnSessionExpired,
  setTokens,
} from './cloud';
import { config, DEV_HUB_ID } from './config';

function memoryStorage(): Storage {
  const values = new Map<string, string>();
  return {
    get length() { return values.size; },
    clear: () => values.clear(),
    getItem: (key) => values.get(key) ?? null,
    key: (index) => [...values.keys()][index] ?? null,
    removeItem: (key) => { values.delete(key); },
    setItem: (key, value) => { values.set(key, String(value)); },
  };
}

const sessionExpired = vi.fn();
const originalHubId = config.hubId;
const originalCloudApiUrl = config.cloudApiUrl;

describe('refresh-on-401 según el plano de sesión', () => {
  beforeEach(() => {
    vi.stubGlobal('localStorage', memoryStorage());
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 401 })));
    config.cloudApiUrl = 'https://cloud.test';
    config.hubId = DEV_HUB_ID;
    tauriMode.value = false;
    sessionExpired.mockClear();
    beginRequest.mockClear();
    endRequest.mockClear();
    setOnSessionExpired(sessionExpired);
    clearTokens();
  });

  afterEach(() => {
    config.hubId = originalHubId;
    config.cloudApiUrl = originalCloudApiUrl;
    vi.unstubAllGlobals();
  });

  it('conserva la sesión local y limpia solo el JWT Cloud cuando billing responde 401', async () => {
    setTokens('access-caducado', '');

    await expect(cloudInvoices()).rejects.toThrow('cloud /api/v1/billing/invoices/ → 401');

    expect(sessionExpired).not.toHaveBeenCalled();
    expect(getAccessToken()).toBeNull();
    expect(beginRequest).toHaveBeenCalledOnce();
    expect(endRequest).toHaveBeenCalledOnce();
  });

  it('mantiene la expiración completa de una sesión Hub Cloud cuyo refresh falla', async () => {
    config.hubId = '11111111-1111-4111-8111-111111111111';
    setTokens('access-caducado', '');

    await expect(cloudInvoices()).rejects.toThrow('cloud /api/v1/billing/invoices/ → 401');

    expect(sessionExpired).toHaveBeenCalledOnce();
    expect(getAccessToken()).toBeNull();
  });

  it('expira una sesión Hub Cloud que ya no conserva ningún token', async () => {
    config.hubId = '11111111-1111-4111-8111-111111111111';

    await expect(cloudInvoices()).rejects.toThrow('cloud /api/v1/billing/invoices/ → 401');

    expect(sessionExpired).toHaveBeenCalledOnce();
  });

  it('conserva una sesión Hub Local Tauri aunque el dispositivo tenga un hub_id real', async () => {
    config.hubId = '22222222-2222-4222-8222-222222222222';
    tauriMode.value = true;
    setTokens('access-caducado', '');

    await expect(cloudInvoices()).rejects.toThrow('cloud /api/v1/billing/invoices/ → 401');

    expect(sessionExpired).not.toHaveBeenCalled();
    expect(getAccessToken()).toBeNull();
  });
});
