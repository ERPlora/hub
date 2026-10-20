<script setup lang="ts">
// Services → Services (WORKBOOK «Pantallas · Servicios»; SERVICE-F01 to F05): the live
// `service.service.list` in a server-side DataTable — Name, Category, Pricing, Price, Duration (min)
// and Status (Active, Not configured with its reason, Archived) —, «Search service…», column filters
// (Status on Archived is the archived view), list or cards, 50 a page. «New service» (whoever may add)
// and a row (whoever may edit) open the form. A row offers Edit and Archive (with its confirmation);
// the archived view only Restore. Changes come back through the stream.
import {
  ConfirmDialog,
  DataTable,
  type DataTableAction,
  type DataTableColumn,
  type DataTableFilters,
  EmptyState,
  InlineFeedback,
  StatusPill,
} from '@erplora/ui/components';
import { type ApiError, useCommand, useLive, useLiveClient } from '@erplora/ui/sdk';
import { AppPage, useSession } from '@erplora/ui/shell';
import { computed, ref } from 'vue';

import PageNotices, { blockingError } from '../components/PageNotices.vue';
import ServiceFormModal from '../components/ServiceFormModal.vue';
import { useLiveList } from '../composables/useLiveList';
import { useServerTable } from '../composables/useServerTable';
import { useLocale, useT } from '../composables/useT';
import { formatMoney } from '../lib/format';
import { parseMoney } from '../lib/money';
import type { PricingType, ServiceListIn, ServiceOut, ServiceStatus } from '../operations';
import { serviceTabs } from '../tabs';

const PRICING: readonly PricingType[] = ['fixed', 'hourly', 'from', 'variable', 'free'];
const STATUSES: readonly ServiceStatus[] = ['active', 'unconfigured', 'archived'];
const TONE: Record<ServiceStatus, 'success' | 'danger' | 'neutral'> = { active: 'success', unconfigured: 'danger', archived: 'neutral' };

const session = useSession();
const t = useT();
const locale = useLocale();
const canAdd = computed(() => session.can('service.add_service'));
const canChange = computed(() => session.can('service.change_service'));
const canArchive = computed(() => session.can('service.delete_service'));
// Appointments' permission only exists while that app is on: without it there is no agenda to ask.
const readsAgenda = computed(() => session.can('appointment.view_own_appointment'));

const table = useServerTable({ sort: 'name' });
const filters = ref<DataTableFilters>({});
const archivedView = computed(() => filters.value.status === 'archived');

/** Cents of a typed price filter; nothing when it is not an amount. */
function cents(text: string | undefined): number | undefined {
  if (!text) return undefined;
  const read = parseMoney(text);
  return read.ok && read.cents !== null ? read.cents : undefined;
}
const minutes = (text: string | undefined): number | undefined => (text && /^\d+$/.test(text.trim()) ? Number(text.trim()) : undefined);

/** The table's filters as the query takes them: prices in cents, minutes as numbers. */
const query = computed<Partial<ServiceListIn>>(() => {
  const f = filters.value;
  const out: Partial<ServiceListIn> = {
    ...(f.name ? { name: f.name } : {}),
    ...(f.category_id ? { category_id: f.category_id } : {}),
    ...(f.pricing_type ? { pricing_type: f.pricing_type as PricingType } : {}),
    ...(f.status ? { status: f.status as ServiceStatus } : {}),
  };
  const bounds: Array<[keyof ServiceListIn, number | undefined]> = [
    ['price_min', cents(f.price_from)],
    ['price_max', cents(f.price_to)],
    ['duration_min', minutes(f.duration_minutes_from)],
    ['duration_max', minutes(f.duration_minutes_to)],
  ];
  for (const [key, value] of bounds) if (value !== undefined) (out as Record<string, number>)[key] = value;
  return out;
});

function onFilters(now: DataTableFilters): void {
  filters.value = now;
  table.restart({ narrowed: Object.keys(now).length > 0 });
}

