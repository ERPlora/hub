// VeriFactu → Configuration (VERIFACTU-F02–F06, F34; the old `erp-verifactu-config`): «VeriFactu configuration» with
// its two routes as tabs, «ERPlora files for you» (the representation authorisation's state) first, and «My
// certificate» (loaded or not, holder, uploaded and expiry dates, the warning before it expires). Both are managed in
// the ERPlora account: the Hub only shows what the account sent, and says when it has sent nothing yet.
import { describe, expect, it } from 'vitest';

import { click, mountVerifactu, settle } from '../__tests__/mount-verifactu';
import type { ConfigOut } from '../operations';
import ConfigPage from './ConfigPage.vue';

const CONFIG: ConfigOut = {
  environment: 'testing',
  route: 'erplora',
  production_since: null,
  production_open: false,
  can_go_back: true,
  gateway_configured: false,
  issuer_nif: 'B12345674',
  issuer_name: 'Peluquería Ana SL',
  producer: { name: 'ERPLORA CLOUD SL', nif: 'B27593136', system_name: 'ERPlora Hub', system_id: 'EC', version: 'dev', installation: 'a', only_verifactu: 'S', multi_ot: 'S', multiple_ot: '' },
  declaration_version: 'v1',
  declaration_url: 'https://erplora.com/legal/declaracion-responsable/v1/',
  account_url: 'https://erplora.com',
  own_certificate: { loaded: false, holder: '', uploaded_at: null, expires_at: null, expires_in_days: null },
  representation: { status: 'none', updated_at: null, reason: '' },
  synced_at: null,
  route_ready: true,
  reasons: [],
};

async function setup(config: Partial<ConfigOut> = {}) {
  const m = await mountVerifactu(ConfigPage, { path: '/verifactu/config' });
  await m.live();
  await m.result('verifactu.config.get', { ...CONFIG, ...config });
  return m;
}

describe('ConfigPage', () => {
  it('opens on «ERPlora files for you» and says the account has not sent anything yet', async () => {
    const s = await setup();
    expect(s.find('verifactu-config-erplora').exists()).toBe(true);
    expect(s.find('verifactu-config-not-synced').text()).toBe('Your ERPlora account has not sent this yet.');
    const manage = s.find('verifactu-config-manage');
    expect([manage.attributes('href'), manage.attributes('target')]).toEqual(['https://erplora.com', '_blank']);
  });

  it('says the authorisation’s state as the account sent it', async () => {
    const s = await setup({ synced_at: '2026-10-14T10:00:00Z', representation: { status: 'approved', updated_at: '2026-10-02T10:00:00Z', reason: '' } });
    expect(s.find('verifactu-config-grant').text()).toContain('ERPlora can file on your behalf.');
    const returned = await setup({ synced_at: '2026-10-14T10:00:00Z', representation: { status: 'returned', updated_at: '2026-10-02T10:00:00Z', reason: 'Unsigned page 2' } });
    expect(returned.find('verifactu-config-grant').text()).toContain('Returned on');
    expect(returned.find('verifactu-config-grant-reason').text()).toContain('Unsigned page 2');
  });

  it('«My certificate» says whether it is loaded, whose it is and when it expires', async () => {
    const s = await setup({
      synced_at: '2026-10-14T10:00:00Z',
      own_certificate: { loaded: true, holder: 'ANA LOPEZ', uploaded_at: '2026-10-01T10:00:00Z', expires_at: '2026-11-01T10:00:00Z', expires_in_days: 17 },
    });
    await click(s.find('verifactu-config-tab-own').element);
    expect(s.find('verifactu-config-cert').text()).toContain('Loaded');
    expect(s.find('verifactu-config-cert').text()).toContain('ANA LOPEZ');
    expect(s.find('verifactu-config-expiry').text()).toBe('Expires in 17 days: renew it in your ERPlora account.');
    expect(s.find('verifactu-config-keys').text()).toContain('never reach this Hub');
  });

  it('an expired certificate says so', async () => {
    const s = await setup({
      synced_at: '2026-10-14T10:00:00Z',
      own_certificate: { loaded: true, holder: 'ANA', uploaded_at: null, expires_at: '2026-10-01T10:00:00Z', expires_in_days: -13 },
    });
    await click(s.find('verifactu-config-tab-own').element);
    expect(s.find('verifactu-config-expiry').text()).toBe('The certificate has expired. Renew it to send to the AEAT.');
  });

  it('speaks Spanish', async () => {
    const m = await mountVerifactu(ConfigPage, { path: '/verifactu/config', locale: 'es' });
    await m.live();
    await m.result('verifactu.config.get', CONFIG);
    await settle();
    expect(m.wrapper.html()).toContain('Lo remite ERPlora');
    expect(m.wrapper.html()).toContain('Mi certificado');
    expect(m.find('verifactu-config-grant').text()).toBe('Sin firmar. Tu negocio no puede pasar a producción por la vía de ERPlora hasta que lo firmes.');
  });
});
