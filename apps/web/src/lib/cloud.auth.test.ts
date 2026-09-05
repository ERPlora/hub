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
import { setHubSession } from './session';

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
    setHubSession(null);
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

  // hub#764 — «Mi plan» expulsaba al login en un hub Cloud REAL. El día a día del TPV es sesión
  // local/PIN (ADR-0003): el runtime emite su propia sesión y NUNCA hay JWT Cloud. Al abrir
  // /billing, el 401 del Cloud no encontraba refresh que rotar y se trataba como «sesión
  // caducada», tirando abajo la sesión del runtime que estaba perfectamente viva. Un 401 solo
  // puede expirar el plano que lo emitió.
  it('hub#764: una sesión de RUNTIME (PIN) sobrevive al 401 de billing en un hub Cloud real', async () => {
    config.hubId = '11111111-1111-4111-8111-111111111111';
    setHubSession('runtime-session-token');

    await expect(cloudInvoices()).rejects.toThrow('cloud /api/v1/billing/invoices/ → 401');

    // El cajero sigue dentro: billing degrada a su estado «hace falta cuenta Cloud», no expulsa.
    expect(sessionExpired).not.toHaveBeenCalled();
  });

  it('hub#764: y sigue expulsando cuando tampoco queda sesión de runtime', async () => {
    // Sin ningún plano vivo no hay nada que conservar — el contrato de arriba se mantiene.
    config.hubId = '11111111-1111-4111-8111-111111111111';
    setTokens('access-caducado', '');

    await expect(cloudInvoices()).rejects.toThrow('cloud /api/v1/billing/invoices/ → 401');

    expect(sessionExpired).toHaveBeenCalledOnce();
  });

  // CONTRATO CAMBIADO por ADR-0159 (antes: «conserva una sesión Hub Local Tauri aunque el
  // dispositivo tenga un hub_id real»). Ese comportamiento era del producto Hub Local (Tauri +
  // SQLite), retirado por ADR-0154: hoy el shell Tauri es un CLIENTE FINO de la misma PWA cloud,
  // así que un refresh fallido con hub_id real expira la sesión exactamente igual que en el
  // navegador. El plano "independiente" queda solo para el runtime local/dev (DEV_HUB_ID).
  it('ADR-0159: dentro del shell Tauri, un hub cloud real expira la sesión como en el navegador', async () => {
    config.hubId = '22222222-2222-4222-8222-222222222222';
    tauriMode.value = true;
    setTokens('access-caducado', '');

    await expect(cloudInvoices()).rejects.toThrow('cloud /api/v1/billing/invoices/ → 401');

    expect(sessionExpired).toHaveBeenCalledOnce();
    expect(getAccessToken()).toBeNull();
  });

  // hub#1538 — the PIN hand-over (`switchUser`) takes the previous person's erplora.com credentials
  // off the till WITHOUT signing the till out. A refresh that was already in flight when that
  // happened — a 401 from billing or from the entitlement re-check on window focus, an instant
  // before the PIN — rotates THAT person's tokens and used to write them straight back when the
  // answer arrived, undoing the hand-over with nobody watching. What comes back belongs to a login
  // that no longer exists: the store is the authority, not the response.
  it('hub#1538: a refresh in flight does not resurrect the credentials the hand-over just cleared', async () => {
    setTokens('acc-owner', 'ref-owner');
    let releaseRefresh!: (res: Response) => void;
    const refreshInFlight = new Promise<Response>((resolve) => { releaseRefresh = resolve; });
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(null, { status: 401 })) // invoices, stale access token
      .mockReturnValueOnce(refreshInFlight) // POST /auth/refresh, still waiting for the SaaS
      .mockResolvedValue(new Response('[]', { status: 200 })); // the retry, if one were to happen
    vi.stubGlobal('fetch', fetchMock);

    const invoices = cloudInvoices();
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));

    clearTokens(); // the hand-over: the owner leaves and her credentials go with her
    releaseRefresh(new Response(
      JSON.stringify({ access: 'acc-owner-rotated', refresh: 'ref-owner-rotated' }),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    ));
    await invoices.catch(() => undefined);

    expect(getAccessToken()).toBeNull();
    expect(localStorage.getItem('erplora.refresh')).toBeNull();
    expect(sessionExpired).not.toHaveBeenCalled();
  });
});
