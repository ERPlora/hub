// @vitest-environment happy-dom
// hub#1905 — the end of a template import ASKS for the permissions of the apps it brought.
//
// The salon of the issue imported «Peluquería»: VeriFactu and Printing came in with their switches
// off (a template cannot grant them — hub#473, on purpose), nobody asked, and the first sale went
// out with no fiscal record and its receipt stuck in the queue. The store already asks when ONE app
// is installed («Requested permissions → Install and grant», pm#132); this is the same question for
// the apps of a template, asked once, at the end of the import.
//
// What these tests protect:
//   - it asks only when there is something to ask — the permissions still OFF of the apps the
//     import left installed — and names each app and what stops working without it;
//   - one click grants them all; nothing is granted without that click (default-deny stays);
//   - a refusal is SAID, and only what failed stays on screen to retry;
//   - «Not now» grants nothing — the checklist keeps saying what is missing (hub#1905, 2nd half).
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';

const getModuleCapabilities = vi.fn();
const putModuleCapabilities = vi.fn();
vi.mock('../lib/runtime', async () => {
  const actual = await vi.importActual<typeof import('../lib/runtime')>('../lib/runtime');
  return {
    ...actual,
    getModuleCapabilities: (...a: unknown[]) => getModuleCapabilities(...a),
    putModuleCapabilities: (...a: unknown[]) => putModuleCapabilities(...a),
    getClient: () => ({}),
  };
});

const refreshSetupStatus = vi.fn();
vi.mock('../lib/setup-status', () => ({ refreshSetupStatus: (...a: unknown[]) => refreshSetupStatus(...a) }));

const appNames = vi.hoisted(() => new Map<string, string>());
vi.mock('../lib/app-names', async () => {
  const actual = await vi.importActual<typeof import('../lib/app-names')>('../lib/app-names');
  return { appLabel: actual.appLabel, loadAppNames: async () => appNames };
});
vi.mock('./HubIcon.vue', () => ({ default: { name: 'HubIcon', template: '<span />' } }));

import ImportPermissionsConsent from './ImportPermissionsConsent.vue';
import type { ImportReport, ModuleCapability } from '../lib/runtime';
import enCatalogue from '../i18n/locales/en';
import esCatalogue from '../i18n/locales/es';

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  missingWarn: false,
  fallbackWarn: false,
  messages: { en: enCatalogue },
});
const en = enCatalogue as unknown as {
  importPermissions: Record<string, string>;
  settings: { capabilityBreaks: Record<string, string> };
};

function cap(id: string, label: string, granted = false): ModuleCapability {
  return { id, label, description: `${label} — what it is for`, requested: true, granted };
}

/** What the «Peluquería» template left in the salon of hub#1905. */
function salonReport(): ImportReport {
  return {
    sections: [],
    installed_modules: [
      { id: 'verifactu', version: '1.5.40', status: 'installed' },
      { id: 'printing', version: '0.1.22', status: 'installed' },
      { id: 'customers', version: '1.0.0', status: 'already_installed' },
    ],
  } as ImportReport;
}

function mountConsent(report: ImportReport | null) {
  return mount(ImportPermissionsConsent, {
    props: { report },
    shallow: true,
    global: { plugins: [i18n], renderStubDefaultSlot: true },
  });
}

const modal = (w: ReturnType<typeof mountConsent>): VueWrapper =>
  w.getComponent('[data-testid="import-permissions"]') as VueWrapper;
const isOpen = (w: ReturnType<typeof mountConsent>): unknown =>
  (modal(w).props() as Record<string, unknown>).isOpen;

beforeEach(() => {
  getModuleCapabilities.mockReset().mockImplementation(async (id: string) => {
    if (id === 'verifactu') return { module_id: id, capabilities: [cap('certificate', 'Business certificate')] };
    if (id === 'printing') return { module_id: id, capabilities: [cap('printer', 'Printer')] };
    return { module_id: id, capabilities: [] };
  });
  putModuleCapabilities.mockReset().mockResolvedValue(undefined);
  refreshSetupStatus.mockReset().mockResolvedValue(undefined);
  appNames.clear();
  appNames.set('verifactu', 'VeriFactu');
  appNames.set('printing', 'Printing');
});

