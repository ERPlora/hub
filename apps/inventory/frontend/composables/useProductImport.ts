// The product import (WORKBOOK INVENTORY-F09), with the server as the authority on every row:
//   1. `start`: the file is read, each column gets its field guessed (`setMapping` corrects it) and
//      the whole file is rehearsed on the server (`dry_run`) before anything is created. The tax
//      category is decided in step 2, so the rehearsal checks the rest of each row with a category
//      Taxes has;
//   2. `confirm`: each fiscal text of the file is read by Taxes (`tax.alias.resolve`: key, name in any
//      language or learned alias). Texts it does not know, and rows without one, are asked for
//      (`unresolved`, `setChoice`, `confirmTax`): pick a category (the text is learned), create one
//      (and learn the text) or skip (those rows fail «The tax category is missing»). What Taxes
//      cannot save is said in the report and its rows fail with that reason;
//   3. the rows go in calls of at most 100 (`progress`; `stop` ends after the call in flight); a SKU
//      repeated anywhere in the file fails on the page and is never sent, since the server only sees
//      one call at a time;
//   4. `report`: one «Import result» for the whole file.
import { useLiveClient } from '@erplora/ui/sdk';
import { computed, ref, shallowRef } from 'vue';

import { type CsvTable, parseCsv } from '../lib/csv';
import { guessMapping, mapRow, PRODUCT_IMPORT_ALIASES, PRODUCT_IMPORT_REQUIRED, type ProductImportField } from '../lib/import-mapping';
import { addReport, chunk, emptyReport, type FailedRow, failRows, type ImportReport } from '../lib/import-report';
import type { ProductImportRowIn } from '../operations';
import { useT } from './useT';

export type ImportPhase = 'idle' | 'preview' | 'tax' | 'running' | 'done';

export interface TaxChoice {
  mode: 'pick' | 'create' | 'skip';
  /** The category picked. */
  key: string;
  /** The category to create. */
  newKey: string;
  newName: string;
}

/** A fiscal text Taxes does not know; `''` stands for the rows that bring none. */
export interface UnresolvedText {
  text: string;
  choice: TaxChoice;
}

export interface Rehearsal {
  status: 'idle' | 'checking' | 'ready' | 'error';
  report: ImportReport | null;
  error: string;
}

const message = (failure: unknown): string => (failure instanceof Error ? failure.message : String(failure));

