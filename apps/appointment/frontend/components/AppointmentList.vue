<script setup lang="ts">
// The agenda's «List» (WORKBOOK «Agenda»; the old `ok-data-table`): Time, No., Customer, Service,
// Professional and Status, «Search no., customer or service…», list or cards. Per row: Charge, Edit,
// Confirm, Start, Complete, No-show, Cancel, History and Delete — the one the row's state does not allow
// is greyed out, never hidden (`lib/states.ts`, the server's rules); Delete exists only for who may
// delete. The rows are the day's (or the week's) appointments, all of them: the page reads them live.
import {
  DataTable,
  type DataTableAction,
  type DataTableColumn,
  EmptyState,
  StatusPill,
} from '@erplora/ui/components';
import { computed } from 'vue';

import { useLocale, useT } from '../composables/useT';
import { dayOf, formatShortDay, formatTime, timeOf } from '../lib/clock';
import { ACTIONS, type AgendaAction, allows, customerLabel, hasOpenCheck, STATUS_TONE } from '../lib/states';
import type { AppointmentRow } from '../operations';

const props = withDefaults(
  defineProps<{
    rows: AppointmentRow[];
    now: Date;
    canAdd: boolean;
    canDelete: boolean;
    loading?: boolean;
    error?: string;
    /** The rows span several days (a week): the time says its day too. */
    withDay?: boolean;
    emptyMessage?: string;
  }>(),
  { loading: false, error: undefined, withDay: false, emptyMessage: undefined },
);

const emit = defineEmits<{ action: [event: { actionId: string; row: AppointmentRow }]; add: []; retry: [] }>();

const t = useT();
const locale = useLocale();

const ICONS: Record<AgendaAction, string> = {
  charge: 'cash-outline',
  edit: 'create-outline',
  confirm: 'checkmark-outline',
  start: 'sync-outline',
  complete: 'checkmark-circle-outline',
  no_show: 'person-remove-outline',
  cancel: 'close-circle-outline',
  history: 'time-outline',
  delete: 'trash-outline',
};
const COLORS: Partial<Record<AgendaAction, string>> = {
  charge: 'success',
  edit: 'primary',
  confirm: 'success',
  start: 'primary',
  complete: 'success',
  no_show: 'warning',
  cancel: 'danger',
  delete: 'danger',
};

const when = (row: AppointmentRow): string => {
  const time = formatTime(timeOf(row.start), locale.value);
  return props.withDay ? `${formatShortDay(dayOf(row.start), locale.value)} · ${time}` : time;
};

const columns = computed<DataTableColumn<AppointmentRow>[]>(() => [
  { key: 'start', label: t('appointment.list.columns.time'), priority: 'high', width: props.withDay ? '9rem' : '6rem', format: (_, row) => when(row) },
  { key: 'number', label: t('appointment.list.columns.number'), width: '11rem' },
  { key: 'customer_name', label: t('appointment.list.columns.customer'), priority: 'high', format: (_, row) => customerLabel(row, t) },
  { key: 'service_names', label: t('appointment.list.columns.service') },
  {
    key: 'staff_name',
    label: t('appointment.list.columns.staff'),
    format: (_, row) => (row.staff_id ? row.staff_name : t('appointment.list.unassigned')),
  },
  { key: 'status', label: t('appointment.list.columns.status'), cell: 'status', width: '9rem' },
]);

const actions = computed<DataTableAction<AppointmentRow>[]>(() =>
  ACTIONS.filter((id) => id !== 'delete' || props.canDelete).map((id) => ({
    id,
    label: id === 'charge' ? (row: AppointmentRow) => t(hasOpenCheck(row) ? 'appointment.actions.goToCheck' : 'appointment.actions.charge') : t(`appointment.actions.${id}`),
    icon: ICONS[id],
    color: COLORS[id] ?? 'medium',
    pinned: id === 'charge',
    showLabel: id === 'charge',
    disabled: (row: AppointmentRow) => !allows(id, row, props.now),
  })),
);
</script>

<template>
  <DataTable
    testid="appointment-list"
    searchable
    :rows="rows"
    :columns="columns"
    :actions="actions"
    :page-size="100"
    :search-keys="['number', 'customer_name', 'service_names', 'staff_name']"
    :search-placeholder="$t('appointment.list.search')"
    :views="['table', 'cards']"
    :card-title="(row: AppointmentRow) => `${when(row)} · ${customerLabel(row, t)}`"
    :card-icon="() => 'calendar-outline'"
    :entity-label="{ one: $t('appointment.list.entity.one'), many: $t('appointment.list.entity.many') }"
    :loading="loading"
    :error="error"
    :addable="canAdd"
    :labels="{ add: $t('appointment.toolbar.add'), loadError: $t('appointment.list.loadError'), retry: $t('appointment.retry') }"
    @action="emit('action', $event)"
    @add="emit('add')"
    @retry="emit('retry')"
  >
    <template #status="{ row }">
      <span class="appointment-status">
        <StatusPill
          size="sm"
          :tone="STATUS_TONE[row.status as AppointmentRow['status']]"
          :label="t(`appointment.status.${row.status}`)"
        />
        <StatusPill
          v-if="row.sale_id"
          size="sm"
          tone="success"
          :label="$t('appointment.list.charged')"
        />
      </span>
    </template>
    <template #empty>
      <EmptyState
        data-testid="appointment-list-empty"
        icon="calendar-outline"
        :heading="emptyMessage ?? $t('appointment.list.empty')"
      />
    </template>
  </DataTable>
</template>

<style scoped>
.appointment-status {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 4px;
}
</style>
