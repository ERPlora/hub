// VeriFactu → Configuration (VERIFACTU-F02–F06, F34; the old `erp-verifactu-config`): «VeriFactu configuration» with
// its two routes as tabs, «ERPlora files for you» (the representation authorisation: its state as the account sent it,
// and the procedure to sign and send it from here, `RepresentationGrant`; it says when the account has sent nothing
// yet) first, and «My certificate»:
// loaded or not, holder, uploaded and expiry dates, the warning before it expires, and the business's .p12/.pfx
// uploaded here with its password («Upload the certificate») or removed («Remove», asking first). Only who
// configures VeriFactu uploads or removes it.
import { toastSuccess } from '@erplora/ui/shell';
import { IonButton } from '@ionic/vue';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { CONFIG, CONFIG_WITHOUT_ERPLORA_ROUTE, LOADED_CERTIFICATE } from '../__tests__/config-fixture';
import { click, EMPLOYEE, ionValue, mountVerifactu, settle } from '../__tests__/mount-verifactu';
import type { ConfigOut } from '../operations';
import ConfigPage from './ConfigPage.vue';

const mocks = vi.hoisted(() => ({ confirm: vi.fn() }));
vi.mock('@erplora/ui/components', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/components')>()),
  useConfirm: () => ({ confirm: mocks.confirm }),
}));
beforeEach(() => {
  mocks.confirm.mockReset();
});

