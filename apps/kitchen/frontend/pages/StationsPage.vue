<script setup lang="ts">
// Kitchen → Stations (WORKBOOK «Pantallas · Estaciones»; KITCHEN-F01 to F04), live
// (`kitchen.station.list`, `kitchen.routing.list`): the stations — Station (with its colour), Destination,
// Printer (the function and, if chosen, the printer), In progress (its dishes to cook) and Active —,
// «Search station…», «Add station»; per row Edit (also a tap on the row), Route (the routing dialog with
// that station chosen) and Delete (asks first; a refusal shows in the dialog). Under them, the routing:
// what goes to each station, with «Route» and «Remove». The actions only for whoever runs the stations
// (`kitchen.manage_station`).
import {
  ConfirmDialog,
  DataTable,
  type DataTableAction,
  type DataTableColumn,
  EmptyState,
  InlineFeedback,
} from '@erplora/ui/components';
import { type ApiError, useCommand, useLive } from '@erplora/ui/sdk';
import { AppPage, useSession } from '@erplora/ui/shell';
import { computed, ref } from 'vue';

import PageNotices, { blockingError } from '../components/PageNotices.vue';
import RouteFormModal from '../components/RouteFormModal.vue';
import StationFormModal from '../components/StationFormModal.vue';
import { useLiveList } from '../composables/useLiveList';
import { useServerTable } from '../composables/useServerTable';
import { useT } from '../composables/useT';
import type { RouteOut, StationOut } from '../operations';
import { kitchenTabs } from '../tabs';

const session = useSession();
const t = useT();
const canManage = computed(() => session.can('kitchen.manage_station'));

// ── Stations ─────────────────────────────────────────────────────────────────────────────────────

const table = useServerTable({ sort: 'sort_order' });
const { data: result, status, error, refresh } = useLiveList('kitchen.station.list', () => table.query.value, () => table.windows.value);
table.followResult(result);
const blocked = computed(() => blockingError(error.value));
/** Every active station, for the routing dialog (a kitchen has a handful). */
const { data: activeList } = useLive('kitchen.station.list', { is_active: true, limit: 100 });

const columns = computed<DataTableColumn<StationOut>[]>(() => [
  { key: 'name', label: t('kitchen.stations.columns.name'), sortable: true, priority: 'high', cell: 'name' },
  { key: 'destination', label: t('kitchen.stations.columns.destination'), format: (_, s) => t(`kitchen.destination.${s.destination}`) },
  {
    key: 'printer_usage',
    label: t('kitchen.stations.columns.printer'),
    format: (_, s) => [t(`kitchen.printerUsage.${s.printer_usage}`), s.printer_name].filter(Boolean).join(' · '),
  },
  { key: 'in_progress', label: t('kitchen.stations.columns.inProgress'), sortable: true, align: 'right' },
  { key: 'is_active', label: t('kitchen.stations.columns.active'), format: (_, s) => (s.is_active ? t('kitchen.yes') : t('kitchen.no')) },
]);

const stationActions = computed<DataTableAction<StationOut>[]>(() =>
  canManage.value
    ? [
        { id: 'edit', label: t('kitchen.stations.actions.edit'), icon: 'create-outline' },
        { id: 'route', label: t('kitchen.routing.route'), icon: 'swap-horizontal-outline' },
        { id: 'delete', label: t('kitchen.stations.actions.delete'), icon: 'trash-outline', color: 'danger', menuOnly: true },
      ]
    : [],
);

const target = ref<StationOut | null>(null);
const formOpen = ref(false);
const deleteOpen = ref(false);
const routeOpen = ref(false);
const routeStation = ref<string | null>(null);
const removal = useCommand('kitchen.station.delete');

function edit(row: StationOut | null): void {
  if (!canManage.value) return;
  target.value = row;
  formOpen.value = true;
}

function openRoute(stationId: string | null): void {
  routeStation.value = stationId;
  routeOpen.value = true;
}

