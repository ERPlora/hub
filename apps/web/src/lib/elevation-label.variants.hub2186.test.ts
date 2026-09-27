// The PIN dialog does not read «and €0.00» when only one of the figures applies (hub#2186).
//
// A ticket discount can carry a percentage AND a fixed amount at once, so Sales' sentence names
// both — and with one of them at zero the manager read «Aplicar al tique un descuento del 50 % y
// 0,00 €». A module can now give `approval_labels`: whole sentences, tried in order, where a
// figure at zero means «not there» — the first sentence whose figures are all present wins. Whole
// sentences rather than optional fragments because the wording changes with the figures («del
// 50 %» but «de 5,00 €») and translators must see complete sentences.
//
// `approval_labels` is a separate key on purpose: a shell from before hub#2186 ignores it and
// keeps rendering `approval_label` as before, so a module can ship both without breaking older hubs.
import { describe, expect, it, vi } from 'vitest';

vi.mock('../i18n', () => ({ getLocale: () => 'es' }));

import { describeElevation } from './elevation-label';

// CLDR puts a NO-BREAK SPACE (U+00A0) between the figure and «%» / «€» in Spanish.
const NBSP = '\u00a0';

const TICKET = 'sales.order.set_discount_over_limit';

function catalogueWith(entry: Record<string, unknown>) {
  return [{ moduleId: 'sales', moduleName: 'Ventas / TPV', commands: { [TICKET]: entry } }];
}

const ticketEntry = {
  label: 'Aplicar al tique un descuento por encima del límite',
  approval_label: 'Aplicar al tique un descuento del {discount_percent, percent} y {discount_amount, money}',
  approval_labels: [
    'Aplicar al tique un descuento del {discount_percent, percent} y {discount_amount, money}',
    'Aplicar al tique un descuento del {discount_percent, percent}',
    'Aplicar al tique un descuento de {discount_amount, money}',
  ],
};

function actionFor(payload: Record<string, unknown>, entry: Record<string, unknown> = ticketEntry): string {
  return describeElevation({ command: TICKET, payload }, catalogueWith(entry) as never).action;
}

describe('approval_labels: the first sentence whose figures are all present wins', () => {
  it('omits the amount when only the percentage applies', () => {
    expect(actionFor({ discount_percent: 50, discount_amount: 0 })).toBe(
      `Aplicar al tique un descuento del 50${NBSP}%`,
    );
  });

  it('omits the percentage when only the amount applies', () => {
    expect(actionFor({ discount_percent: 0, discount_amount: 500 })).toBe(
      `Aplicar al tique un descuento de 5,00${NBSP}€`,
    );
  });

  it('names both figures when both apply', () => {
    expect(actionFor({ discount_percent: 10, discount_amount: 30 })).toBe(
      `Aplicar al tique un descuento del 10${NBSP}% y 0,30${NBSP}€`,
    );
  });

  it('treats a bare number hole at zero as absent too', () => {
    const entry = {
      label: 'Ajustar el stock',
      approval_labels: ['Ajustar el stock en {delta} unidades'],
    };
    expect(actionFor({ delta: 0 }, entry)).toBe('Ajustar el stock');
    expect(actionFor({ delta: 3 }, entry)).toBe('Ajustar el stock en 3 unidades');
  });

  it('does not treat a text hole as a figure', () => {
    const entry = { label: 'Vender a precio libre', approval_labels: ['Vender «{description}» a precio libre'] };
    expect(actionFor({ description: '0' }, entry)).toBe('Vender «0» a precio libre');
  });

  it('falls back to approval_label, as written, when no sentence can be filled', () => {
    // Both figures at zero never reaches the PIN in practice; if it does, the plain template still
    // says what is being approved rather than dropping the figure silently.
    expect(actionFor({ discount_percent: 0, discount_amount: 0 })).toBe(
      `Aplicar al tique un descuento del 0${NBSP}% y 0,00${NBSP}€`,
    );
  });

  it('falls back to the plain label when neither template can be filled', () => {
    expect(actionFor({ discount_percent: 'lots' })).toBe('Aplicar al tique un descuento por encima del límite');
  });

  it('skips a sentence with a hole it cannot fill and tries the next one', () => {
    const entry = {
      label: 'Descuento alto',
      approval_labels: ['Descuento del {missing_field, percent}', 'Descuento de {discount_amount, money}'],
    };
    expect(actionFor({ discount_amount: 250 }, entry)).toBe(`Descuento de 2,50${NBSP}€`);
  });

  it('ignores a malformed approval_labels (not a list, or entries that are not text)', () => {
    const notAList = { ...ticketEntry, approval_labels: 'Aplicar al tique un descuento de {discount_amount, money}' };
    expect(actionFor({ discount_percent: 50, discount_amount: 0 }, notAList)).toBe(
      `Aplicar al tique un descuento del 50${NBSP}% y 0,00${NBSP}€`,
    );
    const oddEntries = {
      label: 'Descuento alto',
      approval_labels: [42, null, { text: 'x' }, 'Descuento del {discount_percent, percent}'],
    };
    expect(actionFor({ discount_percent: 50 }, oddEntries)).toBe(`Descuento del 50${NBSP}%`);
  });

  it('only reads the payload fields a sentence names (hub#363)', () => {
    const entry = { label: 'Descuento alto', approval_labels: ['Descuento del {discount_percent, percent}'] };
    const action = actionFor({ discount_percent: 50, customer_name: 'Ana', discount_amount: 0 }, entry);
    expect(action).toBe(`Descuento del 50${NBSP}%`);
    expect(action).not.toContain('Ana');
  });
});
