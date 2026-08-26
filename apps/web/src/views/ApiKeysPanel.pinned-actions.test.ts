// @vitest-environment happy-dom
// hub#1204 — the per-row actions column (`_actions`) scrolled off-screen with six or more
// columns: it is a custom column (to hide Rotate/Revoke on revoked keys, ADR-0057), so it never
// got the pinned treatment ok-data-table gives its built-in actions column (outfitkit#67).
// OutfitKit 0.1.52 exposes `pinned: 'end'` on a column for exactly this host.
import { describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';

vi.mock('../lib/api-keys', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  listApiKeys: vi.fn(async () => []),
}));
vi.mock('../lib/runtime', () => ({ listInstalledModules: vi.fn(async () => []) }));
vi.mock('../lib/toast', () => ({ toastError: vi.fn(), toastSuccess: vi.fn() }));
vi.mock('../components/HubIcon.vue', () => ({ default: { name: 'HubIcon', template: '<span />' } }));

import '@erplora/outfitkit/ok-data-table';
import ApiKeysPanel from './ApiKeysPanel.vue';
import { i18n } from '../i18n';

describe('ApiKeysPanel: the actions column stays reachable (hub#1204)', () => {
  it('pins the `_actions` column to the end so it cannot scroll off-screen', async () => {
    const wrapper = mount(ApiKeysPanel, { global: { plugins: [i18n] } });
    await flushPromises();
    const table = wrapper.find('ok-data-table');
    expect(table.exists(), 'the panel renders its list as an ok-data-table').toBe(true);
    const columns = (table.element as unknown as { columns: Array<Record<string, unknown>> }).columns;
    const actions = columns.find((c) => c.key === '_actions');
    expect(actions, 'the per-row actions column exists').toBeTruthy();
    expect(actions?.pinned, 'the actions column declares pinned: "end" (outfitkit 0.1.52)').toBe('end');
  });
});