function onStationAction({ actionId, row }: { actionId: string; row: StationOut }): void {
  if (actionId === 'edit') edit(row);
  if (actionId === 'route') openRoute(row.id);
  if (actionId === 'delete') {
    target.value = row;
    removal.error.value = null;
    deleteOpen.value = true;
  }
}

async function confirmDelete(): Promise<void> {
  if (!target.value) return;
  try {
    await removal.run({ station_id: target.value.id });
  } catch {
    return; // The dialog says why.
  }
  deleteOpen.value = false;
}

// ── Routing ──────────────────────────────────────────────────────────────────────────────────────

const routes = useServerTable({ sort: 'kind' });
const { data: routing, status: routingStatus, refresh: refreshRouting } = useLiveList(
  'kitchen.routing.list',
  () => ({ search: routes.query.value.search }),
  () => routes.windows.value,
);
routes.followResult(routing);

const routeColumns = computed<DataTableColumn<RouteOut>[]>(() => [
  { key: 'kind', label: t('kitchen.routing.columns.kind'), format: (_, r) => t(`kitchen.routing.kind.${r.kind}`) },
  { key: 'target_name', label: t('kitchen.routing.columns.target'), priority: 'high' },
  { key: 'station_name', label: t('kitchen.routing.columns.station') },
]);
const routeActions = computed<DataTableAction<RouteOut>[]>(() =>
  canManage.value ? [{ id: 'remove', label: t('kitchen.routing.remove'), icon: 'close-circle-outline', color: 'danger', showLabel: true }] : [],
);
const clear = useCommand('kitchen.routing.clear');
const routeError = ref<ApiError | null>(null);

async function onRouteAction({ row }: { actionId: string; row: RouteOut }): Promise<void> {
  routeError.value = null;
  try {
    await clear.run(row.kind === 'product' ? { product_id: row.target_id } : { category_id: row.target_id });
  } catch (refused) {
    routeError.value = refused as ApiError;
  }
}
</script>

