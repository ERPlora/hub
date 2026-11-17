import { describe, expect, it } from 'vitest';

import { CONFIG, CONFIG_WITHOUT_ERPLORA_ROUTE, LOADED_CERTIFICATE } from '../__tests__/config-fixture';
import { ionValue, mountVerifactu } from '../__tests__/mount-verifactu';
import type { ConfigOut } from '../operations';
import SettingsSendingRoute from './SettingsSendingRoute.vue';

async function setup(config: ConfigOut) {
  return mountVerifactu(SettingsSendingRoute, {
    props: { config, canConfigure: true, busy: false, outsideSpain: false },
  });
}

describe('SettingsSendingRoute', () => {
  it('keeps the route switch when ERPlora is available', async () => {
    const s = await setup(CONFIG);
    await ionValue(s.find('verifactu-settings-own').element, true);
    expect(s.wrapper.emitted('routeChange')).toHaveLength(1);
    expect(s.find('verifactu-settings-route-hint').text()).toContain('ERPlora files your billing records');
  });

  it('shows only the certificate and its next action when ERPlora is unavailable', async () => {
    const s = await setup(CONFIG_WITHOUT_ERPLORA_ROUTE);
    expect(s.find('verifactu-settings-own').exists()).toBe(false);
    expect(s.find('verifactu-settings-certificate').text()).toContain('No certificate uploaded');
    expect(s.find('verifactu-settings-certificate').text()).toContain('Upload your certificate');
  });

  it('links a valid certificate to its management', async () => {
    const s = await setup({ ...CONFIG_WITHOUT_ERPLORA_ROUTE, own_certificate: LOADED_CERTIFICATE });
    expect(s.find('verifactu-settings-certificate').text()).toContain('Valid');
    expect(s.find('verifactu-settings-certificate').text()).toContain('Manage certificate');
  });
});
