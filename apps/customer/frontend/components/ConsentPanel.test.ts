// «Marketing consent» on the card (CUSTOMER-F14, F15): a line for Email, WhatsApp and SMS (and for
// any other channel with something recorded) with its state — «Never asked», «Given», «Withdrawn» —,
// its date and address. «Record consent» shows the exact sentence to read out and «They said yes»
// stores THAT sentence; «Withdraw» is one tap, no dialog. Below, everything that was decided.
import { formatDateTime } from '@erplora/ui/components';
import { toastSuccess } from '@erplora/ui/shell';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { pageOf } from '../__tests__/fixtures';
import { errorFrame, flush, json, type MountOptions, mountCustomer, refusal, sent, subId } from '../__tests__/mount-customer';
import type { ConsentRow, ConsentStateRow } from '../operations';
import ConsentPanel from './ConsentPanel.vue';

vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...((await importOriginal()) as object),
  toastSuccess: vi.fn(() => Promise.resolve()),
}));
beforeEach(() => vi.mocked(toastSuccess).mockClear());

const STATE: ConsentStateRow[] = [
  {
    purpose: 'marketing',
    channel: 'email',
    state: 'granted',
    contact_point: 'ana@x.es',
    source: 'counter',
    notice_version: 'counter-v1',
    occurred_at: '2026-10-01T10:00:00Z',
    recorded_by: 'Ana',
    evidence: '',
  },
  { ...({} as ConsentStateRow), purpose: 'marketing', channel: 'postal', state: 'withdrawn', contact_point: '', source: 'phone', notice_version: '', occurred_at: '2026-09-01T10:00:00Z', recorded_by: 'Luis', evidence: '' },
];
const FACT: ConsentRow = {
  id: 'k1',
  customer_id: 'c1',
  purpose: 'marketing',
  channel: 'email',
  state: 'granted',
  contact_point: 'ana@x.es',
  source: 'counter',
  notice_text: 'I want to receive offers…',
  notice_version: 'counter-v1',
  evidence: '',
  reason: '',
  recorded_by: 'Ana',
  occurred_at: '2026-10-01T10:00:00Z',
  created_at: '2026-10-01T10:00:00Z',
};
const NOTICE = 'I want to receive offers and news from this business through this channel. I can unsubscribe whenever I want.';

async function setup(props: Record<string, unknown> = {}, options: MountOptions = {}) {
  const m = await mountCustomer(ConsentPanel, { props: { customerId: 'c1', consent: STATE, editable: true, ...props }, ...options });
  const call = await m.live();
  const line = (channel: string) => m.wrapper.find(`[data-testid="customer-consent-${channel}"]`);
  const click = async (id: string) => {
    await m.wrapper.get(`[data-testid="${id}"]`).trigger('click');
    await flush();
  };
  return { ...m, call, line, click };
}

describe('ConsentPanel: the state per channel', () => {
  it('a line for Email, WhatsApp and SMS always, and for any other channel with something recorded', async () => {
    const s = await setup();
    expect(s.wrapper.get('h3').text()).toBe('Marketing consent');
    expect(s.wrapper.findAll('[data-consent]').map((l) => l.attributes('data-consent'))).toEqual(['email', 'whatsapp', 'sms', 'postal']);
    expect(s.line('email').get('.customer-consent__state').text()).toBe('Given');
    expect(s.line('email').get('.customer-consent__when').text()).toBe(`${formatDateTime('2026-10-01T10:00:00Z', 'en')} · ana@x.es`);
    expect(s.line('whatsapp').get('.customer-consent__state').text()).toBe('Never asked');
    expect(s.line('postal').get('.customer-consent__state').text()).toBe('Withdrawn');
    expect(s.line('postal').get('strong').text()).toBe('Post');
  });

  it('a given channel offers «Withdraw»; the others «Record consent»', async () => {
    const s = await setup();
    expect(s.line('email').find('[data-testid="customer-consent-email-withdraw"]').text()).toBe('Withdraw');
    expect(s.line('whatsapp').find('[data-testid="customer-consent-whatsapp-grant"]').text()).toBe('Record consent');
    expect(s.line('postal').find('[data-testid="customer-consent-postal-grant"]').exists()).toBe(true);
  });

  it('who cannot manage cards sees the state, with no buttons', async () => {
    const s = await setup({ editable: false });
    expect(s.wrapper.findAll('ion-button')).toHaveLength(0);
  });
});

