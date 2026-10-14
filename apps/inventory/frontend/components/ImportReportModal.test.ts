// «Import result» (WORKBOOK INVENTORY-F09/F10), the old report modal: «Rows», «Created», «Skipped
// (already existed)», «Failed», one line per failed row («Line N · SKU — reason»), «Copy report», and
// the note of an import stopped halfway or of what Taxes could not save.
import { afterEach, describe, expect, it, vi } from 'vitest';

import { flush, mountInventory } from '../__tests__/mount-inventory';
import { emptyReport, type ImportReport } from '../lib/import-report';
import ImportReportModal from './ImportReportModal.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

afterEach(() => {
  document.body.innerHTML = '';
});

const REPORT: ImportReport = {
  ...emptyReport(),
  total: 5,
  created: 2,
  skipped: 1,
  failed: [
    { line: 3, key: 'TEA-1', reason: 'Price is not a number' },
    { line: 6, key: '', reason: 'Name or SKU missing' },
  ],
};

async function setup(report: ImportReport, locale: 'en' | 'es' = 'en') {
  const m = await mountInventory(ImportReportModal, { props: { open: true, report }, locale, attach: true });
  await flush();
  const testid = (id: string) => document.querySelector<HTMLElement>(`[data-testid="${id}"]`);
  return { ...m, testid };
}

describe('ImportReportModal', () => {
  it('counts rows, created, skipped and failed, and lists each failed row with its line', async () => {
    const s = await setup(REPORT);
    expect(s.testid('inventory-import-report')?.getAttribute('aria-label')).toBe('Import result');
    const counts = [...document.querySelectorAll('[data-testid^="inventory-import-report-count-"]')].map((el) => [
      el.getAttribute('data-testid'),
      `${el.querySelector('ion-label')?.textContent?.trim()} ${el.querySelector('ion-note')?.textContent?.trim()}`,
    ]);
    expect(counts).toEqual([
      ['inventory-import-report-count-rows', 'Rows 5'],
      ['inventory-import-report-count-created', 'Created 2'],
      ['inventory-import-report-count-skipped', 'Skipped (already existed) 1'],
      ['inventory-import-report-count-failed', 'Failed 2'],
    ]);
    expect([...document.querySelectorAll('[data-testid="inventory-import-report-failed-line"]')].map((el) => el.textContent?.trim())).toEqual([
      'Line 3 · TEA-1 — Price is not a number',
      'Line 6 · — — Name or SKU missing',
    ]);
  });

  it('«Copy report» puts the report on the clipboard', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal('navigator', { ...navigator, clipboard: { writeText } });
    const s = await setup(REPORT);
    s.testid('inventory-import-report-copy')!.click();
    await flush();
    expect(writeText).toHaveBeenCalledOnce();
    expect(writeText.mock.calls[0][0]).toContain('Line 3 · TEA-1 — Price is not a number');
    vi.unstubAllGlobals();
  });

  it('a stopped import says the rest of the file was left untouched; notes are shown', async () => {
    const s = await setup({ ...REPORT, cancelled: true, notes: ['Taxes could not save «IVA 7»: boom'] });
    expect(s.testid('inventory-import-report-cancelled')?.textContent).toContain('The import was stopped halfway.');
    expect(s.testid('inventory-import-report-note')?.textContent).toContain('Taxes could not save «IVA 7»: boom');
  });

  it('without failures there is nothing to copy', async () => {
    const s = await setup({ ...emptyReport(), total: 2, created: 2 });
    expect(s.testid('inventory-import-report-copy')).toBeNull();
    expect(s.testid('inventory-import-report-failed-line')).toBeNull();
  });

  it('«Close» closes it', async () => {
    const s = await setup(REPORT);
    s.testid('inventory-import-report-close-button')!.click();
    await flush();
    expect(s.wrapper.emitted('update:open')).toEqual([[false]]);
  });

  it('speaks Spanish', async () => {
    const s = await setup(REPORT, 'es');
    expect(s.testid('inventory-import-report')?.getAttribute('aria-label')).toBe('Resultado de la importación');
    expect(s.testid('inventory-import-report-count-skipped')?.querySelector('ion-label')?.textContent?.trim()).toBe('Omitidas (ya existían)');
  });
});