<template>
  <AppPage
    :title="$t('kitchen.title')"
    content-layout="fill"
    :tabs="kitchenTabs($t, { settings: session.can('kitchen.change_settings') })"
    :tabs-label="$t('kitchen.tabs.label')"
  >
    <PageNotices
      testid="kitchen-stations"
      :status="status"
      :error="error"
    />
    <DataTable
      v-if="!blocked"
      v-model:search="table.search.value"
      testid="kitchen-stations"
      fill
      server-side
      searchable
      :row-clickable="canManage"
      :title="$t('kitchen.stations.title')"
      :rows="result?.rows ?? []"
      :total="result?.total ?? 0"
      :page="table.page.value"
      :page-size="table.pageSize.value"
      :sort="table.sort.value"
      :sort-dir="table.dir.value"
      :entity-label="{ one: $t('kitchen.stations.entity.one'), many: $t('kitchen.stations.entity.many') }"
      :loading="status === 'loading'"
      :error="status === 'error' && !blocked ? $t('kitchen.stations.loadError') : undefined"
      :actions="stationActions"
      :primary-action="canManage ? { label: $t('kitchen.stations.add'), icon: 'add-outline' } : undefined"
      :search-placeholder="$t('kitchen.stations.search')"
      :labels="{ loadError: $t('kitchen.stations.loadError'), retry: $t('kitchen.live.retry') }"
      :columns="columns"
      @page-change="table.goToPage"
      @load-more="table.loadMore"
      @page-size-change="table.setPageSize"
      @sort-change="table.setSort"
      @action="onStationAction"
      @row-click="edit"
      @primary-action="edit(null)"
      @retry="refresh()"
    >
      <template #name="{ row }">
        <span class="kitchen-stations__name">
          <i
            class="kitchen-stations__dot"
            :style="{ background: row.color }"
          />{{ row.name }}
        </span>
      </template>
      <template #empty>
        <EmptyState
          data-testid="kitchen-stations-empty"
          icon="layers-outline"
          :heading="table.filtered.value ? $t('kitchen.noResults') : $t('kitchen.stations.empty')"
          :message="table.filtered.value ? $t('kitchen.noResultsMessage') : $t('kitchen.stations.emptyMessage')"
        />
      </template>
    </DataTable>

    <section
      v-if="!blocked"
      class="kitchen-routing"
    >
      <h2
        class="kitchen-routing__title"
        data-testid="kitchen-routing-title"
      >
        {{ $t('kitchen.routing.title') }}
      </h2>
      <p class="kitchen-routing__hint">
        {{ $t('kitchen.routing.hint') }}
      </p>
      <InlineFeedback
        v-if="routeError"
        tone="danger"
        data-testid="kitchen-routing-error"
        :heading="$t('kitchen.routing.removeError')"
      >
        {{ routeError.message }}
      </InlineFeedback>
      <DataTable
        v-model:search="routes.search.value"
        testid="kitchen-routing"
        server-side
        searchable
        :rows="routing?.rows ?? []"
        :row-key="(r: RouteOut) => `${r.kind}-${r.target_id}`"
        :total="routing?.total ?? 0"
        :page="routes.page.value"
        :page-size="routes.pageSize.value"
        :entity-label="{ one: $t('kitchen.routing.entity.one'), many: $t('kitchen.routing.entity.many') }"
        :loading="routingStatus === 'loading'"
        :error="routingStatus === 'error' ? $t('kitchen.routing.loadError') : undefined"
        :actions="routeActions"
        :primary-action="canManage ? { label: $t('kitchen.routing.route'), icon: 'swap-horizontal-outline' } : undefined"
        :search-placeholder="$t('kitchen.routing.search')"
        :labels="{ loadError: $t('kitchen.routing.loadError'), retry: $t('kitchen.live.retry') }"
        :columns="routeColumns"
        @page-change="routes.goToPage"
        @load-more="routes.loadMore"
        @page-size-change="routes.setPageSize"
        @action="onRouteAction"
        @primary-action="openRoute(null)"
        @retry="refreshRouting()"
      >
        <template #empty>
          <EmptyState
            data-testid="kitchen-routing-empty"
            icon="swap-horizontal-outline"
            :heading="routes.filtered.value ? $t('kitchen.noResults') : $t('kitchen.routing.empty')"
          />
        </template>
      </DataTable>
    </section>

    <StationFormModal
      v-model:open="formOpen"
      :station="target"
    />
    <RouteFormModal
      v-model:open="routeOpen"
      :stations="activeList?.rows ?? []"
      :station="routeStation"
    />
    <ConfirmDialog
      v-model:open="deleteOpen"
      testid="kitchen-stations-delete"
      tone="danger"
      :title="t('kitchen.stations.delete.title', { name: target?.name ?? '' })"
      :message="t('kitchen.stations.delete.message')"
      :confirm-label="t('kitchen.stations.delete.confirm')"
      :cancel-label="t('kitchen.cancel')"
      :pending="removal.pending.value"
      :error="removal.error.value"
      @confirm="confirmDelete"
      @cancel="deleteOpen = false"
    />
  </AppPage>
</template>

<style scoped>
.kitchen-stations__name {
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
  font-weight: 600;
}
.kitchen-stations__dot {
  /* A flex item that never shrinks: a long name in a narrow column must not squeeze the colour away. */
  flex: none;
  display: inline-block;
  width: 0.7rem;
  height: 0.7rem;
  border-radius: 50%;
}
.kitchen-routing {
  margin-top: 1.5rem;
}
.kitchen-routing__title {
  margin: 0 0 0.25rem;
  font-size: 1.1rem;
}
.kitchen-routing__hint {
  margin: 0 0 0.75rem;
  color: var(--ion-color-medium, #8b897f);
}
</style>
