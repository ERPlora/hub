// «New numbering series» and «Edit series <code>» (INVOICE-F12, F13; the old panel of the Series table):
// Code, Name, Invoice type, Year, Prefix, Number format, Next number, Active and Default series, with the
// hints of the old screen. Editing, code, type and year are locked, and once the series numbered a document
// so are prefix, format and next number (it says why); the next number it will hand out is the server's.
// Saving runs `invoice.series.create` or `invoice.series.update` (only what changed), says so and closes; a
// refusal stays in the window, under its field when it is one.
import { toastSuccess } from '@erplora/ui/shell';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { click, flush, ionValue, mountInvoice } from '../__tests__/mount-invoice';
import type { SeriesOut } from '../operations';
import SeriesFormModal from './SeriesFormModal.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});
vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...((await importOriginal()) as object),
  toastSuccess: vi.fn(() => Promise.resolve()),
}));
beforeEach(() => vi.mocked(toastSuccess).mockClear());

const prop = (el: Element | null, name: string): unknown => (el as unknown as Record<string, unknown>)[name];

/** An ion-toggle changed, as Ionic says it (`ionChange` with `checked`). */
async function toggle(el: Element | null, checked: boolean): Promise<void> {
  if (!el) throw new Error('no toggle');
  (el as HTMLElement & { checked?: boolean }).checked = checked;
  el.dispatchEvent(new CustomEvent('ionChange', { detail: { checked }, bubbles: true }));
  await flush();
}

const SERIES: SeriesOut = {
  id: 's1',
  code: 'FACT',
  name: 'Invoices',
  display_name: 'Invoices',
  invoice_type: 'F1',
  year: 2026,
  prefix: 'FACT',
  format: '',
  current_number: 0,
  next_number: 'FACT-2026-000001',
  format_locked: false,
  is_active: true,
  is_default: false,
};

async function setup(series: SeriesOut | null = null, locale: 'en' | 'es' = 'en') {
  const m = await mountInvoice(SeriesFormModal, { props: { open: true, series, year: 2026 }, locale });
  const field = (key: string) => m.inDoc(`invoice-series-${key}`);
  const submit = () => click(m.inDoc('invoice-series-form-submit'));
  return { ...m, field, submit };
}

describe('SeriesFormModal: creating', () => {
  it('is «New numbering series» with the fields and hints of the old panel, this year and number 1', async () => {
    const s = await setup();
    expect(s.inDoc('invoice-series-form')?.getAttribute('aria-label')).toBe('New numbering series');
    expect(['code', 'name', 'type', 'year', 'prefix', 'format', 'next-number'].map((key) => prop(s.field(key), 'label'))).toEqual([
      'Code',
      'Name',
      'Invoice type',
      'Year',
      'Prefix',
      'Number format',
      'Next number',
    ]);
    expect([prop(s.field('type'), 'value'), prop(s.field('year'), 'value'), prop(s.field('next-number'), 'value')]).toEqual(['F1', '2026', '1']);
    expect(s.inDoc('invoice-series-format-hint')?.textContent).toContain('{seq:01d}…{seq:09d}');
    // The year and a sequence are required, in plain letters (VeriFactu's NumSerieFactura).
    expect(s.inDoc('invoice-series-format-hint')?.textContent).toContain('The year and a sequence are required');
    expect(s.inDoc('invoice-series-form-submit')?.textContent?.trim()).toBe('Create series');
  });

  it('creates it with what was typed, says so and closes', async () => {
    const s = await setup();
    await ionValue(s.field('code'), 'shop', 'ionInput');
    await ionValue(s.field('name'), 'Shop', 'ionInput');
    await ionValue(s.field('type'), 'F2');
    await ionValue(s.field('format'), 'S{seq:04d}', 'ionInput');
    await ionValue(s.field('next-number'), '120', 'ionInput');
    await toggle(s.field('default'), true);
    s.answer(201, { ...SERIES, code: 'SHOP' });
    await s.submit();
    expect(s.sent()).toEqual([
      {
        method: 'POST',
        path: '/api/invoice/series',
        query: {},
        body: { code: 'shop', name: 'Shop', invoice_type: 'F2', year: 2026, prefix: '', format: 'S{seq:04d}', next_number: 120, is_active: true, is_default: true },
      },
    ]);
    expect(toastSuccess).toHaveBeenCalledWith('Series SHOP created');
    expect(s.wrapper.emitted('update:open')?.at(-1)).toEqual([false]);
  });

  it('a refusal stays in the window, under its field', async () => {
    const s = await setup();
    await ionValue(s.field('code'), 'FACT', 'ionInput');
    s.answer(409, { error: { code: 'invoice.series_exists', message: 'There is already a series with that code that year.', fields: { code: 'There is already a series with that code that year.' } } });
    await s.submit();
    expect(prop(s.field('code'), 'errorText')).toBe('There is already a series with that code that year.');
    expect(s.wrapper.emitted('update:open')).toBeUndefined();
  });
});

describe('SeriesFormModal: editing', () => {
  it('is «Edit series <code>» with code, type and year locked and the next number the server will hand out', async () => {
    const s = await setup(SERIES);
    expect(s.inDoc('invoice-series-form')?.getAttribute('aria-label')).toBe('Edit series FACT');
    expect(['code', 'type', 'year'].map((key) => prop(s.field(key), 'disabled'))).toEqual([true, true, true]);
    expect(prop(s.field('format'), 'disabled')).toBe(false);
    expect(s.inDoc('invoice-series-preview')?.textContent).toContain('FACT-2026-000001');
    expect(s.inDoc('invoice-series-form-submit')?.textContent?.trim()).toBe('Save');
  });

  it('once it numbered a document, prefix, format and next number are locked and it says why', async () => {
    const s = await setup({ ...SERIES, current_number: 3, format_locked: true, next_number: 'FACT-2026-000004' });
    expect(['prefix', 'format', 'next-number'].map((key) => prop(s.field(key), 'disabled'))).toEqual([true, true, true]);
    expect(s.inDoc('invoice-series-format-locked')?.textContent).toContain('the number is part of the VeriFactu chain');
  });

  it('saves only what changed, says so and closes', async () => {
    const s = await setup(SERIES);
    await ionValue(s.field('name'), 'Main', 'ionInput');
    await toggle(s.field('active'), false);
    s.answer(200, { ...SERIES, name: 'Main' });
    await s.submit();
    expect(s.sent()[0]).toEqual({ method: 'POST', path: '/api/invoice/series/update', query: {}, body: { series_id: 's1', name: 'Main', is_active: false } });
    expect(toastSuccess).toHaveBeenCalledWith('Series FACT saved');
  });

  it('speaks Spanish', async () => {
    const s = await setup(SERIES, 'es');
    expect(s.inDoc('invoice-series-form')?.getAttribute('aria-label')).toBe('Editar serie FACT');
    expect(prop(s.field('format'), 'label')).toBe('Formato del número');
    expect(s.inDoc('invoice-series-form-submit')?.textContent?.trim()).toBe('Guardar');
  });
});
