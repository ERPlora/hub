<script setup lang="ts">
// Tips → Tips (TIP-F03 to TIP-F06; WORKBOOK «Pantallas · Propinas»): the tips of the period — «Today» to begin with,
// «7 days» or «30 days», counted back from the hub's business day — live and newest first (`tip.tip.list`) in a
// server-side DataTable: Date, Sale («To the pool» for the jar's), For («Unassigned» for nobody's), Payment method,
// Amount and Status; «Search sale or person…», filters by person, payment and status, table or cards, 50 a page.
// «Record tip» records one of a sale or to the pool; an active tip offers «Adjust» and «Void». What changes comes back
// through the stream by itself.
import {
  DataTable,
  type DataTableAction,
  type DataTableColumn,
  type DataTableFilters,
  EmptyState,
  formatDateTime,
  StatusPill,
} from '@erplora/ui/components';
import { useLiveClient } from '@erplora/ui/sdk';
import { AppPage, useSession } from '@erplora/ui/shell';
import { IonSelect, IonSelectOption } from '@ionic/vue';
import { computed, onMounted, ref, shallowRef } from 'vue';

import ListNotices, { blockingError } from '../../../sale/frontend/components/backoffice/ListNotices.vue';
import { periodBounds } from '../../../sale/frontend/components/sales/period';
import { useBusinessDay } from '../../../sale/frontend/components/sales/useBusinessDay';
import { useServerTable } from '../../../sale/frontend/composables/useServerTable';
import { useLocale, useT } from '../../../sale/frontend/composables/useT';
import { formatMoney } from '../../../sale/frontend/lib/format';
import { useAppTabs } from '../../../../base/frontend/lib/app-tabs';
import { useBusinessMoney } from '../../../../base/frontend/lib/money';
import { useBusinessZone } from '../../../../base/frontend/lib/zone';
import TipAdjustModal from '../components/TipAdjustModal.vue';
import TipFormModal from '../components/TipFormModal.vue';
import TipVoidModal from '../components/TipVoidModal.vue';
import { teamFilter } from '../lib/team';
import type { MethodType, TipListIn, TipOut, TipStatus } from '../operations';

const PERIODS = ['today', 'week', 'month'] as const;
type Period = (typeof PERIODS)[number];
const METHOD_TYPES: readonly MethodType[] = ['cash', 'card', 'transfer', 'other'];
const STATUSES: readonly TipStatus[] = ['active', 'voided'];
/** The longest search the list takes (`TipListIn.search`). */
const MAX_SEARCH = 120;

const tabs = useAppTabs('tip');
const session = useSession();
const t = useT();
const locale = useLocale();
const money = useBusinessMoney();
const zone = useBusinessZone();
const client = useLiveClient();
const canAdd = computed(() => session.can('tip.add_tip'));
const canManage = computed(() => session.can('tip.manage'));

const day = useBusinessDay();
onMounted(() => void day.read());
const period = shallowRef<Period>('today');
function pickPeriod(value: unknown): void {
  if (!PERIODS.includes(value as Period)) return;
  period.value = value as Period;
  void day.read();
}

/** The table's filters as the list takes them: a filter not in use is absent. */
const filters = ref<DataTableFilters>({});
const filterQuery = computed<Partial<TipListIn>>(() => {
  const { member_id, method_type, status } = filters.value as Record<string, string | undefined>;
  return {
    ...(member_id ? { member_id } : {}),
    ...(method_type ? { method_type: method_type as MethodType } : {}),
    ...(status ? { status: status as TipStatus } : {}),
  };
});

const table = useServerTable('tip.tip.list', {
  maxSearch: MAX_SEARCH,
  filters: () => ({ ...periodBounds(period.value, day.today.value), ...filterQuery.value }),
  narrowed: () => Object.keys(filterQuery.value).length > 0,
});
const { data: result, status, error, refresh } = table;
const blocked = computed(() => blockingError(error.value));
const tableError = computed(() => (status.value === 'error' ? error.value?.message : undefined));

const findTeam = teamFilter(client);
const saleOf = (row: TipOut): string => (row.pool ? t('tip.list.pool') : row.sale_number);

