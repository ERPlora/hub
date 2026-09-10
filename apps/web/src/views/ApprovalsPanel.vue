<!--
  ApprovalsPanel — the PIN approval record (People › Approvals), hub#512; paged since hub#884.

  The runtime has written a receipt for every **spent** step-up approval since ADR-0265 (system
  table `_elevation_audit`, system migration v26), and nothing in the product could read it: the
  only answer to «who authorised that refund on Tuesday» was a SQL session against the customer's
  own database — which, for a hub living in Hetzner with its own database (ADR-0201), means ERPlora
  support reading a business's data to answer a question its owner should be able to look up alone.

  The read is SERVER-SIDE (hub#884): the audit grows forever by design, so the panel holds one page
  and the pager, the sort, the search and every filter — the date range above all — re-ask the
  runtime through the SDK's list controller. Filtering in the client only worked while the whole
  trail was in memory, which was exactly the bug.

  Why it lives in People and not in Settings: the row IS two people. It is the same subsystem as the
  rest of this screen (`hub_user`, `crates/runtime/src/hub_users.rs`), it carries the same admin gate
  as the API keys tab, and it opens no new word in the chrome (ADR-0254) — it is one more tab of a
  page that already exists.

  What it reflects, and does not re-decide:
    - the ORDER is the query's (`created_at DESC` by default; the header click flips it there);
    - the NAMES come resolved by the query's LEFT JOIN; a deleted person leaves an empty name and
      the row stays, because losing the row would lose the audit;
    - the GATE is the runtime's (`hub.administer`). Hiding the tab is not the guard: the panel does
      not ask at all when the session is not an administrator.

  Reuses:
    - ok-data-table (OutfitKit) in `server-side` mode for the list;
    - ListController (module-sdk) via lib/approvals.ts — the same state machine every CRUD uses;
    - ok-inline-feedback for a failed read (same pattern as RolesPanel);
    - lib/session.ts + lib/data-table-labels.ts.
-->
<template>
  <div class="fill">
    <div v-if="!ready && loading" class="table-loading">
      <ion-spinner name="crescent" />
    </div>

    <template v-else>
      <!-- What the record is and how long it is kept. An audit trail nobody understands is one
           nobody consults, and «is this deleted at some point?» is the first thing its reader asks. -->
      <span class="intro">{{ t('approvals.intro') }}</span>

      <ok-inline-feedback
        v-if="loadError"
        class="feedback"
        tone="warning"
        icon="cloud-offline-outline"
        :heading="t('approvals.loadError')"
      >
        <ion-button slot="actions" size="small" fill="outline" @click="load">
          {{ t('employees.retry') }}
        </ion-button>
      </ok-inline-feedback>

      <!-- `server-side`: the table renders the page it is given and EMITS pager/sort/search/filter
           changes instead of slicing rows in memory — the rows in memory are only one page. -->
      <ok-data-table
        ref="table"
        fill
        server-side
        searchable
        :search-placeholder="t('approvals.search')"
        :empty-message="t('approvals.empty')"
        views
        csv
        csv-name="approvals"
        column-picker
      ></ok-data-table>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { IonButton, IonSpinner } from '@ionic/vue';
import { dataTableLabels } from '../lib/data-table-labels';
import { createApprovalsController, type Approval, type ApprovalsController } from '../lib/approvals';
import { getClient } from '../lib/runtime';
import { isAdmin } from '../lib/session';
import { formatDateTime } from '../lib/format-datetime';

const { t, locale } = useI18n();

type Row = Record<string, unknown>;
interface DataTableColumn {
  key: string;
  header: string;
  align?: 'left' | 'right' | 'center';
  filterable?: boolean;
  filterType?: 'text' | 'select' | 'number' | 'date' | 'range' | 'daterange';
  sortable?: boolean;
  hidden?: boolean;
  format?: (row: Row) => string;
  render?: (row: Row) => Node | string;
}
type DataTableElement = HTMLElement & {
  labels: Record<string, string>;
  columns: DataTableColumn[];
  rows: Row[];
  total: number;
  page: number;
  pageSize: number;
  sort?: string;
  sortDir: 'asc' | 'desc';
};

const loading = ref(true);
const loadError = ref(false);
/** First answer arrived: from here on the table stays mounted (a remount would drop its state). */
const ready = ref(false);
const rows = ref<Approval[]>([]);

/**
 * The screen's column keys (camelCase, the parsed row shape) → the QUERY's columns (snake_case,
 * what the runtime's list engine filters and sorts by). Only what the query answers is offered.
 */
const SERVER_COLUMNS: Record<string, string> = {
  createdAt: 'created_at',
  command: 'command',
  permission: 'permission',
};

/**
 * One controller for the whole conversation with the runtime: page, size, sort, search and filters
 * live in it, and every change re-asks `hub.approvals.list` for ONE page. Created lazily so a
 * non-admin session never even builds the client path.
 */
let controller: ApprovalsController | null = null;
function ctl(): ApprovalsController {
  controller ??= createApprovalsController(getClient(), syncFromController);
  return controller;
}

/** The controller mutates itself and calls back; this copies its state into Vue's reactivity. */
function syncFromController(): void {
  const c = controller;
  if (!c) return;
  rows.value = [...c.rows];
  loading.value = c.loading;
  loadError.value = !!c.error;
  if (!c.loading) ready.value = true;
  // The table exists only after `ready`; when it appears, the `watch` below re-binds everything.
  bindTable(table.value);
}

/**
 * The instant, in the reader's locale, with the TIME: a shift can hold several refunds and «that
 * Tuesday» is not an answer without the hour.
 *
 * It goes in `render` and not in `format` on purpose — a localized string as the column's VALUE
 * would leak into whatever sorts or exports by value. The raw RFC 3339 instant stays the value.
 */
function whenCell(row: Row): Node {
  const span = document.createElement('span');
  const raw = String(row.createdAt ?? '');
  span.textContent =
    formatDateTime(raw, {
      locale: locale.value,
      day: '2-digit',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    }) ?? raw;
  return span;
}

/**
 * The person, or the fact that they are gone. The query keeps the row of somebody who no longer
 * exists in `hub_user` and leaves the name empty; a blank cell would read as a broken screen
 * instead of as what it is — their id is still on the row, and travels in the export.
 */
function personOf(key: 'createdByName' | 'approvedByName'): (row: Row) => string {
  return (row) => String(row[key] ?? '') || t('approvals.userGone');
}

const columns = computed<DataTableColumn[]>(() => [
  {
    key: 'createdAt',
    header: t('approvals.colWhen'),
    filterable: true,
    filterType: 'daterange',
    // The one sortable column, because it is the one the QUERY sorts by (its whitelist).
    sortable: true,
    render: whenCell,
  },
  // Who approved first: the record exists to answer «who authorised this», and the answer should be
  // the first column the eye lands on after the date.
  { key: 'approvedByName', header: t('approvals.colApprovedBy'), format: personOf('approvedByName') },
  { key: 'createdByName', header: t('approvals.colRequestedBy'), format: personOf('createdByName') },
  { key: 'command', header: t('approvals.colAction'), filterable: true, filterType: 'select' },
  { key: 'permission', header: t('approvals.colLevel'), filterable: true, filterType: 'select' },
  // Out of sight, in the CSV and in the column picker: a hash and two uuids are noise to the owner
  // and decisive to whoever has to prove WHICH €4 ticket was voided, or tell two people who share a
  // name apart. The export carries every column, hidden or not.
  { key: 'payloadFingerprint', header: t('approvals.colFingerprint'), hidden: true },
  { key: 'createdBy', header: t('approvals.colRequestedById'), hidden: true },
  { key: 'approvedBy', header: t('approvals.colApprovedById'), hidden: true },
]);

/**
 * Loads the current page. The two failure modes are kept apart on purpose: `loadError` means we
 * could not ask, an empty `rows` means the hub answered «nothing». Collapsing them would let a
 * broken read pass for a business where no manager ever approved anything.
 */
async function load(): Promise<void> {
  // The runtime gates the query on `hub.administer` — who approved what is information about the
  // staff. Not asking is the guard; the hidden tab is only the tidy version of it.
  if (!isAdmin.value) {
    rows.value = [];
    loadError.value = false;
    loading.value = false;
    ready.value = true;
    return;
  }
  await ctl().load();
}

// ── ok-data-table wiring (camelCase CustomEvents via addEventListener; pattern of EmployeesPage) ──

/** The `to` edge of a day, inclusive: the runtime compares RFC 3339 TEXT, so a bare `2026-08-11`
 *  would exclude every approval given after that day's midnight — i.e. the whole day asked for. */
function inclusiveTo(value: string): string {
  return /^\d{4}-\d{2}-\d{2}$/.test(value) ? `${value}T23:59:59` : value;
}

/** A table filter (screen column key + value) becomes the QUERY's filter, or is dropped. */
function applyFilter(col: string, value: unknown): void {
  const server = SERVER_COLUMNS[col];
  if (!server) return;
  if (server === 'created_at' && value !== null && typeof value === 'object') {
    const range = value as { from?: string; to?: string };
    const mapped: Record<string, string> = {};
    if (range.from !== undefined) mapped.from = range.from;
    if (range.to !== undefined) mapped.to = range.to === '' ? '' : inclusiveTo(String(range.to));
    ctl().setFilter(server, mapped);
    return;
  }
  // Selects are single-value on this screen; anything else exact-matches or clears ('' clears).
  ctl().setFilter(server, Array.isArray(value) ? (value[0] ?? '') : value);
}

const handlers: Record<string, (detail: unknown) => void> = {
  pageChange: (d) => ctl().setPage(Number(d)),
  pageSizeChange: (d) => ctl().setPageSize(Number(d)),
  // Only `created_at` is sortable, so whatever key arrives, the QUERY sorts by its one column.
  sortChange: (d) => ctl().setSort('created_at', (d as { dir: 'asc' | 'desc' }).dir),
  searchChange: (d) => ctl().setSearch(String(d ?? '')),
  filterChange: (d) => {
    const detail = d as { col?: string; value?: unknown; filters?: Record<string, unknown> };
    if (detail.filters) {
      // Bulk shape (the drawer's Apply): re-state every offered filter, absent = cleared.
      for (const col of Object.keys(SERVER_COLUMNS)) applyFilter(col, detail.filters[col] ?? '');
      return;
    }
    if (detail.col) applyFilter(detail.col, detail.value);
  },
};

const table = ref<DataTableElement | null>(null);
const wired = new WeakSet<DataTableElement>();

/** Typed data goes by JS PROPERTY, never by attribute (OutfitKit rule). */
function bindTable(element: DataTableElement | null): void {
  if (!element) return;
  element.labels = dataTableLabels(locale.value);
  element.columns = columns.value;
  element.rows = rows.value as unknown as Row[];
  // Read-only here: binding must never CREATE the controller — a non-admin session renders an
  // empty table and the guard is precisely that the runtime is never asked.
  const c = controller;
  element.total = c?.total ?? 0;
  element.page = c?.state.page ?? 0;
  element.pageSize = c?.state.pageSize ?? 10;
  element.sort = 'createdAt';
  element.sortDir = c?.state.dir ?? 'desc';
  if (!wired.has(element)) {
    wired.add(element);
    for (const [type, handler] of Object.entries(handlers)) {
      element.addEventListener(type, (e) => {
        // Same guard as `load()`: a non-admin session never asks, whatever the table emits.
        if (isAdmin.value) handler((e as CustomEvent).detail);
      });
    }
  }
}

watch(table, (element) => bindTable(element));
// The cells are painted with `t()` and formatted with the locale, so a language change has to
// rebuild the columns — otherwise the headers and the dates stay in the previous language.
watch([locale, columns], () => bindTable(table.value));

onMounted(() => {
  void load();
});

defineExpose({ columns, rows, loadError, load });
</script>

<style scoped>
.fill {
  height: 100%;
  min-height: var(--ok-work-surface-min);
}

.table-loading {
  display: flex;
  justify-content: center;
  padding: 2.5rem 0;
}

.feedback {
  margin-bottom: 0.75rem;
}

.intro {
  display: block;
  margin-bottom: 0.75rem;
  font-size: 0.875rem;
  color: var(--ion-color-medium);
}
</style>
