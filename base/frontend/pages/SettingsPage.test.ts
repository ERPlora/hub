// Settings (the old hub's `/settings`): the footer tabbar of its sections with the tab in the hash. «General» first, as
// in the old hub (APP-BASE-3: «This device», «PIN pad» and «Devices», BASE-G72, G151, G62, G63…G66), then «Data and
// backups» (`#data`, APP-BASE-2); Hub, Business, Tickets and Permissions come with their own flows (APP-BASE-6), never
// painted empty. An unknown or old hash (`#tax`, `#hub`) opens the first tab there is. Whoever does not run the hub
// sees the first two cards of General disabled and, instead of the devices (whose list is an administrator's), why: no
// list is asked for.
import { AppPage } from '@erplora/ui/shell';
import { afterEach, describe, expect, it } from 'vitest';

import { EMPLOYEE, type MountOptions, mountBase } from '../__tests__/mount-base';
import SettingsPage from './SettingsPage.vue';

async function settings(path = '/settings', locale: 'en' | 'es' = 'en', session?: MountOptions['session']) {
  return mountBase(SettingsPage, { path, locale, session, routes: ['/settings'], stubs: { DataPanel: true } });
}

const GENERAL_CARDS = ['device-mode-card', 'pin-policy-card', 'devices-card'];

afterEach(() => {
  document.body.innerHTML = '';
});

describe('SettingsPage', () => {
  it('is «Settings» with two tabs, «General» first and «Data and backups»', async () => {
    const m = await settings('/settings', 'es');
    const page = m.wrapper.getComponent(AppPage);
    expect(page.props('title')).toBe('Ajustes');
    expect(page.props('tabs')).toEqual([
      { id: 'general', label: 'General', icon: 'ion:settings-outline' },
      { id: 'data', label: 'Datos y copias', icon: 'ion:swap-vertical-outline' },
    ]);
    expect(page.props('tabsLabel')).toBe('Secciones de Ajustes');
  });

  it('opens «Data and backups» at `#data`, without the cards of General', async () => {
    const m = await settings('/settings#data');
    expect(m.wrapper.find('data-panel-stub').exists()).toBe(true);
    for (const card of GENERAL_CARDS) expect(m.wrapper.find(`[data-testid="${card}"]`).exists(), card).toBe(false);
    expect(m.client.stream.subscriptions('base.device.list')).toHaveLength(0);
  });

  it('opens «General» from an address with no tab, its own, or one of the old hub that is not here yet', async () => {
    for (const path of ['/settings', '/settings#general', '/settings#tax', '/settings#hub']) {
      const m = await settings(path);
      expect(m.wrapper.find('[data-testid="tab-general"]').exists(), path).toBe(true);
      expect(m.wrapper.find('[data-testid="device-mode-card"]').exists(), path).toBe(true);
      expect(m.wrapper.find('data-panel-stub').exists(), path).toBe(false);
      m.wrapper.unmount();
    }
  });
});

describe('SettingsPage — General', () => {
  it('an administrator gets this device, the PIN pad and the devices', async () => {
    const { wrapper, client } = await settings();
    for (const card of GENERAL_CARDS) expect(wrapper.find(`[data-testid="${card}"]`).exists(), card).toBe(true);
    expect(client.stream.subscriptions('base.device.list')).toHaveLength(1);
  });

  it('whoever does not run the hub reads why there are no devices, and none are asked for', async () => {
    const { wrapper, client } = await settings('/settings', 'en', EMPLOYEE);
    expect(wrapper.find('[data-testid="devices-card"]').exists()).toBe(false);
    expect(wrapper.get('[data-testid="devices-admin-only"]').text()).toContain(
      'Only an administrator can see and remove the devices.',
    );
    expect(client.stream.subscriptions('base.device.list')).toHaveLength(0);
  });

  it('speaks Spanish', async () => {
    const { wrapper } = await settings('/settings', 'es', EMPLOYEE);
    expect(wrapper.text()).toContain('Este dispositivo');
    expect(wrapper.text()).toContain('Pinpad');
    expect(wrapper.text()).toContain('Dispositivos');
  });
});
