// La última puerta antes de escribir en el ERP de alguien, en su idioma (hub#1040).
//
// La tarjeta enseñaba el nombre técnico de la tool y el JSON crudo de los argumentos: un dueño de
// peluquería tenía que aprobar `services.services.create` con `{"price_cents": 1500}` sin que en
// ningún sitio pusiera **15,00 €**. Es el ÚNICO punto del producto donde un humano podía cazar un
// error de ×100 — y era el único sitio donde el importe no se presentaba en euros.
//
// El propio system prompt del runtime lo advierte: «a price written wrong by a factor of 100 is a
// real invoice at the wrong price, and the schema will not catch it».

import { describe, expect, it } from 'vitest';

import { describeToolCall } from './assistant-confirm';

const catalogue = [
  {
    moduleId: 'services',
    moduleName: 'Servicios',
    commands: { 'services.services.create': { label: 'Crear un servicio' } },
  },
];

describe('describeToolCall — el dinero se ve en euros', () => {
  it('formatea en euros el campo que el runtime marcó como dinero', () => {
    const d = describeToolCall({
      command: 'services.services.create',
      args: { name: 'Corte caballero', price_cents: 1500 },
      moneyFields: ['price_cents'],
    });

    const price = d.fields.find((f) => f.key === 'price_cents');
    expect(price?.value).toContain('15');
    // Lo que NO puede pasar: que el dueño apruebe «1500» a secas.
    expect(price?.value).not.toBe('1500');
  });

  it('deja crudo lo que NO está marcado como dinero', () => {
    const d = describeToolCall({
      command: 'staff.members.create',
      args: { commission_rate: 15, hourly_rate: 1200 },
      moneyFields: ['hourly_rate'],
    });

    expect(d.fields.find((f) => f.key === 'commission_rate')?.value).toBe('15');
    expect(d.fields.find((f) => f.key === 'hourly_rate')?.value).not.toBe('1200');
  });

  // El caso que hace peligrosa una heurística por nombre: un porcentaje formateado como dinero
  // sería una mentira NUEVA. Sin marca, no se toca.
  it('sin marcas no inventa: ningún número se convierte en importe', () => {
    const d = describeToolCall({
      command: 'services.services.create',
      args: { duration_minutes: 30, price: 1700 },
    });

    expect(d.fields.find((f) => f.key === 'duration_minutes')?.value).toBe('30');
    expect(d.fields.find((f) => f.key === 'price')?.value).toBe('1700');
  });
});

describe('describeToolCall — la acción en palabras del negocio', () => {
  it('usa la traducción que da el MÓDULO, no el nombre del command', () => {
    const d = describeToolCall({
      command: 'services.services.create',
      args: {},
      catalogue,
    });

    expect(d.action).toBe('Crear un servicio');
    expect(d.app).toBe('Servicios');
  });

  // hub#363, y la razón por la que existe la escalera: `sales.void` es vocabulario NUESTRO. Si el
  // módulo no sabe nombrar su acción, se dice eso — no se rellena con el identificador interno.
  it('sin traducción NO cae al nombre crudo del command', () => {
    const d = describeToolCall({ command: 'sales.void', args: {} });

    expect(d.action).toBe('');
    expect(d.action).not.toContain('sales.void');
  });
});

describe('describeToolCall — los argumentos se leen', () => {
  it('cada argumento sale con su clave y su valor, en orden estable', () => {
    const d = describeToolCall({
      command: 'services.services.create',
      args: { name: 'Corte', active: true, duration_minutes: 30 },
    });

    expect(d.fields.map((f) => f.key)).toEqual(['active', 'duration_minutes', 'name']);
    expect(d.fields.find((f) => f.key === 'active')?.value).toBe('Sí');
  });

  it('un objeto anidado no revienta la tarjeta', () => {
    const d = describeToolCall({
      command: 'x.y',
      args: { nested: { a: 1 }, list: [1, 2] },
    });

    expect(d.fields).toHaveLength(2);
    expect(d.fields.every((f) => typeof f.value === 'string')).toBe(true);
  });
});
