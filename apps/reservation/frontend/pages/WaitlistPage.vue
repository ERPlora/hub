<script setup lang="ts">
// Reservations → Waitlist (WORKBOOK «Pantallas · Lista de espera»; RESERVATION-F14 to F16): the live
// `reservation.waitlist.list` in the order people were written down (day, preferred time, arrival) — Date,
// Pref. time, Guest, Phone, Party, Contacted and Status (Waiting, Converted) —, «Search guest, phone or
// email…», filters by day, guest, phone, contacted and status, 50 a page. «Add guest» opens the form; per
// row «Contacted» (until called), «Convert» (until converted: it books the entry's own data; a full slot
// asks first, «Convert anyway») and «Remove» (asks first).
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
import { useCommand } from '@erplora/ui/sdk';
import { AppPage, useSession } from '@erplora/ui/shell';
import { computed, ref, shallowRef } from 'vue';

import { formatPhone } from '../../../customer/frontend/lib/phoneDisplay';
import PageNotices, { blockingError } from '../components/PageNotices.vue';
import WaitlistFormModal from '../components/WaitlistFormModal.vue';
import { useLiveList } from '../composables/useLiveList';
import { useServerTable } from '../composables/useServerTable';
import { useLocale, useT } from '../composables/useT';
import { formatDay, formatShortDate, formatTime, todayIn } from '../lib/clock';
import type { WaitlistOut } from '../operations';
import { reservationTabs } from '../tabs';

/** The business's zone in phase 1 (the Hub keeps no zone yet): the day a new entry starts on. */
const FALLBACK_ZONE = 'Europe/Madrid';

const session = useSession();
const t = useT();
const locale = useLocale();
const canChange = computed(() => session.can('reservation.change_waitlistentry'));

const table = useServerTable({ sort: 'position' });
const filters = ref<DataTableFilters>({});
const query = computed(() => {
  const f = filters.value;
  return {
    ...(f.date ? { date_from: f.date, date_to: f.date } : {}),
    ...(f.guest_name ? { guest_name: f.guest_name } : {}),
    ...(f.guest_phone ? { guest_phone: f.guest_phone } : {}),
    ...(f.is_contacted ? { is_contacted: f.is_contacted === 'true' } : {}),
    ...(f.is_converted ? { is_converted: f.is_converted === 'true' } : {}),
  };
});

function onFilters(next: DataTableFilters): void {
  filters.value = next;
  table.restart({ narrowed: Object.keys(next).length > 0 });
}

const { data: result, status, error, refresh } = useLiveList(
  'reservation.waitlist.list',
  () => ({ ...query.value, ...table.query.value }),
  () => table.windows.value,
);
table.followResult(result);
const blocked = computed(() => blockingError(error.value));

const guestOf = (row: { guest_name: string }): string => row.guest_name || t('reservation.erasedCustomer');
const columns = computed<DataTableColumn<WaitlistOut>[]>(() => [
  {
    key: 'date',
    label: t('reservation.waitlist.columns.date'),
    sortable: true,
    format: (_, row) => formatShortDate(row.date, locale.value),
    filter: { type: 'date' },
  },
  {
    key: 'preferred_time',
    label: t('reservation.waitlist.columns.time'),
    sortable: true,
    format: (_, row) => formatTime(row.preferred_time, locale.value),
  },
  { key: 'guest_name', label: t('reservation.waitlist.columns.guest'), sortable: true, priority: 'high', cell: 'guest', filter: { type: 'text' } },
  // As Customers paints it (+34 600 111 222): the waitlist keeps it in E.164; the filter is the server's, by digits.
  {
    key: 'guest_phone',
    label: t('reservation.waitlist.columns.phone'),
    sortable: true,
    priority: 'low',
    format: (_, row) => formatPhone(row.guest_phone),
    filter: { type: 'text' },
  },
  { key: 'party_size', label: t('reservation.waitlist.columns.party'), sortable: true, align: 'right', format: (_, row) => String(row.party_size) },
  {
    key: 'is_contacted',
    label: t('reservation.waitlist.columns.contacted'),
    sortable: true,
    format: (_, row) => (row.is_contacted ? t('reservation.yes') : t('reservation.no')),
    filter: {
      type: 'select',
      options: [
        { value: 'true', label: t('reservation.yes') },
        { value: 'false', label: t('reservation.no') },
      ],
    },
  },
  {
    key: 'is_converted',
    label: t('reservation.waitlist.columns.state'),
    cell: 'state',
    filter: {
      type: 'select',
      options: [
        { value: 'false', label: t('reservation.waitlist.states.waiting') },
        { value: 'true', label: t('reservation.waitlist.states.converted') },
      ],
    },
  },
]);

