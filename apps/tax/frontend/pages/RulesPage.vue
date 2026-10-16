<script setup lang="ts">
// Taxes → Rules (TAX-F03–F08, F11): the live `tax.rule.list` in a server-side DataTable — Category (a
// component as «↳ label» right under its root), Country, Region, %, Type, Qualification, Valid from,
// Valid to and Active —, search, Status (Active to begin with · Deactivated · All), the column filters
// behind the table's funnel (Category, Country among the business's, Region, % from–to, Type,
// Qualification, Regime) and sort by
// any column. For whoever can manage: «+» («New tax rule») and the row actions «Set end date» and
// «Deactivate» (confirmed), «Restore» on a deactivated rule (no confirmation: it undoes). A rule is
// never edited (TAX-F07). Every change comes back through the stream; nothing here refetches.
import {
  ConfirmDialog,
  type DataTableAction,
  type DataTableColumn,
  type DataTableFilterField,
  type DataTableFilters,
  DataTable,
  EmptyState,
  InlineFeedback,
} from '@erplora/ui/components';
import { useCommand, useLive, useLiveClient } from '@erplora/ui/sdk';
import { AppPage, useSession } from '@erplora/ui/shell';
import { IonSelect, IonSelectOption } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import PageNotices, { blockingError } from '../components/PageNotices.vue';
import SetupNotice from '../components/SetupNotice.vue';
import RuleCreateModal from '../components/RuleCreateModal.vue';
import RuleEndModal from '../components/RuleEndModal.vue';
import { useLiveList } from '../composables/useLiveList';
import { useServerTable } from '../composables/useServerTable';
import { useLocale, useT } from '../composables/useT';
import { countryChoices } from '../lib/countries';
import { formatDate, formatPercent } from '../lib/format';
import { categorySearch } from '../lib/pickers';
import { OPERATION_CLASSES, ruleCardTitle, ruleCategoryText, TAX_TYPES } from '../lib/rules';
import type { RuleListIn, RuleOut, RuleStatusFilter } from '../operations';
import { taxTabs } from '../tabs';

const STATUSES: readonly RuleStatusFilter[] = ['active', 'inactive', 'all'];

const session = useSession();
const canManage = computed(() => session.can('tax.manage'));
const t = useT();
const locale = useLocale();
const client = useLiveClient();

// ── The list ───────────────────────────────────────────────────────────────────────────────────
const table = useServerTable({ sort: 'tax_category_key' });
const ruleStatus = ref<RuleStatusFilter>('active');
/** The table's filters (its funnel; Status is apart): a filter not in use is absent. */
const filters = ref<DataTableFilters>({});
watch([filters, ruleStatus], ([now, state]) => table.restart({ narrowed: Object.keys(now).length > 0 || state !== 'active' }));

function setStatus(event: CustomEvent<{ value?: unknown }>): void {
  const value = event.detail.value;
  ruleStatus.value = STATUSES.includes(value as RuleStatusFilter) ? (value as RuleStatusFilter) : 'active';
}

const {
  data: result,
  status,
  error,
  refresh,
} = useLiveList('tax.rule.list', () => ({ ...filters.value, status: ruleStatus.value, ...table.query.value }) as RuleListIn, () => table.windows.value);
table.followResult(result);

/** The countries the business has rules for (a filter only narrows what is there): the server's. */
const { data: countriesInUse } = useLive('tax.rule.countries', {});
/** The Category filter searches the server: all the business's categories, not a first page. */
const findCategories = categorySearch(client);

const blocked = computed(() => blockingError(error.value));
/** A filter the server refused (a 422 of the list): said under the filter, the rows stay. */
const filterErrors = computed(() => error.value?.fields ?? {});
const tableError = computed(() => (status.value === 'error' && !Object.keys(filterErrors.value).length ? error.value?.message : undefined));

// ── Filters ────────────────────────────────────────────────────────────────────────────────────
/** The countries of the business's rules, named for the reader (the chosen one kept while it is). */
const countries = computed(() => {
  const codes = [...(countriesInUse.value?.countries ?? [])];
  if (filters.value.country_code) codes.push(filters.value.country_code);
  return countryChoices(codes, locale.value);
});

