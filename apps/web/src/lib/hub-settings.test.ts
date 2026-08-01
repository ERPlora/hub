// @vitest-environment happy-dom
// Contrato del cliente de settings para la presencia web pública del Hub (ADR-0177): la clave
// core `public.landing.visible` (bool, default false) se LEE y se ESCRIBE por la MISMA API de
// settings del hub (`GET/PUT /api/settings`), como `api_docs_enabled`. No es un cliente nuevo:
// es una clave más del store k/v ya existente.
//
// `./runtime` y `./theme` se stubean para aislar el cliente (sin arrastrar el runtime real ni el
// DOM del tema); aquí solo importa el fetch a `/api/settings` y la (de)serialización de la clave.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('./runtime', () => ({ RUNTIME_URL: '', runtimeHeaders: () => ({}) }));
vi.mock('./theme', () => ({ setHubPalette: vi.fn() }));

import { getHubSettings, updateHubSettings, hubSettings } from './hub-settings';

/** Objeto COMPLETO como lo devuelve el runtime (todas las claves conocidas). */
function fullSettings(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    currency: 'EUR',
    language: 'es',
    api_docs_enabled: false,
    country_code: 'ES',
    region_code: null,
    business_tax_id: '',
    business_legal_name: '',
    business_address: '',
    theme_palette: 'erplora',
    'public.landing.visible': false,
    ...overrides,
  };
}

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  hubSettings.value = null;
  fetchMock = vi.fn();
  vi.stubGlobal('fetch', fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('hub-settings · public.landing.visible', () => {
  it('GET expone el valor de `public.landing.visible` en la cache', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => fullSettings({ 'public.landing.visible': true }),
    });
    const s = await getHubSettings();
    expect(s['public.landing.visible']).toBe(true);
    expect(hubSettings.value?.['public.landing.visible']).toBe(true);
  });

  it('si la clave no llega (hub sin la fila), degrada a false por defecto', async () => {
    const raw = fullSettings();
    delete raw['public.landing.visible'];
    fetchMock.mockResolvedValue({ ok: true, json: async () => raw });
    const s = await getHubSettings();
    expect(s['public.landing.visible']).toBe(false);
  });

  it('PUT parcial envía `public.landing.visible` a la API de settings', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => fullSettings({ 'public.landing.visible': true }),
    });
    await updateHubSettings({ 'public.landing.visible': true });

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/settings');
    expect(init.method).toBe('PUT');
    expect(JSON.parse(init.body as string)).toEqual({ 'public.landing.visible': true });
  });
});