describe('when it asks', () => {
  it('at the end of an import, for the permissions still off of the apps it brought', async () => {
    const w = mountConsent(salonReport());
    await flushPromises();

    expect(isOpen(w)).toBe(true);
    const groups = w.findAll('[data-testid="import-permissions-app"]');
    expect(groups.map((g) => g.attributes('data-module'))).toEqual(['verifactu', 'printing']);
    expect(w.text()).toContain('VeriFactu');
    expect(w.text()).toContain('Business certificate');
    expect(w.text()).toContain('Printer');
  });

  it('says what stops working without each one, in the words Settings → Permissions uses', async () => {
    const w = mountConsent(salonReport());
    await flushPromises();

    expect(w.text()).toContain(en.settings.capabilityBreaks.certificate);
    expect(w.text()).toContain(en.settings.capabilityBreaks.printer);
  });

  it('asks nothing when every permission is already on', async () => {
    getModuleCapabilities.mockImplementation(async (id: string) => ({
      module_id: id,
      capabilities: [cap('certificate', 'Business certificate', true)],
    }));
    const w = mountConsent(salonReport());
    await flushPromises();

    expect(isOpen(w)).toBe(false);
    expect(putModuleCapabilities).not.toHaveBeenCalled();
  });

  it('asks nothing before there is a report (the import has not finished)', async () => {
    const w = mountConsent(null);
    await flushPromises();

    expect(getModuleCapabilities).not.toHaveBeenCalled();
    expect(isOpen(w)).toBe(false);
  });

  it('asks again for the next import, not only the first one', async () => {
    const w = mountConsent(null);
    await flushPromises();
    await w.setProps({ report: salonReport() });
    await flushPromises();

    expect(isOpen(w)).toBe(true);
  });
});

describe('granting', () => {
  it('one click grants every permission listed, and nothing is granted before it', async () => {
    const w = mountConsent(salonReport());
    await flushPromises();
    expect(putModuleCapabilities).not.toHaveBeenCalled();

    await w.find('[data-testid="import-permissions-grant"]').trigger('click');
    await flushPromises();

    expect(putModuleCapabilities).toHaveBeenCalledWith('verifactu', { certificate: true });
    expect(putModuleCapabilities).toHaveBeenCalledWith('printing', { printer: true });
    expect(isOpen(w)).toBe(false);
    // The checklist below re-reads: «Configure VeriFactu» stops waiting on the switch at once.
    expect(refreshSetupStatus).toHaveBeenCalled();
    expect(w.emitted('granted')).toHaveLength(1);
  });

  it('a refusal is said, and only what failed stays on screen to try again', async () => {
    putModuleCapabilities.mockImplementation(async (id: string) => {
      if (id === 'verifactu') throw new Error('put-capabilities verifactu → 401');
    });
    const w = mountConsent(salonReport());
    await flushPromises();

    await w.find('[data-testid="import-permissions-grant"]').trigger('click');
    await flushPromises();

    expect(isOpen(w)).toBe(true);
    const error = w.find('[data-testid="import-permissions-error"]');
    expect(error.exists()).toBe(true);
    expect(error.attributes('role')).toBe('alert');
    expect(w.findAll('[data-testid="import-permissions-app"]').map((g) => g.attributes('data-module'))).toEqual([
      'verifactu',
    ]);
    expect(w.emitted('granted')).toBeUndefined();
  });

  it('«Not now» grants nothing and closes', async () => {
    const w = mountConsent(salonReport());
    await flushPromises();

    await w.find('[data-testid="import-permissions-later"]').trigger('click');
    await flushPromises();

    expect(isOpen(w)).toBe(false);
    expect(putModuleCapabilities).not.toHaveBeenCalled();
  });
});

describe('the strings', () => {
  it('exist in English (source) and in Spanish', () => {
    const es = esCatalogue as unknown as { importPermissions: Record<string, string> };
    expect(Object.keys(en.importPermissions).length).toBeGreaterThan(3);
    expect(Object.keys(es.importPermissions).sort()).toEqual(Object.keys(en.importPermissions).sort());
  });
});
