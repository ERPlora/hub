// The CSV buttons of an inventory list (the old table's «Import CSV» / «Export CSV», WORKBOOK
// INVENTORY-F09/F10/F11), each shown only to whoever may use it. Import picks a file and hands the
// page its text, decoded as Excel saves it (UTF-8 with or without BOM, or Windows-1252); export asks
// the page to export. Until DataTable has its own (UI-REQUESTS.md) they go in its `toolbar` slot.
import { describe, expect, it } from 'vitest';

import { flush, mountInventory } from '../__tests__/mount-inventory';
import CsvButtons from './CsvButtons.vue';

async function setup(props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  const m = await mountInventory(CsvButtons, { props: { importable: true, exportable: true, testid: 'list', ...props }, locale });
  const testid = (id: string) => m.wrapper.find(`[data-testid="${id}"]`);
  return { ...m, testid };
}

describe('CsvButtons', () => {
  it('offers import (a CSV file input) and export, named for screen readers', async () => {
    const s = await setup();
    expect(s.testid('list-csv-import-button').attributes('aria-label')).toBe('Import CSV');
    expect(s.testid('list-csv-export').attributes('aria-label')).toBe('Export CSV');
    const input = s.testid('list-csv-import');
    expect([input.attributes('type'), input.attributes('accept')]).toEqual(['file', '.csv,text/csv']);
  });

  it('shows only what the person may do', async () => {
    const s = await setup({ importable: false });
    expect(s.testid('list-csv-import').exists()).toBe(false);
    expect(s.testid('list-csv-export').exists()).toBe(true);
    const e = await setup({ exportable: false });
    expect(e.testid('list-csv-export').exists()).toBe(false);
  });

  it('hands the page the text of the file picked, then forgets the file', async () => {
    const s = await setup();
    const input = s.testid('list-csv-import').element as HTMLInputElement;
    const file = new File([new Uint8Array([0xef, 0xbb, 0xbf, 0x4e, 0x3b, 0x53, 0x0a, 0x43, 0x61, 0x66, 0xc3, 0xa9])], 'menu.csv', { type: 'text/csv' });
    Object.defineProperty(input, 'files', { value: [file], configurable: true });
    input.dispatchEvent(new Event('change'));
    await flush();
    expect(s.wrapper.emitted('import')).toEqual([['N;S\nCafé']]);
  });

  it('export asks the page to export', async () => {
    const s = await setup();
    await s.testid('list-csv-export').trigger('click');
    expect(s.wrapper.emitted('export')).toHaveLength(1);
  });

  it('speaks Spanish', async () => {
    const s = await setup({}, 'es');
    expect(s.testid('list-csv-import-button').attributes('aria-label')).toBe('Importar CSV');
    expect(s.testid('list-csv-export').attributes('aria-label')).toBe('Exportar CSV');
  });
});
