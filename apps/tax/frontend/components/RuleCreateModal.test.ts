// TAX-F04/F05/F06/F11 — the «+» of Rules opens this dialog (the old table's create panel, field for
// field): Country (a Combo over the closed ISO list), Region, Category (a Combo searching the server
// among the business's), %, Type, Qualification, Exemption reason (only when exempt), Regime, Valid from, Valid
// to, «Root rule (component of)» (the roots the server says the component may hang from), «Component
// label», the hint and «Add».
// A class that charges no tax pins the rate to 0 % and says why; the server's refusals (an overlap
// on «Valid from», a 422 per field) stay in the dialog under their field, with what was typed kept.
import { Combo, type ComboOption } from '@erplora/ui/components';
import { describe, expect, it, vi } from 'vitest';

import type { CategoryRowOut, RuleOut } from '../operations';
import { click, ionValue, mountTax, settle } from '../__tests__/mount-tax';
import RuleCreateModal from './RuleCreateModal.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

type Control = HTMLElement & {
  label?: string;
  value?: unknown;
  placeholder?: string;
  fill?: string;
  type?: string;
  errorText?: string;
  helperText?: string;
  disabled?: boolean;
};

const category = (key: string, display: string): CategoryRowOut => ({
  id: key,
  key,
  name: display,
  description: '',
  display_name: display,
  display_description: '',
  is_system: true,
  is_active: true,
  rate_pct: null,
  operation_class: null,
});
const CATEGORIES = [category('restaurant.food', 'Restaurant — food'), category('product.generic', 'Product — generic')];
const CATEGORY_PAGE = { rows: CATEGORIES, total: 2, limit: 50, offset: 0 };

const rule = (over: Partial<RuleOut>): RuleOut => ({
  id: 'r1',
  country_code: 'ES',
  region_code: null,
  tax_category_key: 'restaurant.food',
  tax_category_name: 'Restaurant — food',
  rate_pct: '10.00',
  tax_type: 'vat',
  operation_class: 'subject',
  exempt_reason: null,
  regime_key: null,
  parent_id: null,
  component_label: null,
  valid_from: '2012-09-01',
  valid_to: null,
  is_active: true,
  updated_at: '2026-10-13T10:00:00Z',
  ...over,
});
async function setup(locale: 'en' | 'es' = 'en') {
  const m = await mountTax(RuleCreateModal, { props: { open: true }, locale, path: '/tax/rules' });
  await m.wrapper.setProps({ 'onUpdate:open': (open: boolean) => m.wrapper.setProps({ open }) });
  await settle();
  const field = (name: string) => m.inDoc(`tax-rule-form-${name}`) as Control | null;
  const control = (name: string) => field(name) as Control;
  const add = () => m.inDoc('tax-rule-form-submit') as Control;
  /** The choices of an `ion-select`. */
  const options = (name: string) =>
    [...control(name).querySelectorAll('ion-select-option')].map((o) => [(o as Control).value, o.textContent?.trim()]);
  /** The Combo of a searchable field (Country, Category). */
  const combo = (name: string) => {
    const found = m.wrapper.findAllComponents(Combo).find((c) => c.props('testid') === `tax-rule-form-${name}`);
    if (!found) throw new Error(`no Combo for ${name}`);
    return found;
  };
  /** The fixed options of a Combo, as [id, label]. */
  const listed = (name: string) => (combo(name).props('options') as ComboOption[]).map((o) => [o.id, o.label]);
  const type = (name: string, value: string) => ionValue(control(name), value, 'ionInput');
  const pick = (name: string, value: string) => ionValue(control(name), value);
  /** Chooses `value` in a searchable field, as its Combo does when the person picks an option. */
  async function choose(name: string, value: string) {
    const label = name === 'country_code' ? (listed(name).find(([id]) => id === value)?.[1] ?? value) : value;
    combo(name).vm.$emit('update:modelValue', { id: value, label });
    await settle();
  }
  async function fillBasics() {
    await choose('country_code', 'ES');
    await choose('tax_category_key', 'restaurant.food');
    await type('rate_pct', '10');
  }
  return { ...m, field, control, add, options, combo, listed, type, pick, choose, fillBasics };
}

