<script setup lang="ts">
// Kitchen → Tickets (WORKBOOK «Pantallas · Comandas»; KITCHEN-F21 to F23): every ticket, live
// (`kitchen.ticket.list`), newest first, 50 a page. Ticket (its full number YYYYMMDD-NNNN), Destination, Type,
// Priority, Status, Dishes, Total and Sent; «Search ticket or destination…», filters by type, priority and
// status, table or cards. Row actions, icon only, only for whoever may and only when the status allows:
// Fire, Ready, Served, Recall, Reprint and Cancel (in «⋮», asks first with an optional reason). A row opens
// its detail; «New ticket» opens the form (its type starts at the settings' default).
import {
  ConfirmDialog,
  DataTable,
  type DataTableAction,
  type DataTableColumn,
  type DataTableFilters,
  EmptyState,
  InlineFeedback,
} from '@erplora/ui/components';
import { type ApiError, useCommand, useLive } from '@erplora/ui/sdk';
import { AppPage, useSession } from '@erplora/ui/shell';
import { IonInput } from '@ionic/vue';
import { computed, ref } from 'vue';

import PageNotices, { blockingError } from '../components/PageNotices.vue';
import TicketDetailModal from '../components/TicketDetailModal.vue';
import TicketFormModal from '../components/TicketFormModal.vue';
import { useLiveList } from '../composables/useLiveList';
import { useServerTable } from '../composables/useServerTable';
import { useLocale, useT } from '../composables/useT';
import { formatDateTime, formatMoney } from '../lib/format';
import type { OrderType, Priority, TicketListIn, TicketRowOut, TicketStatus } from '../operations';
import { kitchenTabs } from '../tabs';

const STATUSES: readonly TicketStatus[] = ['pending', 'preparing', 'ready', 'served', 'cancelled'];
const TYPES: readonly OrderType[] = ['dine_in', 'takeaway', 'delivery'];
const PRIORITIES: readonly Priority[] = ['normal', 'rush', 'vip'];
const COOKING: readonly TicketStatus[] = ['pending', 'preparing'];
const ON_THE_LINE: readonly TicketStatus[] = ['pending', 'preparing', 'ready'];

const session = useSession();
const t = useT();
const locale = useLocale();
const canAdd = computed(() => session.can('kitchen.add_ticket'));
const canChange = computed(() => session.can('kitchen.change_ticket'));
const canServe = computed(() => session.can('kitchen.complete_ticket'));
const canCancel = computed(() => session.can('kitchen.cancel_ticket'));

const { data: settings } = useLive('kitchen.settings.get', {});
const timezone = computed(() => settings.value?.timezone ?? 'Europe/Madrid');

const table = useServerTable({ sort: '-received_at' });
const filters = ref<DataTableFilters>({});
const query = computed<Partial<TicketListIn>>(() => {
  const f = filters.value;
  return {
    ...(f.status ? { status: f.status as TicketStatus } : {}),
    ...(f.order_type ? { order_type: f.order_type as OrderType } : {}),
    ...(f.priority ? { priority: f.priority as Priority } : {}),
  };
});

function onFilters(now: DataTableFilters): void {
  filters.value = now;
  table.restart({ narrowed: Object.keys(now).length > 0 });
}

const { data: result, status, error, refresh } = useLiveList('kitchen.ticket.list', () => ({ ...table.query.value, ...query.value }), () => table.windows.value);
table.followResult(result);
const blocked = computed(() => blockingError(error.value));

const options = (values: readonly string[], prefix: string) => values.map((value) => ({ value, label: t(`${prefix}.${value}`) }));

