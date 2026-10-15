// VeriFactu → Configuration (VERIFACTU-F02–F06, F34; the old `erp-verifactu-config`): «VeriFactu configuration» with
// its two routes as tabs, «ERPlora files for you» (the representation authorisation's state, managed in the ERPlora
// account; the Hub shows what the account sent and says when it has sent nothing yet) first, and «My certificate»:
// loaded or not, holder, uploaded and expiry dates, the warning before it expires, and the business's .p12/.pfx
// uploaded here with its password («Upload the certificate») or removed («Remove», asking first). Only who
// configures VeriFactu uploads or removes it.
import { toastSuccess } from '@erplora/ui/shell';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { click, EMPLOYEE, ionValue, mountVerifactu, settle } from '../__tests__/mount-verifactu';
import type { ConfigOut } from '../operations';
import ConfigPage from './ConfigPage.vue';

const mocks = vi.hoisted(() => ({ confirm: vi.fn() }));
vi.mock('@erplora/ui/components', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/components')>()),
  useConfirm: () => ({ confirm: mocks.confirm }),
}));
vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...((await importOriginal()) as object),
  toastSuccess: vi.fn(() => Promise.resolve()),
}));
beforeEach(() => {
  mocks.confirm.mockReset();
  vi.mocked(toastSuccess).mockClear();
});

const CONFIG: ConfigOut = {
  environment: 'testing',
  route: 'erplora',
  production_since: null,
  production_open: false,
  can_go_back: true,
  gateway_configured: false,
  issuer_nif: 'B12345674',
  issuer_name: 'Peluquería Ana SL',
  producer: { name: 'ERPLORA CLOUD SL', nif: 'B27593136', system_name: 'ERPlora Hub', system_id: 'EC', version: 'dev', installation: 'a', only_verifactu: 'S', multi_ot: 'S', multiple_ot: 'S' },
  declaration_version: 'v1',
  declaration_url: 'https://erplora.com/legal/declaracion-responsable/v1/',
  account_url: 'https://erplora.com',
  own_certificate: { loaded: false, holder: '', holder_tax_id: '', kind: '', uploaded_at: null, expires_at: null, expires_in_days: null },
  representation: { status: 'none', updated_at: null, reason: '' },
  synced_at: null,
  route_ready: true,
  reasons: [],
  issue_blocker: null,
  live_blockers: [],
};

const LOADED: ConfigOut['own_certificate'] = {
  loaded: true,
  holder: 'ACME SL',
  holder_tax_id: 'B12345674',
  kind: 'representative',
  uploaded_at: '2026-10-01T10:00:00Z',
  expires_at: '2027-10-01T10:00:00Z',
  expires_in_days: 351,
};

async function setup(config: Partial<ConfigOut> = {}, options: { session?: typeof EMPLOYEE } = {}) {
  const m = await mountVerifactu(ConfigPage, { path: '/verifactu/config', session: options.session });
  await m.live();
  await m.result('verifactu.config.get', { ...CONFIG, ...config });
  return m;
}

async function ownTab(config: Partial<ConfigOut> = {}, options: { session?: typeof EMPLOYEE } = {}) {
  const m = await setup(config, options);
  await click(m.find('verifactu-config-tab-own').element);
  return m;
}

/** Picks `file` in the certificate's file input, as the browser's picker does. */
async function pick(m: Awaited<ReturnType<typeof setup>>, file: File): Promise<void> {
  const input = m.wrapper.get('[data-testid="verifactu-config-cert-file"]');
  Object.defineProperty(input.element, 'files', { value: [file], configurable: true });
  await input.trigger('change');
  await settle();
}