describe('RuleCreateModal: the fields of the old panel', () => {
  it('asks for every field of a rule in outlined md boxes, under «New tax rule», with the hint and «Add»', async () => {
    const s = await setup();
    expect(s.inDoc('tax-rule-form')?.getAttribute('aria-label')).toBe('New tax rule');
    const names = ['country_code', 'region_code', 'tax_category_key', 'rate_pct', 'tax_type', 'operation_class', 'regime_key', 'valid_from', 'valid_to', 'parent_id', 'component_label'];
    expect(names.map((n) => s.control(n).label)).toEqual([
      'Country',
      'Region',
      'Category',
      '%',
      'Type',
      'Qualification',
      'Regime',
      'Valid from',
      'Valid to',
      'Root rule (component of)',
      'Component label',
    ]);
    for (const n of names) expect([n, s.control(n).fill, s.control(n).getAttribute('mode')]).toEqual([n, 'outline', 'md']);
    expect([s.control('valid_from').type, s.control('valid_to').type, s.control('rate_pct').type]).toEqual(['date', 'date', 'number']);
    expect(s.control('region_code').placeholder).toBe('Optional — ISO 3166-2, e.g. ES-CN');
    expect(s.inDoc('tax-rule-form-hint')?.textContent).toContain('equivalence surcharge');
    expect(s.add().textContent?.trim()).toBe('Add');
  });

  it('types the country among the 249 the server accepts, named in the reader’s language (a Combo, the old ok-combo)', async () => {
    const s = await setup();
    expect(s.control('country_code').placeholder).toBe('Choose a country');
    const countries = s.listed('country_code');
    expect(countries).toHaveLength(249);
    expect(countries).toContainEqual(['ES', 'Spain (ES)']);
    expect(countries.some(([value]) => value === 'ZZ')).toBe(false);
    expect(s.combo('country_code').props('search')).toBeUndefined();
  });

  it('searches the category on the server, among all the business’s, by name; the key is its hint', async () => {
    const s = await setup();
    expect(s.params('tax.category.list')).toEqual([]);
    s.answer(200, CATEGORY_PAGE);
    const search = s.combo('tax_category_key').props('search') as (q: string) => Promise<ComboOption[]>;
    expect(await search(' books ')).toEqual([
      { id: 'restaurant.food', label: 'Restaurant — food', hint: 'restaurant.food' },
      { id: 'product.generic', label: 'Product — generic', hint: 'product.generic' },
    ]);
    expect(s.sent()).toEqual([
      { method: 'GET', path: '/api/tax/categories', query: { search: 'books', sort: 'display_name', dir: 'asc', limit: '50' }, body: undefined },
    ]);
  });

  it('starts as a VAT rule subject to tax: the eight families, the five qualifications, no exemption reason', async () => {
    const s = await setup();
    expect(s.control('tax_type').value).toBe('vat');
    expect(s.options('tax_type').map(([, label]) => label)).toEqual([
      'VAT',
      'IGIC (Canary Islands)',
      'IPSI (Ceuta/Melilla)',
      'Surcharge',
      'Sales tax',
      'Withholding',
      'Excise',
      'Import duty',
    ]);
    expect(s.control('operation_class').value).toBe('subject');
    expect(s.options('operation_class').map(([value]) => value)).toEqual(['subject', 'subject_reverse', 'exempt', 'not_subject', 'not_subject_location']);
    expect(s.field('exempt_reason')).toBeNull();
  });

  it('«Add» waits for a country, a category and a rate', async () => {
    const s = await setup();
    expect(s.add().disabled).toBe(true);
    await s.choose('country_code', 'ES');
    await s.choose('tax_category_key', 'restaurant.food');
    expect(s.add().disabled).toBe(true);
    await s.type('rate_pct', '10');
    expect(s.add().disabled).toBe(false);
  });
});

describe('RuleCreateModal: sending the rule', () => {
  it('sends tax.rule.create with what was chosen, the optional fields only when filled, then closes', async () => {
    const s = await setup();
    s.answer(201, rule({ id: 'new' }));
    await s.fillBasics();
    await s.type('region_code', ' es-cn ');
    await s.pick('tax_type', 'igic');
    await s.type('valid_from', '2027-01-01');
    await click(s.add());
    expect(s.sent()).toEqual([
      {
        method: 'POST',
        path: '/api/tax/rules',
        query: {},
        body: {
          country_code: 'ES',
          region_code: 'es-cn',
          tax_category_key: 'restaurant.food',
          rate_pct: '10',
          tax_type: 'igic',
          operation_class: 'subject',
          valid_from: '2027-01-01',
        },
      },
    ]);
    expect(s.wrapper.emitted('update:open')?.at(-1)).toEqual([false]);
  });

  it('an overlap (409) is said under «Valid from»; everything typed stays to change only the date', async () => {
    const s = await setup();
    const message = 'It overlaps another active rule of this country, region and category: two rates cannot apply on the same day.';
    s.answer(409, { error: { code: 'tax.rule_overlaps', message, fields: { valid_from: message } } });
    await s.fillBasics();
    await s.type('valid_from', '2020-01-01');
    await click(s.add());
    expect(s.control('valid_from').errorText).toBe(message);
    expect(s.control('valid_from').classList.contains('ion-invalid')).toBe(true);
    expect(s.control('rate_pct').classList.contains('ion-invalid')).toBe(false);
    expect(s.inDoc('tax-rule-form-error')?.textContent).toContain(message);
    expect([s.control('country_code').value, s.control('rate_pct').value, s.control('valid_from').value]).toEqual(['Spain (ES)', '10', '2020-01-01']);
    expect(s.wrapper.emitted('update:open')).toBeUndefined();
  });

  it('a 422 paints each message under its field', async () => {
    const s = await setup();
    s.answer(422, { error: { code: 'invalid_payload', message: 'Some fields are not valid.', fields: { rate_pct: 'Input should be less than or equal to 100' } } });
    await s.fillBasics();
    await s.type('rate_pct', '150');
    await click(s.add());
    expect(s.control('rate_pct').errorText).toBe('Input should be less than or equal to 100');
  });
});

