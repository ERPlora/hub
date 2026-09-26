// @vitest-environment happy-dom
//
// On an English hub the shell also reads each module's `locales/en.json` (hub#2179).
//
// The manifest is canonical English for `name`, `navigation` and widgets, but `commands[].label`
// has no place in it: its ONLY English source is `locales/en.json`. The loader skipped that file
// when the active language was `en`, so the manager's approval dialog (and the assistant's
// confirmation card) fell back to «To approve: an action in Sales / POS» even though the module
// ships «Sell an item at an open price». In Spanish the good sentence did show up.
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('./icons', () => ({ moduleIconRegistry: (i: Record<string, string>) => i }));
vi.mock('ionicons', () => ({ addIcons: () => {} }));
vi.mock('../i18n', () => ({ getLocale: () => 'en' }));
vi.mock('./entitlement', () => ({ isModuleEntitled: () => true }));
vi.mock('./runtime', () => ({
  RUNTIME_URL: '',
  runtimeHeaders: () => ({}),
  listInstalledModules: async () => [{ id: 'sales', status: 'active' }],
}));

import { invalidateManifestCache, loadInstalledManifests } from './module-loader';
import { catalogueFromManifests, describeElevation } from './elevation-label';

const EN_LOCALE = {
  name: 'Sales / POS',
  commands: { 'sales.open_price': { label: 'Sell an item at an open price' } },
};

function stubFetch(options: { enLocale: boolean }): string[] {
  const urls: string[] = [];
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => {
      urls.push(url);
      const ok = (body: unknown) => ({ ok: true, status: 200, json: async () => body }) as unknown as Response;
      if (url.startsWith('/api/navigation')) {
        return ok({
          ok: true,
          data: [
            {
              module_id: 'sales',
              module_name: 'Sales / POS',
              module_version: '1.0.0',
              id: 'sales-main',
              label: 'Sales',
              icon: null,
              component: 'erp-sales',
            },
          ],
          active_modules: 1,
        });
      }
      if (/\/modules\/sales(?:\/v\/[^/]+)?\/module\.json$/.test(url)) {
        return ok({ name: 'Sales / POS', version: '1.0.0', ui: { entry: 'dist/sales.esm.js' } });
      }
      if (url.endsWith('/locales/en.json') && options.enLocale) return ok(EN_LOCALE);
      return { ok: false, status: 404, json: async () => ({}) } as unknown as Response;
    }),
  );
  return urls;
}

beforeEach(() => {
  vi.unstubAllGlobals();
  invalidateManifestCache();
});

describe('module locale on an English hub (hub#2179)', () => {
  it('reads locales/en.json so command labels reach the approval dialog', async () => {
    const urls = stubFetch({ enLocale: true });

    const installed = await loadInstalledManifests();

    expect(urls.some((u) => u.endsWith('/locales/en.json'))).toBe(true);
    expect(installed[0]?.locale?.commands?.['sales.open_price']?.label).toBe(
      'Sell an item at an open price',
    );
    const described = describeElevation(
      { command: 'sales.open_price' },
      catalogueFromManifests(installed),
    );
    expect(described.action).toBe('Sell an item at an open price');
  });

  it('a module without locales/en.json still loads, named from its manifest', async () => {
    stubFetch({ enLocale: false });

    const installed = await loadInstalledManifests();

    expect(installed).toHaveLength(1);
    expect(installed[0]?.locale).toBeUndefined();
    const described = describeElevation(
      { command: 'sales.open_price' },
      catalogueFromManifests(installed),
    );
    expect(described).toEqual({ action: '', moduleName: 'Sales / POS' });
  });
});