describe('ConsentPanel: recording and withdrawing', () => {
  it('«Record consent» shows the exact sentence and how to ask; «They said yes» stores that sentence', async () => {
    const s = await setup();
    await s.click('customer-consent-whatsapp-grant');
    const ask = s.wrapper.get('[data-testid="customer-consent-whatsapp-ask"]');
    expect(ask.text()).toContain(NOTICE);
    expect(ask.text()).toContain('Read it out loud and only press if they say yes.');
    s.net.onApi(() => json(FACT, 201));
    await s.click('customer-consent-whatsapp-confirm');
    expect(sent(s.net.api[0])).toMatchObject({
      path: '/api/customer/consents/grant',
      body: { customer_id: 'c1', channel: 'whatsapp', notice_text: NOTICE, notice_version: 'counter-v1', source: 'counter' },
    });
    expect(toastSuccess).toHaveBeenCalledWith('Consent recorded.');
    expect(s.wrapper.find('[data-testid="customer-consent-whatsapp-ask"]').exists()).toBe(false);
  });

  it('Cancel leaves it without recording anything', async () => {
    const s = await setup();
    await s.click('customer-consent-sms-grant');
    await s.click('customer-consent-sms-cancel');
    expect(s.wrapper.find('[data-testid="customer-consent-sms-ask"]').exists()).toBe(false);
    expect(s.net.api).toHaveLength(0);
  });

  it('«Withdraw» is one tap: no dialog, no reason asked', async () => {
    const s = await setup();
    s.net.onApi(() => json({ ...FACT, state: 'withdrawn' }, 201));
    await s.click('customer-consent-email-withdraw');
    expect(sent(s.net.api[0])).toMatchObject({ path: '/api/customer/consents/withdraw', body: { customer_id: 'c1', channel: 'email', source: 'counter' } });
    expect(toastSuccess).toHaveBeenCalledWith('Consent withdrawn. It is in force from now on.');
  });

  it('a refusal is told in the panel', async () => {
    const s = await setup();
    s.net.onApi(() => refusal(404, 'customer.customer_unavailable', 'This customer is no longer available.'));
    await s.click('customer-consent-email-withdraw');
    expect(s.wrapper.get('[data-testid="customer-consent-error"]').text()).toContain('This customer is no longer available.');
  });
});

describe('ConsentPanel: everything that was decided', () => {
  it('follows the history of the card, newest first, with the words, the source, when and who', async () => {
    const s = await setup();
    expect(s.params('customer.consent.history')).toEqual([{ customer_id: 'c1', limit: 50 }]);
    await s.result(s.call, 'customer.consent.history', pageOf([FACT]));
    const fact = s.wrapper.get('[data-testid="customer-consent-fact-k1"]');
    expect(fact.text()).toContain('Given — Email (at the counter)');
    expect(fact.text()).toContain('I want to receive offers…');
    expect(fact.text()).toContain(`${formatDateTime('2026-10-01T10:00:00Z', 'en')} · Ana`);
  });

  it('a health permission (CUSTOMER-F32) has no channel: the history names its purpose', async () => {
    const s = await setup();
    await s.result(s.call, 'customer.consent.history', pageOf([{ ...FACT, id: 'k2', purpose: 'health', channel: '' }]));
    expect(s.wrapper.get('[data-testid="customer-consent-fact-k2"]').text()).toContain('Given — Health data (at the counter)');
    // It is no marketing channel: no line for it above.
    expect(s.wrapper.findAll('[data-consent]').map((l) => l.attributes('data-consent'))).toEqual(['email', 'whatsapp', 'sms', 'postal']);
  });

  it('with nothing recorded says so; a failed load says so', async () => {
    const s = await setup({ consent: [] });
    await s.result(s.call, 'customer.consent.history', pageOf([]));
    expect(s.wrapper.get('[data-testid="customer-consent-history-empty"]').text()).toBe('Nothing has been recorded yet.');
    s.call.push(errorFrame(subId(s.client, 'customer.consent.history'), 'boom'));
    await flush();
    expect(s.wrapper.get('[data-testid="customer-consent-history-error"]').text()).toContain('The consent could not be loaded');
  });

  it('speaks Spanish, and stores the sentence the person read, in Spanish', async () => {
    const s = await setup({}, { locale: 'es' });
    expect(s.wrapper.get('h3').text()).toBe('Consentimiento de marketing');
    expect(s.line('whatsapp').get('.customer-consent__state').text()).toBe('Nunca se le ha preguntado');
    await s.click('customer-consent-whatsapp-grant');
    s.net.onApi(() => json(FACT, 201));
    await s.click('customer-consent-whatsapp-confirm');
    expect((sent(s.net.api[0]).body as { notice_text: string }).notice_text).toBe(
      'Quiero recibir ofertas y novedades de este negocio por este canal. Puedo darme de baja cuando quiera.',
    );
  });
});
