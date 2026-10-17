// The till settings form (SALE-F34; WORKBOOK «Pantallas · Ajustes»): the heading «Point of sale», one row
// per setting with the business's live values, and «Save», which sends only what changed («Settings
// saved.»). Untouched, the form follows the server; what is being written is never overwritten. Whoever
// may not change them sees the values blocked, no «Save» and «You do not have permission to change these
// settings…»; a read the server refuses or that fails shows no values at all (never the factory ones).
import { toastSuccess } from '@erplora/ui/shell';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { BYE, click, errorFrame, flush, ionValue, mountSale } from '../../__tests__/mount-sale';
import type { SettingsOut } from '../../operations';
import SettingsField from './SettingsField.vue';
import SettingsForm from './SettingsForm.vue';

vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/shell')>()),
  toastSuccess: vi.fn(() => Promise.resolve()),
}));
beforeEach(() => vi.mocked(toastSuccess).mockClear());

type Control = HTMLElement & { checked?: boolean; value?: unknown; disabled?: boolean; errorText?: string };

const SETTINGS: SettingsOut = {
  allow_cash: true,
  allow_card: true,
  allow_transfer: false,
  show_products: true,
  show_services: true,
  require_customer: false,
  allow_discounts: true,
  max_discount_percent: 100,
  enable_parked_tickets: true,
  default_tax_included: true,
  auto_invoice_with_tax_id: false,
  default_document_type: 'ticket',
  receipt_header: '',
  receipt_footer: '',
  receipt_footer_image: '',
  receipt_marketing_url: '',
  receipt_marketing_text: '',
  updated_at: null,
};

async function setup(editable = true, locale: 'en' | 'es' = 'en') {
  const m = await mountSale(SettingsForm, { props: { editable }, locale });
  await m.live();
  const op = editable ? 'sale.settings.get' : 'sale.pos_settings.get';
  const show = (data: SettingsOut, rev = 1) => m.result(op, data, {}, rev);
  const control = (key: string) => m.inDoc(`sale-settings-field-${key}`) as Control;
  const save = () => m.inDoc('sale-settings-save') as Control;
  const text = (id: string) => m.inDoc(id)?.textContent?.trim() ?? '';
  async function toggle(key: string, checked: boolean) {
    control(key).dispatchEvent(new CustomEvent('ionChange', { detail: { checked } }));
    await flush();
  }
  const type = (key: string, value: string) => ionValue(control(key), value, 'ionInput');
  return { ...m, op, show, control, save, text, toggle, type };
}

describe('SettingsForm: reading', () => {
  it('reads sale.settings.get for whoever may change them, «Loading settings…» until it answers', async () => {
    const s = await setup();
    expect(s.params('sale.settings.get')).toEqual([{}]);
    expect(s.text('sale-settings-loading')).toBe('Loading settings…');
    expect(s.inDoc('sale-settings-form')).toBeNull();
    await s.show(SETTINGS);
    expect(s.inDoc('sale-settings-loading')).toBeNull();
    expect(s.text('sale-settings-heading')).toBe('Point of sale');
  });

  it('paints one row per setting, in the server’s order, with the business’s values; the first with the till’s icon', async () => {
    const s = await setup();
    await s.show({ ...SETTINGS, max_discount_percent: 15, default_document_type: 'invoice', receipt_header: 'Bar Pepe\nCalle Mayor 1' });
    const rows = s.wrapper.findAllComponents(SettingsField);
    expect(rows.map((row) => row.props('field').key)).toHaveLength(17);
    expect(rows[0].props('icon')).toBe('ion:card-outline');
    expect(rows.slice(1).every((row) => row.props('icon') === undefined)).toBe(true);
    expect([s.control('allow_cash').checked, s.control('allow_transfer').checked]).toEqual([true, false]);
    expect([s.control('max_discount_percent').value, s.control('default_document_type').value, s.control('receipt_header').value]).toEqual([
      '15',
      'invoice',
      'Bar Pepe\nCalle Mayor 1',
    ]);
  });

  it('reads the business territory’s tax from the start and names it in «Prices include IGIC»', async () => {
    const s = await setup(true, 'es');
    // Asked with the settings, before any row is painted: the stream opens with both, and is not reopened.
    expect(s.params('sale.sale.tax_kind')).toEqual([{}]);
    await s.result('sale.sale.tax_kind', { tax: 'igic' });
    await s.show(SETTINGS);
    expect(s.control('default_tax_included').getAttribute('aria-label')).toBe('Precios con IGIC incluido');
    const r = await setup(false);
    expect(r.params('sale.sale.tax_kind')).toEqual([{}]);
    await r.show(SETTINGS);
    expect(r.control('default_tax_included').getAttribute('aria-label')).toBe('Prices include VAT');
  });

  it('untouched, follows a change made elsewhere', async () => {
    const s = await setup();
    await s.show(SETTINGS);
    await s.show({ ...SETTINGS, allow_card: false }, 2);
    expect(s.control('allow_card').checked).toBe(false);
  });
});