const P12 = new File([new Uint8Array([0x30, 0x82, 0x0a, 0xff])], 'acme.p12', { type: 'application/x-pkcs12' });

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
    const s = await ownTab({ own_certificate: { ...LOADED, expires_in_days: 17, expires_at: '2026-11-01T10:00:00Z' } });
    const cert = s.find('verifactu-config-cert').text();
    expect(cert).toContain('Loaded');
    expect(cert).toContain('ACME SL');
    expect(cert).toContain('B12345674');
    expect(cert).toContain('Representative of an entity');
    expect(s.find('verifactu-config-expiry').text()).toBe('Expires in 17 days: upload the renewed one here.');
    expect(s.find('verifactu-config-keys').text()).toContain('kept encrypted in this Hub');
  });

  it('an expired certificate says so', async () => {
    const s = await ownTab({ own_certificate: { ...LOADED, expires_at: '2026-10-01T10:00:00Z', expires_in_days: -13 } });
    expect(s.find('verifactu-config-expiry').text()).toBe('The certificate has expired. Upload a valid one to send to the AEAT.');
  });

  it('without a certificate it says so and offers to upload one', async () => {
    const s = await ownTab();
    expect(s.find('verifactu-config-cert').text()).toContain('Not loaded');
    expect(s.wrapper.get('[data-testid="verifactu-config-cert-file"]').attributes('accept')).toBe('.p12,.pfx');
    expect(s.find('verifactu-config-cert-choose').text()).toBe('Choose the .p12 / .pfx file');
    expect(s.find('verifactu-config-cert-upload').text()).toBe('Upload the certificate');
    expect(s.find('verifactu-config-cert-remove').exists()).toBe(false);
  });

  it('«Upload the certificate» sends the file in base64 with its password', async () => {
    const s = await ownTab();
    await pick(s, P12);
    expect(s.find('verifactu-config-cert-picked').text()).toBe('acme.p12');
    await ionValue(s.find('verifactu-config-cert-password').element, 'secret', 'ionInput');
    s.answer(201, { ...CONFIG, own_certificate: LOADED });
    await click(s.find('verifactu-config-cert-upload').element);
    await settle();
    expect(s.sent()).toEqual([
      { method: 'POST', path: '/api/verifactu/certificate', query: {}, body: { p12_base64: 'MIIK/w==', password: 'secret' } },
    ]);
    expect(toastSuccess).toHaveBeenCalledWith('Certificate uploaded: ACME SL (B12345674).');
    expect(s.find('verifactu-config-cert-picked').exists()).toBe(false);
  });

  it('without a file it asks for one and sends nothing', async () => {
    const s = await ownTab();
    await click(s.find('verifactu-config-cert-upload').element);
    expect(s.find('verifactu-config-cert-error').text()).toBe('Choose the .p12 / .pfx file first.');
    expect(s.sent()).toEqual([]);
  });

  it('a file larger than 1 MB is not a certificate and is not sent', async () => {
    const s = await ownTab();
    await pick(s, new File([new Uint8Array(1024 * 1024 + 1)], 'big.p12'));
    await click(s.find('verifactu-config-cert-upload').element);
    expect(s.find('verifactu-config-cert-error').text()).toBe('The file is larger than 1 MB: it is not a certificate.');
    expect(s.sent()).toEqual([]);
  });

  it('a refusal says why, as the server worded it', async () => {
    const s = await ownTab();
    await pick(s, P12);
    s.answer(409, { error: { code: 'verifactu.certificate_holder_mismatch', message: 'The certificate belongs to B99999999, not to this business’s issuer B12345674.' } });
    await click(s.find('verifactu-config-cert-upload').element);
    await settle();
    expect(s.find('verifactu-config-cert-error').text()).toBe('The certificate belongs to B99999999, not to this business’s issuer B12345674.');
    expect(toastSuccess).not.toHaveBeenCalled();
  });

  it('«Remove» asks first and removes it', async () => {
    const s = await ownTab({ own_certificate: LOADED });
    mocks.confirm.mockResolvedValue(true);
    s.answer(200, CONFIG);
    await click(s.find('verifactu-config-cert-remove').element);
    await settle();
    expect(mocks.confirm.mock.calls[0][0].title).toBe('Remove the certificate?');
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/verifactu/certificate/remove', query: {}, body: {} }]);
    expect(toastSuccess).toHaveBeenCalledWith('Certificate removed.');
  });

  it('«Remove» cancelled removes nothing', async () => {
    const s = await ownTab({ own_certificate: LOADED });
    mocks.confirm.mockResolvedValue(false);
    await click(s.find('verifactu-config-cert-remove').element);
    expect(s.sent()).toEqual([]);
  });

  it('who does not configure VeriFactu sees the certificate and cannot change it', async () => {
    const s = await ownTab({ own_certificate: LOADED }, { session: EMPLOYEE });
    expect(s.find('verifactu-config-cert').text()).toContain('ACME SL');
    expect(s.find('verifactu-config-cert-upload').exists()).toBe(false);
    expect(s.find('verifactu-config-cert-remove').exists()).toBe(false);
  });

  it('speaks Spanish', async () => {
    const m = await mountVerifactu(ConfigPage, { path: '/verifactu/config', locale: 'es' });
    await m.live();
    await m.result('verifactu.config.get', CONFIG);
    await settle();
    expect(m.wrapper.html()).toContain('Lo remite ERPlora');
    expect(m.wrapper.html()).toContain('Mi certificado');
    expect(m.find('verifactu-config-grant').text()).toBe('Sin firmar. Tu negocio no puede pasar a producción por la vía de ERPlora hasta que lo firmes.');
    await click(m.find('verifactu-config-tab-own').element);
    expect(m.find('verifactu-config-cert-upload').text()).toBe('Subir el certificado');
    expect(m.find('verifactu-config-cert-choose').text()).toBe('Elegir el fichero .p12 / .pfx');
  });
});
