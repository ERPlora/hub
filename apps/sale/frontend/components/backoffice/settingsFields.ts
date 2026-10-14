// The till settings as the Settings page paints them (SALE-F34): one control per field of the server's
// `SettingsFields` (apps/sale/schemas.py), in its order, with the limits the server takes. Labels and
// explanations live in the catalogue under `sale.settings.fields.<key>.label` / `.description`.
import type { DocumentType, SettingsFields } from '../../operations';

export type SettingsKey = keyof SettingsFields;

interface Base {
  key: SettingsKey;
  /** It has an explanation under its name (`sale.settings.fields.<key>.description`). */
  described?: boolean;
}

export type SettingsField =
  | (Base & { control: 'toggle' })
  | (Base & { control: 'number'; min: number; max: number })
  | (Base & { control: 'select'; options: readonly DocumentType[] })
  | (Base & { control: 'textarea'; maxlength: number })
  | (Base & { control: 'text'; type: 'text' | 'url'; maxlength: number });

export const SETTINGS_FIELDS: readonly SettingsField[] = Object.freeze([
  { key: 'allow_cash', control: 'toggle' },
  { key: 'allow_card', control: 'toggle' },
  { key: 'allow_transfer', control: 'toggle' },
  { key: 'show_products', control: 'toggle', described: true },
  { key: 'show_services', control: 'toggle', described: true },
  { key: 'require_customer', control: 'toggle' },
  { key: 'allow_discounts', control: 'toggle' },
  { key: 'max_discount_percent', control: 'number', min: 0, max: 100, described: true },
  { key: 'enable_parked_tickets', control: 'toggle' },
  { key: 'default_tax_included', control: 'toggle' },
  { key: 'auto_invoice_with_tax_id', control: 'toggle' },
  { key: 'default_document_type', control: 'select', options: ['ticket', 'invoice'] },
  { key: 'receipt_header', control: 'textarea', maxlength: 1000, described: true },
  { key: 'receipt_footer', control: 'textarea', maxlength: 1000 },
  { key: 'receipt_footer_image', control: 'text', type: 'url', maxlength: 500 },
  { key: 'receipt_marketing_url', control: 'text', type: 'url', maxlength: 500, described: true },
  { key: 'receipt_marketing_text', control: 'text', type: 'text', maxlength: 200, described: true },
]);
