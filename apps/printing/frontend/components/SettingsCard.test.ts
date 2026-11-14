// The ticket settings (PRINTING-F06; WORKBOOK «Pantallas · Ajustes»): «Print receipt on checkout», «Open
// drawer on checkout», «Receipt copies» and, per role, its printer — «The first active one of this role» or
// one of its active printers —, the note that the receipt's texts are the till's (with the link when Sales
// is on) and «Save settings», which sends only what changed. A read that fails shows no values; whoever may
// not change them sees them blocked, without «Save settings».
import { resolveIcon, toastSuccess } from '@erplora/ui/shell';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ADMIN, click, errorFrame, flush, ionToggle, ionValue, mountPrinting } from '../__tests__/mount-printing';
import type { PrinterOut, SettingsOut } from '../operations';
import SettingsCard from './SettingsCard.vue';

vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...((await importOriginal()) as object),
  toastSuccess: vi.fn(() => Promise.resolve()),
}));
beforeEach(() => vi.mocked(toastSuccess).mockClear());

const OP = 'printing.settings.get';
const PRINTERS = 'printing.printer.list';
const prop = (el: Element | null, name: string): unknown => (el as unknown as Record<string, unknown>)[name];
const FACTORY: SettingsOut = {
  print_receipt_on_sale: true,
  open_drawer_on_sale: false,
  receipt_copies: 1,
  receipt_printer_id: null,
  kitchen_printer_id: null,
  bar_printer_id: null,
  label_printer_id: null,
  updated_at: null,
};
const printer = (id: string, name: string, usage: PrinterOut['usage']) => ({ id, name, usage, is_active: true }) as PrinterOut;
const ACTIVE = { rows: [printer('k1', 'Kitchen', 'kitchen'), printer('k2', 'Kitchen 2', 'kitchen'), printer('t1', 'Till', 'receipt')], total: 3, limit: 100, offset: 0 };

async function setup(editable = true, locale: 'en' | 'es' = 'en', apps = [{ label: 'sale', state: 'on' as const }]) {
  const m = await mountPrinting(SettingsCard, { props: { editable }, locale, session: { ...ADMIN, apps } });
  await m.live();
  const field = (key: string) => m.inDoc(`printing-setting-${key}`);
  return { ...m, field };
}

