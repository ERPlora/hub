// @vitest-environment happy-dom
// hub#2207 — Settings › Data & copies: the purpose chosen in Export survives a visit to Reset.
//
// Reset's «Export before deleting» sends the owner back to Export, so going Export → Reset → Export
// is the path the screen itself invites. The sub-views are swapped with v-if, so ExportPanel was
// rebuilt from scratch and the purpose fell back to «Backup»: an owner who had picked «Template»
// could download a backup (identities and fiscal data included) believing it was a template.
//
// Mounted with the REAL ExportPanel (only its transport is stubbed): the contract is what the
// panel sends to the engine after the round trip, not a prop on a stub.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';

const exportHub = vi.fn();
const listInstalledModules = vi.fn();
const fetchExportTables = vi.fn();

vi.mock('../lib/runtime', () => ({
  exportHub: (...a: unknown[]) => exportHub(...a),
  listInstalledModules: (...a: unknown[]) => listInstalledModules(...a),
  fetchExportTables: (...a: unknown[]) => fetchExportTables(...a),
}));
vi.mock('../lib/session', () => ({ isAdmin: { value: true } }));
vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock('./HubIcon.vue', () => ({ default: { name: 'HubIcon', template: '<span />' } }));
vi.mock('./ImportPanel.vue', () => ({ default: { name: 'ImportPanel', template: '<div />' } }));
vi.mock('./ResetPanel.vue', () => ({ default: { name: 'ResetPanel', template: '<div />' } }));

import DataPanel from './DataPanel.vue';
import ExportPanel from './ExportPanel.vue';

const i18n = createI18n({ legacy: false, locale: 'en', missingWarn: false, fallbackWarn: false, messages: { en: {} } });

function mountPanel() {
  return mount(DataPanel, {
    props: { initial: 'export' },
    shallow: true,
    global: { plugins: [i18n], renderStubDefaultSlot: true, stubs: { ExportPanel: false } },
  });
}

async function switchTo(w: VueWrapper, view: 'import' | 'export' | 'reset'): Promise<void> {
  (w.getComponent('[data-testid="data-view-segment"]') as VueWrapper).vm.$emit(
    'ionChange',
    new CustomEvent('ionChange', { detail: { value: view } }),
  );
  await flushPromises();
}

async function pickPurpose(w: VueWrapper, purpose: 'backup' | 'template'): Promise<void> {
  (w.getComponent('[data-testid="export-purpose"]') as VueWrapper).vm.$emit('update:modelValue', purpose);
  await flushPromises();
}

async function purposeSent(w: VueWrapper): Promise<unknown> {
  await (w.getComponent(ExportPanel).vm as unknown as { doExport: () => Promise<void> }).doExport();
  await flushPromises();
  return (exportHub.mock.calls.at(-1)?.[2] as Record<string, unknown>).purpose;
}

beforeEach(() => {
  exportHub.mockReset().mockResolvedValue({ blob: new Blob(['x']), filename: 'hub_es.blueprint.zip' });
  listInstalledModules.mockReset().mockResolvedValue([]);
  fetchExportTables.mockReset().mockResolvedValue({ modules: [], lockedPurpose: null });
});

describe('DataPanel · Export keeps its purpose across the sub-views (hub#2207)', () => {
  it('Template chosen, Reset visited, back to Export: still Template', async () => {
    const w = mountPanel();
    await flushPromises();
    await pickPurpose(w, 'template');

    await switchTo(w, 'reset');
    expect(w.findComponent(ExportPanel).exists()).toBe(false);
    await switchTo(w, 'export');

    // The users/fiscal boxes stay hidden: the form is still in template mode…
    expect(w.find('[data-testid="export-section-users"]').exists()).toBe(false);
    // …and that is what reaches the engine.
    expect(await purposeSent(w)).toBe('template');
  });

  it('through Import too', async () => {
    const w = mountPanel();
    await flushPromises();
    await pickPurpose(w, 'template');

    await switchTo(w, 'import');
    await switchTo(w, 'export');

    expect(await purposeSent(w)).toBe('template');
  });

  it('a fresh Data & copies still starts on Backup, the conservative default', async () => {
    const w = mountPanel();
    await flushPromises();
    expect(await purposeSent(w)).toBe('backup');
  });
});
