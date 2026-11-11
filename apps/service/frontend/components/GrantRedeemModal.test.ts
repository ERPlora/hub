// SERVICE-F21 «Gastar una sesión fuera del cobro» (hub#1058): «Spend a session» of a voucher sold, outside the till. The
// Service (one of those the voucher covers; preselected when it covers one), the Professional who did it (the team's
// picker of the service forms, optional as in the operation), a Note and the balance «N left · M after this one». On
// opening and on each change of service it asks `service.grant.redeem_check` and says why a session cannot be spent;
// Spend sends `service.grant.redeem` with the voucher, the service, the professional and the note, and closes; a refusal
// stays in the dialog. Something chosen or typed asks before any way out throws it away (hub#1023).
import { Combo } from '@erplora/ui/components';
import { describe, expect, it, vi } from 'vitest';

import { unsavedChangesIn } from '../../../../base/frontend/lib/system-back';
import { click, flush, ionValue, mountService, settle } from '../__tests__/mount-service';
import { grant } from '../__tests__/grant';
import { pkg } from '../__tests__/package';
import type { GrantOut, PackageOut, RedeemCheckOut } from '../operations';
import GrantRedeemModal from './GrantRedeemModal.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

type Control = HTMLElement & { label?: string; disabled?: boolean; helperText?: string; value?: unknown };

const CHECK = '/api/service/grants/redeem_check';
const REDEEM = '/api/service/grants/redeem';
const TWO_SERVICES = pkg({
  item_count: 2,
  items: [
    { id: 'i1', service_id: 's1', service_name: 'Cut', service_price: 2000, sessions: 5, sort_order: 0 },
    { id: 'i2', service_id: 's2', service_name: 'Wash', service_price: 800, sessions: 5, sort_order: 1 },
  ],
});
const ok = (over: Partial<RedeemCheckOut> = {}): RedeemCheckOut => ({ id: 'g1', redeemable: true, reason: '', remaining: 3, ...over });

interface Setup {
  grant?: Partial<GrantOut>;
  pkg?: PackageOut;
  check?: [number, unknown];
  locale?: 'en' | 'es';
}

async function setup(options: Setup = {}) {
  const m = await mountService(GrantRedeemModal, {
    props: { open: false, grant: grant(options.grant), pkg: options.pkg ?? pkg() },
    locale: options.locale ?? 'en',
    answers: { [CHECK]: options.check ?? [200, ok()] },
  });
  await m.wrapper.setProps({ 'onUpdate:open': (open: boolean) => m.wrapper.setProps({ open }) });
  await m.wrapper.setProps({ open: true });
  await settle();
  await settle();
  const el = (id: string) => m.inDoc(id) as Control;
  const member = () => m.wrapper.findComponent(Combo);
  const checks = () => m.sent().filter((call) => call.path === CHECK);
  const spends = () => m.sent().filter((call) => call.path === REDEEM);
  return { ...m, el, member, checks, spends };
}

