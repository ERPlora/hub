import { describe, expect, it } from 'vitest';

import { CONFIG, CONFIG_WITHOUT_ERPLORA_ROUTE, LOADED_CERTIFICATE } from '../__tests__/config-fixture';
import { mountVerifactu } from '../__tests__/mount-verifactu';
import type { ConfigOut } from '../operations';
import SettingsSendingRoute from './SettingsSendingRoute.vue';

async function setup(config: ConfigOut, locale: 'en' | 'es' = 'en') {
  return mountVerifactu(SettingsSendingRoute, { props: { config, canConfigure: true }, locale });
}

const APPROVED: ConfigOut['representation'] = { ...CONFIG.representation, status: 'approved' };

describe('SettingsSendingRoute', () => {
  it('says the own certificate files, with nothing to switch', async () => {
    const s = await setup({ ...CONFIG, route: 'own', own_certificate: LOADED_CERTIFICATE });
    expect(s.find('verifactu-settings-route-hint').text()).toContain('You file directly with the tax agency using your business certificate');
    expect(s.find('verifactu-settings-route-hint').attributes('data-route')).toBe('own');
    expect(s.wrapper.find('ion-toggle').exists()).toBe(false);
  });

  it('says ERPlora files for the business once its authorisation is approved', async () => {
    const s = await setup({ ...CONFIG, representation: APPROVED });
    expect(s.find('verifactu-settings-route-hint').text()).toContain('your signed authorisation is approved');
    expect(s.find('verifactu-settings-route-hint').attributes('data-route')).toBe('erploraApproved');
  });

  it('in testing without the authorisation says what is missing to go live', async () => {
    const s = await setup(CONFIG);
    expect(s.find('verifactu-settings-route-hint').text()).toContain(
      'ERPlora files your test records with its seal. To go live, upload your business certificate or get ERPlora to approve your signed authorisation.',
    );
  });

  it('in production without the authorisation says the records wait', async () => {
    const s = await setup({ ...CONFIG, environment: 'production', can_go_back: false });
    expect(s.find('verifactu-settings-route-hint').text()).toContain('your records wait until it is');
    expect(s.find('verifactu-settings-route-hint').attributes('data-route')).toBe('erploraWaiting');
  });

  it('says it in Spanish too', async () => {
    const s = await setup({ ...CONFIG, route: 'own', own_certificate: LOADED_CERTIFICATE }, 'es');
    expect(s.find('verifactu-settings-route-hint').text()).toContain('Envías tú directamente a Hacienda con el certificado de tu negocio');
  });

  it('shows only the certificate and its next action when ERPlora is unavailable', async () => {
    const s = await setup(CONFIG_WITHOUT_ERPLORA_ROUTE);
    expect(s.find('verifactu-settings-route-hint').exists()).toBe(false);
    expect(s.find('verifactu-settings-certificate').text()).toContain('No certificate uploaded');
    expect(s.find('verifactu-settings-certificate').text()).toContain('Upload your certificate');
  });

  it('links a valid certificate to its management', async () => {
    const s = await setup({ ...CONFIG_WITHOUT_ERPLORA_ROUTE, own_certificate: LOADED_CERTIFICATE });
    expect(s.find('verifactu-settings-certificate').text()).toContain('Valid');
    expect(s.find('verifactu-settings-certificate').text()).toContain('Manage certificate');
  });
});
