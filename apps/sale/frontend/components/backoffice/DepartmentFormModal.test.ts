// SALE-F35 (the open-price departments): the «+» of Sections opens «New section» — Name («e.g.
// Fruit and veg», 60 characters at most), «VAT charged» (searched on the server among the business's tax
// categories) and Position — with «Add»; a row's «Edit» opens «Edit section» from that department, with
// «Save», and sends only what changed. No VAT chosen: «Choose the VAT this section charges.» under it.
// It closes once the server saved it; a refusal keeps it open with what was typed (a category the server
// does not know under «VAT charged», a department another device deleted on top).
import { describe, expect, it, vi } from 'vitest';

import { click, ionValue, mountSale, settle } from '../../__tests__/mount-sale';
import { plain } from '../../lib/format';
import type { DepartmentOut } from '../../operations';
import DepartmentFormModal from './DepartmentFormModal.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

type Control = HTMLElement & {
  label?: string;
  value?: unknown;
  placeholder?: string;
  fill?: string;
  type?: string;
  maxlength?: number;
  errorText?: string;
  disabled?: boolean;
};

const TAX = 'tax.category.list';
const FRUIT: DepartmentOut = {
  id: 'd1',
  name: 'Fruit and veg',
  tax_category_key: 'food.basic',
  tax_category_name: 'Basic food',
  tax_rate_pct: '4.00',
  sort_order: 1,
};
const CATEGORIES = {
  rows: [
    { id: 'c1', key: 'food.basic', name: 'food', description: '', display_name: 'Basic food', display_description: '', is_system: true, is_active: true, rate_pct: '4.00', operation_class: 'subject' },
    { id: 'c2', key: 'general', name: 'general', description: '', display_name: 'General', display_description: '', is_system: true, is_active: true, rate_pct: '21.00', operation_class: 'subject' },
  ],
  total: 2,
  limit: 50,
  offset: 0,
};
const GONE = 'That section is no longer in this business. Reload the list and try again.';
const UNKNOWN = 'That tax category does not exist in Taxes.';

async function setup(department: DepartmentOut | null = null, locale: 'en' | 'es' = 'en') {
  const m = await mountSale(DepartmentFormModal, { props: { open: true, department }, locale });
  await m.wrapper.setProps({ 'onUpdate:open': (open: boolean) => m.wrapper.setProps({ open }) });
  await settle();
  await m.live();
  await m.result(TAX, CATEGORIES);
  const field = (name: string) => m.inDoc(`sale-department-form-${name}`) as Control;
  const submit = () => m.inDoc('sale-department-form-submit') as Control;
  const title = () => m.inDoc('sale-department-form')?.getAttribute('aria-label');
  const type = (name: string, value: string) => ionValue(field(name), value, 'ionInput');
  async function chooseTax(key: string) {
    await click(field('tax'));
    await click(m.wrapper.find(`[data-testid="sale-department-form-tax-option"][data-value="${key}"]`).element);
  }
  const closed = () => m.wrapper.emitted('update:open')?.at(-1)?.[0] === false;
  return { ...m, field, submit, title, type, chooseTax, closed };
}

