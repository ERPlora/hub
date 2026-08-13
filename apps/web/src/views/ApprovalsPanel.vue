<!--
  ApprovalsPanel — the PIN approval record (People › Approvals), hub#512.

  The runtime has written a receipt for every **spent** step-up approval since ADR-0265 (system
  table `_elevation_audit`, system migration v26), and nothing in the product could read it: the
  only answer to «who authorised that refund on Tuesday» was a SQL session against the customer's
  own database — which, for a hub living in Hetzner with its own database (ADR-0201), means ERPlora
  support reading a business's data to answer a question its owner should be able to look up alone.

  Why it lives in People and not in Settings: the row IS two people. It is the same subsystem as the
  rest of this screen (`hub_user`, `crates/runtime/src/hub_users.rs`), it carries the same admin gate
  as the API keys tab, and it opens no new word in the chrome (ADR-0254) — it is one more tab of a
  page that already exists.

  What it reflects, and does not re-decide:
    - the ORDER is the query's (`created_at DESC`);
    - the NAMES come resolved by the query's LEFT JOIN; a deleted person leaves an empty name and
      the row stays, because losing the row would lose the audit;
    - the GATE is the runtime's (`hub.administer`). Hiding the tab is not the guard: the panel does
      not ask at all when the session is not an administrator.

  Reuses:
    - ok-data-table (OutfitKit) for the list — same as People / Roles / API keys;
    - ok-inline-feedback for a failed read (same pattern as RolesPanel);
    - lib/approvals.ts (the one query) + lib/session.ts + lib/data-table-labels.ts.
-->
<template>
  <div class="fill">
    <div v-if="loading" class="table-loading">
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

      <ok-data-table
        ref="table"
        fill
        :rows="rows"
        :searchKeys="['approvedByName', 'createdByName', 'command']"
        :search-placeholder="t('approvals.search')"
        :empty-message="t('approvals.empty')"
        page-size="10"
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
import { listApprovals, type Approval } from '../lib/approvals';
import { getClient } from '../lib/runtime';
import { isAdmin } from '../lib/session';

const { t, locale } = useI18n();

type Row = Record<string, unknown>;
interface DataTableColumn {
  key: string;
  header: string;
  align?: 'left' | 'right' | 'center';
  filterable?: boolean;
  filterType?: 'text' | 'select' | 'number' | 'date' | 'range' | 'daterange';
  hidden?: boolean;
  format?: (row: Row) => string;
  render?: (row: Row) => Node | string;
}
type DataTableElement = HTMLElement & { labels: Record<string, string>; columns: DataTableColumn[] };

const loading = ref(true);
const loadError = ref(false);
const rows = ref<Approval[]>([]);

/**
 * The instant, in the reader's locale, with the TIME: a shift can hold several refunds and «that
 * Tuesday» is not an answer without the hour.
 *
 * It goes in `render` and not in `format` on purpose — `ok-data-table` filters and sorts by
 * `format(row)` when a column has one, so a localized string here would make the date-range filter
 * parse `NaN` and match nothing, on the one screen whose job is finding a day.
 */
function whenCell(row: Row): Node {
  const span = document.createElement('span');
  const raw = String(row.createdAt ?? '');
  const date = new Date(raw);
  span.textContent = Number.isNaN(date.getTime())
    ? raw
    : date.toLocaleString(locale.value === 'en' ? 'en-GB' : 'es-ES', {
        day: '2-digit',
        month: 'short',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
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
 * Reads the record. The two failure modes are kept apart on purpose: `loadError` means we could not
 * ask, an empty `rows` means the hub answered «nothing». Collapsing them would let a broken read
 * pass for a business where no manager ever approved anything.
 */
async function load(): Promise<void> {
  // The runtime gates the query on `hub.administer` — who approved what is information about the
  // staff. Not asking is the guard; the hidden tab is only the tidy version of it.
  if (!isAdmin.value) {
    rows.value = [];
    loadError.value = false;
    loading.value = false;
    return;
  }
  loading.value = true;
  loadError.value = false;
  try {
    rows.value = await listApprovals(getClient());
  } catch {
    rows.value = [];
    loadError.value = true;
  } finally {
    loading.value = false;
  }
}

const table = ref<DataTableElement | null>(null);

/** Typed data goes by JS PROPERTY, never by attribute (OutfitKit rule). */
function bindTable(element: DataTableElement | null): void {
  if (!element) return;
  element.labels = dataTableLabels(locale.value);
  element.columns = columns.value;
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
