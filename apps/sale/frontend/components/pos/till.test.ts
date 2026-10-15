// The till's small rules, kept pure: the tile's initials and colour, the time a check is parked under,
// the quick-note chips that add or take out a segment of the note, the line a second tap on a product
// raises (SALE-F01 step 2), and the one door to the Customers app.
import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

import { countryOptions, snapshotOf } from '../../../../customer/frontend/components/CustomerSearch.vue';
import type { OrderLineOut } from '../../operations';
import { initials, mergeableLine, mergeableServiceLine, noteHasChip, plusOne, shortTime, tileGradient, toggleNoteChip } from './till';

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
  service_id: null,
  paid_by_voucher: false,
  voucher_session_id: null,
  voucher_grant_id: null,
  voucher_name: '',
  voucher_remaining: null,
  voucher_hold_until: null,
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

describe('the Customers app, reached only through its search component', () => {
  it('copies the card’s tax details as the sale wants them (CustomerSearch’s own `snapshotOf`)', () => {
    const card = { id: 'c1', name: 'Lucía Pérez', tax_id: '12345678Z', address: 'Calle Mayor 1', postal_code: '28001', city: 'Madrid', country: 'ES' };
    expect(snapshotOf(card, 'es')).toEqual({
      customer_id: 'c1',
      customer_name: 'Lucía Pérez',
      display_name: 'Lucía Pérez',
      customer_tax_id: '12345678Z',
      customer_address: 'Calle Mayor 1, 28001 Madrid, España',
      customer_country: 'ES',
    });
    // A company's card: the fiscal name is the company's, the person stays for the screen.
    expect(snapshotOf({ ...card, company_name: 'Estudio Ana SL' }, 'es')).toMatchObject({
      customer_name: 'Estudio Ana SL',
      display_name: 'Lucía Pérez',
    });
    expect(snapshotOf({ ...card, address: '', postal_code: '', city: '', country: '' }, 'es').customer_address).toBe('');
  });

  it('lists the countries in the reader’s language (for the invoice’s recipient)', () => {
    expect(countryOptions('es').find((option) => option.value === 'ES')?.label).toBe('España');
  });

  it('no source of the sale app imports anything of Customers but CustomerSearch.vue', () => {
    const FRONTEND = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
    const sources = (dir: string): string[] =>
      readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
        const path = join(dir, entry.name);
        if (entry.isDirectory()) return entry.name === '__tests__' ? [] : sources(path);
        return /\.(vue|ts)$/.test(entry.name) && !/\.(test|d)\.ts$/.test(entry.name) ? [path] : [];
      });
    const reached = sources(FRONTEND).flatMap((file) =>
      [...readFileSync(file, 'utf8').matchAll(/from '([^']*customer\/frontend\/[^']*)'/g)]
        .map((m) => m[1])
        .filter((path) => !path.endsWith('/components/CustomerSearch.vue'))
        .map((path) => `${file.slice(FRONTEND.length)}: ${path}`),
    );
    expect(reached).toEqual([]);
  });
});

describe('mergeableServiceLine (SALE-F38)', () => {
  const service = (over: Partial<OrderLineOut> = {}) => line({ product_id: null, service_id: 's1', is_service: true, ...over });

  it('a second tap on a service raises its pending line, as a product', () => {
    expect(mergeableServiceLine([service({ id: 'l7' })], 's1', null)?.id).toBe('l7');
  });

  it('never a line a voucher pays, nor one of another service, professional, with a note, comp or discount', () => {
    for (const over of [
      { paid_by_voucher: true, voucher_session_id: 'r1' },
      { service_id: 's2' },
      { staff_id: 'st2' },
      { notes: 'short' },
      { is_gift: true },
      { discount_percent: '5.00' },
      { fired_at: '2026-10-14T10:00:00Z' },
    ]) {
      expect(mergeableServiceLine([service(over)], 's1', null), JSON.stringify(over)).toBeUndefined();
    }
  });
});