describe('GrantRedeemModal', () => {
  it('opens on the voucher of its customer, with the only service it covers chosen and the balance after this one', async () => {
    const s = await setup();
    expect(s.inDoc('service-grant-redeem')?.getAttribute('aria-label')).toBe('Spend a session');
    expect(s.el('service-grant-redeem-message')?.textContent).toContain('Lucía Pérez');
    expect(s.el('service-grant-redeem-message')?.textContent).toContain('Bono 5 cortes');
    expect([s.el('service-grant-redeem-service').label, s.el('service-grant-redeem-service').value]).toEqual(['Service', 's1']);
    expect(s.member().props('label')).toBe('Professional');
    expect(s.el('service-grant-redeem-note').label).toBe('Note');
    expect(s.el('service-grant-redeem-balance')?.textContent?.trim()).toBe('3 sessions left · 2 after this one');
    expect(s.checks()).toEqual([{ method: 'GET', path: CHECK, query: { id: 'g1', service_id: 's1' }, body: undefined }]);
    expect(s.el('service-grant-redeem-refused')).toBeNull();
    expect(s.el('service-grant-redeem-submit').disabled).toBe(false);
  });

  it('spends a session on the service and the professional chosen, with the note, and closes', async () => {
    const s = await setup();
    s.member().vm.$emit('update:modelValue', { id: 'm9', label: 'Ana López' });
    await settle();
    await ionValue(s.el('service-grant-redeem-note'), ' came for her cut ', 'ionInput');
    s.answerBy({ [CHECK]: [200, ok()], [REDEEM]: [200, { id: 'r1', grant_id: 'g1', service_id: 's1', service_name: 'Cut', member_id: 'm9', member_name: 'Ana López', redeemed_at: '2026-11-11T10:00:00Z', remaining: 2 }] });
    await click(s.el('service-grant-redeem-submit'));
    await settle();
    expect(s.spends()).toEqual([
      { method: 'POST', path: REDEEM, query: {}, body: { id: 'g1', service_id: 's1', member_id: 'm9', note: 'came for her cut' } },
    ]);
    expect(s.wrapper.emitted('update:open')?.at(-1)).toEqual([false]);
  });

  it('the professional is optional: without one the session counts for nobody', async () => {
    const s = await setup();
    s.answerBy({ [CHECK]: [200, ok()], [REDEEM]: [200, { id: 'r1', grant_id: 'g1', service_id: 's1', service_name: 'Cut', member_id: null, member_name: null, redeemed_at: '2026-11-11T10:00:00Z', remaining: 2 }] });
    await click(s.el('service-grant-redeem-submit'));
    await settle();
    expect(s.spends().map((call) => call.body)).toEqual([{ id: 'g1', service_id: 's1' }]);
  });

  it('a voucher of several services asks which one, and checks the one chosen', async () => {
    const s = await setup({ pkg: TWO_SERVICES });
    expect(s.el('service-grant-redeem-service').value).toBe('');
    expect(s.el('service-grant-redeem-submit').disabled).toBe(true);
    expect(s.checks().map((call) => call.query)).toEqual([{ id: 'g1' }]);
    await ionValue(s.el('service-grant-redeem-service'), 's2');
    await settle();
    expect(s.checks().map((call) => call.query)).toEqual([{ id: 'g1' }, { id: 'g1', service_id: 's2' }]);
    expect(s.el('service-grant-redeem-submit').disabled).toBe(false);
  });

  it.each([
    ['voided', 'This voucher was voided: it can no longer be used.'],
    ['expired', 'This voucher has expired.'],
    ['no_uses_left', 'This voucher has no sessions left.'],
    ['does_not_cover_service', 'This voucher does not cover that service.'],
  ] as const)('a check that says no (%s) is seen, and nothing can be spent', async (reason, text) => {
    const s = await setup({ check: [200, ok({ redeemable: false, reason })] });
    expect(s.el('service-grant-redeem-refused')?.textContent).toContain('This session cannot be spent');
    expect(s.el('service-grant-redeem-refused')?.textContent).toContain(text);
    expect(s.el('service-grant-redeem-submit').disabled).toBe(true);
  });

  it('the balance follows what the check finds left (another till may have spent one)', async () => {
    const s = await setup({ check: [200, ok({ remaining: 1 })] });
    expect(s.el('service-grant-redeem-balance')?.textContent?.trim()).toBe('1 session left · 0 after this one');
  });

  it('an unlimited voucher says it has no limit', async () => {
    const s = await setup({ grant: { max_uses: null, remaining: null }, check: [200, ok({ remaining: null })] });
    expect(s.el('service-grant-redeem-balance')?.textContent?.trim()).toBe('No session limit');
  });

  it('says it is checking until the check answers', async () => {
    const m = await mountService(GrantRedeemModal, { props: { open: false, grant: grant(), pkg: pkg() } });
    m.net.onApi(() => new Promise<Response>(() => {}));
    await m.wrapper.setProps({ open: true });
    await settle();
    expect(m.inDoc('service-grant-redeem-checking')?.textContent).toContain('Checking the voucher…');
    expect((m.inDoc('service-grant-redeem-submit') as Control).disabled).toBe(true);
  });

  it('a check that cannot be made says so with its reason; the server still has the last word', async () => {
    const s = await setup({ check: [503, { error: { code: 'base.hub_busy', message: 'The business is busy, try again.' } }] });
    expect(s.el('service-grant-redeem-check-error')?.textContent).toContain('The voucher could not be checked');
    expect(s.el('service-grant-redeem-check-error')?.textContent).toContain('The business is busy, try again.');
    expect(s.el('service-grant-redeem-submit').disabled).toBe(false);
  });

  it('a refusal of the spend stays in the dialog', async () => {
    const s = await setup();
    s.answerBy({ [CHECK]: [200, ok()], [REDEEM]: [409, { error: { code: 'service.grant_expired', message: 'This voucher has expired.' } }] });
    await click(s.el('service-grant-redeem-submit'));
    await settle();
    expect(s.inDoc('service-grant-redeem-error')?.textContent).toContain('This voucher has expired.');
    expect(s.wrapper.emitted('update:open')?.at(-1)).not.toEqual([false]);
  });

  it('speaks Spanish', async () => {
    const s = await setup({ locale: 'es', check: [200, ok({ remaining: 1 })] });
    expect(s.inDoc('service-grant-redeem')?.getAttribute('aria-label')).toBe('Gastar una sesión');
    expect([s.el('service-grant-redeem-service').label, s.member().props('label'), s.el('service-grant-redeem-note').label]).toEqual([
      'Servicio',
      'Profesional',
      'Nota',
    ]);
    expect(s.el('service-grant-redeem-balance')?.textContent?.trim()).toBe('Queda 1 sesión · 0 después de esta');
    const refused = await setup({ locale: 'es', check: [200, ok({ redeemable: false, reason: 'no_uses_left' })] });
    expect(refused.el('service-grant-redeem-refused')?.textContent).toContain('Este bono ya no tiene sesiones disponibles.');
    const plural = await setup({ locale: 'es' });
    expect(plural.el('service-grant-redeem-balance')?.textContent?.trim()).toBe('Quedan 3 sesiones · 2 después de esta');
  });
});

