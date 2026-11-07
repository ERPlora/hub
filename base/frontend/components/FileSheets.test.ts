// Files › the preview of a table (hub#578, BASE-F74): a CSV, a TSV or each sheet of a spreadsheet, drawn as a table
// whose first row is the header. A spreadsheet with several sheets shows one tab per sheet, as Excel does; each one
// its first 500 rows, saying when it has more; an empty one says so.
import { describe, expect, it } from 'vitest';

import { flush, mountBase } from '../__tests__/mount-base';
import FileSheets from './FileSheets.vue';

type Sheets = { name: string; rows: string[][]; cut: boolean }[];

async function sheets(value: Sheets, locale: 'en' | 'es' = 'en') {
  const m = await mountBase(FileSheets, { props: { sheets: value }, locale });
  await flush();
  return m.wrapper;
}

const cells = (root: Element) => [...root.querySelectorAll('[data-testid="file-preview-table"] th, [data-testid="file-preview-table"] td')].map((cell) => cell.textContent);

describe('FileSheets', () => {
  it('draws one sheet as a table, its first row the header, without tabs', async () => {
    const wrapper = await sheets([{ name: 'ventas.csv', rows: [['producto', 'precio'], ['Café, solo', '1.20']], cut: false }]);
    expect(wrapper.find('[data-testid="file-preview-sheet-tabs"]').exists()).toBe(false);
    expect(wrapper.findAll('th').map((cell) => cell.text())).toEqual(['producto', 'precio']);
    expect(cells(wrapper.element)).toEqual(['producto', 'precio', 'Café, solo', '1.20']);
    expect(wrapper.find('[data-testid="file-preview-cut"]').exists()).toBe(false);
  });

  it('shows a tab per sheet when there are several, and the one picked', async () => {
    const wrapper = await sheets([
      { name: 'Ventas', rows: [['Producto'], ['Café']], cut: false },
      { name: 'Notas', rows: [['Cerrar la caja']], cut: false },
    ]);
    const tabs = wrapper.find('[data-testid="file-preview-sheet-tabs"]');
    expect(tabs.findAll('[data-testid="file-preview-sheet-tab"]').map((tab) => tab.text())).toEqual(['Ventas', 'Notas']);
    expect(cells(wrapper.element)).toEqual(['Producto', 'Café']);
    tabs.element.dispatchEvent(new CustomEvent('ionChange', { detail: { value: '1' } }));
    await flush();
    expect(cells(wrapper.element)).toEqual(['Cerrar la caja']);
  });

  it('names the tabs for a screen reader, in the person’s language', async () => {
    const two: Sheets = [
      { name: 'A', rows: [['a']], cut: false },
      { name: 'B', rows: [['b']], cut: false },
    ];
    expect((await sheets(two, 'es')).find('[data-testid="file-preview-sheet-tabs"]').attributes('aria-label')).toBe('Hojas');
    expect((await sheets(two)).find('[data-testid="file-preview-sheet-tabs"]').attributes('aria-label')).toBe('Sheets');
  });

  it('says when a sheet shows only its first rows', async () => {
    const wrapper = await sheets([{ name: 'x', rows: [['a']], cut: true }], 'es');
    expect(wrapper.find('[data-testid="file-preview-cut"]').text()).toBe('Mostrando las primeras 500 filas. Descarga el archivo para verlas todas.');
  });

  it('an empty sheet says so', async () => {
    expect((await sheets([{ name: 'x', rows: [], cut: false }], 'es')).find('[data-testid="file-preview-sheet-empty"]').text()).toBe('Esta hoja está vacía.');
    expect((await sheets([{ name: 'x', rows: [], cut: false }])).find('[data-testid="file-preview-sheet-empty"]').text()).toBe('This sheet is empty.');
  });
});