const { data: result, status, error, refresh } = useLiveList('service.service.list', () => ({ ...query.value, ...table.query.value }), () => table.windows.value);
table.followResult(result);
const blocked = computed(() => blockingError(error.value));

// The category filter offers the business's categories (a salon has a handful).
const { data: categories } = useLive('service.category.list', { limit: 100 });

const columns = computed<DataTableColumn<ServiceOut>[]>(() => [
  { key: 'name', label: t('service.services.columns.name'), sortable: true, priority: 'high', filter: { type: 'text' } },
  {
    key: 'category_name',
    label: t('service.services.columns.category'),
    sortable: true,
    format: (_, row) => row.category_name ?? t('service.none'),
    filter: { type: 'select', key: 'category_id', options: (categories.value?.rows ?? []).map((c) => ({ value: c.id, label: c.name })) },
  },
  {
    key: 'pricing_type',
    label: t('service.services.columns.pricingType'),
    sortable: true,
    format: (_, row) => t(`service.pricing.${row.pricing_type}`),
    filter: { type: 'select', options: PRICING.map((value) => ({ value, label: t(`service.pricing.${value}`) })) },
  },
  {
    key: 'price',
    label: t('service.services.columns.price'),
    sortable: true,
    align: 'right',
    format: (_, row) => formatMoney(row.price, locale.value),
    filter: { type: 'range' },
  },
  {
    key: 'duration_minutes',
    label: t('service.services.columns.duration'),
    sortable: true,
    align: 'right',
    format: (_, row) => String(row.duration_minutes),
    filter: { type: 'range' },
  },
  {
    key: 'status',
    label: t('service.services.columns.status'),
    sortable: true,
    cell: 'status',
    filter: { type: 'select', options: STATUSES.map((value) => ({ value, label: t(`service.services.status.${value}`) })) },
  },
]);

const actions = computed<DataTableAction<ServiceOut>[]>(() => {
  if (archivedView.value) {
    return canChange.value ? [{ id: 'restore', label: t('service.services.actions.restore'), icon: 'arrow-undo-outline', color: 'success' }] : [];
  }
  return [
    ...(canChange.value ? [{ id: 'edit', label: t('service.services.actions.edit'), icon: 'create-outline' }] : []),
    ...(canArchive.value ? [{ id: 'archive', label: t('service.services.actions.archive'), icon: 'file-tray-outline', color: 'danger' }] : []),
  ];
});

// The form
const editing = ref<ServiceOut | null>(null);
const formOpen = ref(false);
function openForm(service: ServiceOut | null): void {
  editing.value = service;
  formOpen.value = true;
}

// Row actions
const archive = useCommand('service.service.archive');
const restore = useCommand('service.service.restore');
const archiving = ref<ServiceOut | null>(null);
const archiveOpen = ref(false);
const rowError = ref<ApiError | null>(null);
const client = useLiveClient();
/** Upcoming appointments that keep using the service being archived (Appointments' count). */
const upcoming = ref(0);
const archiveConsequences = computed(() =>
  upcoming.value > 0 ? [t('service.services.archive.upcoming', { count: upcoming.value })] : [],
);

/** Asks Appointments how many upcoming appointments carry `row`. The line is advice, never a gate: when the
 *  agenda cannot answer, the dialog goes without it (WORKBOOK SERVICE-F04). */
async function countUpcoming(row: ServiceOut): Promise<void> {
  upcoming.value = 0;
  if (!readsAgenda.value) return;
  let count = 0;
  try {
    count = (await client.api.call('appointment.appointment.count_active_for_service', { service_id: row.id })).count;
  } catch {
    count = 0;
  }
  if (archiving.value?.id === row.id) upcoming.value = count;
}

async function confirmArchive(): Promise<void> {
  if (!archiving.value) return;
  try {
    await archive.run({ id: archiving.value.id });
  } catch {
    return; // The dialog says why.
  }
  archiveOpen.value = false;
}

