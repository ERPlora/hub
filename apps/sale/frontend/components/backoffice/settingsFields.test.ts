// The till settings as the Settings page paints them (SALE-F34): one control per field of the server's
// `SettingsFields`, in its order — the old generated screen's order —, each with the control its type asks
// for (a switch, a whole number 0–100, «Ticket» or «Invoice», a text as long as the server takes it).
import { describe, expect, it } from 'vitest';

import { SETTINGS_FIELDS } from './settingsFields';

describe('SETTINGS_FIELDS', () => {
  it('lists the 17 fields of the till settings, in the server’s order, each once', () => {
    expect(SETTINGS_FIELDS.map((field) => field.key)).toEqual([
      'allow_cash',
      'allow_card',
      'allow_transfer',
      'show_products',
      'show_services',
      'require_customer',
      'allow_discounts',
      'max_discount_percent',
      'enable_parked_tickets',
      'default_tax_included',
      'auto_invoice_with_tax_id',
      'default_document_type',
      'receipt_header',
      'receipt_footer',
      'receipt_footer_image',
      'receipt_marketing_url',
      'receipt_marketing_text',
    ]);
  });

  it('gives each the control its type asks for, with the server’s limits', () => {
    const control = Object.fromEntries(SETTINGS_FIELDS.map((field) => [field.key, field]));
    for (const key of ['allow_cash', 'allow_card', 'allow_transfer', 'show_products', 'show_services', 'require_customer', 'allow_discounts', 'enable_parked_tickets', 'default_tax_included', 'auto_invoice_with_tax_id']) {
      expect(control[key].control, key).toBe('toggle');
    }
    expect(control.max_discount_percent).toMatchObject({ control: 'number', min: 0, max: 100 });
    expect(control.default_document_type).toMatchObject({ control: 'select', options: ['ticket', 'invoice'] });
    // The header holds the name on its first line and the address on the rest.
    expect(control.receipt_header).toMatchObject({ control: 'textarea', maxlength: 1000 });
    expect(control.receipt_footer).toMatchObject({ control: 'textarea', maxlength: 1000 });
    expect(control.receipt_footer_image).toMatchObject({ control: 'text', type: 'url', maxlength: 500 });
    expect(control.receipt_marketing_url).toMatchObject({ control: 'text', type: 'url', maxlength: 500 });
    expect(control.receipt_marketing_text).toMatchObject({ control: 'text', type: 'text', maxlength: 200 });
  });

  it('says which ones carry an explanation under their name', () => {
    expect(SETTINGS_FIELDS.filter((field) => field.described).map((field) => field.key)).toEqual([
      'show_products',
      'show_services',
      'max_discount_percent',
      'receipt_header',
      'receipt_marketing_url',
      'receipt_marketing_text',
    ]);
  });
});