describe('SettingsCard', () => {
  it('says it is loading, then paints the business’s values and each role’s active printers', async () => {
    const s = await setup();
    expect(s.find('printing-settings-loading').text()).toBe('Loading settings…');
    expect(s.params(PRINTERS)).toEqual([{ is_active: true, limit: 100 }]);
    await s.result(OP, { ...FACTORY, kitchen_printer_id: 'k2' });
    await s.result(PRINTERS, ACTIVE);
    expect(s.find('printing-settings-heading').text()).toBe('Ticket settings');
    expect(prop(s.field('print_receipt_on_sale'), 'checked')).toBe(true);
    expect(prop(s.field('open_drawer_on_sale'), 'checked')).toBe(false);
    expect(prop(s.field('receipt_copies'), 'value')).toBe(1);
    expect(prop(s.field('kitchen_printer'), 'value')).toBe('k2');
    expect(prop(s.field('bar_printer'), 'value')).toBe('');
    const kitchen = [...(s.field('kitchen_printer')?.querySelectorAll('ion-select-option') ?? [])].map((o) => o.textContent?.trim());
    expect(kitchen).toEqual(['The first active one of this role', 'Kitchen', 'Kitchen 2']);
  });

  it('«Save settings» sends only what changed; a role back to automatic is null', async () => {
    const s = await setup();
    await s.result(OP, { ...FACTORY, kitchen_printer_id: 'k2' });
    await s.result(PRINTERS, ACTIVE);
    expect(prop(s.inDoc('printing-settings-save'), 'disabled')).toBe(true);
    expect(prop(s.inDoc('printing-settings-save')?.querySelector('ion-icon[slot="start"]') ?? null, 'icon')).toBe(resolveIcon('lucide:save'));
    await ionToggle(s.field('open_drawer_on_sale'), true);
    await ionValue(s.field('receipt_copies'), 2);
    await ionValue(s.field('kitchen_printer'), '');
    await ionValue(s.field('receipt_printer'), 't1');
    s.answer(200, { ...FACTORY, open_drawer_on_sale: true, receipt_copies: 2, receipt_printer_id: 't1', updated_at: '2026-10-14T10:00:00Z' });
    await click(s.inDoc('printing-settings-save'));
    expect(s.sent()).toEqual([
      {
        method: 'POST',
        path: '/api/printing/settings',
        query: {},
        body: { open_drawer_on_sale: true, receipt_copies: 2, kitchen_printer: null, receipt_printer: 't1' },
      },
    ]);
    expect(s.find('printing-settings-saved').text()).toBe('Settings saved.');
    expect(toastSuccess).not.toHaveBeenCalled();
  });

  it('a refused save says so with the server’s words, and under the role it names', async () => {
    const s = await setup();
    await s.result(OP, FACTORY);
    await s.result(PRINTERS, ACTIVE);
    await ionValue(s.field('kitchen_printer'), 'k1');
    s.answer(422, { error: { code: 'invalid_payload', message: 'That printer is inactive.', fields: { kitchen_printer: 'That printer is inactive.' } } });
    await click(s.inDoc('printing-settings-save'));
    expect(s.find('printing-settings-save-error').text()).toContain('That printer is inactive.');
    expect(prop(s.field('kitchen_printer'), 'errorText')).toBe('That printer is inactive.');
    expect(prop(s.field('bar_printer'), 'errorText')).toBeUndefined();
  });

  it('after a refused save, another printer for that role lifts its message and the notice; the next refusal says them again', async () => {
    const s = await setup();
    await s.result(OP, FACTORY);
    await s.result(PRINTERS, ACTIVE);
    s.answer(422, { error: { code: 'invalid_payload', message: 'That printer is inactive.', fields: { kitchen_printer: 'That printer is inactive.' } } });
    const says = () => [prop(s.field('kitchen_printer'), 'errorText') ?? '', s.inDoc('printing-settings-save-error') !== null];
    await ionValue(s.field('kitchen_printer'), 'k1');
    await click(s.inDoc('printing-settings-save'));
    expect(says()).toEqual(['That printer is inactive.', true]);
    await ionValue(s.field('kitchen_printer'), 'k2');
    expect(says()).toEqual(['', false]);
    await click(s.inDoc('printing-settings-save'));
    expect(says()).toEqual(['That printer is inactive.', true]);
  });

  it('a failure the server did not word says the card’s sentence, never the server’s', async () => {
    const s = await setup();
    await s.result(OP, FACTORY);
    await ionToggle(s.field('open_drawer_on_sale'), true);
    s.answer(500, { error: { code: 'internal_error', message: 'Internal server error: boom' } });
    await click(s.inDoc('printing-settings-save'));
    expect(s.find('printing-settings-save-error').text()).toContain('Could not save the settings.');
    expect(s.find('printing-settings-save-error').text()).not.toContain('boom');
  });

  it('the receipt’s texts are the till’s: the note, and the link while Sales is on', async () => {
    const s = await setup();
    await s.result(OP, FACTORY);
    expect(s.find('printing-settings-receipt-text').text()).toContain('The receipt header and footer are part of your till settings');
    expect(s.find('printing-settings-receipt-link').attributes('href')).toBe('/sale/settings');
    const off = await setup(true, 'en', []);
    await off.result(OP, FACTORY);
    expect(off.find('printing-settings-receipt-link').exists()).toBe(false);
  });

  it('a failed read shows no values and offers to retry', async () => {
    const s = await setup();
    s.net.lastStream().push(errorFrame(s.subId(OP), 'internal_error'));
    await flush();
    expect(s.find('printing-settings-load-error').text()).toContain('Could not load the settings.');
    expect(s.field('print_receipt_on_sale')).toBeNull();
  });

  it('without the permission the values are blocked and there is no «Save settings»', async () => {
    const s = await setup(false);
    await s.result(OP, FACTORY);
    expect(prop(s.field('print_receipt_on_sale'), 'disabled')).toBe(true);
    expect(prop(s.field('kitchen_printer'), 'disabled')).toBe(true);
    expect(s.inDoc('printing-settings-save')).toBeNull();
    expect(s.find('printing-settings-read-only').text()).toContain('You do not have permission');
  });

  it('speaks Spanish', async () => {
    const s = await setup(true, 'es');
    await s.result(OP, FACTORY);
    expect(s.find('printing-settings-label-print_receipt_on_sale').text()).toBe('Imprimir tique al cobrar');
    expect(s.inDoc('printing-settings-save')?.textContent?.trim()).toBe('Guardar ajustes');
  });

  // hub#914: only what was sent is saved; what was changed while the save was on its way stays, still to send.
  it('a change made while «Save settings» is on its way stays, and the next save sends only it', async () => {
    const s = await setup();
    await s.result(OP, FACTORY);
    await s.result(PRINTERS, ACTIVE);
    let release: (answer: Response) => void = () => {};
    s.net.onApi(() => new Promise<Response>((resolve) => (release = resolve)));
    await ionToggle(s.field('open_drawer_on_sale'), true);
    await click(s.inDoc('printing-settings-save'));
    await ionValue(s.field('receipt_copies'), 3);
    release(Response.json({ ...FACTORY, open_drawer_on_sale: true }));
    await flush();
    await flush();
    const save = s.inDoc('printing-settings-save');
    expect([prop(s.field('open_drawer_on_sale'), 'checked'), prop(s.field('receipt_copies'), 'value'), prop(save, 'disabled')]).toEqual([true, 3, false]);
    expect(s.inDoc('printing-settings-saved')).toBeNull();
    // What was sent is the server's now: someone else's change repaints it; the copies stay as typed.
    await s.result(OP, { ...FACTORY, open_drawer_on_sale: false }, {}, 2);
    expect([prop(s.field('open_drawer_on_sale'), 'checked'), prop(s.field('receipt_copies'), 'value')]).toEqual([false, 3]);
    s.answer(200, { ...FACTORY, receipt_copies: 3 });
    await click(save);
    expect(s.sent().map((call) => call.body)).toEqual([{ open_drawer_on_sale: true }, { receipt_copies: 3 }]);
  });
});