async function onAction({ actionId, row }: { actionId: string; row: ServiceOut }): Promise<void> {
  rowError.value = null;
  if (actionId === 'edit') openForm(row);
  if (actionId === 'archive') {
    archive.error.value = null;
    archiving.value = row;
    archiveOpen.value = true;
    await countUpcoming(row);
  }
  if (actionId === 'restore') {
    try {
      await restore.run({ id: row.id });
    } catch {
      rowError.value = restore.error.value;
    }
  }
}

function onRowClick(row: ServiceOut): void {
  if (canChange.value && !archivedView.value) openForm(row);
}
</script>

<template>
  <AppPage
    :title="$t('service.title')"
    content-layout="fill"
    :tabs="serviceTabs($t, { settings: session.can('service.manage_settings') })"
    :tabs-label="$t('service.tabs.label')"
  >
    <PageNotices
      testid="service-services"
      :status="status"
      :error="error"
    />
    <InlineFeedback
      v-if="rowError"
      tone="danger"
      dismissible
      data-testid="service-services-row-error"
      :heading="t('service.services.restoreError')"
      @dismiss="rowError = null"
    >
      {{ rowError.message }}
    </InlineFeedback>
    <DataTable
      v-if="!blocked"
      v-model:search="table.search.value"
      testid="service-services"
      fill
      server-side
      searchable
      :filters="filters"
      filterable
      :rows="result?.rows ?? []"
      :total="result?.total ?? 0"
      :page="table.page.value"
      :page-size="table.pageSize.value"
      :sort="table.sort.value"
      :sort-dir="table.dir.value"
      :views="['table', 'cards']"
      :card-title="(row: ServiceOut) => row.name"
      :card-icon="() => 'pricetag-outline'"
      :entity-label="{ one: $t('service.services.entity.one'), many: $t('service.services.entity.many') }"
      :loading="status === 'loading'"
      :error="status === 'error' && !blocked ? $t('service.services.loadError') : undefined"
      :addable="canAdd"
      :row-clickable="canChange && !archivedView"
      :actions="actions"
      :search-placeholder="$t('service.services.search')"
      :labels="{ add: $t('service.services.new'), loadError: $t('service.services.loadError'), retry: $t('service.live.retry') }"
      :columns="columns"
      @filters-change="onFilters"
      @page-change="table.goToPage"
      @load-more="table.loadMore"
      @page-size-change="table.setPageSize"
      @sort-change="table.setSort"
      @row-click="onRowClick"
      @add="openForm(null)"
      @action="onAction"
      @retry="refresh()"
    >
      <template #status="{ row }">
        <span class="service-status">
          <StatusPill
            size="sm"
            :tone="TONE[row.status]"
            :label="t(`service.services.status.${row.status}`)"
          />
          <small
            v-if="row.status === 'unconfigured'"
            class="service-status__reason"
          >{{ t('service.services.statusReason') }}</small>
        </span>
      </template>
      <template #empty>
        <EmptyState
          data-testid="service-services-empty"
          icon="pricetag-outline"
          :heading="table.filtered.value ? $t('service.noResults') : $t('service.services.empty')"
          :message="table.filtered.value ? $t('service.noResultsMessage') : undefined"
        />
      </template>
    </DataTable>
    <ServiceFormModal
      v-model:open="formOpen"
      :service="editing"
      :can-change="canChange"
    />
    <ConfirmDialog
      v-model:open="archiveOpen"
      testid="service-services-archive"
      tone="danger"
      :title="t('service.services.archive.title')"
      :message="archiving ? t('service.services.archive.message', { name: archiving.name }) : ''"
      :consequences="archiveConsequences"
      :confirm-label="t('service.services.archive.confirm')"
      :cancel-label="t('service.cancel')"
      :pending="archive.pending.value"
      :error="archive.error.value"
      @confirm="confirmArchive"
      @cancel="archiveOpen = false"
    />
  </AppPage>
</template>

<style scoped>
.service-status {
  display: inline-flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
}
.service-status__reason {
  font-size: 0.72rem;
  line-height: 1.2;
  color: var(--ion-color-danger-shade, #c5000f);
}
</style>
