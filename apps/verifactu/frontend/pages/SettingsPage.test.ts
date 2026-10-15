// VeriFactu → Settings (VERIFACTU-F04, F08–F12; the old `erp-verifactu-settings`): «Sending» (the «Use my own
// certificate» switch and the AEAT environment with «Go live» / «Back to testing», each asking first), «Live test»
// («Test the connection», presenting nothing, and «Create test invoice» in testing) and «Responsible declaration»
// (the signed declaration and the identifying data of this system).
import { toastSuccess } from '@erplora/ui/shell';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { click, EMPLOYEE, flush, ionValue, type MountOptions, mountVerifactu } from '../__tests__/mount-verifactu';
import type { ConfigOut, DiagnosticOut } from '../operations';
import SettingsPage from './SettingsPage.vue';

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
  production_open: true,
  can_go_back: true,
  gateway_configured: false,
  issuer_nif: 'B12345674',
  issuer_name: 'Peluquería Ana SL',
  producer: { name: 'ERPLORA CLOUD SL', nif: 'B27593136', system_name: 'ERPlora Hub', system_id: 'EC', version: 'dev', installation: 'a', only_verifactu: 'S', multi_ot: 'S', multiple_ot: '' },
  declaration_version: 'v1',
  declaration_url: 'https://erplora.com/legal/declaracion-responsable/v1/',
  account_url: 'https://erplora.com',
  own_certificate: { loaded: false, holder: '', holder_tax_id: '', kind: '', uploaded_at: null, expires_at: null, expires_in_days: null },
  representation: { status: 'none', updated_at: null, reason: '' },
  synced_at: null,
  route_ready: true,
  reasons: [],
  live_blockers: [],
};
const UNPAID = { code: 'live_option_unpaid', message: 'the live option of VeriFactu is not in your plan: add it in your ERPlora account' };
const DIAGNOSTIC: DiagnosticOut = {
  ran_at: '2026-10-14T10:00:00Z',
  environment: 'testing',
  route: 'erplora',
  issuer_ready: true,
  producer_ready: false,
  route_ready: true,
  gateway_configured: false,
  gateway_ready: null,
  gateway_detail: '',
  can_send: false,
  reasons: [{ code: 'gateway_unavailable', message: "ERPlora's sending gateway is not configured on this server" }],
};

async function setup(config: Partial<ConfigOut> = {}, options: MountOptions = {}) {
  const m = await mountVerifactu(SettingsPage, { path: '/verifactu/settings', ...options });
  await m.live();
  await m.result('verifactu.config.get', { ...CONFIG, ...config });
  await m.result('verifactu.diagnostic.last', { result: null });
  return m;
}