const columns = computed<DataTableColumn<TicketRowOut>[]>(() => [
  { key: 'number', label: t('kitchen.tickets.columns.number'), sortable: true, priority: 'high' },
  { key: 'label', label: t('kitchen.tickets.columns.label'), format: (_, r) => r.label || '—' },
  {
    key: 'order_type',
    label: t('kitchen.tickets.columns.type'),
    format: (_, r) => t(`kitchen.orderType.${r.order_type}`),
    filter: { type: 'select', options: options(TYPES, 'kitchen.orderType') },
  },
  {
    key: 'priority',
    label: t('kitchen.tickets.columns.priority'),
    format: (_, r) => t(`kitchen.priority.${r.priority}`),
    filter: { type: 'select', options: options(PRIORITIES, 'kitchen.priority') },
  },
  {
    key: 'status',
    label: t('kitchen.tickets.columns.status'),
    sortable: true,
    format: (_, r) => t(`kitchen.status.${r.status}`),
    filter: { type: 'select', options: options(STATUSES, 'kitchen.status') },
  },
  { key: 'items_count', label: t('kitchen.tickets.columns.items'), align: 'right' },
  { key: 'total', label: t('kitchen.tickets.columns.total'), sortable: true, align: 'right', format: (_, r) => formatMoney(r.total, locale.value) },
  {
    key: 'received_at',
    label: t('kitchen.tickets.columns.received'),
    sortable: true,
    width: 'minmax(8.5rem,1fr)',
    format: (_, r) => formatDateTime(r.received_at, locale.value, timezone.value),
  },
]);

const actions = computed<DataTableAction<TicketRowOut>[]>(() => [
  { id: 'detail', label: t('kitchen.tickets.actions.detail'), icon: 'information-circle-outline' },
  ...(canChange.value
    ? [
        { id: 'start', label: t('kitchen.tickets.actions.start'), icon: 'chevron-forward-outline', hidden: (r: TicketRowOut) => r.status !== 'pending' },
        { id: 'ready', label: t('kitchen.tickets.actions.ready'), icon: 'checkmark-circle-outline', color: 'success', hidden: (r: TicketRowOut) => !COOKING.includes(r.status) },
      ]
    : []),
  ...(canServe.value ? [{ id: 'serve', label: t('kitchen.tickets.actions.serve'), icon: 'checkmark-outline', color: 'success', hidden: (r: TicketRowOut) => r.status !== 'ready' }] : []),
  ...(canChange.value
    ? [
        { id: 'recall', label: t('kitchen.tickets.actions.recall'), icon: 'arrow-undo-outline', hidden: (r: TicketRowOut) => r.status !== 'ready' },
        { id: 'reprint', label: t('kitchen.tickets.actions.reprint'), icon: 'receipt-outline', menuOnly: true },
      ]
    : []),
  ...(canCancel.value
    ? [
        {
          id: 'cancel',
          label: t('kitchen.tickets.actions.cancel'),
          icon: 'close-circle-outline',
          color: 'danger',
          menuOnly: true,
          hidden: (r: TicketRowOut) => !ON_THE_LINE.includes(r.status),
        },
      ]
    : []),
]);

const start = useCommand('kitchen.ticket.start');
const ready = useCommand('kitchen.ticket.ready');
const serve = useCommand('kitchen.ticket.serve');
const recall = useCommand('kitchen.ticket.recall');
const reprint = useCommand('kitchen.ticket.reprint');
const cancel = useCommand('kitchen.ticket.cancel');
const STEPS = { start, ready, serve, recall } as const;
const actionError = ref<ApiError | null>(null);
const reprinted = ref<string | null>(null);

const target = ref<TicketRowOut | null>(null);
const detailOpen = ref(false);
const formOpen = ref(false);
const cancelOpen = ref(false);
const reason = ref('');

async function step(run: () => Promise<unknown>): Promise<void> {
  actionError.value = null;
  reprinted.value = null;
  try {
    await run();
  } catch (refused) {
    actionError.value = refused as ApiError;
  }
}

function onAction({ actionId, row }: { actionId: string; row: TicketRowOut }): void {
  target.value = row;
  if (actionId === 'detail') detailOpen.value = true;
  else if (actionId === 'cancel') {
    cancel.error.value = null;
    reason.value = '';
    cancelOpen.value = true;
  } else if (actionId === 'reprint') {
    void step(async () => {
      await reprint.run({ ticket_id: row.id });
      reprinted.value = row.number;
    });
  } else if (actionId in STEPS) {
    void step(() => STEPS[actionId as keyof typeof STEPS].run({ ticket_id: row.id }));
  }
}

function openDetail(row: TicketRowOut): void {
  target.value = row;
  detailOpen.value = true;
}