describe('SettingsForm: saving', () => {
  it('«Save» waits for a change, and a change undone is no change', async () => {
    const s = await setup();
    await s.show(SETTINGS);
    expect([s.save().textContent?.trim(), s.save().disabled]).toEqual(['Save', true]);
    await s.toggle('allow_transfer', true);
    expect(s.save().disabled).toBe(false);
    await s.toggle('allow_transfer', false);
    expect(s.save().disabled).toBe(true);
  });

  it('sends only what changed, says «Settings saved.» and keeps the saved values', async () => {
    const s = await setup();
    await s.show(SETTINGS);
    const saved = { ...SETTINGS, allow_transfer: true, max_discount_percent: 20, receipt_header: 'Bar Pepe\nCalle Mayor 1' };
    s.answer(200, saved);
    await s.toggle('allow_transfer', true);
    await s.type('max_discount_percent', '20');
    await s.type('receipt_header', 'Bar Pepe\nCalle Mayor 1');
    await click(s.save());
    expect(s.sent()).toEqual([
      { method: 'POST', path: '/api/sale/settings', query: {}, body: { allow_transfer: true, max_discount_percent: 20, receipt_header: 'Bar Pepe\nCalle Mayor 1' } },
    ]);
    expect(toastSuccess).toHaveBeenCalledWith('Settings saved.');
    expect([s.control('allow_transfer').checked, s.control('max_discount_percent').value, s.save().disabled]).toEqual([true, '20', true]);
  });

  it('what is written while a save is on its way is kept, not swept away by its answer', async () => {
    const s = await setup();
    await s.show(SETTINGS);
    let answer!: (response: Response) => void;
    s.net.onApi(() => new Promise<Response>((resolve) => (answer = resolve)));
    await s.toggle('allow_transfer', true);
    await click(s.save());
    await s.type('receipt_footer', 'Thanks!');
    answer(Response.json({ ...SETTINGS, allow_transfer: true }));
    await flush();
    expect([s.control('allow_transfer').checked, s.control('receipt_footer').value, s.save().disabled]).toEqual([true, 'Thanks!', false]);
  });

  it('what is being written survives a change made elsewhere', async () => {
    const s = await setup();
    await s.show(SETTINGS);
    await s.type('receipt_footer', 'Thanks!');
    await s.show({ ...SETTINGS, receipt_footer: 'See you', allow_cash: false }, 2);
    expect([s.control('receipt_footer').value, s.control('allow_cash').checked]).toEqual(['Thanks!', false]);
  });

  it('a blank largest discount cannot be saved', async () => {
    const s = await setup();
    await s.show(SETTINGS);
    await s.type('max_discount_percent', '');
    expect(s.save().disabled).toBe(true);
  });

  it('a refusal: «Could not save settings.» with the server’s words, and the field it names', async () => {
    const s = await setup();
    await s.show(SETTINGS);
    const message = 'Input should be less than or equal to 100';
    s.answer(422, { error: { code: 'invalid_payload', message: 'Some fields are not valid.', fields: { max_discount_percent: message } } });
    await s.type('max_discount_percent', '150');
    await click(s.save());
    const banner = s.text('sale-settings-save-error');
    expect(banner).toContain('Could not save settings.');
    expect(banner).toContain('Some fields are not valid.');
    expect(s.control('max_discount_percent').errorText).toBe(message);
    expect(toastSuccess).not.toHaveBeenCalled();
    expect(s.control('max_discount_percent').value).toBe('150');
  });
});

