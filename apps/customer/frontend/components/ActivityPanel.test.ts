// «Add note» and «Activity» on the card (CUSTOMER-F05, F03): the note goes in with «Add» («Note
// added») and appears at the top of the activity by itself (the live query re-runs); the activity is
// newest first, 50 at a time, each entry with its title in the page language, its text, when and who. An amount
// is in the currency its entry carries, with the decimals the server counts; one without, in the business's
// (customer-business-currency).
import { formatDateTime } from '@erplora/ui/components';
import { toastSuccess } from '@erplora/ui/shell';
import { IonTextarea } from '@ionic/vue';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { pageOf } from '../__tests__/fixtures';
import {
  business,
  errorFrame,
  flush,
  json,
  type MountOptions,
  mountCustomer,
  POLISH,
  refusal,
  sent,
  subId,
} from '../__tests__/mount-customer';
import { formatMoney, type Money } from '../lib/money';
import type { ActivityRow } from '../operations';
import ActivityPanel from './ActivityPanel.vue';

vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...((await importOriginal()) as object),
  toastSuccess: vi.fn(() => Promise.resolve()),
}));
beforeEach(() => vi.mocked(toastSuccess).mockClear());

const entry = (id: string, kind: string, extra: Partial<ActivityRow> = {}): ActivityRow => ({
  id,
  customer_id: 'c1',
  kind,
  title: '',
  text: '',
  data: {},
  currency_decimals: null,
  related_id: '',
  related_type: '',
  actor: 'Ana',
  created_at: '2026-10-02T10:00:00Z',
  ...extra,
});
const ACTIVITY = 'customer.activity.list';
const EUR: Money = { currency: 'EUR', decimals: 2 };

async function setup(props: Record<string, unknown> = {}, options: MountOptions = {}) {
  const m = await mountCustomer(ActivityPanel, { props: { customerId: 'c1', canAddNote: true, ...props }, ...options });
  const call = await m.live();
  const note = () => m.wrapper.findComponent(IonTextarea);
  const items = () => m.wrapper.findAll('[data-testid="customer-activity-item"]');
  return { ...m, call, note, items };
}

describe('ActivityPanel: the currency of each amount (customer-business-currency)', () => {
  const texts = (s: Awaited<ReturnType<typeof setup>>) =>
    s.wrapper.findAll('.customer-activity__text').map((t) => t.text().replace(/\s/g, ' '));

  it('in Poland a purchase is in złoty; one recorded in euros keeps its euros; one without a currency, the business\'s', async () => {
    const s = await setup({}, { locale: 'es' });
    await s.result(s.call, 'base.business.get', business(POLISH));
    await s.result(
      s.call,
      ACTIVITY,
      pageOf([
        entry('a1', 'purchase_recorded', { data: { amount: 2550, currency: 'PLN' }, currency_decimals: 2 }),
        entry('a2', 'purchase_recorded', { data: { amount: 1000, currency: 'EUR' }, currency_decimals: 2 }),
        entry('a3', 'purchase_voided', { data: { amount: 1250 } }),
      ]),
    );
    expect(texts(s)).toEqual(['25,50 zł', '10,00 €', '12,50 zł']);
  });
});

