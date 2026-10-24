// Settings (the old hub's `/settings`, APP-BASE-2): the footer tabbar of its sections with the tab in the hash
// (`#data`), and today only «Data and backups» — Hub, Business, Tickets and Permissions come with their own flows
// (APP-BASE-6), never painted empty. An unknown or old hash (`#tax`, `#hub`) opens the first tab there is.
import { AppPage } from '@erplora/ui/shell';
import { afterEach, describe, expect, it } from 'vitest';

import { mountBase } from '../__tests__/mount-base';
import SettingsPage from './SettingsPage.vue';

async function settings(path = '/settings', locale: 'en' | 'es' = 'en') {
  return mountBase(SettingsPage, { path, locale, routes: ['/settings'], stubs: { DataPanel: true } });
}

afterEach(() => {
  document.body.innerHTML = '';
});

describe('SettingsPage', () => {
  it('is «Settings» with one tab, «Data and backups», and its panel', async () => {
    const m = await settings('/settings#data', 'es');
    const page = m.wrapper.getComponent(AppPage);
    expect(page.props('title')).toBe('Ajustes');
    expect(page.props('tabs')).toEqual([{ id: 'data', label: 'Datos y copias', icon: 'ion:swap-vertical-outline' }]);
    expect(page.props('tabsLabel')).toBe('Secciones de Ajustes');
    expect(m.wrapper.find('data-panel-stub').exists()).toBe(true);
  });

  it('opens «Data and backups» from an address with no tab, or with one of the old hub that is not here yet', async () => {
    for (const path of ['/settings', '/settings#tax', '/settings#hub']) {
      const m = await settings(path);
      expect(m.wrapper.find('[data-testid="tab-data"]').exists(), path).toBe(true);
      expect(m.wrapper.find('data-panel-stub').exists(), path).toBe(true);
      m.wrapper.unmount();
    }
  });
});