export function useProductImport() {
  const client = useLiveClient();
  const { t } = useT();

  const phase = ref<ImportPhase>('idle');
  const table = shallowRef<CsvTable | null>(null);
  const mapping = ref<(ProductImportField | '')[]>([]);
  const rehearsal = ref<Rehearsal>({ status: 'idle', report: null, error: '' });
  const unresolved = ref<UnresolvedText[]>([]);
  const progress = ref<{ done: number; total: number } | null>(null);
  const report = ref<ImportReport | null>(null);
  /** Why the file could not even be previewed. */
  const error = ref('');
  /** Texts are being resolved, Taxes taught or rows sent: a second «Import» or «Confirm» is ignored. */
  const busy = ref(false);

  const requiredMapped = computed(() => PRODUCT_IMPORT_REQUIRED.every((field) => mapping.value.includes(field)));

  /** Fiscal text → the key decided for it. */
  let keys = new Map<string, string>();
  /** A rehearsal superseded by a newer one (a column changed) is dropped when it answers. */
  let rehearsalSeq = 0;
  let stopping = false;
  let placeholder: string | undefined;

  const fiscalText = (cells: Partial<Record<ProductImportField, string>>): string => (cells.tax_category_key ?? '').trim();

  /** The rows as the API takes them; a SKU seen before in the file fails here, never sent. */
  function rowsToSend(taxKey: (text: string) => string): { send: Array<ProductImportRowIn & { text: string }>; local: FailedRow[] } {
    const seen = new Set<string>();
    const send: Array<ProductImportRowIn & { text: string }> = [];
    const local: FailedRow[] = [];
    for (const row of table.value?.rows ?? []) {
      const cells = mapRow(row.values, mapping.value);
      const sku = (cells.sku ?? '').trim();
      if (sku && seen.has(sku)) {
        local.push({ line: row.line, key: sku, reason: t('inventory.import.duplicateInFile') });
        continue;
      }
      if (sku) seen.add(sku);
      const text = fiscalText(cells);
      send.push({ ...cells, line: row.line, tax_category_key: taxKey(text), text });
    }
    return { send, local };
  }

  /**
   * Calls `bulk_create` per 100 rows; a call that fails fails its rows with the reason. A rehearsal
   * stops as soon as it is `superseded` (a column changed): its remaining calls would be wasted.
   */
  async function callInChunks(
    rows: Array<ProductImportRowIn & { text: string }>,
    dryRun: boolean,
    start: ImportReport,
    superseded: () => boolean = () => false,
  ) {
    let done = start;
    let cancelled = false;
    for (const part of chunk(rows)) {
      if (superseded()) break;
      if (!dryRun && stopping) {
        cancelled = true;
        break;
      }
      try {
        // `text` is the page's bookkeeping (the fiscal text read from the file), not part of the row.
        const payload = part.map((row) => {
          const sent: Partial<typeof row> = { ...row };
          delete sent.text;
          return sent as ProductImportRowIn;
        });
        done = addReport(done, await client.api.call('inventory.product.bulk_create', { rows: payload, ...(dryRun ? { dry_run: true } : {}) }));
      } catch (failure) {
        const reason = t('inventory.import.chunkFailed', { reason: message(failure) });
        done = failRows(done, part.map((row) => ({ line: row.line, key: (row.sku ?? '').trim(), reason })));
      }
      if (progress.value) progress.value = { ...progress.value, done: progress.value.done + part.length };
    }
    return { report: done, cancelled };
  }

  /** A category Taxes has, for the rehearsal only (`''` when there is none: every row then fails). */
  async function placeholderKey(): Promise<string> {
    if (placeholder === undefined) {
      const page = await client.api.call('tax.category.list', { limit: 1 });
      placeholder = page.rows[0]?.key ?? '';
    }
    return placeholder;
  }

  async function rehearse(): Promise<void> {
    const mine = ++rehearsalSeq;
    if (!requiredMapped.value) {
      rehearsal.value = { status: 'idle', report: null, error: '' };
      return;
    }
    rehearsal.value = { status: 'checking', report: rehearsal.value.report, error: '' };
    try {
      const key = await placeholderKey();
      const { send, local } = rowsToSend(() => key);
      const { report: done } = await callInChunks(send, true, failRows(emptyReport(), local), () => mine !== rehearsalSeq);
      if (mine === rehearsalSeq) rehearsal.value = { status: 'ready', report: done, error: '' };
    } catch (failure) {
      if (mine === rehearsalSeq) rehearsal.value = { status: 'error', report: null, error: message(failure) };
    }
  }

  function reset(): void {
    rehearsalSeq++;
    phase.value = 'idle';
    table.value = null;
    mapping.value = [];
    rehearsal.value = { status: 'idle', report: null, error: '' };
    unresolved.value = [];
    progress.value = null;
    keys = new Map();
  }

  async function start(text: string): Promise<void> {
    reset();
    error.value = '';
    report.value = null;
    const parsed = parseCsv(text);
    if (parsed.rows.length === 0) {
      error.value = t('inventory.import.emptyFile');
      return;
    }
    table.value = parsed;
    mapping.value = guessMapping(parsed.headers, PRODUCT_IMPORT_ALIASES);
    phase.value = 'preview';
    await rehearse();
  }

  /** Column `index` goes to `field` (`''`: not imported); a field leaves the column that had it. */
  function setMapping(index: number, field: ProductImportField | ''): void {
    const next = mapping.value.map((current) => (field && current === field ? '' : current));
    next[index] = field;
    mapping.value = next;
    void rehearse();
  }

  function cancel(): void {
    reset();
  }

  async function confirm(): Promise<void> {
    if (busy.value || !requiredMapped.value || !table.value) return;
    busy.value = true;
    try {
      await resolveTexts();
    } finally {
      busy.value = false;
    }
  }

  async function resolveTexts(): Promise<void> {
    const { send } = rowsToSend(() => '');
    const texts = [...new Set(send.map((row) => row.text).filter(Boolean))];
    keys = new Map();
    const unknown: string[] = [];
    for (const text of texts) {
      try {
        const found = await client.api.call('tax.alias.resolve', { text });
        if (found.tax_category_key) keys.set(text, found.tax_category_key);
        else unknown.push(text);
      } catch {
        unknown.push(text);
      }
    }
    if (send.some((row) => !row.text)) unknown.push('');
    if (unknown.length > 0) {
      unresolved.value = unknown.map((text) => ({ text, choice: { mode: 'pick', key: '', newKey: '', newName: text } }));
      phase.value = 'tax';
      return;
    }
    await run([], new Map());
  }

  function setChoice(text: string, patch: Partial<TaxChoice>): void {
    unresolved.value = unresolved.value.map((item) => (item.text === text ? { ...item, choice: { ...item.choice, ...patch } } : item));
  }

  /** Applies the decisions in Taxes (learned texts, new categories), then imports. */
  async function confirmTax(): Promise<void> {
    if (busy.value || phase.value !== 'tax') return;
    busy.value = true;
    try {
      await applyDecisions();
    } finally {
      busy.value = false;
    }
  }

  async function applyDecisions(): Promise<void> {
    const notes: string[] = [];
    const failedTexts = new Map<string, string>();
    for (const { text, choice } of unresolved.value) {
      try {
        if (choice.mode === 'pick' && choice.key) {
          if (text) await client.api.call('tax.alias.create', { alias: text, tax_category_key: choice.key });
          keys.set(text, choice.key);
        } else if (choice.mode === 'create' && choice.newKey.trim()) {
          const key = choice.newKey.trim();
          await client.api.call('tax.category.create', { key, name: choice.newName.trim() || key });
          if (text) await client.api.call('tax.alias.create', { alias: text, tax_category_key: key });
          keys.set(text, key);
        }
      } catch (failure) {
        const reason = t('inventory.import.taxSaveFailed', { text: text || t('inventory.import.taxMissing'), reason: message(failure) });
        notes.push(reason);
        failedTexts.set(text, reason);
      }
    }
    await run(notes, failedTexts);
  }

  async function run(notes: string[], failedTexts: Map<string, string>): Promise<void> {
    phase.value = 'running';
    stopping = false;
    const { send, local } = rowsToSend((text) => keys.get(text) ?? '');
    const blocked = send.filter((row) => failedTexts.has(row.text));
    const ready = send.filter((row) => !failedTexts.has(row.text));
    const start = failRows(
      failRows(emptyReport(), local),
      blocked.map((row) => ({ line: row.line, key: (row.sku ?? '').trim(), reason: failedTexts.get(row.text) ?? '' })),
    );
    progress.value = { done: 0, total: ready.length };
    const { report: done, cancelled } = await callInChunks(ready, false, start);
    progress.value = null;
    // «Rows» are the file's: a stopped import leaves the rest untouched, and the note says so.
    report.value = { ...done, total: table.value?.rows.length ?? done.total, cancelled, notes };
    unresolved.value = [];
    phase.value = 'done';
  }

  function stop(): void {
    stopping = true;
  }

  return { phase, table, mapping, requiredMapped, rehearsal, unresolved, progress, report, error, busy, start, setMapping, cancel, confirm, setChoice, confirmTax, stop };
}
