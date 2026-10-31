// The payment methods of the charge sheet (SALE-F02, F03, F37): only those the till settings let charge
// today (`allowed`, decided by the server), cash first; each with its icon; cash unavailable from the
// legal cash limit the preview gives (Spain: 1,000 €), and the sheet starting on the first method that
// can charge this total.
import { describe, expect, it } from 'vitest';

import type { PaymentMethodOut } from '../../operations';
import { cashOverLimit, chargeableMethods, defaultMethod, isCash, methodIcon } from './methods';

const method = (id: string, type: PaymentMethodOut['type'], over: Partial<PaymentMethodOut> = {}): PaymentMethodOut => ({
  id,
  name: id,
  display_name: id,
  type,
  sort_order: 0,
  requires_change: type === 'cash',
  allowed: true,
  ...over,
});

const CARD = method('card', 'card');
const CASH = method('cash', 'cash');
const BIZUM = method('bizum', 'other', { name: 'Bizum', display_name: 'Bizum' });
const TRANSFER = method('transfer', 'transfer', { allowed: false });

describe('payment methods of the sheet', () => {
  it('keeps the ones the settings allow, cash first and the rest in the server’s order', () => {
    expect(chargeableMethods([CARD, BIZUM, CASH, TRANSFER]).map((m) => m.id)).toEqual(['cash', 'card', 'bizum']);
    expect(chargeableMethods([])).toEqual([]);
  });

  it('paints each with its icon, by type and, for the others, by name', () => {
    expect(methodIcon(CASH)).toBe('ion:cash-outline');
    expect(methodIcon(CARD)).toBe('ion:card-outline');
    expect(methodIcon(TRANSFER)).toBe('ion:swap-horizontal-outline');
    expect(methodIcon(BIZUM)).toBe('ion:phone-portrait-outline');
    expect(methodIcon(method('vale', 'other', { name: 'Vale restaurante' }))).toBe('ion:ticket-outline');
  });

  it('a gift method is painted apart from a voucher, as the current product does (a «vale regalo» is a voucher)', () => {
    expect(methodIcon(method('regalo', 'other', { name: 'Regalo' }))).toBe('ion:gift-outline');
    expect(methodIcon(method('gift', 'other', { name: 'Gift' }))).toBe('ion:gift-outline');
    expect(methodIcon(method('cheque', 'other', { name: 'Cheque comida' }))).toBe('ion:ticket-outline');
    expect(methodIcon(method('vale-regalo', 'other', { name: 'Vale regalo' }))).toBe('ion:ticket-outline');
    expect(methodIcon(method('x', 'other', { name: 'Crypto' }))).toBe('ion:wallet-outline');
  });

  it('cash is not allowed from the limit on (the limit itself included); no limit, no ban', () => {
    expect(isCash(CASH)).toBe(true);
    expect(isCash(CARD)).toBe(false);
    expect(cashOverLimit(100000, 99999)).toBe(false);
    expect(cashOverLimit(100000, 100000)).toBe(true);
    expect(cashOverLimit(null, 5000000)).toBe(false);
    expect(cashOverLimit(100000, undefined)).toBe(false);
  });

  it('starts on the first method that can charge: cash, or the next one over the cash limit', () => {
    expect(defaultMethod([CASH, CARD], false)?.id).toBe('cash');
    expect(defaultMethod([CASH, CARD], true)?.id).toBe('card');
    expect(defaultMethod([CASH], true)?.id).toBe('cash');
    expect(defaultMethod([], false)).toBeUndefined();
  });
});
