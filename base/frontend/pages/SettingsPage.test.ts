// Settings › General (`/settings`; the old hub's «Ajustes › General», BASE-G72, G151, G62, G63…G66): «This device»,
// «PIN pad» and «Devices». Whoever does not run the hub sees the first two disabled and, instead of the devices (whose
// list is an administrator's), why: no list is asked for.
import { afterEach, describe, expect, it } from 'vitest';

import { EMPLOYEE, mountBase } from '../__tests__/mount-base';
import SettingsPage from './SettingsPage.vue';

afterEach(() => {
  document.body.innerHTML = '';
});

describe('SettingsPage — General', () => {
  it('an administrator gets this device, the PIN pad and the devices', async () => {
    const { wrapper, client } = await mountBase(SettingsPage, { path: '/settings', routes: ['/settings'] });
    for (const card of ['device-mode-card', 'pin-policy-card', 'devices-card']) {
      expect(wrapper.find(`[data-testid="${card}"]`).exists()).toBe(true);
    }
    expect(client.stream.subscriptions('base.device.list')).toHaveLength(1);
  });

  it('whoever does not run the hub reads why there are no devices, and none are asked for', async () => {
    const { wrapper, client } = await mountBase(SettingsPage, { path: '/settings', routes: ['/settings'], session: EMPLOYEE });
    expect(wrapper.find('[data-testid="devices-card"]').exists()).toBe(false);
    expect(wrapper.get('[data-testid="devices-admin-only"]').text()).toContain(
      'Only an administrator can see and remove the devices.',
    );
    expect(client.stream.subscriptions('base.device.list')).toHaveLength(0);
  });

  it('speaks Spanish', async () => {
    const { wrapper } = await mountBase(SettingsPage, { path: '/settings', routes: ['/settings'], locale: 'es', session: EMPLOYEE });
    expect(wrapper.text()).toContain('Este dispositivo');
    expect(wrapper.text()).toContain('Pinpad');
    expect(wrapper.text()).toContain('Dispositivos');
  });
});