const columns = computed<DataTableColumn<TipOut>[]>(() => [
  {
    key: 'created_at',
    label: t('tip.list.columns.date'),
    format: (_, row) => formatDateTime(row.created_at, locale.value, { timeZone: zone.value }),
  },
  { key: 'sale_number', label: t('tip.list.columns.sale'), priority: 'high', format: (_, row) => saleOf(row) },
  {
    key: 'member_name',
    label: t('tip.list.columns.for'),
    format: (_, row) => row.member_name || t('tip.list.unassigned'),
    filter: { type: 'lookup', key: 'member_id', load: findTeam },
  },
  {
    key: 'method_name',
    label: t('tip.list.columns.method'),
    filter: { type: 'select', key: 'method_type', options: METHOD_TYPES.map((value) => ({ value, label: t(`tip.list.methodTypes.${value}`) })) },
  },
  { key: 'amount', label: t('tip.list.columns.amount'), align: 'right', format: (_, row) => formatMoney(row.amount, locale.value, money.value) },
  {
    key: 'status',
    label: t('tip.list.columns.status'),
    cell: 'status',
    format: (_, row) => t(`tip.list.status.${row.status}`),
    filter: { type: 'select', options: STATUSES.map((value) => ({ value, label: t(`tip.list.status.${value}`) })) },
  },
]);

const voided = (row: TipOut): boolean => row.status === 'voided';
const actions = computed<DataTableAction<TipOut>[]>(() =>
  canManage.value
    ? [
        { id: 'adjust', label: t('tip.list.actions.adjust'), icon: 'ion:create-outline', hidden: voided },
        { id: 'void', label: t('tip.list.actions.void'), icon: 'ion:ban-outline', color: 'danger', hidden: voided },
      ]
    : [],
);

const recording = ref(false);
const adjusting = ref(false);
const voiding = ref(false);
const chosen = shallowRef<TipOut | null>(null);

function onAction({ actionId, row }: { actionId: string; row: TipOut }): void {
  if (!canManage.value || voided(row)) return;
  chosen.value = row;
  if (actionId === 'adjust') adjusting.value = true;
  else if (actionId === 'void') voiding.value = true;
}
</script>

<template>
  <AppPage
    :title="$t('tip.title')"
    content-layout="fill"
    :tabs="tabs"
    :tabs-label="$t('tip.tabs.label')"
  >
    <ListNotices
      testid="tip-list"
      :status="status"
      :error="error"
    />
    <DataTable
      v-if="!blocked"
      v-model:search="table.search.value"
      testid="tip-list"
      fill
      server-side
      searchable
      :filters="filters"
      :rows="result?.rows ?? []"
      :total="result?.total ?? 0"
      :page="table.page.value"
      :page-size="table.pageSize.value"
      :views="['table', 'cards']"
      :card-title="saleOf"
      :card-icon="() => 'wallet-outline'"
      :entity-label="{ one: $t('tip.list.entity.one'), many: $t('tip.list.entity.many') }"
      :loading="status === 'loading'"
      :error="tableError"
      :addable="canAdd"
      :actions="actions"
      :search-placeholder="$t('tip.list.search')"
      :labels="{ add: $t('tip.list.add'), loading: $t('tip.list.loading'), loadError: $t('tip.list.loadError'), retry: $t('sale.live.retry') }"
      :columns="columns"
      @update:filters="filters = $event"
      @page-change="table.goToPage"
      @load-more="table.loadMore"
      @page-size-change="table.setPageSize"
      @add="recording = true"
      @action="onAction"
      @retry="refresh()"
    >
      <template #toolbar>
        <ion-select
          data-testid="tip-list-period"
          interface="popover"
          :value="period"
          :aria-label="$t('tip.list.period.label')"
          @ion-change="pickPeriod($event.detail.value)"
        >
          <ion-select-option
            v-for="value in PERIODS"
            :key="value"
            :value="value"
          >
            {{ $t(`tip.list.period.${value}`) }}
          </ion-select-option>
        </ion-select>
      </template>
      <template #status="{ row }">
        <StatusPill
          size="sm"
          :tone="row.status === 'active' ? 'success' : 'neutral'"
          :label="$t(`tip.list.status.${row.status}`)"
        />
      </template>
      <template #empty>
        <EmptyState
          data-testid="tip-list-empty"
          icon="wallet-outline"
          :heading="table.filtered.value ? $t('tip.list.noResults') : $t('tip.list.empty')"
          :message="table.filtered.value ? $t('tip.list.noResultsMessage') : $t('tip.list.emptyMessage')"
        />
      </template>
    </DataTable>
    <TipFormModal v-model:open="recording" />
    <TipAdjustModal
      v-model:open="adjusting"
      :tip="chosen"
    />
    <TipVoidModal
      v-model:open="voiding"
      :tip="chosen"
    />
  </AppPage>
</template>