const actions = computed<DataTableAction<WaitlistOut>[]>(() =>
  canChange.value
    ? [
        {
          id: 'contact',
          label: t('reservation.waitlist.actions.contact'),
          icon: 'chatbubbles-outline',
          color: 'primary',
          hidden: (row) => row.is_contacted || row.is_converted,
        },
        {
          id: 'convert',
          label: t('reservation.waitlist.actions.convert'),
          icon: 'checkmark-circle-outline',
          color: 'success',
          showLabel: true,
          hidden: (row) => row.is_converted,
        },
        { id: 'remove', label: t('reservation.waitlist.actions.remove'), icon: 'trash-outline', color: 'danger' },
      ]
    : [],
);

const update = useCommand('reservation.waitlist.update');
const convert = useCommand('reservation.waitlist.convert');
const remove = useCommand('reservation.waitlist.delete');

const formOpen = ref(false);
const pageError = ref<string | null>(null);
const outcome = ref<string | null>(null);
const overbookRow = shallowRef<WaitlistOut | null>(null);
const overbookMessage = ref('');
const removing = shallowRef<WaitlistOut | null>(null);

const today = computed(() => todayIn(FALLBACK_ZONE));
const when = (row: WaitlistOut): string => `${formatDay(row.date, locale.value)} · ${formatTime(row.preferred_time, locale.value)}`;

async function attempt(work: () => Promise<void>): Promise<boolean> {
  pageError.value = null;
  outcome.value = null;
  try {
    await work();
    return true;
  } catch (caught) {
    pageError.value = (caught as Error)?.message || t('reservation.waitlist.actions.failed');
    return false;
  }
}

async function convertEntry(row: WaitlistOut, overbook: boolean): Promise<void> {
  pageError.value = null;
  outcome.value = null;
  try {
    const done = await convert.run({ id: row.id, overbook });
    const booked = done.reservation;
    outcome.value = t('reservation.waitlist.converted', {
      guest: guestOf(booked),
      when: `${formatDay(booked.date, locale.value)} · ${formatTime(booked.time, locale.value)}`,
    });
  } catch (caught) {
    const failure = caught as { code?: string; message?: string; fields?: Record<string, string> };
    // The server says when a full slot may be filled anyway (`fields.overbook`).
    if (failure?.code === 'reservation.no_capacity' && failure.fields?.overbook && !overbook) {
      overbookRow.value = row;
      overbookMessage.value = failure.message ?? '';
    } else {
      pageError.value = failure?.message || t('reservation.waitlist.actions.failed');
    }
  }
}

function onAction({ actionId, row }: { actionId: string; row: WaitlistOut }): void {
  if (actionId === 'contact') void attempt(async () => void (await update.run({ id: row.id, is_contacted: true })));
  if (actionId === 'convert') void convertEntry(row, false);
  if (actionId === 'remove') removing.value = row;
}

async function convertAnyway(): Promise<void> {
  const row = overbookRow.value;
  overbookRow.value = null;
  if (row) await convertEntry(row, true);
}

async function confirmRemove(): Promise<void> {
  const row = removing.value;
  if (!row) return;
  const done = await attempt(async () => void (await remove.run({ id: row.id })));
  if (done) removing.value = null;
}
</script>