/** The filters with no column of their own, after the columns' (bounded as RuleListIn takes it). */
const filterFields = computed<DataTableFilterField[]>(() => [{ type: 'text', key: 'regime_key', label: t('tax.rules.columns.regime'), maxlength: 10 }]);

// ── Columns and cards ──────────────────────────────────────────────────────────────────────────
const dash = (value: unknown): string => (value === null || value === undefined || value === '' ? '—' : String(value));
/** A rule's day in the reader's language, «—» for an open end. */
const day = (value: unknown): string => (typeof value === 'string' && value ? formatDate(value, locale.value) : '—');
/** The qualification, with the exemption reason of an exempt rule («Exempt · E1»). */
const qualification = (row: RuleOut): string =>
  [t(`tax.classes.${row.operation_class}`), row.operation_class === 'exempt' ? row.exempt_reason : null].filter(Boolean).join(' · ');

// The filters bounded as RuleListIn takes them: a longer region or regime, or a % off 0–100, is a 422.
const columns = computed<DataTableColumn<RuleOut>[]>(() => [
  {
    key: 'tax_category_key',
    label: t('tax.rules.columns.category'),
    sortable: true,
    priority: 'high',
    format: (_, row) => ruleCategoryText(row),
    filter: { type: 'lookup', load: findCategories },
  },
  {
    key: 'country_code',
    label: t('tax.rules.columns.country'),
    sortable: true,
    width: 'minmax(4.5rem,0.6fr)',
    filter: { type: 'select', options: countries.value },
  },
  {
    key: 'region_code',
    label: t('tax.rules.columns.region'),
    sortable: true,
    width: 'minmax(4.5rem,0.6fr)',
    format: dash,
    filter: { type: 'text', maxlength: 6 },
  },
  {
    key: 'rate_pct',
    label: t('tax.rules.columns.rate'),
    sortable: true,
    align: 'right',
    width: 'minmax(4.5rem,0.6fr)',
    format: (_, row) => formatPercent(row.rate_pct, locale.value),
    filter: { type: 'range', keys: ['rate_min', 'rate_max'], min: 0, max: 100 },
  },
  {
    key: 'tax_type',
    label: t('tax.rules.columns.type'),
    sortable: true,
    format: (_, row) => t(`tax.types.${row.tax_type}`),
    filter: { type: 'select', options: TAX_TYPES.map((value) => ({ value, label: t(`tax.types.${value}`) })) },
  },
  {
    key: 'operation_class',
    label: t('tax.rules.columns.qualification'),
    sortable: true,
    format: (_, row) => qualification(row),
    filter: { type: 'select', options: OPERATION_CLASSES.map((value) => ({ value, label: t(`tax.classes.${value}`) })) },
  },
  { key: 'valid_from', label: t('tax.rules.columns.validFrom'), sortable: true, format: day },
  { key: 'valid_to', label: t('tax.rules.columns.validTo'), sortable: true, priority: 'low', format: day },
  { key: 'is_active', label: t('tax.rules.columns.active'), sortable: true, priority: 'low', format: (value) => (value ? t('tax.yes') : t('tax.no')) },
]);

// ── Row actions ────────────────────────────────────────────────────────────────────────────────
/** A row action that has no dialog to show its refusal (Restore) says it on the page. */
const pageError = ref('');
const restoring = ref<string | null>(null);

const actions = computed<DataTableAction<RuleOut>[]>(() =>
  canManage.value
    ? [
        { id: 'end', label: t('tax.rules.actions.end'), icon: 'calendar-outline', hidden: (row) => !row.is_active },
        { id: 'deactivate', label: t('tax.rules.actions.deactivate'), icon: 'ban-outline', color: 'danger', hidden: (row) => !row.is_active },
        {
          id: 'restore',
          label: t('tax.rules.actions.restore'),
          icon: 'arrow-undo-outline',
          color: 'success',
          hidden: (row) => row.is_active,
          loading: (row) => restoring.value === row.id,
        },
      ]
    : [],
);

const ending = ref<RuleOut | null>(null);
const endOpen = ref(false);

const deactivation = useCommand('tax.rule.deactivate');
const deactivating = ref<RuleOut | null>(null);
const confirmOpen = ref(false);

const activation = useCommand('tax.rule.activate');

