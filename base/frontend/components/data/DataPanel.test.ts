// Settings › Data and backups (BASE-G101–G109): the old hub's selector of its three sections, Import (what opens),
// Export and Reset, with the section in the address (`?data=export`), so a link opens it and Back leaves the page.
import { afterEach, describe, expect, it, vi } from 'vitest';

import { flush, mountBase } from '../../__tests__/mount-base';
import DataPanel from './DataPanel.vue';

const STUBS = { ImportPanel: true, ExportPanel: true, ResetPanel: true };

async function panel(path = '/settings#data') {
  return mountBase(DataPanel, { path, routes: ['/settings'], stubs: STUBS });
}

const shown = (m: Awaited<ReturnType<typeof panel>>) =>
  m.wrapper.findAll('import-panel-stub, export-panel-stub, reset-panel-stub').map((el) => el.element.tagName.toLowerCase());

afterEach(() => {
  document.body.innerHTML = '';
});

describe('DataPanel', () => {
  it('offers Import, Export and Reset, and opens Import', async () => {
    const m = await panel();
    expect(m.wrapper.findAll('ion-segment-button').map((b) => (b.element as HTMLElement & { value?: string }).value)).toEqual([
      'import',
      'export',
      'reset',
    ]);
    // Ionic's labels render their text apart from the button's own: read from the panel's.
    expect(m.wrapper.get('[data-testid="data-sections"]').html()).toMatch(/Import[\s\S]*Export[\s\S]*Reset/);
    expect(m.wrapper.get('ion-segment').attributes('aria-label')).toBe('What to do with the data');
    expect(shown(m)).toEqual(['import-panel-stub']);
  });

  it('opens the section the address names', async () => {
    const m = await panel('/settings?data=export#data');
    expect((m.wrapper.get('ion-segment').element as HTMLElement & { value?: string }).value).toBe('export');
    expect(shown(m)).toEqual(['export-panel-stub']);
  });

  it('puts the section chosen in the address, keeping the tab, without a step of history', async () => {
    const m = await panel();
    const push = vi.spyOn(m.router, 'push');
    m.wrapper.get('ion-segment').element.dispatchEvent(new CustomEvent('ionChange', { detail: { value: 'reset' } }));
    await flush();
    expect(m.router.currentRoute.value.fullPath).toBe('/settings?data=reset#data');
    expect(push).not.toHaveBeenCalled();
    expect(shown(m)).toEqual(['reset-panel-stub']);
  });
});
