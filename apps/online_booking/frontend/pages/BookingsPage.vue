<script setup lang="ts">
// Online booking → Bookings (WORKBOOK «Reservas (bandeja)»; ONLINE_BOOKING-F02 to F06, F08): the live
// `online_booking.booking.list` (the diary's appointments booked online) in a server-side DataTable — No.,
// Customer with her phone, Service, Professional, Date, Time, Status and Booked —, the newest first, search,
// column filters, list or cards, 50 a page. Per row Confirm, Complete, No-show, Cancel (its dialog, with a
// reason) and Delete (its confirmation, only for who may delete), greyed out when the state does not allow
// them (the diary's rules, `lib/actions.ts`). What changes comes back through the stream.
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
import { type ApiError, useCommand } from '@erplora/ui/sdk';
import { AppPage, useSession } from '@erplora/ui/shell';
import { computed, ref } from 'vue';

import { dayOf, formatShortDate, formatTime, timeOf } from '../../../appointment/frontend/lib/clock';
import { STATUS_TONE } from '../../../appointment/frontend/lib/states';
import CancelDialog from '../components/CancelDialog.vue';
import PageNotices, { blockingError } from '../components/PageNotices.vue';
import { useLiveList } from '../composables/useLiveList';
import { useServerTable } from '../composables/useServerTable';
import { useLocale, useT } from '../composables/useT';
import { allowed, type InboxAction, inboxActions } from '../lib/actions';
import type { BookingListIn, BookingRow, BookingSort, BookingStatus } from '../operations';
import { onlineBookingTabs } from '../tabs';

const STATUSES: readonly BookingStatus[] = ['pending', 'confirmed', 'in_progress', 'completed', 'cancelled', 'no_show'];
const ICONS: Record<InboxAction, string> = {
  confirm: 'checkmark-outline',
  complete: 'checkmark-circle-outline',
  no_show: 'person-remove-outline',
  cancel: 'close-circle-outline',
  delete: 'trash-outline',
};
const COLORS: Record<InboxAction, string> = {
  confirm: 'success',
  complete: 'primary',
  no_show: 'medium',
  cancel: 'warning',
  delete: 'danger',
};

const session = useSession();
const t = useT();
const locale = useLocale();

const table = useServerTable({ sort: 'booked_at', dir: 'desc' });
const filters = ref<DataTableFilters>({});

/** The table's filters as the query takes them: a day is its first and last day. */
const query = computed<Partial<BookingListIn>>(() => {
  const { date, status, ...text } = filters.value;
  return {
    ...text,
    ...(date ? { date_from: date, date_to: date } : {}),
    ...(status ? { status: status as BookingStatus } : {}),
  };
});

function onFilters(now: DataTableFilters): void {
  filters.value = now;
  table.restart({ narrowed: Object.keys(now).length > 0 });
}

const { data: result, status, error, refresh } = useLiveList(
  'online_booking.booking.list',
  () => ({ ...query.value, ...table.query.value, sort: table.query.value.sort as BookingSort }),
  () => table.windows.value,
);
table.followResult(result);
const blocked = computed(() => blockingError(error.value));

const customer = (row: BookingRow): string => row.customer_name || t('online_booking.bookings.erasedCustomer');
const day = (moment: string): string => formatShortDate(dayOf(moment), locale.value);
const time = (moment: string): string => formatTime(timeOf(moment), locale.value);

const columns = computed<DataTableColumn<BookingRow>[]>(() => [
  { key: 'number', label: t('online_booking.bookings.columns.number'), sortable: true, width: '11rem', filter: { type: 'text' } },
  {
    key: 'customer_name',
    label: t('online_booking.bookings.columns.customer'),
    sortable: true,
    priority: 'high',
    cell: 'customer',
    format: (_, row) => customer(row),
    filter: { type: 'text' },
  },
  { key: 'service_names', label: t('online_booking.bookings.columns.service'), filter: { type: 'text', key: 'service' } },
  {
    key: 'staff_name',
    label: t('online_booking.bookings.columns.staff'),
    sortable: true,
    format: (_, row) => (row.staff_id ? row.staff_name : t('online_booking.bookings.unassigned')),
    filter: { type: 'text' },
  },
  {
    key: 'start',
    label: t('online_booking.bookings.columns.date'),
    sortable: true,
    priority: 'high',
    format: (_, row) => day(row.start),
    filter: { type: 'date', key: 'date' },
  },
  { key: 'time', label: t('online_booking.bookings.columns.time'), width: '6rem', format: (_, row) => time(row.start) },
  {
    key: 'status',
    label: t('online_booking.bookings.columns.status'),
    sortable: true,
    cell: 'status',
    width: '9rem',
    format: (_, row) => t(`online_booking.bookings.status.${row.status}`),
    filter: { type: 'select', options: STATUSES.map((value) => ({ value, label: t(`online_booking.bookings.status.${value}`) })) },
  },
  {
    key: 'booked_at',
    label: t('online_booking.bookings.columns.bookedAt'),
    sortable: true,
    priority: 'low',
    format: (_, row) => `${day(row.booked_at)} · ${time(row.booked_at)}`,
  },
]);

const actions = computed<DataTableAction<BookingRow>[]>(() =>
  inboxActions((permission) => session.can(permission)).map((id) => ({
    id,
    label: t(`online_booking.bookings.actions.${id}`),
    icon: ICONS[id],
    color: COLORS[id],
    disabled: (row: BookingRow) => !allowed(id, row, new Date()),
  })),
);