describe('ActivityPanel: the activity', () => {
  it('follows the card\'s activity, 50 newest first', async () => {
    const s = await setup();
    expect(s.params(ACTIVITY)).toEqual([{ customer_id: 'c1', limit: 50, offset: 0 }]);
  });

  it('paints each entry with its title in the page language, its text, when and who', async () => {
    const s = await setup();
    await s.result(
      s.call,
      ACTIVITY,
      pageOf([
        entry('a1', 'note_added', { text: 'Prefers mornings' }),
        entry('a2', 'purchase_recorded', { data: { amount: 2550, currency: 'EUR' }, currency_decimals: 2 }),
        entry('a6', 'purchase_refunded', { text: 'One cup back', data: { amount: 1210, currency: 'EUR' } }),
        entry('a3', 'consent_granted', { text: 'I want offers' }),
        entry('a4', 'appointment.visit', { title: 'Visit: haircut', actor: 'Luis' }),
        entry('a5', 'note_added', { title: 'From the flow', text: 'Auto', data: { author_name: 'Bot' } }),
      ]),
    );
    const read = (i: number) => s.items()[i];
    expect(read(0).get('.customer-activity__title').text()).toBe('Note added');
    expect(read(0).get('.customer-activity__text').text()).toBe('Prefers mornings');
    expect(read(0).get('.customer-activity__when').text()).toBe(`${formatDateTime('2026-10-02T10:00:00Z', 'en')} · by Ana`);
    expect(read(1).get('.customer-activity__title').text()).toBe('Purchase recorded');
    expect(read(1).get('.customer-activity__text').text()).toBe(formatMoney(2550, 'en', EUR));
    expect(read(2).get('.customer-activity__title').text()).toBe('Purchase refunded');
    expect(read(2).get('.customer-activity__text').text()).toBe('One cup back');
    expect(read(3).get('.customer-activity__title').text()).toBe('Consent given');
    expect(read(4).get('.customer-activity__title').text()).toBe('Visit: haircut');
    expect(read(5).get('.customer-activity__title').text()).toBe('From the flow');
    expect(read(5).get('.customer-activity__when').text()).toContain('by Bot');
  });

  it('«Show more» grows by 50 while there are more, never asking for more than 100 at once', async () => {
    const s = await setup();
    await s.result(s.call, ACTIVITY, { ...pageOf([entry('a1', 'note_added')]), total: 220 });
    await s.wrapper.get('[data-testid="customer-activity-more"]').trigger('click');
    await flush();
    expect(s.params(ACTIVITY)).toEqual([{ customer_id: 'c1', limit: 100, offset: 0 }]);
    await s.wrapper.get('[data-testid="customer-activity-more"]').trigger('click');
    await flush();
    const windows = s.params(ACTIVITY) as { limit: number; offset: number }[];
    expect(windows.map((w) => [w.offset, w.limit]).sort((a, b) => a[0] - b[0])).toEqual([
      [0, 100],
      [100, 50],
    ]);
    for (const w of windows) expect(w.limit).toBeLessThanOrEqual(100);
  });

  it('with nothing recorded says «No activity recorded.»; a failed load says so', async () => {
    const s = await setup();
    await s.result(s.call, ACTIVITY, pageOf([]));
    expect(s.wrapper.get('[data-testid="customer-activity-empty"]').text()).toBe('No activity recorded.');
    s.call.push(errorFrame(subId(s.client, ACTIVITY), 'boom'));
    await flush();
    expect(s.wrapper.get('[data-testid="customer-activity-error"]').text()).toContain('The activity could not be loaded');
  });
});

describe('ActivityPanel: adding a note (F05)', () => {
  it('«Add» waits for some text, sends the note and says «Note added»; the field empties', async () => {
    const s = await setup();
    await s.result(s.call, ACTIVITY, pageOf([]));
    const add = () => s.wrapper.get('[data-testid="customer-note-add"]').element as HTMLElement & { disabled?: boolean };
    expect(s.wrapper.get('h3').text()).toBe('Add note');
    expect(add().disabled).toBe(true);
    await s.note().setValue('  Prefers mornings ');
    expect(add().disabled).toBe(false);
    s.net.onApi(() => json(entry('n1', 'note_added'), 201));
    await s.wrapper.get('[data-testid="customer-note-form"]').trigger('submit');
    await flush();
    expect(sent(s.net.api[0])).toMatchObject({ path: '/api/customer/notes', body: { customer_id: 'c1', content: 'Prefers mornings' } });
    expect(toastSuccess).toHaveBeenCalledWith('Note added');
    expect(s.note().props('modelValue')).toBe('');
  });

  it('a refusal of the note stays under it, with the text', async () => {
    const s = await setup();
    s.net.onApi(() => refusal(422, 'invalid_payload', 'Too long', { content: 'Too long' }));
    await s.note().setValue('x');
    await s.wrapper.get('[data-testid="customer-note-form"]').trigger('submit');
    await flush();
    expect(s.note().props('errorText')).toBe('Too long');
    expect(s.note().props('modelValue')).toBe('x');
  });

  it('who cannot manage cards sees the activity without the note form', async () => {
    const s = await setup({ canAddNote: false });
    expect(s.wrapper.find('[data-testid="customer-note-form"]').exists()).toBe(false);
  });

  it('speaks Spanish', async () => {
    const s = await setup({}, { locale: 'es' });
    await s.result(s.call, ACTIVITY, pageOf([entry('a1', 'merged')]));
    expect(s.wrapper.get('h3').text()).toBe('Añadir nota');
    expect(s.items()[0].get('.customer-activity__title').text()).toBe('Ficha duplicada fusionada en esta');
  });
});