describe('DepartmentFormModal: «New section»', () => {
  it('asks Name, VAT charged and Position in outlined md boxes, with «Add»', async () => {
    const s = await setup();
    expect(s.title()).toBe('New section');
    const name = s.field('name');
    expect([name.label, name.placeholder, name.fill, name.getAttribute('mode'), name.maxlength]).toEqual(['Name', 'e.g. Fruit and veg', 'outline', 'md', 60]);
    expect([s.field('tax').label, s.field('tax').fill, s.field('tax').getAttribute('mode')]).toEqual(['VAT charged', 'outline', 'md']);
    const order = s.field('order');
    expect([order.label, order.type, order.fill, order.getAttribute('mode'), order.value]).toEqual(['Position', 'number', 'outline', 'md', '0']);
    expect(s.submit().textContent?.trim()).toBe('Add');
  });

  it('«Add» waits for a name', async () => {
    const s = await setup();
    expect(s.submit().disabled).toBe(true);
    await s.type('name', 'Butchery');
    expect(s.submit().disabled).toBe(false);
  });

  it('with no tax category to choose, «Add» stays off and the old notice says why', async () => {
    const s = await setup();
    await s.result(TAX, { rows: [], total: 0, limit: 50, offset: 0 }, {}, 2);
    await s.type('name', 'Butchery');
    expect(s.submit().disabled).toBe(true);
    expect(s.inDoc('sale-department-form-tax-none')?.textContent?.trim()).toBe(
      'There are no tax categories to choose from. Set up your VAT first, in Taxes.',
    );
  });

  it('no VAT chosen: says «Choose the VAT this section charges.» under it and sends nothing', async () => {
    const s = await setup();
    await s.type('name', 'Butchery');
    await click(s.submit());
    expect(s.field('tax').errorText).toBe('Choose the VAT this section charges.');
    expect(s.sent()).toEqual([]);
    expect(s.closed()).toBe(false);
    await s.chooseTax('general');
    expect(s.field('tax').errorText).toBeFalsy();
  });

  it('sends sale.department.create with the name trimmed, the category’s key and the position, then closes', async () => {
    const s = await setup();
    s.answer(201, { ...FRUIT, id: 'd9', name: 'Butchery' });
    await s.type('name', '  Butchery ');
    await s.chooseTax('general');
    await s.type('order', '4');
    await click(s.submit());
    expect(s.sent()).toEqual([
      { method: 'POST', path: '/api/sale/departments', query: {}, body: { name: 'Butchery', tax_category_key: 'general', sort_order: 4 } },
    ]);
    expect(s.closed()).toBe(true);
  });
});

describe('DepartmentFormModal: «Edit section»', () => {
  it('starts from the section: its name, its VAT as its row reads it and its position, with «Save»', async () => {
    const s = await setup(FRUIT);
    expect(s.title()).toBe('Edit section');
    expect([s.field('name').value, plain(String(s.field('tax').value)), s.field('order').value]).toEqual(['Fruit and veg', 'Basic food · 4%', '1']);
    expect(s.submit().textContent?.trim()).toBe('Save');
  });

  it('sends sale.department.update with its id and only what changed', async () => {
    const s = await setup(FRUIT);
    s.answer(200, { ...FRUIT, tax_category_key: 'general' });
    await s.chooseTax('general');
    await click(s.submit());
    expect(s.sent()).toEqual([
      { method: 'POST', path: '/api/sale/departments/update', query: {}, body: { id: 'd1', tax_category_key: 'general' } },
    ]);
    expect(s.closed()).toBe(true);
  });

  it('nothing changed: closes without asking the server', async () => {
    const s = await setup(FRUIT);
    await click(s.submit());
    expect([s.sent(), s.closed()]).toEqual([[], true]);
  });
});

describe('DepartmentFormModal: refusals keep it open', () => {
  it('a category the server does not know is said under «VAT charged»', async () => {
    const s = await setup();
    s.answer(422, { error: { code: 'invalid_field', message: UNKNOWN, fields: { tax_category_key: UNKNOWN } } });
    await s.type('name', 'Butchery');
    await s.chooseTax('general');
    await click(s.submit());
    expect(s.field('tax').errorText).toBe(UNKNOWN);
    expect(s.closed()).toBe(false);
    expect(s.field('name').value).toBe('Butchery');
  });

  it('a department another device deleted: the server’s words on top', async () => {
    const s = await setup(FRUIT);
    s.answer(404, { error: { code: 'sale.department_not_found', message: GONE } });
    await s.type('name', 'Fruit');
    await click(s.submit());
    expect(s.inDoc('sale-department-form-error')?.textContent).toContain(GONE);
  });

  it('a failure without words says «The section could not be saved.»', async () => {
    const s = await setup(FRUIT);
    s.net.onApi(() => new Response('<html>502</html>', { status: 502 }));
    await s.type('name', 'Fruit');
    await click(s.submit());
    expect(s.inDoc('sale-department-form-error')?.textContent).toContain('The section could not be saved.');
  });
});

describe('DepartmentFormModal: Spanish', () => {
  it('speaks the old screen’s words, «sección» for «departamento»', async () => {
    const s = await setup(null, 'es');
    expect(s.title()).toBe('Nueva sección');
    expect([s.field('name').label, s.field('name').placeholder, s.field('tax').label, s.field('order').label, s.submit().textContent?.trim()]).toEqual([
      'Nombre',
      'p. ej. Frutas y verduras',
      'IVA que cobra',
      'Posición',
      'Añadir',
    ]);
    await s.type('name', 'Carnicería');
    await click(s.submit());
    expect(s.field('tax').errorText).toBe('Elige el IVA que cobra esta sección.');
  });
});