// Row actions
const confirmBooking = useCommand('online_booking.booking.confirm');
const completeBooking = useCommand('online_booking.booking.complete');
const noShowBooking = useCommand('online_booking.booking.no_show');
const deleteBooking = useCommand('online_booking.booking.delete');
const rowError = ref<ApiError | null>(null);
const cancelling = ref<BookingRow | null>(null);
const cancelOpen = ref(false);
const deleting = ref<BookingRow | null>(null);
const deleteOpen = ref(false);

const DIRECT = { confirm: confirmBooking, complete: completeBooking, no_show: noShowBooking } as const;

async function onAction({ actionId, row }: { actionId: string; row: BookingRow }): Promise<void> {
  rowError.value = null;
  if (actionId === 'cancel') {
    cancelling.value = row;
    cancelOpen.value = true;
    return;
  }
  if (actionId === 'delete') {
    deleteBooking.error.value = null;
    deleting.value = row;
    deleteOpen.value = true;
    return;
  }
  const command = DIRECT[actionId as keyof typeof DIRECT];
  if (!command) return;
  try {
    await command.run({ id: row.id });
  } catch {
    rowError.value = command.error.value;
  }
}

async function confirmDelete(): Promise<void> {
  if (!deleting.value) return;
  try {
    await deleteBooking.run({ id: deleting.value.id });
  } catch {
    return; // The dialog says why.
  }
  deleteOpen.value = false;
}
</script>

<template>
  <AppPage
    :title="$t('online_booking.title')"
    content-layout="fill"
    :tabs="onlineBookingTabs(t, { settings: session.can('online_booking.manage_settings') })"
    :tabs-label="$t('online_booking.tabs.label')"
  >
    <PageNotices
      testid="ob-bookings"
      :status="status"
      :error="error"
    />
    <InlineFeedback
      v-if="rowError"
      tone="danger"
      dismissible
      data-testid="ob-bookings-row-error"
      :heading="t('online_booking.bookings.actionError')"
      @dismiss="rowError = null"
    >
      {{ rowError.message }}
    </InlineFeedback>
    <DataTable
      v-if="!blocked"
      v-model:search="table.search.value"
      testid="ob-bookings"
      fill
      server-side
      searchable
      filterable
      row-key="id"
      :filters="filters"
      :rows="result?.rows ?? []"
      :total="result?.total ?? 0"
      :page="table.page.value"
      :page-size="table.pageSize.value"
      :sort="table.sort.value"
      :sort-dir="table.dir.value"
      :views="['table', 'cards']"
      :card-title="(row: BookingRow) => `${row.number} · ${customer(row)}`"
      :card-icon="() => 'calendar-outline'"
      :entity-label="{ one: $t('online_booking.bookings.entity.one'), many: $t('online_booking.bookings.entity.many') }"
      :loading="status === 'loading'"
      :error="status === 'error' && !blocked ? $t('online_booking.bookings.loadError') : undefined"
      :addable="false"
      :actions="actions"
      :search-placeholder="$t('online_booking.bookings.search')"
      :labels="{ loadError: $t('online_booking.bookings.loadError'), retry: $t('online_booking.live.retry') }"
      :columns="columns"
      @filters-change="onFilters"
      @page-change="table.goToPage"
      @load-more="table.loadMore"
      @page-size-change="table.setPageSize"
      @sort-change="table.setSort"
      @action="onAction"
      @retry="refresh()"
    >
      <template #customer="{ row }">
        <span class="ob-customer">
          <span data-testid="ob-bookings-customer-name">{{ customer(row) }}</span>
          <small v-if="row.customer_phone">{{ row.customer_phone }}</small>
        </span>
      </template>
      <template #status="{ row }">
        <StatusPill
          size="sm"
          :tone="STATUS_TONE[row.status as BookingStatus]"
          :label="t(`online_booking.bookings.status.${row.status}`)"
        />
      </template>
      <template #empty>
        <EmptyState
          data-testid="ob-bookings-empty"
          icon="calendar-outline"
          :heading="table.filtered.value ? $t('online_booking.bookings.noMatch') : $t('online_booking.bookings.empty')"
        />
      </template>
    </DataTable>
    <CancelDialog
      v-model:open="cancelOpen"
      :booking="cancelling"
    />
    <ConfirmDialog
      v-model:open="deleteOpen"
      testid="ob-bookings-delete"
      tone="danger"
      :title="t('online_booking.bookings.delete.title')"
      :message="deleting ? t('online_booking.bookings.delete.message', { number: deleting.number }) : ''"
      :confirm-label="t('online_booking.bookings.delete.confirm')"
      :cancel-label="t('online_booking.bookings.delete.keep')"
      :pending="deleteBooking.pending.value"
      :error="deleteBooking.error.value"
      @confirm="confirmDelete"
      @cancel="deleteOpen = false"
    />
  </AppPage>
</template>

<style scoped>
.ob-customer {
  display: inline-flex;
  flex-direction: column;
  gap: 2px;
  max-width: 100%;
  min-width: 0;
}
/* A long name ends in «…» inside its column instead of being cut off mid-letter. */
.ob-customer span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ob-customer small {
  font-size: 0.75rem;
  opacity: 0.7;
}
</style>