describe('SettingsPage', () => {
  it('says who files and in which environment', async () => {
    const s = await setup();
    expect(s.find('verifactu-settings-route-hint').text()).toContain('ERPlora files your billing records');
    expect(s.find('verifactu-settings-environment').text()).toContain('Testing (AEAT test)');
    expect(s.find('verifactu-settings-go-live').exists()).toBe(true);
  });

  it('the switch chooses the route and says so', async () => {
    const s = await setup();
    s.answer(200, { ...CONFIG, route: 'own' });
    await ionValue(s.find('verifactu-settings-own').element, true);
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/verifactu/config', query: {}, body: { route: 'own' } }]);
    expect(toastSuccess).toHaveBeenCalledWith('Done: from now on you send with your own certificate.');
  });

  it('with the own route it says the certificate is the one uploaded in Configuration', async () => {
    const s = await setup({ route: 'own' });
    expect(s.find('verifactu-settings-route-hint').text()).toContain('uploaded in Configuration → My certificate');
  });

  it('a refused switch says why', async () => {
    const s = await setup();
    s.answer(409, { error: { code: 'verifactu.no_own_certificate', message: 'There is no certificate loaded.' } });
    await ionValue(s.find('verifactu-settings-own').element, true);
    expect(s.find('verifactu-settings-error').text()).toBe('There is no certificate loaded.');
  });

  it('a refused switch goes back to where it was', async () => {
    const s = await setup();
    s.answer(409, { error: { code: 'verifactu.no_own_certificate', message: 'There is no certificate loaded.' } });
    const toggle = s.find('verifactu-settings-own').element as unknown as HTMLElement & { checked: boolean };
    // What the person's tap does: the toggle turns itself on and says so.
    toggle.checked = true;
    toggle.dispatchEvent(new CustomEvent('ionChange', { detail: { checked: true }, bubbles: true }));
    await flush();
    expect(s.find('verifactu-settings-error').text()).toBe('There is no certificate loaded.');
    expect(toggle.checked).toBe(false);
  });

  it('«Go live» asks first and goes live', async () => {
    const s = await setup();
    mocks.confirm.mockResolvedValue(true);
    s.answer(200, { ...CONFIG, environment: 'production' });
    await click(s.find('verifactu-settings-go-live').element);
    expect(mocks.confirm.mock.calls[0][0].title).toBe('Send your invoices to the AEAT for real?');
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/verifactu/config/go_live', query: {}, body: {} }]);
    expect(toastSuccess).toHaveBeenCalledWith('Your business is live: records now go to the real AEAT.');
  });

  it('while the server keeps going live closed, it says so', async () => {
    const s = await setup({ production_open: false });
    expect(s.find('verifactu-settings-closed').text()).toContain('Going live is not open on this server yet');
    expect((s.find('verifactu-settings-go-live').element as unknown as { disabled: boolean }).disabled).toBe(true);
  });

  it('in testing it says what keeps it from going live, and «Go live» stays off', async () => {
    const s = await setup({
      live_blockers: [
        { code: 'representation_not_approved', message: 'ERPlora still has to approve your signed authorisation to file in production' },
        UNPAID,
      ],
    });
    const blockers = s.find('verifactu-settings-live-blockers').text();
    expect(blockers).toContain('It cannot go live yet:');
    expect(blockers).toContain('ERPlora still has to approve your signed authorisation');
    expect(blockers).toContain('the live option of VeriFactu is not in your plan');
    expect((s.find('verifactu-settings-go-live').element as unknown as { disabled: boolean }).disabled).toBe(true);
    const ready = await setup();
    expect(ready.find('verifactu-settings-live-blockers').exists()).toBe(false);
  });

  it('in production it says why records wait, without going back to testing', async () => {
    const s = await setup({ environment: 'production', can_go_back: false, reasons: [UNPAID] });
    const waiting = s.find('verifactu-settings-waiting').text();
    expect(waiting).toContain('Records are waiting:');
    expect(waiting).toContain('the live option of VeriFactu is not in your plan');
    expect(s.find('verifactu-settings-environment').text()).toContain('Production');
    const sending = await setup({ environment: 'production', can_go_back: false });
    expect(sending.find('verifactu-settings-waiting').exists()).toBe(false);
  });

  it('in production it goes back to testing until the first production record, then never', async () => {
    const live = await setup({ environment: 'production', production_since: '2026-10-14T10:00:00Z' });
    expect(live.find('verifactu-settings-back').exists()).toBe(true);
    const sealed = await setup({ environment: 'production', can_go_back: false });
    expect(sealed.find('verifactu-settings-back').exists()).toBe(false);
    expect(sealed.find('verifactu-settings-one-way').text()).toContain('cannot go back to testing');
  });

  it('«Test the connection» says what is missing, presenting nothing', async () => {
    const s = await setup();
    s.answer(200, DIAGNOSTIC);
    await click(s.find('verifactu-settings-test').element);
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/verifactu/diagnostics/run', query: {}, body: {} }]);
    expect(s.find('verifactu-settings-result').text()).toContain('It cannot send yet:');
    expect(s.find('verifactu-settings-result').text()).toContain("ERPlora's sending gateway is not configured on this server");
  });

  it('«Create test invoice» creates it in testing and says where its record is', async () => {
    const s = await setup();
    s.answer(200, { invoice_id: 'i1', number: 'TICKET-2026-000009', record: { id: 'r1' } });
    await click(s.find('verifactu-settings-test-invoice').element);
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/verifactu/test_invoice', query: {}, body: {} }]);
    expect(toastSuccess).toHaveBeenCalledWith('Test invoice TICKET-2026-000009 created: its record is in Records.');
    const live = await setup({ environment: 'production' });
    expect(live.find('verifactu-settings-test-invoice').exists()).toBe(false);
  });

  it('the responsible declaration and the identifying data of this system', async () => {
    const s = await setup();
    const read = s.find('verifactu-settings-declaration');
    expect([read.attributes('href'), read.attributes('target')]).toEqual([CONFIG.declaration_url, '_blank']);
    const identity = s.find('verifactu-settings-identity').text();
    for (const text of ['ERPLORA CLOUD SL', 'B27593136', 'ERPlora Hub', 'EC', 'dev', 'v1']) expect(identity).toContain(text);
    expect(s.find('verifactu-settings-pending-indicator').exists()).toBe(true);
  });

  it('the employee only reads', async () => {
    const s = await setup({}, { session: EMPLOYEE });
    for (const hook of ['own', 'go-live', 'test', 'test-invoice']) expect(s.find(`verifactu-settings-${hook}`).exists(), hook).toBe(false);
  });
});
