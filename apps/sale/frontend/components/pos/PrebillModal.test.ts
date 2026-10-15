// «Bill», the pre-bill (SALE-F21): the check as the paper taken to the table — business, title, date,
// customer, lines with their notes and comps, the discount, the VAT breakdown and the total the server
// works out —, «Bill — this is not an invoice…», and the print and close buttons. No number, no QR.
import { formatDateTime } from '@erplora/ui/components';
import { toastError } from '@erplora/ui/shell';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { h, ref } from 'vue';

import { click, errorFrame, mountSale, settle } from '../../__tests__/mount-sale';
import { printPaper } from '../../lib/print';
import { plain } from '../../lib/format';
import { line, order, preview } from './__tests__/fixtures';
import PrebillModal from './PrebillModal.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});
vi.mock('../../lib/print', () => ({ printPaper: vi.fn() }));
vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/shell')>()),
  toastError: vi.fn(() => Promise.resolve()),
}));

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(new Date(2026, 9, 14, 21, 30));
});
afterEach(() => {
  vi.useRealTimers();
  vi.mocked(printPaper).mockReset();
  vi.mocked(toastError).mockClear();
});

const CHECK = order({
  label: 'Table 4',
  discount_percent: '10.00',
  lines: [
    line({ id: 'l1', name: 'Steak', quantity: '2.000', unit_price: 1500, line_total: 3000, notes: 'Rare' }),
    line({ id: 'l2', name: 'Wine', is_gift: true, line_total: 0 }),
  ],
});
const VALUED = preview({
  subtotal: 2455,
  tax_total: 245,
  discount_amount: 300,
  ticket_discount_amount: 300,
  total: 2700,
  breakdown: [{ tax_type: 'vat', regime: '01', qualification: 'subject', exempt_reason: '', rate_pct: '10.00', label: 'vat', base: 2455, tax: 245 }],
});

async function setup(props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  const open = ref(true);
  const m = await mountSale(
    {
      setup: () => () =>
        h(PrebillModal, { open: open.value, 'onUpdate:open': (v: boolean) => (open.value = v), order: CHECK, customerName: null, header: '', ...props }),
    },
    { locale },
  );
  await settle();
  await m.live();
  return { ...m, open };
}

describe('PrebillModal', () => {
  it('values the whole check on the server', async () => {
    const m = await setup();
    expect(m.params('sale.checkout.preview')).toEqual([{ order_id: 'o1' }]);
    expect(m.find('pos-prebill-loading').exists()).toBe(true);
  });

  it('paints the paper: business, «Bill», title, date, lines with notes and comps, discount, VAT and total', async () => {
    const m = await setup({ header: 'Casa Pepe\nCalle Mayor 1', customerName: 'Lucía' }, 'es');
    await m.result('sale.checkout.preview', VALUED);
    const paper = m.find('pos-prebill-paper');
    expect(m.find('pos-prebill-title').text()).toBe('Cuenta');
    expect(paper.find('.pos-bill__business').text()).toBe('Casa Pepe');
    expect(paper.find('.pos-bill__label').text()).toBe('Table 4');
    expect(paper.find('.pos-bill__date').text()).toBe(formatDateTime(new Date(), 'es'));
    expect(paper.find('.pos-bill__customer').text()).toBe('Cliente: Lucía');
    const rows = paper.findAll('.pos-bill__line').map((row) => row.findAll(':scope > span').map((part) => plain(part.text())).join(' '));
    expect(rows).toEqual(['Steak 2 × 15,00 € 30,00 € Rare', 'Wine (invitación) 1 × 1,50 € 0,00 €']);
    expect(plain(paper.find('.pos-bill__discount').text())).toContain('−3,00 €');
    const tax = paper.find('.pos-bill__tax');
    expect([tax.find('dt'), ...tax.findAll('dd span')].map((part) => plain(part.text()))).toEqual(['IVA 10 %', '24,55 €', '2,45 €']);
    expect(plain(paper.find('.pos-bill__total').text())).toContain('27,00 €');
    expect(paper.find('.pos-bill__notice').text()).toBe('Cuenta — no es una factura. El tiquet fiscal se entrega al cobrar.');
  });

  it('names each tax by its kind in the reader’s language; a named component keeps its own name', async () => {
    const m = await setup();
    await m.result(
      'sale.checkout.preview',
      preview({
        breakdown: [
          { tax_type: 'vat', regime: '01', qualification: 'subject', exempt_reason: '', rate_pct: '21.00', label: 'vat', base: 100, tax: 21 },
          { tax_type: 'surcharge', regime: '01', qualification: 'subject', exempt_reason: '', rate_pct: '5.20', label: 'surcharge', base: 100, tax: 5 },
          { tax_type: 'vat', regime: '01', qualification: 'subject', exempt_reason: '', rate_pct: '1.00', label: 'Tasa turística', base: 100, tax: 1 },
        ],
      }),
    );
    expect(m.find('pos-prebill-paper').findAll('.pos-bill__tax dt').map((dt) => plain(dt.text()))).toEqual([
      'VAT 21%',
      'Surcharge 5.2%',
      'Tasa turística 1%',
    ]);
  });

  it('a row per fiscal key: an exempt one names its cause, as the ticket will', async () => {
    const m = await setup();
    await m.result(
      'sale.checkout.preview',
      preview({
        breakdown: [
          { tax_type: 'vat', regime: '01', qualification: 'subject', exempt_reason: '', rate_pct: '10.00', label: 'vat', base: 273, tax: 27 },
          { tax_type: 'vat', regime: '01', qualification: 'exempt', exempt_reason: 'E1', rate_pct: '0.00', label: 'vat', base: 4000, tax: 0 },
        ],
      }),
    );
    expect(m.find('pos-prebill-paper').findAll('.pos-bill__tax dt').map((dt) => plain(dt.text()))).toEqual([
      'VAT 10%',
      'Exempt (E1)',
    ]);
  });

  it('without a receipt header the business is «My business»', async () => {
    const m = await setup();
    await m.result('sale.checkout.preview', VALUED);
    expect(m.find('pos-prebill-paper').find('.pos-bill__business').text()).toBe('My business');
  });

  it('prints the paper; a failure says the bill could not be printed', async () => {
    const m = await setup();
    await m.result('sale.checkout.preview', VALUED);
    expect(m.find('pos-prebill-print').attributes('aria-label')).toBe('Print');
    await click(m.find('pos-prebill-print').element);
    expect(printPaper).toHaveBeenCalledExactlyOnceWith(m.find('pos-prebill-paper').element);
    vi.mocked(printPaper).mockImplementationOnce(() => {
      throw new Error('blocked');
    });
    await click(m.find('pos-prebill-print').element);
    expect(toastError).toHaveBeenCalledExactlyOnceWith('Bill could not be printed');
  });

  it('cannot be valued: says so with «Retry»; the close button closes it', async () => {
    const m = await setup();
    m.net.lastStream().push(errorFrame(m.subId('sale.checkout.preview'), 'sale.order_changed'));
    await m.reopen();
    expect(m.find('pos-prebill-error').text()).toContain('The bill could not be worked out.');
    await click(m.find('pos-prebill-close').element);
    expect(m.open.value).toBe(false);
  });
});
