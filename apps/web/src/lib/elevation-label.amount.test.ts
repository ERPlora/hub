// The approval dialog says HOW MUCH is being approved, not only what kind of action (hub#2180).
//
// Since sales#393 the manager reads «Apply a line discount above the limit», but not whether it is
// 15 % or 90 %. Toast and Square print «Approve 50% discount» so the manager does not sign off on
// something out of proportion blind.
//
// The module opts in with `commands["<cmd>"].approval_label` in its locale: a template whose holes
// name payload fields and how to format them — `{discount_percent, percent}`,
// `{discount_amount, money}` (minor units, the hub currency) or a bare `{field}`. Only the fields
// the template names ever reach the screen (hub#363: the payload is not the customer's business).
// When the template cannot be filled completely, the plain `label` is used — never a half sentence
// with a raw `{hole}` in it.
import { describe, expect, it, vi } from 'vitest';

vi.mock('../i18n', () => ({ getLocale: () => 'es' }));

import { describeElevation } from './elevation-label';

// CLDR puts a NO-BREAK SPACE (U+00A0) between the figure and «%» / «€» in Spanish.
const NBSP = ' ';

const LINE = 'sales.order.set_line_discount_over_limit';
const TICKET = 'sales.order.set_discount_over_limit';

const catalogue = [
  {
    moduleId: 'sales',
    moduleName: 'Ventas / TPV',
    commands: {
      [LINE]: {
        label: 'Aplicar a una línea un descuento por encima del límite',
        approval_label: 'Aplicar a una línea un descuento del {discount_percent, percent}',
      },
      [TICKET]: {
        label: 'Aplicar al tique un descuento por encima del límite',
        approval_label: 'Aplicar al tique un descuento de {discount_amount, money}',
      },
      'sales.order.add_open_line': {
        label: 'Vender un artículo a precio libre',
        approval_label: 'Vender «{description}» a precio libre',
      },
      'sales.void': { label: 'Anular una venta' },
    },
  },
];

describe('the dialog says the figure that is being approved', () => {
  it('fills a percent hole with the locale percent format', () => {
    const described = describeElevation(
      { command: LINE, payload: { order_id: 'o-1', line_id: 'l-1', discount_percent: 90 } },
      catalogue,
    );
    expect(described.action).toBe(`Aplicar a una línea un descuento del 90${NBSP}%`);
    expect(described.moduleName).toBe('Ventas / TPV');
  });

  it('keeps the decimals of a fractional percent', () => {
    const described = describeElevation({ command: LINE, payload: { discount_percent: 12.5 } }, catalogue);
    expect(described.action).toBe(`Aplicar a una línea un descuento del 12,5${NBSP}%`);
  });

  it('fills a money hole from minor units with the hub currency formatter', () => {
    const described = describeElevation(
      { command: TICKET, payload: { order_id: 'o-1', discount_amount: 123456 } },
      catalogue,
    );
    expect(described.action).toBe(`Aplicar al tique un descuento de 1.234,56${NBSP}€`);
  });

  it('fills a bare hole with the text the module named', () => {
    const described = describeElevation(
      { command: 'sales.order.add_open_line', payload: { description: 'Menú del día', unit_price: 1200 } },
      catalogue,
    );
    expect(described.action).toBe('Vender «Menú del día» a precio libre');
  });

  it('fills a bare number hole grouped from four digits, like money (hub#1090)', () => {
    const counted = [
      {
        moduleId: 'sales',
        moduleName: 'Ventas / TPV',
        commands: { [LINE]: { label: 'Descuento alto', approval_label: 'Rebajar {units} unidades' } },
      },
    ];
    expect(describeElevation({ command: LINE, payload: { units: 1234.5 } }, counted).action).toBe(
      'Rebajar 1.234,5 unidades',
    );
  });

  it('never prints a payload field the template does not name', () => {
    const described = describeElevation(
      { command: LINE, payload: { order_id: 'secret-order', line_id: 'secret-line', discount_percent: 50 } },
      catalogue,
    );
    expect(described.action).not.toContain('secret');
  });

  it('falls back to the plain label when the named field is missing', () => {
    const described = describeElevation({ command: LINE, payload: { order_id: 'o-1' } }, catalogue);
    expect(described.action).toBe('Aplicar a una línea un descuento por encima del límite');
  });

  it('falls back to the plain label when there is no payload at all', () => {
    expect(describeElevation({ command: LINE }, catalogue).action).toBe(
      'Aplicar a una línea un descuento por encima del límite',
    );
  });

  it('falls back when a money or percent hole is not a finite number', () => {
    for (const bad of ['90', null, Number.NaN, Number.POSITIVE_INFINITY, { v: 90 }, true]) {
      expect(describeElevation({ command: LINE, payload: { discount_percent: bad } }, catalogue).action).toBe(
        'Aplicar a una línea un descuento por encima del límite',
      );
      expect(describeElevation({ command: TICKET, payload: { discount_amount: bad } }, catalogue).action).toBe(
        'Aplicar al tique un descuento por encima del límite',
      );
    }
  });

  it('falls back when a bare hole is an object, an array or blank text', () => {
    for (const bad of [{ a: 1 }, ['x'], '   ', null]) {
      expect(
        describeElevation({ command: 'sales.order.add_open_line', payload: { description: bad } }, catalogue).action,
      ).toBe('Vender un artículo a precio libre');
    }
  });

  it('falls back when the template asks for a format the shell does not know', () => {
    const odd = [
      {
        moduleId: 'sales',
        moduleName: 'Ventas / TPV',
        commands: { [LINE]: { label: 'Descuento alto', approval_label: 'Descuento del {discount_percent, date}' } },
      },
    ];
    expect(describeElevation({ command: LINE, payload: { discount_percent: 9 } }, odd).action).toBe('Descuento alto');
  });

  it('falls back when the template has a hole it cannot parse', () => {
    const malformed = [
      {
        moduleId: 'sales',
        moduleName: 'Ventas / TPV',
        commands: { [LINE]: { label: 'Descuento alto', approval_label: 'Descuento del {discount-percent}' } },
      },
    ];
    expect(describeElevation({ command: LINE, payload: { discount_percent: 9 } }, malformed).action).toBe(
      'Descuento alto',
    );
  });

  it('uses the filled template even when the module ships no plain label', () => {
    const onlyTemplate = [
      {
        moduleId: 'sales',
        moduleName: 'Ventas / TPV',
        commands: { [LINE]: { approval_label: 'Descuento del {discount_percent, percent}' } },
      },
    ];
    expect(describeElevation({ command: LINE, payload: { discount_percent: 30 } }, onlyTemplate).action).toBe(
      `Descuento del 30${NBSP}%`,
    );
  });

  it('a command without a template keeps its plain label', () => {
    expect(describeElevation({ command: 'sales.void', payload: { sale_id: 's-1' } }, catalogue).action).toBe(
      'Anular una venta',
    );
  });
});
