// One row of the till settings (SALE-F34), as the old generated settings screen painted it: the setting's
// name and its explanation, and its control — a switch, a whole number, «Ticket» or «Invoice» (translated:
// the old screen showed the raw `ticket`/`invoice`), a text or a multi-line text in an outlined md box.
// Blocked, nothing can be changed; a refusal of the server is said at the field.
import { describe, expect, it } from 'vitest';

import { ionValue, mountSale } from '../../__tests__/mount-sale';
import { SETTINGS_FIELDS, type SettingsKey } from './settingsFields';
import SettingsField from './SettingsField.vue';

type Control = HTMLElement & {
  checked?: boolean;
  value?: unknown;
  disabled?: boolean;
  type?: string;
  min?: string | number;
  max?: string | number;
  fill?: string;
  maxlength?: number;
  placeholder?: string;
  interface?: string;
  autoGrow?: boolean;
  errorText?: string;
};

const fieldOf = (key: SettingsKey) => SETTINGS_FIELDS.find((field) => field.key === key)!;

async function setup(key: SettingsKey, props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  const m = await mountSale(SettingsField, { props: { field: fieldOf(key), value: '', disabled: false, taxName: 'VAT', ...props }, locale });
  const control = () => m.inDoc(`sale-settings-field-${key}`) as Control;
  // happy-dom reads no text off an `ion-item`: the name and the explanation are read from their own nodes.
  const text = () => m.wrapper.findAll('h2, p').map((node) => node.element.textContent?.trim()).join(' ');
  return { ...m, control, text };
}

describe('SettingsField', () => {
  it('a switch: its name, its state, and the new state when flipped', async () => {
    const s = await setup('allow_cash', { value: true });
    expect(s.text()).toContain('Allow cash');
    expect([s.control().tagName, s.control().checked, s.control().disabled]).toEqual(['ION-TOGGLE', true, false]);
    s.control().dispatchEvent(new CustomEvent('ionChange', { detail: { checked: false } }));
    expect(s.wrapper.emitted('update:value')?.at(-1)).toEqual([false]);
  });

  it('with its explanation under its name', async () => {
    const s = await setup('show_products', { value: true });
    expect(s.text()).toContain('Show products in the till');
    expect(s.text()).toContain('Products show up when the Inventory app is active. Turn it off to sell only services or free-price lines.');
  });

  it('the largest discount: a whole number from 0 to 100 in an outlined md box', async () => {
    const s = await setup('max_discount_percent', { value: '15' });
    const c = s.control();
    expect([c.tagName, c.type, String(c.min), String(c.max), c.fill, c.getAttribute('mode'), c.value]).toEqual(['ION-INPUT', 'number', '0', '100', 'outline', 'md', '15']);
    await ionValue(c, '20', 'ionInput');
    expect(s.wrapper.emitted('update:value')?.at(-1)).toEqual(['20']);
  });

  it('the default document: «Ticket» or «Invoice», translated', async () => {
    const s = await setup('default_document_type', { value: 'invoice' });
    expect([s.control().tagName, s.control().value, s.control().interface]).toEqual(['ION-SELECT', 'invoice', 'popover']);
    expect(s.wrapper.findAll('ion-select-option').map((o) => [(o.element as HTMLElement & { value?: string }).value, o.element.textContent?.trim()])).toEqual([
      ['ticket', 'Ticket'],
      ['invoice', 'Invoice'],
    ]);
    await ionValue(s.control(), 'ticket');
    expect(s.wrapper.emitted('update:value')?.at(-1)).toEqual(['ticket']);
    const es = await setup('default_document_type', { value: 'ticket' }, 'es');
    expect(es.wrapper.findAll('ion-select-option').map((o) => o.element.textContent?.trim())).toEqual(['Tique', 'Factura']);
  });

  it('the receipt header: several lines (name, then address), as long as the server takes', async () => {
    const s = await setup('receipt_header', { value: 'Bar Pepe\nCalle Mayor 1' });
    const c = s.control();
    expect([c.tagName, c.fill, c.getAttribute('mode'), c.maxlength, c.autoGrow, c.value]).toEqual(['ION-TEXTAREA', 'outline', 'md', 1000, true, 'Bar Pepe\nCalle Mayor 1']);
    expect(s.text()).toContain('First line = name; the rest = address.');
    await ionValue(c, 'Bar Pepa', 'ionInput');
    expect(s.wrapper.emitted('update:value')?.at(-1)).toEqual(['Bar Pepa']);
  });

  it('an address: a URL box with the old «Type here…» hint', async () => {
    const s = await setup('receipt_marketing_url', { value: '' });
    const c = s.control();
    expect([c.tagName, c.type, c.maxlength, c.placeholder, c.fill, c.getAttribute('mode')]).toEqual(['ION-INPUT', 'url', 500, 'Type here…', 'outline', 'md']);
  });

  it('an empty text stays empty (never read as a switch that is on)', async () => {
    for (const key of ['receipt_footer', 'receipt_marketing_text'] as const) {
      const s = await setup(key, { value: '' });
      expect(s.control().value, key).toBe('');
    }
  });

  it('blocked: nothing can be changed', async () => {
    for (const key of ['allow_cash', 'max_discount_percent', 'default_document_type', 'receipt_footer', 'receipt_marketing_text'] as const) {
      const s = await setup(key, { disabled: true });
      expect(s.control().disabled, key).toBe(true);
    }
  });

  it('a refusal of the server is said at the field', async () => {
    const toggle = await setup('allow_card', { value: true, error: 'Input should be a valid boolean' });
    expect(toggle.find('sale-settings-invalid-allow_card').element.textContent?.trim()).toBe('Input should be a valid boolean');
    const input = await setup('receipt_marketing_text', { value: 'x', error: 'String should have at most 200 characters' });
    expect(input.control().errorText).toBe('String should have at most 200 characters');
    expect(input.control().classList.contains('ion-invalid')).toBe(true);
  });

  it('the first row carries the screen’s icon, as the old one did', async () => {
    const s = await setup('allow_cash', { value: true, icon: 'ion:card-outline' });
    expect(s.wrapper.find('[slot="start"]').exists()).toBe(true);
    const plain = await setup('allow_card', { value: true });
    expect(plain.wrapper.find('[slot="start"]').exists()).toBe(false);
  });

  it('«Prices include VAT» names the tax its form gives it: the business territory’s («IGIC», «IPSI»)', async () => {
    const vat = await setup('default_tax_included', { value: true, taxName: 'IVA' }, 'es');
    expect(vat.text()).toContain('Precios con IVA incluido');
    const s = await setup('default_tax_included', { value: true, taxName: 'IGIC' }, 'es');
    expect(s.text()).toContain('Precios con IGIC incluido');
    expect(s.control().getAttribute('aria-label')).toBe('Precios con IGIC incluido');
    const ipsi = await setup('default_tax_included', { value: true, taxName: 'IPSI' });
    expect(ipsi.text()).toContain('Prices include IPSI');
  });

  it('speaks Spanish', async () => {
    const s = await setup('max_discount_percent', { value: '100' }, 'es');
    expect(s.text()).toContain('Descuento máximo que puede aplicar solo quien cobra, por descuento (%)');
    expect(s.text()).toContain('100 = sin límite.');
  });
});
