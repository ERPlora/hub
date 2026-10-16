// «Health and allergies» on the card (CUSTOMER-F32): allergies and the sensitivity test, kept only
// with the person's explicit permission (GDPR art. 9). Without it the block asks for it with the exact
// words to read out; «They said yes» stores THOSE words. With it, the data shows (allergies as a
// warning) and «Edit» saves them; «Withdraw permission» asks first, because it erases the data.
import { formatDateTime } from '@erplora/ui/components';
import { toastSuccess } from '@erplora/ui/shell';
import { IonInput, IonTextarea } from '@ionic/vue';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { errorFrame, flush, json, type MountOptions, mountCustomer, refusal, sent, subId } from '../__tests__/mount-customer';
import { formatDay } from '../lib/dates';
import type { HealthOut } from '../operations';
import HealthPanel from './HealthPanel.vue';

vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...((await importOriginal()) as object),
  toastSuccess: vi.fn(() => Promise.resolve()),
}));
beforeEach(() => vi.mocked(toastSuccess).mockClear());
afterEach(() => {
  document.body.innerHTML = '';
});

const NEVER: HealthOut = {
  customer_id: 'c1',
  consent: 'none',
  consent_at: null,
  consent_by: '',
  notice_text: '',
  allergies: '',
  sensitivity_test_on: null,
  sensitivity_test_result: '',
  updated_at: null,
  updated_by: '',
};
const NOTICE =
  'I give my permission for this business to keep my allergies and my sensitivity tests to look after me safely. I can withdraw it whenever I want and they will then be erased.';
const GRANTED: HealthOut = { ...NEVER, consent: 'granted', consent_at: '2026-10-01T10:00:00Z', consent_by: 'Clara', notice_text: NOTICE };
const KEPT: HealthOut = {
  ...GRANTED,
  allergies: 'PPD (hair dye)',
  sensitivity_test_on: '2026-10-10',
  sensitivity_test_result: 'negative',
  updated_at: '2026-10-10T09:00:00Z',
  updated_by: 'Clara',
};

async function setup(block: HealthOut | null = NEVER, props: Record<string, unknown> = {}, options: MountOptions = {}) {
  const m = await mountCustomer(HealthPanel, { props: { customerId: 'c1', editable: true, ...props }, ...options });
  const call = await m.live();
  if (block) await m.result(call, 'customer.health.detail', block);
  const click = async (id: string) => {
    await m.wrapper.get(`[data-testid="${id}"]`).trigger('click');
    await flush();
  };
  const has = (id: string) => m.wrapper.find(`[data-testid="${id}"]`).exists();
  const submit = async () => {
    await m.wrapper.get('[data-testid="customer-health-form"]').trigger('submit');
    await flush();
  };
  return { ...m, call, click, has, submit };
}

describe('HealthPanel: reading the block', () => {
  it('follows customer.health.detail of the card and says «Loading…» until the first result', async () => {
    const s = await setup(null);
    expect(s.params('customer.health.detail')).toEqual([{ customer_id: 'c1' }]);
    expect(s.wrapper.get('h3').text()).toBe('Health and allergies');
    expect(s.wrapper.get('[data-testid="customer-health-loading"]').text()).toBe('Loading…');
  });

  it('a failed load says so in its place', async () => {
    const s = await setup(null);
    s.call.push(errorFrame(subId(s.client, 'customer.health.detail'), 'boom'));
    await flush();
    expect(s.wrapper.get('[data-testid="customer-health-error"]').text()).toContain('The health data could not be loaded');
  });

  it('without permission it holds nothing and explains what is needed', async () => {
    const s = await setup();
    expect(s.wrapper.get('[data-testid="customer-health-intro"]').text()).toBe(
      'To note allergies or sensitivity tests you need their explicit permission.',
    );
    expect(s.has('customer-health-data')).toBe(false);
    expect(s.wrapper.get('[data-testid="customer-health-ask"]').text()).toBe('Ask for permission');
  });

  it('a withdrawn permission says when, and asks again', async () => {
    const s = await setup({ ...NEVER, consent: 'withdrawn', consent_at: '2026-10-05T10:00:00Z' });
    expect(s.wrapper.get('[data-testid="customer-health-withdrawn"]').text()).toBe(
      `Permission withdrawn on ${formatDateTime('2026-10-05T10:00:00Z', 'en')}.`,
    );
    expect(s.has('customer-health-ask')).toBe(true);
  });

  it('with permission: when and who, the allergies as a warning and the test with its result', async () => {
    const s = await setup(KEPT);
    expect(s.wrapper.get('[data-testid="customer-health-consent"]').text()).toBe(
      `Permission given on ${formatDateTime('2026-10-01T10:00:00Z', 'en')} · Clara`,
    );
    const allergies = s.wrapper.get('[data-testid="customer-health-allergies"]');
    expect(allergies.classes()).toContain('customer-health__alert');
    expect(allergies.text()).toBe('Allergies: PPD (hair dye)');
    expect(s.wrapper.get('[data-testid="customer-health-test"]').text()).toBe(
      `Sensitivity test: ${formatDay('2026-10-10', 'en')} · Negative`,
    );
  });

  it('with permission and nothing noted, it says so', async () => {
    const s = await setup(GRANTED);
    expect(s.wrapper.get('[data-testid="customer-health-allergies"]').text()).toBe('No allergies noted.');
    expect(s.wrapper.get('[data-testid="customer-health-allergies"]').classes()).not.toContain('customer-health__alert');
    expect(s.wrapper.get('[data-testid="customer-health-test"]').text()).toBe('No sensitivity test.');
  });

  it('who cannot manage cards reads it, with no buttons', async () => {
    const s = await setup(KEPT, { editable: false });
    expect(s.wrapper.findAll('ion-button')).toHaveLength(0);
    const never = await setup(NEVER, { editable: false });
    expect(never.wrapper.findAll('ion-button')).toHaveLength(0);
  });
});

