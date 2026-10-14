// One card per way the sale was paid, in the Refund window (SALE-F31 step 2–4): the method, «Charged»,
// «Already refunded» (when something was) and «Refundable», the server's figures; «Refund amount» to
// edit what goes back on it (euros as typed); and, when the money cannot go back its own way, why, and
// «Give it back through» to choose another method (searched on the server).
import { describe, expect, it, vi } from 'vitest';

import { ionValue, mountSale } from '../../__tests__/mount-sale';
import { plain } from '../../lib/format';
import type { TenderOption } from '../../operations';
import PaymentMethodPicker from './PaymentMethodPicker.vue';
import RefundTenderCard from './RefundTenderCard.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const prop = (el: Element, name: string): unknown => (el as unknown as Record<string, unknown>)[name];

const tender = (over: Partial<TenderOption> = {}): TenderOption => ({
  payment_id: 'p1',
  position: 1,
  method_id: 'm1',
  method_name: 'Cash',
  method_type: 'cash',
  charged: 1000,
  refunded: 0,
  remaining: 1000,
  refundable: true,
  reason: '',
  ...over,
});

async function setup(props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  const m = await mountSale(RefundTenderCard, { props: { tender: tender(), amount: '10.00', destination: '', ...props }, locale });
  const figures = () => m.wrapper.findAll('[data-testid="refund-tender-figure"]').map((f) => plain(f.text()));
  return { ...m, figures };
}

describe('RefundTenderCard', () => {
  it('names the method and says what it charged and what is refundable', async () => {
    const s = await setup();
    expect(s.find('refund-tender-name-p1').text()).toBe('Cash');
    expect(s.figures()).toEqual(['Charged: €10.00', 'Refundable: €10.00']);
  });

  it('says what was already refunded, when something was', async () => {
    const s = await setup({ tender: tender({ refunded: 300, remaining: 700 }) });
    expect(s.figures()).toEqual(['Charged: €10.00', 'Already refunded: €3.00', 'Refundable: €7.00']);
  });

  it('edits what goes back on it, as typed', async () => {
    const s = await setup();
    const amount = s.find('refund-amount-p1');
    expect([prop(amount.element, 'label'), prop(amount.element, 'value'), prop(amount.element, 'inputmode'), prop(amount.element, 'fill'), amount.attributes('mode') ?? prop(amount.element, 'mode')]).toEqual([
      'Refund amount',
      '10.00',
      'decimal',
      'outline',
      'md',
    ]);
    await ionValue(amount.element, '4,5', 'ionInput');
    expect(s.wrapper.emitted('update:amount')).toEqual([['4,5']]);
  });

  it('marks the amount with the window’s message when it cannot go', async () => {
    const s = await setup({ error: 'Cash: €12.00 is more than the €10.00 still refundable.' });
    const amount = s.find('refund-amount-p1');
    expect(prop(amount.element, 'errorText')).toBe('Cash: €12.00 is more than the €10.00 still refundable.');
    expect(amount.classes()).toContain('ion-invalid');
  });

  it('a tender that cannot go back its own way says why and asks where it goes', async () => {
    const s = await setup({ tender: tender({ method_name: 'Gift card', refundable: false, reason: 'method_unavailable' }), destination: 'm2' });
    expect(s.find('refund-tender-reason-p1').text()).toBe('That payment method is no longer available.');
    const picker = s.wrapper.findComponent(PaymentMethodPicker);
    expect(picker.props()).toMatchObject({ valueKey: 'id', label: 'Give it back through', modelValue: 'm2', testid: 'refund-destination-p1' });
    picker.vm.$emit('update:modelValue', 'm3');
    await s.wrapper.vm.$nextTick();
    expect(s.wrapper.emitted('update:destination')).toEqual([['m3']]);
  });

  it('a reason it does not know reads «Cannot go back the way it was paid.»', async () => {
    const s = await setup({ tender: tender({ refundable: false, reason: 'something_new' as TenderOption['reason'] }) });
    expect(s.find('refund-tender-reason-p1').text()).toBe('Cannot go back the way it was paid.');
  });

  it('a tender with nothing left shows its figures only', async () => {
    const s = await setup({ tender: tender({ refunded: 1000, remaining: 0, refundable: false, reason: 'already_refunded' }), amount: '' });
    expect(s.find('refund-amount-p1').exists()).toBe(false);
    expect(s.find('refund-tender-reason-p1').text()).toBe('Already given back in full.');
    expect(s.wrapper.findComponent(PaymentMethodPicker).exists()).toBe(false);
  });

  it('speaks Spanish', async () => {
    const s = await setup({ tender: tender({ refunded: 300, remaining: 700, refundable: false, reason: 'already_refunded' }) }, 'es');
    expect(s.figures()).toEqual(['Cobrado: 10,00 €', 'Ya devuelto: 3,00 €', 'Devolvible: 7,00 €']);
    expect(prop(s.find('refund-amount-p1').element, 'label')).toBe('Importe a devolver');
    expect(s.find('refund-tender-reason-p1').text()).toBe('Ya se devolvió entero.');
    expect(s.wrapper.findComponent(PaymentMethodPicker).props('label')).toBe('Devolver por');
  });
});
