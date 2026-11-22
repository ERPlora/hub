// The summary of «Import CSV» (CUSTOMER-F08): «Import: 3 rows — 2 created, 1 skipped.», each count
// in singular when it is 1, each skipped row with its reasons, the rows to review and any refused block; it stays
// on screen until «Close» or the next import.
import { InlineFeedback } from '@erplora/ui/components';
import { describe, expect, it } from 'vitest';

import { mountCustomer } from '../__tests__/mount-customer';
import type { ImportReport as Report } from '../lib/useCustomerImport';
import ImportReport from './ImportReport.vue';

const CLEAN: Report = { total: 3, created: 3, skipped: [], warnings: [], failed: [] };

async function setup(report: Report, locale: 'en' | 'es' = 'en') {
  const m = await mountCustomer(ImportReport, { props: { report }, locale });
  const banner = () => m.wrapper.findComponent(InlineFeedback);
  return { ...m, banner };
}

describe('ImportReport', () => {
  it('a clean import is a success with its summary', async () => {
    const s = await setup(CLEAN);
    expect(s.banner().props('tone')).toBe('success');
    expect(s.wrapper.get('[data-testid="customer-import-summary"]').text()).toBe('Import: 3 rows — 3 created, 0 skipped.');
  });

  it('lists each skipped row with its reasons, and the rows to review, as a warning', async () => {
    const s = await setup({
      ...CLEAN,
      created: 1,
      skipped: [{ line: 2, reasons: ['This field is required.', 'Enter a valid email.'] }],
      warnings: [{ line: 4, reasons: ['Country not recognised.'] }],
    });
    expect(s.banner().props('tone')).toBe('warning');
    expect(s.wrapper.get('[data-testid="customer-import-summary"]').text()).toBe('Import: 3 rows — 1 created, 1 skipped.');
    expect(s.wrapper.findAll('[data-testid="customer-import-skipped"] li').map((li) => li.text())).toEqual([
      'Row 2: This field is required. Enter a valid email.',
    ]);
    expect(s.wrapper.get('[data-testid="customer-import-warnings"]').text()).toContain('To review');
    expect(s.wrapper.findAll('[data-testid="customer-import-warnings"] li').map((li) => li.text())).toEqual([
      'Row 4: Country not recognised.',
    ]);
  });

  it('shows the first 20 skipped rows and «…» for the rest', async () => {
    const skipped = Array.from({ length: 25 }, (_, i) => ({ line: i + 2, reasons: ['x'] }));
    const s = await setup({ ...CLEAN, total: 25, created: 0, skipped });
    const items = s.wrapper.findAll('[data-testid="customer-import-skipped"] li').map((li) => li.text());
    expect(items).toHaveLength(21);
    expect(items.at(-1)).toBe('…');
  });

  it('a refused block makes it a danger, with its lines and reason', async () => {
    const s = await setup({ ...CLEAN, failed: [{ from: 2, to: 51, reason: 'No permission' }] });
    expect(s.banner().props('tone')).toBe('danger');
    expect(s.wrapper.get('[data-testid="customer-import-failed"]').text()).toBe('Rows 2–51 were not imported: No permission');
  });

  it('«Close» asks to drop it', async () => {
    const s = await setup(CLEAN);
    await s.wrapper.get('[data-testid="customer-import-close"]').trigger('click');
    expect(s.wrapper.emitted('close')).toHaveLength(1);
  });

  it('speaks Spanish', async () => {
    const s = await setup({ ...CLEAN, created: 2, skipped: [{ line: 2, reasons: ['Falta el nombre.'] }] }, 'es');
    expect(s.wrapper.get('[data-testid="customer-import-summary"]').text()).toBe('Importación: 3 filas — 2 creadas, 1 omitida.');
    expect(s.wrapper.get('[data-testid="customer-import-skipped"] li').text()).toBe('Fila 2: Falta el nombre.');
  });

  it.each([
    ['en', 1, 1, 0, 'Import: 1 row — 1 created, 0 skipped.'],
    ['en', 2, 0, 2, 'Import: 2 rows — 0 created, 2 skipped.'],
    ['es', 1, 1, 0, 'Importación: 1 fila — 1 creada, 0 omitidas.'],
    ['es', 1, 0, 1, 'Importación: 1 fila — 0 creadas, 1 omitida.'],
    ['es', 5, 3, 2, 'Importación: 5 filas — 3 creadas, 2 omitidas.'],
  ] as const)('says each count in singular only when it is 1 (%s: %i rows, %i created, %i skipped)', async (locale, total, created, skippedCount, summary) => {
    const skipped = Array.from({ length: skippedCount }, (_, i) => ({ line: i + 2, reasons: ['x'] }));
    const s = await setup({ ...CLEAN, total, created, skipped }, locale);
    expect(s.wrapper.get('[data-testid="customer-import-summary"]').text()).toBe(summary);
  });
});
