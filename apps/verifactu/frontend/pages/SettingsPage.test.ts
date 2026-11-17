// VeriFactu → Settings (VERIFACTU-F04, F08–F12; the old `erp-verifactu-settings`): «Sending» (the «Use my own
// certificate» switch and the AEAT environment with «Go live» / «Back to testing», each asking first), «Live test»
// («Test the connection», presenting nothing, and «Create test invoice» in testing) and «Responsible declaration»
// (the signed declaration and the identifying data of this system).
import { toastSuccess } from '@erplora/ui/shell';
import { IonButton } from '@ionic/vue';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { outOfTheApp } from '../../../../base/frontend/__tests__/app-download';
import { expectTapOpensInTheSystemBrowser, insideTheInstalledApp } from '../__tests__/system-browser';
import { CONFIG as STARTING_CONFIG, CONFIG_WITHOUT_ERPLORA_ROUTE, LOADED_CERTIFICATE } from '../__tests__/config-fixture';
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

const CONFIG: ConfigOut = { ...STARTING_CONFIG, production_open: true };
const NOT_APPROVED = { code: 'representation_not_approved', message: 'ERPlora still has to approve your signed authorisation to file for you' };
const NOT_ACTIVE = { code: 'hub_not_active', message: 'your ERPlora account has a pending payment or is suspended' };
const GATEWAY = { code: 'gateway_unavailable', message: "ERPlora's sending gateway is not configured on this server" };
const DIAGNOSTIC: DiagnosticOut = {
  ran_at: '2026-10-14T10:00:00Z',
  environment: 'testing',
  route: 'erplora',
  issuer_ready: true,
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

afterEach(outOfTheApp);

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

  it('while the server keeps going live closed, it says so once, among what keeps it from going live', async () => {
    const closed = { code: 'production_closed', message: 'ERPlora has not opened real filing with the AEAT on this server yet' };
    const s = await setup({ production_open: false, live_blockers: [closed] });
    const blockers = s.find('verifactu-settings-live-blockers').text();
    expect(blockers).toContain('ERPlora has not opened real filing with the AEAT on this server yet');
    expect(s.find('verifactu-settings-closed').exists()).toBe(false);
    expect((s.find('verifactu-settings-go-live').element as unknown as { disabled: boolean }).disabled).toBe(true);
  });

  it('in testing it says what keeps it from going live, and «Go live» stays off', async () => {
    const s = await setup({
      live_blockers: [NOT_APPROVED, NOT_ACTIVE],
    });
    const blockers = s.find('verifactu-settings-live-blockers').text();
    expect(blockers).toContain('It cannot go live yet:');
    expect(blockers).toContain('ERPlora still has to approve your signed authorisation');
    expect(blockers).toContain('your ERPlora account has a pending payment or is suspended');
    expect((s.find('verifactu-settings-go-live').element as unknown as { disabled: boolean }).disabled).toBe(true);
    const ready = await setup();
    expect(ready.find('verifactu-settings-live-blockers').exists()).toBe(false);
  });

  it('in production it says when new sales are refused and why records wait, without going back to testing', async () => {
    const s = await setup({ environment: 'production', can_go_back: false, route_ready: false, issue_blocker: NOT_APPROVED, reasons: [GATEWAY] });
    const refused = s.find('verifactu-settings-issue-blocked').text();
    expect(refused).toContain('New sales and invoices are refused until this is fixed:');
    expect(refused).toContain('ERPlora still has to approve your signed authorisation');
    const waiting = s.find('verifactu-settings-waiting').text();
    expect(waiting).toContain('Records are waiting:');
    expect(waiting).toContain("ERPlora's sending gateway is not configured on this server");
    expect(s.find('verifactu-settings-environment').text()).toContain('Production');
    const sending = await setup({ environment: 'production', can_go_back: false });
    expect(sending.find('verifactu-settings-waiting').exists()).toBe(false);
    expect(sending.find('verifactu-settings-issue-blocked').exists()).toBe(false);
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
    expect(s.find('verifactu-settings-result').text()).not.toContain("Producer's details");
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
    // IndicadorMultiplesOT is always «S» (ERPlora serves many taxpayers): nothing is pending from the account.
    expect(identity).toMatch(/Serves several taxpayers\s*IndicadorMultiplesOT\s*S/);
    expect(s.find('verifactu-settings-pending-indicator').exists()).toBe(false);
  });

  it('in the installed app, «Read the signed declaration» opens it in the system browser', async () => {
    const invoke = insideTheInstalledApp();
    const s = await setup();
    expectTapOpensInTheSystemBrowser(s.find('verifactu-settings-declaration').element, invoke, CONFIG.declaration_url);
  });

  // VeriFactu is only for Spain; outside it nothing that would lead to the AEAT is offered, with that one reason in
  // sight.
  const OUTSIDE_SPAIN = { code: 'outside_spain', message: 'this business is not in Spain: VeriFactu is only for businesses in Spain, so nothing is sent to the AEAT' };
  const disabled = (s: Awaited<ReturnType<typeof setup>>, hook: string) =>
    (s.find(`verifactu-settings-${hook}`).element as unknown as { disabled: boolean }).disabled;

  it('outside Spain it says VeriFactu is only for Spain and offers nothing that leads to the AEAT', async () => {
    const s = await setup({ live_blockers: [OUTSIDE_SPAIN], reasons: [OUTSIDE_SPAIN] });
    expect(s.find('verifactu-settings-outside-spain').text()).toBe('VeriFactu is only for businesses in Spain.');
    for (const hook of ['own', 'go-live', 'test', 'test-invoice']) expect(disabled(s, hook), hook).toBe(true);
    // That one reason: not repeated in the list of what keeps it from going live.
    expect(s.find('verifactu-settings-live-blockers').exists()).toBe(false);
  });

  it('outside Spain, in production, the waiting records give no other reason than that one', async () => {
    const s = await setup({ environment: 'production', reasons: [OUTSIDE_SPAIN], live_blockers: [OUTSIDE_SPAIN] });
    expect(s.find('verifactu-settings-outside-spain').exists()).toBe(true);
    expect(s.find('verifactu-settings-waiting').exists()).toBe(false);
  });

  it('outside Spain it says so in Spanish', async () => {
    const s = await setup({ live_blockers: [OUTSIDE_SPAIN] }, { locale: 'es' });
    expect(s.find('verifactu-settings-outside-spain').text()).toBe('VeriFactu solo es para negocios de España.');
  });

  it('in Spain the switch and the live test are offered, with no word of it', async () => {
    const s = await setup();
    expect(s.find('verifactu-settings-outside-spain').exists()).toBe(false);
    for (const hook of ['own', 'test', 'test-invoice']) expect(disabled(s, hook), hook).toBe(false);
  });

  it('the employee only reads', async () => {
    const s = await setup({}, { session: EMPLOYEE });
    for (const hook of ['own', 'go-live', 'test', 'test-invoice']) expect(s.find(`verifactu-settings-${hook}`).exists(), hook).toBe(false);
  });

  it('without the ERPlora route it shows only the certificate and the environment', async () => {
    const s = await setup({ ...CONFIG_WITHOUT_ERPLORA_ROUTE, production_open: true });
    expect(s.find('verifactu-settings-own').exists()).toBe(false);
    expect(s.find('verifactu-settings-certificate').text()).toContain('No certificate uploaded');
    expect(s.find('verifactu-settings-certificate').text()).toContain('Upload your certificate');
    expect(s.find('verifactu-settings-environment').text()).toContain('Testing (AEAT test)');
    expect(s.find('verifactu-settings-sending-card').text()).not.toContain('ERPlora');
  });

  it('explains the certificate needed to go live without a technical error or an alarm about testing', async () => {
    const required = { code: 'own_certificate_required', message: 'ERPlora does not file on behalf of businesses for now: use your own certificate' };
    const s = await setup({ ...CONFIG_WITHOUT_ERPLORA_ROUTE, production_open: true, live_blockers: [NOT_APPROVED, required] });
    const notice = s.find('verifactu-settings-certificate-required');
    expect(notice.text()).toContain('You can keep testing. To go live, upload your business certificate.');
    expect(notice.text()).toContain('Upload your certificate');
    expect(notice.text()).not.toContain('ERPlora');
    expect(s.find('verifactu-settings-live-blockers').exists()).toBe(false);
    expect(disabled(s, 'go-live')).toBe(true);
  });

  it('enables going live with a valid certificate when nothing else blocks it', async () => {
    const required = { code: 'own_certificate_required', message: 'technical server wording' };
    const starting = {
      ...CONFIG_WITHOUT_ERPLORA_ROUTE,
      route: 'erplora' as const,
      production_open: true,
      own_certificate: LOADED_CERTIFICATE,
      live_blockers: [required],
    };
    const s = await setup(starting);
    expect(s.find('verifactu-settings-certificate').text()).toContain('Valid');
    expect(s.find('verifactu-settings-certificate-required').exists()).toBe(false);
    expect(disabled(s, 'go-live')).toBe(false);
    const testButton = s.wrapper.findAllComponents(IonButton).find((button) => button.attributes('data-testid') === 'verifactu-settings-test');
    expect(testButton?.props('fill')).toBe('outline');

    mocks.confirm.mockResolvedValue(true);
    s.answerBy({
      '/api/verifactu/config': [200, { ...starting, route: 'own', live_blockers: [] }],
      '/api/verifactu/config/go_live': [200, { ...starting, route: 'own', environment: 'production', live_blockers: [] }],
    });
    await click(s.find('verifactu-settings-go-live').element);
    expect(s.sent()).toEqual([
      { method: 'POST', path: '/api/verifactu/config', query: {}, body: { route: 'own' } },
      { method: 'POST', path: '/api/verifactu/config/go_live', query: {}, body: {} },
    ]);
  });

  it('omits the diagnostic route when the closed ERPlora route still carries testing records', async () => {
    const s = await setup(CONFIG_WITHOUT_ERPLORA_ROUTE);
    await s.result('verifactu.diagnostic.last', { result: { ...DIAGNOSTIC, reasons: [NOT_APPROVED] } });
    const result = s.find('verifactu-settings-result').text();
    expect(result).not.toContain('Filed through');
    expect(result).not.toContain('My certificate');
    expect(result).not.toContain('ERPlora files for you');
    expect(result).not.toMatch(/authorisation|representation/i);
  });

  it('shows the own certificate in the diagnostic when it really carries the records', async () => {
    const s = await setup(CONFIG_WITHOUT_ERPLORA_ROUTE);
    await s.result('verifactu.diagnostic.last', { result: { ...DIAGNOSTIC, route: 'own' } });
    const result = s.find('verifactu-settings-result').text();
    expect(result).toContain('Filed through');
    expect(result).toContain('My certificate');
  });

  it('keeps both diagnostic route labels when ERPlora is available', async () => {
    for (const [route, label] of [['erplora', 'ERPlora files for you'], ['own', 'My certificate']] as const) {
      const s = await setup();
      await s.result('verifactu.diagnostic.last', { result: { ...DIAGNOSTIC, route } });
      const result = s.find('verifactu-settings-result').text();
      expect(result).toContain('Filed through');
      expect(result).toContain(label);
    }
  });

  it('speaks Spanish when only the own certificate can go live', async () => {
    const required = { code: 'own_certificate_required', message: 'technical server wording' };
    const s = await setup({ ...CONFIG_WITHOUT_ERPLORA_ROUTE, production_open: true, live_blockers: [required] }, { locale: 'es' });
    expect(s.find('verifactu-settings-certificate').text()).toContain('Sin certificado');
    expect(s.find('verifactu-settings-certificate-required').text()).toContain('Puedes seguir probando. Para pasar a producción, sube el certificado de tu negocio.');
    expect(s.find('verifactu-settings-sending-card').text()).not.toContain('ERPlora');
  });

  it('does not bring the authorisation back in production notices', async () => {
    const s = await setup({
      ...CONFIG_WITHOUT_ERPLORA_ROUTE,
      environment: 'production',
      issue_blocker: NOT_APPROVED,
      reasons: [NOT_APPROVED],
    });
    expect(s.find('verifactu-settings-issue-blocked').exists()).toBe(false);
    expect(s.find('verifactu-settings-waiting').exists()).toBe(false);
    expect(s.find('verifactu-settings-sending-card').text()).not.toMatch(/authorisation|representation/i);
  });
});