describe('HealthPanel: the permission', () => {
  it('«Ask for permission» shows the exact words; «They said yes» stores those words', async () => {
    const s = await setup();
    await s.click('customer-health-ask');
    const ask = s.wrapper.get('[data-testid="customer-health-asking"]');
    expect(ask.text()).toContain(NOTICE);
    expect(ask.text()).toContain('Read it out loud and only press if they say yes.');
    s.net.onApi(() => json(GRANTED));
    await s.click('customer-health-confirm');
    expect(sent(s.net.api[0])).toMatchObject({
      path: '/api/customer/health/grant',
      body: { customer_id: 'c1', notice_text: NOTICE, notice_version: 'health-v1', source: 'counter' },
    });
    expect(toastSuccess).toHaveBeenCalledWith('Permission recorded.');
    expect(s.has('customer-health-asking')).toBe(false);
  });

  it('Cancel records nothing', async () => {
    const s = await setup();
    await s.click('customer-health-ask');
    await s.click('customer-health-ask-cancel');
    expect(s.has('customer-health-asking')).toBe(false);
    expect(s.net.api).toHaveLength(0);
  });

  it('«Withdraw permission» asks first, because it erases the data; confirmed, it withdraws', async () => {
    const s = await setup(KEPT, {}, { attachTo: document.body });
    await s.click('customer-health-withdraw');
    expect(document.body.textContent).toContain('Their allergies and sensitivity test are erased.');
    expect(s.net.api).toHaveLength(0);
    s.net.onApi(() => json({ ...NEVER, consent: 'withdrawn', consent_at: '2026-10-11T10:00:00Z' }));
    (document.querySelector('[data-testid="customer-health-withdraw-dialog-submit"]') as HTMLElement).click();
    await flush();
    expect(sent(s.net.api[0])).toMatchObject({ path: '/api/customer/health/withdraw', body: { customer_id: 'c1', source: 'counter' } });
    expect(toastSuccess).toHaveBeenCalledWith('Permission withdrawn and health data erased.');
  });
});

describe('HealthPanel: editing the data', () => {
  it('«Edit» opens the form with what is kept; «Save» sends the three fields', async () => {
    const s = await setup(KEPT);
    await s.click('customer-health-edit');
    expect(s.wrapper.findComponent(IonTextarea).props('modelValue')).toBe('PPD (hair dye)');
    expect(s.wrapper.findComponent(IonInput).props('modelValue')).toBe('2026-10-10');
    s.net.onApi(() => json(KEPT));
    await s.submit();
    expect(sent(s.net.api[0])).toMatchObject({
      path: '/api/customer/health/update',
      body: { customer_id: 'c1', allergies: 'PPD (hair dye)', sensitivity_test_on: '2026-10-10', sensitivity_test_result: 'negative' },
    });
    expect(toastSuccess).toHaveBeenCalledWith('Health data saved.');
    expect(s.has('customer-health-form')).toBe(false);
  });

  it('an empty date travels as no date', async () => {
    const s = await setup(GRANTED);
    await s.click('customer-health-edit');
    s.net.onApi(() => json(GRANTED));
    await s.submit();
    expect((sent(s.net.api[0]).body as Record<string, unknown>).sensitivity_test_on).toBeNull();
  });

  it('a refusal keeps the form and what was typed, with the reason under its field', async () => {
    const s = await setup(GRANTED);
    await s.click('customer-health-edit');
    s.net.onApi(() =>
      refusal(422, 'customer.health_test_date_missing', 'Enter the date of the test.', { sensitivity_test_on: 'Enter the date of the test.' }),
    );
    await s.wrapper.findComponent(IonTextarea).setValue('Latex');
    await s.submit();
    expect(s.has('customer-health-form')).toBe(true);
    expect(s.wrapper.findComponent(IonInput).props('errorText')).toBe('Enter the date of the test.');
    expect(s.wrapper.findComponent(IonTextarea).props('modelValue')).toBe('Latex');
    expect(toastSuccess).not.toHaveBeenCalled();
  });

  it('a permission withdrawn elsewhere is told in the panel', async () => {
    const s = await setup(GRANTED);
    await s.click('customer-health-edit');
    s.net.onApi(() => refusal(409, 'customer.health_consent_required', 'Record their permission first to keep health data.'));
    await s.submit();
    expect(s.wrapper.get('[data-testid="customer-health-failure"]').text()).toContain('Record their permission first to keep health data.');
  });
});

describe('HealthPanel: in Spanish', () => {
  it('speaks Spanish and stores the Spanish words the person heard', async () => {
    const s = await setup(NEVER, {}, { locale: 'es' });
    expect(s.wrapper.get('h3').text()).toBe('Salud y alergias');
    expect(s.wrapper.get('[data-testid="customer-health-ask"]').text()).toBe('Pedir permiso');
    await s.click('customer-health-ask');
    s.net.onApi(() => json(GRANTED));
    await s.click('customer-health-confirm');
    expect((sent(s.net.api[0]).body as { notice_text: string }).notice_text).toBe(
      'Doy mi permiso para que este negocio guarde mis alergias y mis pruebas de sensibilidad para atenderme con seguridad. Puedo retirarlo cuando quiera y entonces se borrarán.',
    );
  });
});