describe('SettingsForm: whoever may not change them', () => {
  it('sees the business’s values (sale.pos_settings.get) blocked, no «Save», and why', async () => {
    const s = await setup(false);
    expect(s.params('sale.pos_settings.get')).toEqual([{}]);
    expect(s.params('sale.settings.get')).toEqual([]);
    await s.show({ ...SETTINGS, allow_cash: false });
    expect(s.control('allow_cash').checked).toBe(false);
    expect(['allow_cash', 'max_discount_percent', 'default_document_type', 'receipt_header'].map((key) => s.control(key).disabled)).toEqual([true, true, true, true]);
    expect(s.inDoc('sale-settings-save')).toBeNull();
    expect(s.text('sale-settings-read-only')).toBe('You do not have permission to change these settings. Ask an administrator if you need to.');
  });
});

describe('SettingsForm: a read that fails shows no values', () => {
  it('refused by the server: the no-permission sentence, no fields', async () => {
    const s = await setup();
    s.net.lastStream().push(errorFrame(s.subId('sale.settings.get'), 'permission_denied'));
    await flush();
    expect(s.text('sale-settings-no-permission')).toBe('You do not have permission to change these settings. Ask an administrator if you need to.');
    expect(s.inDoc('sale-settings-form')).toBeNull();
  });

  it('a failed read: «Could not load settings.», the reassurance and «Retry»', async () => {
    const s = await setup();
    s.net.lastStream().push(errorFrame(s.subId('sale.settings.get'), 'server_error'));
    await flush();
    const notice = s.text('sale-settings-load-error');
    expect(notice).toContain('Could not load settings.');
    expect(notice).toContain('Your saved settings have not changed. Check the connection and try again.');
    expect(s.inDoc('sale-settings-form')).toBeNull();
    const before = s.net.streams.length;
    await click(s.inDoc('sale-settings-retry'));
    expect(s.net.streams.length).toBe(before + 1);
  });

  it('the app off: «This app is not active in this business.»', async () => {
    const s = await setup();
    s.net.lastStream().push(errorFrame(s.subId('sale.settings.get'), 'app_inactive'));
    await flush();
    expect(s.text('sale-settings-load-error')).toContain('This app is not active in this business.');
  });

  it('while the stream recovers, «Reconnecting…» and the values stay', async () => {
    const s = await setup();
    await s.show(SETTINGS);
    s.net.lastStream().push(BYE);
    await flush();
    expect(s.text('sale-settings-reconnecting')).toBe('Reconnecting…');
    expect(s.inDoc('sale-settings-form')).not.toBeNull();
  });
});

describe('SettingsForm: Spanish', () => {
  it('speaks the old screen’s words', async () => {
    const s = await setup(true, 'es');
    expect(s.text('sale-settings-loading')).toBe('Cargando ajustes…');
    await s.show(SETTINGS);
    expect([s.text('sale-settings-heading'), s.save().textContent?.trim()]).toEqual(['TPV', 'Guardar']);
    const r = await setup(false, 'es');
    await r.show(SETTINGS);
    expect(r.text('sale-settings-read-only')).toBe('No tienes permiso para cambiar estos ajustes. Pídeselo a un administrador si lo necesitas.');
  });
});