describe('RuleCreateModal: a class that charges no tax (TAX-F05)', () => {
  it('pins the rate to 0 % and locks it, says why, and asks for the exemption reason when exempt', async () => {
    const s = await setup();
    await s.type('rate_pct', '21');
    expect(s.control('rate_pct').helperText).toBeFalsy();
    await s.pick('operation_class', 'exempt');
    expect([s.control('rate_pct').value, s.control('rate_pct').disabled]).toEqual(['0', true]);
    expect(s.control('rate_pct').helperText).toBe('This operation carries no tax, so its rate is 0 %.');
    expect([s.control('exempt_reason').label, s.control('exempt_reason').placeholder]).toEqual(['Exemption reason', 'e.g. E1 (jurisdiction code)']);
  });

  it('going back to subject unlocks the rate and asks for it again; a stale reason is never sent', async () => {
    const s = await setup();
    s.answer(201, rule({ id: 'new' }));
    await s.choose('country_code', 'ES');
    await s.choose('tax_category_key', 'restaurant.food');
    await s.pick('operation_class', 'exempt');
    await s.type('exempt_reason', 'e1');
    await s.pick('operation_class', 'subject');
    expect([s.control('rate_pct').value, s.control('rate_pct').disabled]).toEqual(['', false]);
    expect(s.field('exempt_reason')).toBeNull();
    await s.type('rate_pct', '10');
    await click(s.add());
    expect(s.sent()[0].body).not.toHaveProperty('exempt_reason');
  });

  it('an exempt rule sends its 0 %, its class and its reason', async () => {
    const s = await setup();
    s.answer(201, rule({ id: 'new' }));
    await s.choose('country_code', 'ES');
    await s.choose('tax_category_key', 'restaurant.food');
    await s.pick('operation_class', 'exempt');
    await s.type('exempt_reason', ' e1 ');
    await s.type('regime_key', '01');
    await click(s.add());
    expect(s.sent()[0].body).toMatchObject({ rate_pct: '0', operation_class: 'exempt', exempt_reason: 'e1', regime_key: '01' });
  });
});

describe('RuleCreateModal: a component under its root (TAX-F06)', () => {
  it('asks the server for the roots of the slot the form describes, once country and category are chosen', async () => {
    const s = await setup();
    expect(s.params('tax.rule.parent_candidates')).toEqual([]);
    expect(s.control('parent_id').disabled).toBe(true);
    await s.choose('country_code', 'ES');
    await s.choose('tax_category_key', 'restaurant.food');
    await s.type('rate_pct', '1.4');
    // The roots are the dialog's only live subscription: the stream opens with it.
    await s.live();
    expect(s.params('tax.rule.parent_candidates')).toEqual([{ country_code: 'ES', tax_category_key: 'restaurant.food', rate_pct: '1.4', limit: 50 }]);
    // A root starting in 2027 (TAX-F07 then F06) is offered: the server says so.
    await s.result('tax.rule.parent_candidates', { rows: [rule({ id: 'root-2027', valid_from: '2027-01-01' })], total: 1, limit: 50, offset: 0 });
    expect(s.options('parent_id')).toEqual([
      ['', 'None (this is a root rule)'],
      ['root-2027', '10.00% · VAT · Jan 1, 2027'],
    ]);
  });

  it('a chosen root travels as parent_id with the component label', async () => {
    const s = await setup();
    await s.fillBasics();
    await s.live();
    await s.result('tax.rule.parent_candidates', { rows: [rule({ id: 'root-food' })], total: 1, limit: 50, offset: 0 });
    s.answer(201, rule({ id: 'new' }));
    await s.pick('tax_type', 'surcharge');
    await s.pick('parent_id', 'root-food');
    await s.type('component_label', 'Recargo de equivalencia');
    await click(s.add());
    expect(s.sent()[0].body).toMatchObject({ parent_id: 'root-food', component_label: 'Recargo de equivalencia', tax_type: 'surcharge' });
  });
});

describe('RuleCreateModal speaks Spanish', () => {
  it('names the fields, the countries and the families in Spanish', async () => {
    const s = await setup('es');
    expect(s.inDoc('tax-rule-form')?.getAttribute('aria-label')).toBe('Nueva regla fiscal');
    expect(['country_code', 'valid_from', 'parent_id', 'component_label'].map((n) => s.control(n).label)).toEqual([
      'País',
      'Vigente desde',
      'Regla raíz (componente de)',
      'Etiqueta componente',
    ]);
    expect(s.listed('country_code')).toContainEqual(['ES', 'España (ES)']);
    expect(s.options('tax_type')[1][1]).toBe('IGIC (Canarias)');
    expect(s.options('tax_type')[4][1]).toBe('Impuesto sobre las ventas');
    expect(s.add().textContent?.trim()).toBe('Añadir');
  });
});