async function restore(row: RuleOut): Promise<void> {
  restoring.value = row.id;
  try {
    await activation.run({ id: row.id });
  } catch (err) {
    pageError.value = err instanceof Error ? err.message : String(err);
  } finally {
    restoring.value = null;
  }
}

function onAction({ actionId, row }: { actionId: string; row: RuleOut }): void {
  // The server checks the permission on every command; the page does not offer what it would refuse.
  if (!canManage.value) return;
  pageError.value = '';
  if (actionId === 'end' && row.is_active) {
    ending.value = row;
    endOpen.value = true;
  } else if (actionId === 'deactivate' && row.is_active) {
    deactivating.value = row;
    deactivation.error.value = null;
    confirmOpen.value = true;
  } else if (actionId === 'restore' && !row.is_active) {
    void restore(row);
  }
}

async function deactivate(): Promise<void> {
  const row = deactivating.value;
  if (!row) return;
  try {
    await deactivation.run({ id: row.id });
  } catch {
    return; // The dialog shows `error`.
  }
  confirmOpen.value = false;
}

const creating = ref(false);
function create(): void {
  pageError.value = '';
  creating.value = true;
}
</script>

<template>
  <AppPage
    :title="$t('tax.title')"
    content-layout="fill"
    :tabs="taxTabs($t)"
    :tabs-label="$t('tax.tabs.label')"
  >
    <PageNotices
      testid="tax-rules"
      :status="status"
      :error="error"
      :read-only="!canManage"
    />
    <SetupNotice v-if="canManage" />
    <InlineFeedback
      v-if="pageError"
      tone="danger"
      data-testid="tax-rules-error"
    >
      {{ pageError }}
    </InlineFeedback>
    <DataTable
      v-if="!blocked"
      v-model:search="table.search.value"
      v-model:filters="filters"
      testid="tax-rules"
      fill
      server-side
      searchable
      filterable
      :filter-fields="filterFields"
      :filter-errors="filterErrors"
      :rows="result?.rows ?? []"
      :total="result?.total ?? 0"
      :page="table.page.value"
      :page-size="table.pageSize.value"
      :sort="table.sort.value"
      :sort-dir="table.dir.value"
      :views="['table', 'cards']"
      :card-breakpoint="834"
      :card-title="ruleCardTitle"
      card-title-column="tax_category_key"
      :entity-label="{ one: $t('tax.rules.entity.one'), many: $t('tax.rules.entity.many') }"
      :loading="status === 'loading'"
      :error="tableError"
      :addable="canManage"
      :actions="actions"
      :search-placeholder="$t('tax.rules.search')"
      :labels="{ add: $t('tax.add'), loadError: $t('tax.rules.loadError'), retry: $t('tax.live.retry') }"
      :columns="columns"
      @page-change="table.goToPage"
      @load-more="table.loadMore"
      @page-size-change="table.setPageSize"
      @sort-change="table.setSort"
      @action="onAction"
      @add="create"
      @retry="refresh()"
    >
      <template #filters>
        <ion-select
          data-testid="tax-rules-status"
          interface="popover"
          :aria-label="$t('tax.rules.status.label')"
          :value="ruleStatus"
          @ion-change="setStatus"
        >
          <ion-select-option
            v-for="value in STATUSES"
            :key="value"
            :value="value"
          >
            {{ $t(`tax.rules.status.${value}`) }}
          </ion-select-option>
        </ion-select>
      </template>
      <template #empty>
        <EmptyState
          data-testid="tax-rules-empty"
          icon="receipt-outline"
          :heading="table.filtered.value ? $t('tax.noResults') : $t('tax.rules.empty')"
          :message="table.filtered.value ? $t('tax.noResultsMessage') : undefined"
        />
      </template>
    </DataTable>
    <template v-if="canManage">
      <RuleCreateModal v-model:open="creating" />
      <RuleEndModal
        v-model:open="endOpen"
        :rule="ending"
      />
      <ConfirmDialog
        v-model:open="confirmOpen"
        testid="tax-rule-deactivate"
        tone="danger"
        :title="$t('tax.rules.deactivate.title')"
        :message="$t('tax.rules.deactivate.message')"
        :confirm-label="$t('tax.rules.deactivate.confirm')"
        :pending="deactivation.pending.value"
        :error="deactivation.error.value"
        @confirm="deactivate"
      />
    </template>
  </AppPage>
</template>