<template>
  <AppPage
    :title="$t('reservation.title')"
    content-layout="fill"
    :tabs="reservationTabs($t, { settings: session.can('reservation.manage_settings') })"
    :tabs-label="$t('reservation.tabs.label')"
  >
    <PageNotices
      testid="reservation-waitlist"
      :status="status"
      :error="error"
    />
    <InlineFeedback
      v-if="pageError"
      tone="danger"
      dismissible
      data-testid="reservation-waitlist-page-error"
      :heading="$t('reservation.waitlist.actions.failed')"
    >
      {{ pageError }}
    </InlineFeedback>
    <InlineFeedback
      v-if="outcome"
      tone="success"
      dismissible
      data-testid="reservation-waitlist-outcome"
    >
      {{ outcome }}
    </InlineFeedback>
    <DataTable
      v-if="!blocked"
      v-model:search="table.search.value"
      testid="reservation-waitlist"
      server-side
      searchable
      filterable
      fill
      :filters="filters"
      :rows="result?.rows ?? []"
      :total="result?.total ?? 0"
      :page="table.page.value"
      :page-size="table.pageSize.value"
      :sort="table.sort.value"
      :sort-dir="table.dir.value"
      :views="['table', 'cards']"
      :card-title="guestOf"
      :card-icon="() => 'people-outline'"
      :entity-label="{ one: $t('reservation.waitlist.entity.one'), many: $t('reservation.waitlist.entity.many') }"
      :loading="status === 'loading'"
      :error="status === 'error' && !blocked ? $t('reservation.waitlist.loadError') : undefined"
      :addable="canChange"
      :actions="actions"
      :search-placeholder="$t('reservation.waitlist.search')"
      :labels="{ add: $t('reservation.waitlist.add'), loadError: $t('reservation.waitlist.loadError'), retry: $t('reservation.retry') }"
      :columns="columns"
      @filters-change="onFilters"
      @page-change="table.goToPage"
      @load-more="table.loadMore"
      @page-size-change="table.setPageSize"
      @sort-change="table.setSort"
      @add="formOpen = true"
      @action="onAction"
      @retry="refresh()"
    >
      <template #guest="{ row }">
        <span :class="{ 'reservation-waitlist__erased': !row.guest_name }">{{ guestOf(row) }}</span>
      </template>
      <template #state="{ row }">
        <StatusPill
          size="sm"
          :tone="row.is_converted ? 'success' : 'warning'"
          :label="row.is_converted ? $t('reservation.waitlist.states.converted') : $t('reservation.waitlist.states.waiting')"
        />
      </template>
      <template #empty>
        <EmptyState
          data-testid="reservation-waitlist-empty"
          icon="people-outline"
          :heading="$t('reservation.waitlist.empty')"
        />
      </template>
    </DataTable>
    <WaitlistFormModal
      v-model:open="formOpen"
      :day="today"
    />
    <ConfirmDialog
      :open="overbookRow !== null"
      testid="reservation-waitlist-overbook"
      tone="warning"
      :title="t('reservation.overbook.title')"
      :message="t('reservation.overbook.message', { message: overbookMessage })"
      :confirm-label="t('reservation.overbook.convert')"
      :cancel-label="t('reservation.cancelButton')"
      :pending="convert.pending.value"
      @update:open="(value: boolean) => !value && (overbookRow = null)"
      @confirm="convertAnyway"
      @cancel="overbookRow = null"
    />
    <ConfirmDialog
      :open="removing !== null"
      testid="reservation-waitlist-remove"
      tone="danger"
      :title="t('reservation.waitlist.remove.title')"
      :message="removing ? t('reservation.waitlist.remove.message', { guest: guestOf(removing), when: when(removing) }) : ''"
      :confirm-label="t('reservation.waitlist.remove.confirm')"
      :cancel-label="t('reservation.cancelButton')"
      :pending="remove.pending.value"
      @update:open="(value: boolean) => !value && (removing = null)"
      @confirm="confirmRemove"
      @cancel="removing = null"
    />
  </AppPage>
</template>

<style scoped>
.reservation-waitlist__erased {
  font-style: italic;
  color: var(--ion-color-medium, #8b897f);
}
</style>