// hub#1023, BASE-F05: as it opened, every way out closes it at once; with a professional chosen or a note typed, they ask
// «Discard changes?» first, and so does Android's Back.
describe('GrantRedeemModal: unsaved changes ask before any way out (hub#1023, BASE-F05)', () => {
  const QUESTION = '[data-stub="ion-modal"][aria-label="Discard changes?"]';
  const asked = () => document.querySelector<HTMLElement>(QUESTION);

  it('Cancel as it opened closes at once', async () => {
    const s = await setup();
    s.el('service-grant-redeem-cancel')!.click();
    await flush();
    expect(asked()).toBeNull();
    expect(s.wrapper.emitted('update:open')?.at(-1)).toEqual([false]);
  });

  it('Cancel with a note typed asks, and «Keep editing» keeps the note', async () => {
    const s = await setup();
    await ionValue(s.el('service-grant-redeem-note'), 'came late', 'ionInput');
    s.el('service-grant-redeem-cancel')!.click();
    await flush();
    expect(asked()).not.toBeNull();
    asked()!.querySelector<HTMLElement>('.ep-form-modal__cancel')!.click();
    await flush();
    expect(s.wrapper.emitted('update:open')).toBeUndefined();
    expect(s.el('service-grant-redeem-note').value).toBe('came late');
  });

  it('a professional chosen holds Android Back; cleared, it lets go', async () => {
    const s = await setup();
    const overlay = s.inDoc('service-grant-redeem')!;
    expect(unsavedChangesIn(overlay)).toBeUndefined();
    s.member().vm.$emit('update:modelValue', { id: 'm9', label: 'Ana López' });
    await settle();
    expect(unsavedChangesIn(overlay)).toBeDefined();
    s.member().vm.$emit('update:modelValue', null);
    await settle();
    expect(unsavedChangesIn(overlay)).toBeUndefined();
  });
});