async function confirmCancel(): Promise<void> {
  if (!target.value) return;
  try {
    await cancel.run({ ticket_id: target.value.id, reason: reason.value.trim() });
  } catch {
    return; // The dialog says why.
  }
  cancelOpen.value = false;
}
</script>

<template>
  <AppPage
    :title="$t('kitchen.title')"
    :tabs="kitchenTabs($t, { settings: session.can('kitchen.change_settings') })"
    :tabs-label="$t('kitchen.tabs.label')"
  >
    <PageNotices
      testid="kitchen-tickets"
      :status="status"
      :error="error"
    />
    <InlineFeedback
      v-if="actionError"
      tone="danger"
      data-testid="kitchen-tickets-action-error"
      :heading="$t('kitchen.tickets.actionError')"
    >
      {{ actionError.message }}
    </InlineFeedback>
    <InlineFeedback
      v-if="reprinted"
      tone="success"
      data-testid="kitchen-tickets-reprinted"
    >
      {{ $t('kitchen.tickets.reprinted', { number: reprinted }) }}
    </InlineFeedback>
    <DataTable
      v-if="!blocked"
      v-model:search="table.search.value"
      testid="kitchen-tickets"
      server-side
      searchable
      row-clickable
      :filters="filters"
      :rows="result?.rows ?? []"
      :total="result?.total ?? 0"
      :page="table.page.value"
      :page-size="table.pageSize.value"
      :sort="table.sort.value"
      :sort-dir="table.dir.value"
      :views="['table', 'cards']"
      :card-title="(r: TicketRowOut) => `#${r.short_number} ${r.label}`.trim()"
      :card-icon="() => 'ticket-outline'"
      :entity-label="{ one: $t('kitchen.tickets.entity.one'), many: $t('kitchen.tickets.entity.many') }"
      :loading="status === 'loading'"
      :error="status === 'error' && !blocked ? $t('kitchen.tickets.loadError') : undefined"
      :actions="actions"
      :primary-action="canAdd ? { label: $t('kitchen.tickets.new'), icon: 'add-outline' } : undefined"
      :search-placeholder="$t('kitchen.tickets.search')"
      :labels="{ loadError: $t('kitchen.tickets.loadError'), retry: $t('kitchen.live.retry') }"
      :columns="columns"
      :card-breakpoint="900"
      @filters-change="onFilters"
      @page-change="table.goToPage"
      @load-more="table.loadMore"
      @page-size-change="table.setPageSize"
      @sort-change="table.setSort"
      @action="onAction"
      @row-click="openDetail"
      @primary-action="formOpen = true"
      @retry="refresh()"
    >
      <template #empty>
        <EmptyState
          data-testid="kitchen-tickets-empty"
          icon="ticket-outline"
          :heading="table.filtered.value ? $t('kitchen.noResults') : $t('kitchen.tickets.empty')"
          :message="table.filtered.value ? $t('kitchen.noResultsMessage') : undefined"
        />
      </template>
    </DataTable>
    <TicketDetailModal
      v-if="detailOpen && target"
      v-model:open="detailOpen"
      :ticket-id="target.id"
      :timezone="timezone"
    />
    <TicketFormModal
      v-model:open="formOpen"
      :default-type="settings?.default_order_type ?? 'dine_in'"
      @saved="table.goToPage(0)"
    />
    <ConfirmDialog
      v-model:open="cancelOpen"
      testid="kitchen-tickets-cancel"
      tone="danger"
      :title="t('kitchen.tickets.cancelDialog.title', { number: target?.number ?? '' })"
      :confirm-label="t('kitchen.tickets.cancelDialog.confirm')"
      :cancel-label="t('kitchen.close')"
      :pending="cancel.pending.value"
      :error="cancel.error.value"
      @confirm="confirmCancel"
      @cancel="cancelOpen = false"
    >
      <p>{{ t('kitchen.tickets.cancelDialog.message') }}</p>
      <ion-input
        data-testid="kitchen-tickets-cancel-reason"
        :value="reason"
        :label="t('kitchen.tickets.cancelDialog.reason')"
        label-placement="floating"
        fill="outline"
        mode="md"
        :maxlength="255"
        @ion-input="reason = String($event.detail.value ?? '')"
      />
    </ConfirmDialog>
  </AppPage>
</template>
