import { AppPage, type SessionMe } from '@erplora/ui/shell';
import { nextTick, ref } from 'vue';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { EMPLOYEE, type MountOptions, mountBase, OWNER } from '../__tests__/mount-base';
import SettingsPage from './SettingsPage.vue';

// The owner holds every permission, Printing's included.
const OWNER_ALL: SessionMe = { ...OWNER, permissions: [...OWNER.permissions, 'printing.manage_settings'] };
// A manager sets Printing up but does not run the business.
const MANAGER: SessionMe = { ...EMPLOYEE, user: { id: 'u3', label: 'Eva' }, permissions: [...EMPLOYEE.permissions, 'printing.manage_settings'] };

async function settings(path = '/settings', locale: 'en' | 'es' = 'en', session: MountOptions['session'] = OWNER_ALL) {
  return mountBase(SettingsPage, {
    path,
    locale,
    session,
    routes: ['/settings'],
    stubs: { DataPanel: true, BusinessPanel: true, TicketsPanel: true },
  });
}

/** The ids of the tabs the page offers. */
function tabIds(m: Awaited<ReturnType<typeof settings>>): string[] {
  return (m.wrapper.getComponent(AppPage).props('tabs') ?? []).map((tab) => tab.id);
}

// «API documentation» closes General.
const GENERAL_CARDS = ['device-mode-card', 'pin-policy-card', 'devices-card', 'api-docs-card'];

afterEach(() => {
  document.body.innerHTML = '';
});

describe('SettingsPage', () => {
  it('is «Settings» with its four tabs, «General» first', async () => {
    const m = await settings('/settings#data', 'es');
    const page = m.wrapper.getComponent(AppPage);
    expect(page.props('title')).toBe('Ajustes');
    expect(page.props('tabs')).toEqual([
      { id: 'general', label: 'General', icon: 'ion:settings-outline' },
      { id: 'business', label: 'Negocio', icon: 'ion:wallet-outline' },
      { id: 'tickets', label: 'Impresión', icon: 'lucide:receipt' },
      { id: 'data', label: 'Datos y copias', icon: 'ion:swap-vertical-outline' },
    ]);
    expect(page.props('tabsLabel')).toBe('Secciones de Ajustes');
  });

  it('an employee has only «General» and «Business»: Printing and Data are not theirs to use', async () => {
    const m = await settings('/settings', 'es', EMPLOYEE);
    expect(tabIds(m)).toEqual(['general', 'business']);
  });

  it('a manager also has «Printing», and not «Data and backups»', async () => {
    const m = await settings('/settings', 'en', MANAGER);
    expect(tabIds(m)).toEqual(['general', 'business', 'tickets']);
  });

  it('a link to a tab the person does not have opens their first one, and paints nothing of the other', async () => {
    for (const path of ['/settings#data', '/settings#tickets']) {
      const m = await settings(path, 'en', EMPLOYEE);
      expect(m.wrapper.find('[data-testid="device-mode-card"]').exists(), path).toBe(true);
      expect(m.wrapper.find('data-panel-stub').exists(), path).toBe(false);
      expect(m.wrapper.find('tickets-panel-stub').exists(), path).toBe(false);
      m.wrapper.unmount();
    }
  });

  it('follows the session: a permission taken away on its tab takes the tab away and opens the first', async () => {
    const session = ref<SessionMe>(OWNER_ALL);
    const m = await settings('/settings#data', 'en', session);
    expect(m.wrapper.find('data-panel-stub').exists()).toBe(true);
    session.value = MANAGER;
    await nextTick();
    expect(tabIds(m)).not.toContain('data');
    expect(m.wrapper.find('data-panel-stub').exists()).toBe(false);
    expect(m.wrapper.find('[data-testid="device-mode-card"]').exists()).toBe(true);
  });

  it('opens «General» from an address with no tab, its own, the older `#hub` or one it does not have', async () => {
    for (const path of ['/settings', '/settings#general', '/settings#hub', '/settings#permissions']) {
      const m = await settings(path);
      expect(m.wrapper.find('[data-testid="tab-general"]').exists(), path).toBe(true);
      expect(m.wrapper.find('[data-testid="device-mode-card"]').exists(), path).toBe(true);
      expect(m.wrapper.find('business-panel-stub').exists(), path).toBe(false);
      expect(m.wrapper.find('data-panel-stub').exists(), path).toBe(false);
      m.wrapper.unmount();
    }
  });

  it('paints the panel of the tab in the address, and only that one, without the cards of General', async () => {
    const panels = { '#business': 'business-panel-stub', '#tickets': 'tickets-panel-stub', '#data': 'data-panel-stub' };
    for (const [hash, shown] of Object.entries(panels)) {
      const m = await settings(`/settings${hash}`);
      for (const card of GENERAL_CARDS) expect(m.wrapper.find(`[data-testid="${card}"]`).exists(), `${hash} ${card}`).toBe(false);
      expect(m.client.stream.subscriptions('base.device.list'), hash).toHaveLength(0);
      for (const stub of Object.values(panels)) {
        expect(m.wrapper.find(stub).exists(), `${hash} ${stub}`).toBe(stub === shown);
      }
      m.wrapper.unmount();
    }
  });

  it('lands the older `#tax` on Business, the business’s own tab', async () => {
    const m = await settings('/settings#tax');
    expect(m.wrapper.find('business-panel-stub').exists()).toBe(true);
    expect(m.wrapper.find('[data-testid="device-mode-card"]').exists()).toBe(false);
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
