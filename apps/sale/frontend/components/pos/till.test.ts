// The till's small rules, kept pure: the tile's initials and colour, the time a check is parked under,
// the quick-note chips that add or take out a segment of the note, the line a second tap on a product
// raises (SALE-F01 step 2) and the words a refused write shows.
import { ApiError } from '@erplora/ui/sdk';
import { describe, expect, it } from 'vitest';

import type { OrderLineOut } from '../../operations';
import { customerSnapshot, initials, mergeableLine, noteHasChip, plusOne, refusal, shortTime, tileGradient, toggleNoteChip } from './till';

const line = (over: Partial<OrderLineOut> = {}): OrderLineOut => ({
  id: 'l1',
  position: 1,
  product_id: 'p1',
  department_id: null,
  name: 'Coffee',
  sku: 'CAF',
  is_service: false,
  unit: 'ud',
  quantity: '1.000',
  unit_price: 150,
  price_quantity: '1.000',
  pricing_unit: 'ud',
  tax_category_key: 'food',
  discount_percent: '0.00',
  discount_approved: false,
  is_gift: false,
  gift_reason: '',
  notes: '',
  staff_id: null,
  line_total: 150,
  round_no: 0,
  fired_at: null,
  ...over,
});

describe('tile', () => {
  it('initials: the first letters of the first two words, upper case', () => {
    expect(initials('café con leche')).toBe('CC');
    expect(initials('  Tostada ')).toBe('T');
    expect(initials('')).toBe('');
  });

  it('the same name always gets the same gradient, two names usually two', () => {
    expect(tileGradient('Coffee')).toBe(tileGradient('Coffee'));
    expect(tileGradient('Coffee')).toMatch(/^linear-gradient\(135deg, hsl\(\d+ 42% 38%\), hsl\(\d+ 44% 26%\)\)$/);
    expect(tileGradient('Coffee')).not.toBe(tileGradient('Tea'));
  });
});

describe('shortTime', () => {
  it('is the hour and minutes in the reader’s language', () => {
    const at = new Date(2026, 9, 14, 9, 5);
    expect(shortTime(at, 'es')).toBe('9:05');
    expect(shortTime(at, 'en').replace(/\s/g, ' ')).toBe('9:05 AM');
    expect(shortTime('2026-10-14T21:30:00', 'es')).toBe('21:30');
  });
});

describe('quick-note chips', () => {
  it('a chip is on when the note holds it as one of its comma-separated parts', () => {
    expect(noteHasChip('No ice, well done', 'well done')).toBe(true);
    expect(noteHasChip('No ice, well done', 'done')).toBe(false);
    expect(noteHasChip('', 'No ice')).toBe(false);
  });

  it('toggling adds the chip after a comma, or takes that part out, never twice', () => {
    expect(toggleNoteChip('', 'No ice')).toBe('No ice');
    expect(toggleNoteChip('Allergy', 'No ice')).toBe('Allergy, No ice');
    expect(toggleNoteChip('Allergy, No ice', 'No ice')).toBe('Allergy');
    expect(toggleNoteChip('No ice, Allergy', 'No ice')).toBe('Allergy');
  });
});

describe('mergeableLine', () => {
  it('a second tap raises the pending line of the same product, same professional, no note, no discount, no comp', () => {
    const lines = [line({ id: 'l1' })];
    expect(mergeableLine(lines, 'p1', null)?.id).toBe('l1');
  });

  it('never a line with a note, a discount, a comp, another professional or already sent to the kitchen', () => {
    for (const over of [
      { notes: 'no ice' },
      { discount_percent: '10.00' },
      { is_gift: true },
      { staff_id: 's2' },
      { fired_at: '2026-10-14T10:00:00Z', round_no: 1 },
      { product_id: 'p2' },
    ]) {
      expect(mergeableLine([line(over)], 'p1', null), JSON.stringify(over)).toBeUndefined();
    }
    expect(mergeableLine([line({ staff_id: 's2' })], 'p1', 's2')?.id).toBe('l1');
  });
});

describe('plusOne', () => {
  it('adds one unit to a decimal quantity without float noise', () => {
    expect(plusOne('1.000')).toBe('2');
    expect(plusOne('0.532')).toBe('1.532');
    expect(plusOne('2.100')).toBe('3.1');
  });
});

describe('refusal', () => {
  it('the server’s own sentence when it refused (it comes translated)', () => {
    const refused = new ApiError(409, 'sale.quantity_off_grid', 'La cantidad no encaja con el escalón del producto');
    expect(refusal(refused, 'fallback')).toBe('La cantidad no encaja con el escalón del producto');
  });

  it('the fallback when nobody answered (network, a proxy page)', () => {
    expect(refusal(new ApiError(0, 'client_error', 'Failed to fetch'), 'fallback')).toBe('fallback');
    expect(refusal(new ApiError(502, 'unexpected_response', 'Unexpected response (HTTP 502)'), 'fallback')).toBe('fallback');
    expect(refusal(new Error('boom'), 'fallback')).toBe('fallback');
  });
});

describe('customerSnapshot', () => {
  it('copies the card’s tax details as the sale wants them, as the Customers search does', () => {
    const card = { id: 'c1', name: 'Lucía Pérez', tax_id: '12345678Z', address: 'Calle Mayor 1', postal_code: '28001', city: 'Madrid', country: 'ES' };
    expect(customerSnapshot(card, 'es')).toEqual({
      customer_id: 'c1',
      customer_name: 'Lucía Pérez',
      customer_tax_id: '12345678Z',
      customer_address: 'Calle Mayor 1, 28001 Madrid, España',
      customer_country: 'ES',
    });
    expect(customerSnapshot({ ...card, address: '', postal_code: '', city: '', country: '' }, 'es').customer_address).toBe('');
  });
});