const LOADED = LOADED_CERTIFICATE;

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
  });

  it('the authorisation is signed and sent from here, not from the account', async () => {
    const s = await setup();
    expect(s.find('verifactu-config-manage').exists()).toBe(false);
    expect(s.find('verifactu-grant-form').exists()).toBe(true);
    expect(s.find('verifactu-grant-download').exists()).toBe(true);
  });

  it('who does not configure VeriFactu sees the authorisation’s state and cannot send it', async () => {
    const s = await setup({}, { session: EMPLOYEE });
    expect(s.find('verifactu-config-grant').exists()).toBe(true);
    expect(s.find('verifactu-grant-form').exists()).toBe(false);
  });

  it('says the authorisation’s state as the account sent it', async () => {
    const s = await setup({ synced_at: '2026-10-14T10:00:00Z', representation: { ...CONFIG.representation, status: 'approved', updated_at: '2026-10-02T10:00:00Z' } });
    expect(s.find('verifactu-config-grant').text()).toContain('ERPlora can file on your behalf.');
    const returned = await setup({ synced_at: '2026-10-14T10:00:00Z', representation: { ...CONFIG.representation, status: 'returned', updated_at: '2026-10-02T10:00:00Z', reason: 'Unsigned page 2' } });
    expect(returned.find('verifactu-config-grant').text()).toContain('Returned on');
    expect(returned.find('verifactu-config-grant-reason').text()).toContain('Unsigned page 2');
  });

  it('«My certificate» says whether it is loaded, whose it is and when it expires', async () => {
    const s = await ownTab({ own_certificate: { ...LOADED, expires_in_days: 17, expires_soon: true, expires_at: '2026-11-01T10:00:00Z' } });
    const cert = s.find('verifactu-config-cert').text();
    expect(cert).toContain('Loaded');
    expect(cert).toContain('ACME SL');
    expect(cert).toContain('B12345674');
    expect(cert).toContain('Representative of an entity');
    expect(s.find('verifactu-config-expiry').text()).toBe('Expires in 17 days: upload the renewed one here.');
    expect(s.find('verifactu-config-keys').text()).toContain('kept encrypted in this Hub');
  });

  it('warns of the expiry only when the server says it expires soon', async () => {
    const soon = await ownTab({ own_certificate: { ...LOADED, expires_in_days: 45, expires_soon: true } });
    expect(soon.find('verifactu-config-expiry').text()).toBe('Expires in 45 days: upload the renewed one here.');
    const notYet = await ownTab({ own_certificate: { ...LOADED, expires_in_days: 17, expires_soon: false } });
    expect(notYet.find('verifactu-config-expiry').exists()).toBe(false);
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

  it.each([
    ['testing', 'own', 'You can keep testing without it: your test records keep going out.'],
    ['production', 'own', 'Records will wait until you upload another certificate.'],
    ['production', 'erplora', "Your records keep going out with ERPlora's seal."],
  ] as const)('«Remove» in %s on the %s route says what happens to the records', async (environment, route, message) => {
    const s = await ownTab({ environment, route, own_certificate: LOADED });
    mocks.confirm.mockResolvedValue(false);
    await click(s.find('verifactu-config-cert-remove').element);
    expect(mocks.confirm.mock.calls[0][0].message).toBe(message);
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

  // VeriFactu is only for Spain; outside it neither the authorisation for ERPlora nor an own certificate is offered,
  // with that one reason in sight.
  const OUTSIDE_SPAIN = { code: 'outside_spain', message: 'this business is not in Spain: VeriFactu is only for businesses in Spain, so nothing is sent to the AEAT' };

  it('outside Spain it says VeriFactu is only for Spain and offers neither the authorisation nor a certificate', async () => {
    const s = await setup({ live_blockers: [OUTSIDE_SPAIN] });
    expect(s.find('verifactu-config-outside-spain').text()).toBe('VeriFactu is only for businesses in Spain.');
    // That one reason: no authorisation to sign («Not signed… until you sign it») nor the account's sync.
    expect(s.find('verifactu-config-grant').exists()).toBe(false);
    expect(s.find('verifactu-config-not-synced').exists()).toBe(false);
    expect(s.find('verifactu-grant-form').exists()).toBe(false);
    await click(s.find('verifactu-config-tab-own').element);
    expect(s.find('verifactu-config-cert').exists()).toBe(true);
    expect(s.find('verifactu-config-cert-form').exists()).toBe(false);
  });

  it('in Spain it says nothing of it and offers both', async () => {
    const s = await setup();
    expect(s.find('verifactu-config-outside-spain').exists()).toBe(false);
    expect(s.find('verifactu-grant-form').exists()).toBe(true);
    await click(s.find('verifactu-config-tab-own').element);
    expect(s.find('verifactu-config-cert-form').exists()).toBe(true);
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

  it('without the ERPlora route it shows the own certificate directly and nothing of the authorisation', async () => {
    const s = await setup(CONFIG_WITHOUT_ERPLORA_ROUTE);
    expect(s.find('verifactu-config-tab-erplora').exists()).toBe(false);
    expect(s.find('verifactu-config-tab-own').exists()).toBe(false);
    expect(s.find('verifactu-config-erplora').exists()).toBe(false);
    expect(s.find('verifactu-config-grant').exists()).toBe(false);
    expect(s.find('verifactu-grant-form').exists()).toBe(false);
    expect(s.find('verifactu-config-own').exists()).toBe(true);
    expect(s.find('verifactu-config-cert-status').text()).toBe('No certificate uploaded');
    expect(s.wrapper.text()).not.toContain('ERPlora');
    expect(s.wrapper.text()).not.toMatch(/authorisation|representation/i);
  });

  it('in testing without a certificate it reassures instead of warning', async () => {
    const s = await setup(CONFIG_WITHOUT_ERPLORA_ROUTE);
    expect(s.find('verifactu-config-testing-note').text()).toBe('You can test VeriFactu without a certificate. You only need one to go live.');
    expect(s.find('verifactu-config-expiry').exists()).toBe(false);
  });

  it.each([
    { days: 351, soon: false, label: 'Valid' },
    { days: 17, soon: true, label: 'Expires soon' },
    { days: 45, soon: true, label: 'Expires soon' },
    { days: 17, soon: false, label: 'Valid' },
    { days: -1, soon: false, label: 'Expired' },
  ])('gives a certificate with $days days left, expiring soon $soon, the explicit status $label', async ({ days, soon, label }) => {
    const s = await setup({ ...CONFIG_WITHOUT_ERPLORA_ROUTE, own_certificate: { ...LOADED, expires_in_days: days, expires_soon: soon } });
    expect(s.find('verifactu-config-cert-status').text()).toBe(label);
    expect(s.find('verifactu-config-cert').text()).toContain('ACME SL');
  });

  it('keeps one primary action in the certificate card', async () => {
    const s = await setup({ ...CONFIG_WITHOUT_ERPLORA_ROUTE, own_certificate: LOADED });
    const primary = s.wrapper.findAllComponents(IonButton).filter((button) => button.props('fill') !== 'outline');
    expect(primary).toHaveLength(1);
    expect(primary[0].attributes('data-testid')).toBe('verifactu-config-cert-upload');
  });

  it('does not name the ERPlora route when removing the certificate in testing', async () => {
    const s = await setup({ ...CONFIG_WITHOUT_ERPLORA_ROUTE, own_certificate: LOADED });
    mocks.confirm.mockResolvedValue(false);
    await click(s.find('verifactu-config-cert-remove').element);
    expect(mocks.confirm.mock.calls[0][0].message).toBe('You can keep testing without it: your test records keep going out.');
  });

  it('speaks Spanish without the ERPlora route', async () => {
    const m = await mountVerifactu(ConfigPage, { path: '/verifactu/config', locale: 'es' });
    await m.live();
    await m.result('verifactu.config.get', CONFIG_WITHOUT_ERPLORA_ROUTE);
    await settle();
    expect(m.find('verifactu-config-cert-status').text()).toBe('Sin certificado');
    expect(m.find('verifactu-config-testing-note').text()).toBe('Puedes probar VeriFactu sin certificado. Solo lo necesitas para pasar a producción.');
    expect(m.wrapper.text()).not.toContain('ERPlora');
    expect(m.wrapper.text()).not.toMatch(/autorización|otorgamiento|representación/i);
  });
});
