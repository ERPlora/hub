// Settings (the old hub's `/settings`; BASE-G96): the footer tabbar of its sections with the tab in the hash, so a link
// opens it and Back leaves the page. «Business» (APP-BASE-6: the business's data, its fiscal data), «Printing»
// (APP-BASE-6: printers and the ticket) and «Data and backups» (APP-BASE-2). The old hub's addresses still land:
// `#tax` on Business; one it does not have (`#hub`, `#store`, `#permissions`) on the first tab.
import { AppPage } from '@erplora/ui/shell';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { mountBase } from '../__tests__/mount-base';
import SettingsPage from './SettingsPage.vue';

async function settings(path = '/settings', locale: 'en' | 'es' = 'en') {
  return mountBase(SettingsPage, {
    path,
    locale,
    routes: ['/settings'],
    stubs: { DataPanel: true, BusinessPanel: true, TicketsPanel: true },
  });
}

afterEach(() => {
  document.body.innerHTML = '';
});

describe('SettingsPage', () => {
  it('is «Settings» with its three tabs, in the old hub’s order', async () => {
    const m = await settings('/settings#data', 'es');
    const page = m.wrapper.getComponent(AppPage);
    expect(page.props('title')).toBe('Ajustes');
    expect(page.props('tabs')).toEqual([
      { id: 'business', label: 'Negocio', icon: 'ion:wallet-outline' },
      { id: 'tickets', label: 'Impresión', icon: 'lucide:receipt' },
      { id: 'data', label: 'Datos y copias', icon: 'ion:swap-vertical-outline' },
    ]);
    expect(page.props('tabsLabel')).toBe('Secciones de Ajustes');
  });

  it('paints the panel of the tab in the address, and only that one', async () => {
    const panels = { '#business': 'business-panel-stub', '#tickets': 'tickets-panel-stub', '#data': 'data-panel-stub' };
    for (const [hash, shown] of Object.entries(panels)) {
      const m = await settings(`/settings${hash}`);
      for (const stub of Object.values(panels)) {
        expect(m.wrapper.find(stub).exists(), `${hash} ${stub}`).toBe(stub === shown);
      }
      m.wrapper.unmount();
    }
  });

  it('lands the old hub’s addresses: `#tax` on Business, and no hash or one it does not have on the first tab', async () => {
    for (const path of ['/settings', '/settings#tax', '/settings#hub', '/settings#permissions']) {
      const m = await settings(path);
      expect(m.wrapper.find('business-panel-stub').exists(), path).toBe(true);
      m.wrapper.unmount();
    }
  });

  it('choosing a tab replaces the address’s hash, so Back leaves Settings instead of walking its tabs', async () => {
    const m = await settings('/settings#business');
    // Memory history (mount-base) keeps no `state.position`: the proof is the call itself — a replace, never a push.
    const replace = vi.spyOn(m.router, 'replace');
    const push = vi.spyOn(m.router, 'push');
    m.wrapper.getComponent(AppPage).vm.$emit('update:tab', 'tickets');
    await m.router.isReady();
    await new Promise((resolve) => setTimeout(resolve));
    expect(m.router.currentRoute.value.hash).toBe('#tickets');
    expect(replace).toHaveBeenCalledTimes(1);
    expect(push).not.toHaveBeenCalled();
    expect(m.wrapper.find('tickets-panel-stub').exists()).toBe(true);
  });
});
