// The shift review of the close (CASH_REGISTER-F08): «Checking what is still pending…» while it reads; the
// open checks of Sales, the kitchen tickets not served yet and the prints that did not come out, each with
// what names them, when there are any (with «The shift will be closed anyway. Press again to confirm.» once
// the first press warned); «could not be checked» when a reading failed; nothing at all for a clean shift.
import { describe, expect, it } from 'vitest';

import { mountCash } from '../__tests__/mount-cash-register';
import ShiftReview from './ShiftReview.vue';

const base = {
  checking: false,
  incomplete: false,
  openChecks: 0,
  labels: [] as string[],
  unserved: 0,
  unservedLabels: [] as string[],
  prints: 0,
  printUsages: [] as string[],
  acknowledged: false,
};

async function setup(props: Partial<typeof base>, locale: 'en' | 'es' = 'en') {
  return mountCash(ShiftReview, { props: { ...base, ...props }, locale });
}

describe('ShiftReview', () => {
  it('says it is checking', async () => {
    const m = await setup({ checking: true });
    expect(m.find('cash-register-review-checking').text()).toBe('Checking what is still pending…');
  });

  it('a clean shift says nothing', async () => {
    const m = await setup({});
    expect(m.wrapper.text()).toBe('');
  });

  it('names the open checks, and the confirmation once warned', async () => {
    const m = await setup({ openChecks: 2, labels: ['Table 4', 'Bar'] });
    const review = m.find('cash-register-review');
    expect(review.text()).toContain('Shift review');
    expect(review.text()).toContain('Open checks: 2');
    expect(review.text()).toContain('Table 4 · Bar');
    expect(m.find('cash-register-review-confirm').exists()).toBe(false);
    await m.wrapper.setProps({ acknowledged: true });
    expect(m.find('cash-register-review-confirm').text()).toBe('The shift will be closed anyway. Press again to confirm.');
  });

  it('names the kitchen tickets not served yet (cash_register#68)', async () => {
    const m = await setup({ unserved: 3, unservedLabels: ['Table 4', '#12'] });
    const review = m.find('cash-register-review');
    expect(review.text()).toContain('Kitchen tickets not served: 3');
    expect(review.text()).toContain('Table 4 · #12');
    expect(review.text()).not.toContain('Open checks');
  });

  it('names the prints that did not come out, by function (cash_register#68)', async () => {
    const m = await setup({ prints: 2, printUsages: ['receipt', 'kitchen'] });
    const review = m.find('cash-register-review');
    expect(review.text()).toContain('Prints not out yet: 2');
    expect(review.text()).toContain('Receipts · Kitchen');
  });

  it('a failed reading is said, alone or with what was found', async () => {
    const m = await setup({ incomplete: true });
    expect(m.find('cash-register-review-unavailable').text()).toContain('could not be checked');
    await m.wrapper.setProps({ openChecks: 1, labels: [] });
    expect(m.find('cash-register-review').text()).toContain('could not be checked');
  });

  it('speaks Spanish', async () => {
    const m = await setup({ openChecks: 1, labels: ['Mesa 2'], unserved: 1, prints: 4, printUsages: ['bar', 'label'] }, 'es');
    const review = m.find('cash-register-review').text();
    expect(review).toContain('Cuentas abiertas: 1');
    expect(review).toContain('Comandas sin servir: 1');
    expect(review).toContain('Impresiones sin salir: 4');
    expect(review).toContain('Barra · Etiquetas');
  });
});
