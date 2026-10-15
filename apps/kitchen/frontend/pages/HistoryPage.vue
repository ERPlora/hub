<script setup lang="ts">
// Kitchen → History, «Kitchen history» (WORKBOOK «Pantallas · Historial»; KITCHEN-F25), live
// (`kitchen.log.list`): what happened in the kitchen, newest first — Action, Ticket (its number), Dish, Who
// («System» for what the kitchen did by itself), Notes (a reason) and When (the business's date and time) —,
// «Search ticket or notes…» and a filter by action, 50 a page.
import { DataTable, type DataTableColumn, type DataTableFilters, EmptyState } from '@erplora/ui/components';
import { useLive } from '@erplora/ui/sdk';
import { AppPage, useSession } from '@erplora/ui/shell';
import { computed, ref } from 'vue';

import PageNotices, { blockingError } from '../components/PageNotices.vue';
import { useLiveList } from '../composables/useLiveList';
import { useServerTable } from '../composables/useServerTable';
import { useLocale, useT } from '../composables/useT';
import { formatDateTime } from '../lib/format';
import type { LogAction, LogOut } from '../operations';
import { kitchenTabs } from '../tabs';

const ACTIONS: readonly LogAction[] = [
  'received',
  'created',
  'started',
  'ready',
  'item_ready',
  'item_recalled',
  'item_voided',
  'served',
  'recalled',
  'cancelled',
  'rushed',
  'unrushed',
  'reprinted',
  'deleted',
];

const session = useSession();
const t = useT();
const locale = useLocale();
const { data: settings } = useLive('kitchen.settings.get', {});
const timezone = computed(() => settings.value?.timezone ?? 'Europe/Madrid');

const table = useServerTable({ sort: '-created_at' });
const filters = ref<DataTableFilters>({});

function onFilters(now: DataTableFilters): void {
  filters.value = now;
  table.restart({ narrowed: Object.keys(now).length > 0 });
}

const { data: result, status, error, refresh } = useLiveList(
  'kitchen.log.list',
  () => ({
    ...(table.query.value.search ? { search: table.query.value.search } : {}),
    ...(filters.value.action ? { action: filters.value.action as LogAction } : {}),
  }),
  () => table.windows.value,
);
table.followResult(result);
const blocked = computed(() => blockingError(error.value));

const columns = computed<DataTableColumn<LogOut>[]>(() => [
  {
    key: 'action',
    label: t('kitchen.history.columns.action'),
    priority: 'high',
    format: (_, e) => t(`kitchen.action.${e.action}`),
    filter: { type: 'select', options: ACTIONS.map((value) => ({ value, label: t(`kitchen.action.${value}`) })) },
  },
  { key: 'ticket_number', label: t('kitchen.history.columns.ticket') },
  { key: 'item_name', label: t('kitchen.history.columns.dish'), format: (_, e) => [e.item_name, e.station_name && `(${e.station_name})`].filter(Boolean).join(' ') || '—' },
  { key: 'actor', label: t('kitchen.history.columns.who'), format: (_, e) => e.actor || t('kitchen.history.system') },
  { key: 'notes', label: t('kitchen.history.columns.notes'), format: (_, e) => e.notes || '—' },
  { key: 'created_at', label: t('kitchen.history.columns.when'), width: 'minmax(8.5rem,1fr)', format: (_, e) => formatDateTime(e.created_at, locale.value, timezone.value) },
]);
</script>

<template>
  <AppPage
    :title="$t('kitchen.title')"
    :tabs="kitchenTabs($t, { settings: session.can('kitchen.change_settings') })"
    :tabs-label="$t('kitchen.tabs.label')"
  >
    <h2
      class="kitchen-history__title"
      data-testid="kitchen-history-title"
    >
      {{ $t('kitchen.history.title') }}
    </h2>
    <PageNotices
      testid="kitchen-history"
      :status="status"
      :error="error"
    />
    <DataTable
      v-if="!blocked"
      v-model:search="table.search.value"
      testid="kitchen-history"
      server-side
      searchable
      :filters="filters"
      :rows="result?.rows ?? []"
      :total="result?.total ?? 0"
      :page="table.page.value"
      :page-size="table.pageSize.value"
      :entity-label="{ one: $t('kitchen.history.entity.one'), many: $t('kitchen.history.entity.many') }"
      :loading="status === 'loading'"
      :error="status === 'error' && !blocked ? $t('kitchen.history.loadError') : undefined"
      :search-placeholder="$t('kitchen.history.search')"
      :labels="{ loadError: $t('kitchen.history.loadError'), retry: $t('kitchen.live.retry') }"
      :columns="columns"
      @filters-change="onFilters"
      @page-change="table.goToPage"
      @load-more="table.loadMore"
      @page-size-change="table.setPageSize"
      @retry="refresh()"
    >
      <template #empty>
        <EmptyState
          data-testid="kitchen-history-empty"
          icon="time-outline"
          :heading="table.filtered.value ? $t('kitchen.noResults') : $t('kitchen.history.empty')"
          :message="table.filtered.value ? $t('kitchen.noResultsMessage') : undefined"
        />
      </template>
    </DataTable>
  </AppPage>
</template>

<style scoped>
.kitchen-history__title {
  margin: 0 0 0.6rem;
  font-size: 1.1rem;
}
</style>
