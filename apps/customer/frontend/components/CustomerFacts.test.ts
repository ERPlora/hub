// The card's data (CUSTOMER-F03): Email, Phone, Tax ID, Company, Address, Stage, Source, Preferred
// channel, Purchases, Spent, Last purchase and Active, as the product showed them; and also the
// birthday, anniversary, internal notes and custom fields, which the product only showed when editing.
// «Spent» in the business's currency (customer-business-currency).
import { formatDateTime } from '@erplora/ui/components';
import { describe, expect, it } from 'vitest';

import { DETAIL } from '../__tests__/fixtures';
import { business, JAPANESE, mountCustomer, POLISH } from '../__tests__/mount-customer';
import { formatMoney } from '../lib/money';
import type { CustomerDetailOut } from '../operations';
import CustomerFacts from './CustomerFacts.vue';

async function setup(detail: CustomerDetailOut = DETAIL, locale: 'en' | 'es' = 'en') {
  const m = await mountCustomer(CustomerFacts, { props: { customer: detail }, locale });
  const facts = () =>
    m.wrapper.findAll('[data-testid="customer-facts"] .customer-facts__item').map((item) => [item.find('dt').text(), item.find('dd').text()]);
  return { ...m, facts };
}

describe('CustomerFacts: «Spent» in the business\'s currency (customer-business-currency)', () => {
  const spent = (s: Awaited<ReturnType<typeof setup>>) =>
    Object.fromEntries(s.facts())[s.wrapper.vm.$t('customer.detail.facts.spent')].replace(/\s/g, ' ');

  it('in Poland in złoty, in Japan in yen without decimals, never in euros', async () => {
    const pl = await setup(DETAIL, 'es');
    await pl.result(await pl.live(), 'base.business.get', business(POLISH));
    expect(spent(pl)).toBe('45,50 zł');

    const jp = await setup();
    await jp.result(await jp.live(), 'base.business.get', business(JAPANESE));
    expect(spent(jp)).toBe('¥4,550');
  });

  it('a figure without a symbol until the business answers', async () => {
    const s = await setup();
    await s.live();
    expect(spent(s)).toBe('45.50');
  });
});

describe('CustomerFacts', () => {
  it('shows the card\'s data in the product order, and what was hidden before', async () => {
    const s = await setup();
    expect(s.facts()).toEqual([
      ['Email', 'ana@x.es'],
      ['Phone', '+34 600 111 222'],
      ['Tax ID', '12345678Z'],
      ['Company', 'ACME'],
      ['Address', 'Calle Mayor 1, 28001, Madrid, Spain'],
      ['Stage', 'VIP'],
      ['Source', 'Walk-in'],
      ['Preferred channel', 'Email'],
      ['Purchases', '3'],
      ['Spent', formatMoney(4550, 'en')],
      ['Last purchase', formatDateTime('2026-10-01T10:00:00Z', 'en')],
      ['Active', 'Yes'],
      ['Birthday', 'Feb 3, 1990'],
      ['Anniversary', '—'],
      ['Internal notes', 'Likes tea'],
    ]);
  });

  it('lists the custom fields with their values; a yes/no reads Yes or No; an empty one «—»', async () => {
    const s = await setup();
    expect(
      s.wrapper.findAll('[data-testid="customer-facts-custom"] .customer-facts__item').map((i) => [i.find('dt').text(), i.find('dd').text()]),
    ).toEqual([
      ['Allergies', 'Nuts'],
      ['Newsletter', 'Yes'],
      ['Dye', '—'],
    ]);
  });

  it('an empty value is «—»', async () => {
    const s = await setup({ ...DETAIL, email: '', address: '', city: '', postal_code: '', country: '', last_purchase_at: null, notes: '', custom_fields: [] });
    expect(Object.fromEntries(s.facts())).toMatchObject({ Email: '—', Address: '—', 'Last purchase': '—', 'Internal notes': '—' });
    expect(s.wrapper.find('[data-testid="customer-facts-custom"]').exists()).toBe(false);
  });

  it('speaks Spanish', async () => {
    const s = await setup(DETAIL, 'es');
    expect(s.facts().slice(0, 6)).toEqual([
      ['Email', 'ana@x.es'],
      ['Teléfono', '+34 600 111 222'],
      ['NIF/CIF', '12345678Z'],
      ['Empresa', 'ACME'],
      ['Dirección', 'Calle Mayor 1, 28001, Madrid, España'],
      ['Etapa', 'VIP'],
    ]);
  });
});
