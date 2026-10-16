<script setup lang="ts">
// «Repeating» (APPOINTMENT-F12 to F15), the third segment of the agenda: the series as a table — Customer,
// Service, Professional, Repeats («Every week · Monday · 11:00»), Starts, Ends («No end», «After {n}
// appointments» or the date) and the «Active» switch (pause / reactivate). Per row «Edit series», «Book
// appointments» and «Delete» (asked first: the booked appointments are kept); add opens «New repeating
// appointment». Booking runs turn after turn (50 a turn) until the window is booked, then says what was
// booked and what was skipped, with each date's reason, and what is left or when the next date comes.
import {
  ConfirmDialog,
  DataTable,
  type DataTableAction,
  type DataTableColumn,
  EmptyState,
  InlineFeedback,
} from '@erplora/ui/components';
import { type ApiError, useCommand } from '@erplora/ui/sdk';
import { IonToggle } from '@ionic/vue';
import { computed, ref } from 'vue';

import { useLiveWindows } from '../composables/useLiveWindows';
import { useLocale, useT } from '../composables/useT';
import { formatShortDate, formatTime } from '../lib/clock';
import { describeOutcome, type OutcomeText } from '../lib/outcome';
import type { MaterializeOut, RecurringOut, RecurringUpdatedOut } from '../operations';
import SeriesFormModal from './SeriesFormModal.vue';

const props = withDefaults(
  defineProps<{
    canAdd: boolean;
    canChange: boolean;
    businessToday: string;
    ownStaff?: { id: string; name: string } | null;
  }>(),
  { ownStaff: null },
);

/** Turns of 50 a single «Book appointments» runs at most. */
const MAX_TURNS = 20;

const t = useT();
const locale = useLocale();
const list = useLiveWindows<'appointment.recurring.list', RecurringOut>('appointment.recurring.list', () => ({ sort: 'customer_name' }), 100);

const activate = useCommand('appointment.recurring.activate');
const deactivate = useCommand('appointment.recurring.deactivate');
const materialize = useCommand('appointment.recurring.materialize');
const remove = useCommand('appointment.recurring.delete');
const rowError = ref<ApiError | null>(null);
const said = ref<OutcomeText | null>(null);

const formOpen = ref(false);
const editing = ref<RecurringOut | null>(null);
const deleting = ref<RecurringOut | null>(null);
const deleteOpen = ref(false);

function pattern(row: RecurringOut): string {
  const parts = [t(`appointment.series.frequency.${row.frequency}`)];
  if ((row.frequency === 'weekly' || row.frequency === 'biweekly') && row.day_of_week !== null) {
    parts.push(t(`appointment.weekday.${row.day_of_week}`));
  }
  parts.push(formatTime(row.time.slice(0, 5), locale.value));
  return parts.join(' · ');
}

function ends(row: RecurringOut): string {
  if (row.max_occurrences) return t('appointment.series.endsAfter', { n: row.max_occurrences });
  if (row.end_date) return formatShortDate(row.end_date, locale.value);
  return t('appointment.series.noEnd');
}

const columns = computed<DataTableColumn<RecurringOut>[]>(() => [
  { key: 'customer_name', label: t('appointment.series.columns.customer'), priority: 'high', format: (_, row) => row.customer_name || t('appointment.list.erasedCustomer') },
  { key: 'service_names', label: t('appointment.series.columns.service') },
  { key: 'staff_name', label: t('appointment.series.columns.staff'), format: (_, row) => (row.staff_id ? row.staff_name : t('appointment.series.noStaff')) },
  { key: 'frequency', label: t('appointment.series.columns.pattern'), format: (_, row) => pattern(row) },
  { key: 'start_date', label: t('appointment.series.columns.starts'), format: (_, row) => formatShortDate(row.start_date, locale.value), priority: 'low' },
  { key: 'end_date', label: t('appointment.series.columns.ends'), format: (_, row) => ends(row), priority: 'low' },
  { key: 'is_active', label: t('appointment.series.columns.active'), cell: 'active', width: '6rem' },
]);

const actions = computed<DataTableAction<RecurringOut>[]>(() =>
  props.canChange
    ? [
        { id: 'edit', label: t('appointment.series.actions.edit'), icon: 'create-outline', color: 'primary' },
        { id: 'materialize', label: t('appointment.series.actions.materialize'), icon: 'calendar-outline', color: 'success', disabled: (row) => !row.is_active },
        { id: 'delete', label: t('appointment.series.actions.delete'), icon: 'trash-outline', color: 'danger' },
      ]
    : [],
);

async function toggle(row: RecurringOut, active: boolean): Promise<void> {
  rowError.value = null;
  try {
    await (active ? activate : deactivate).run({ id: row.id });
  } catch (error) {
    rowError.value = error as ApiError;
  }
}

async function bookWindow(row: RecurringOut): Promise<void> {
  rowError.value = null;
  said.value = null;
  let total: MaterializeOut | null = null;
  let next: { from_date?: string; to_date?: string } = {};
  try {
    for (let turn = 0; turn < MAX_TURNS; turn += 1) {
      const answer = await materialize.run({ id: row.id, ...next });
      total = total
        ? { ...answer, booked: total.booked + answer.booked, skipped: [...total.skipped, ...answer.skipped] }
        : answer;
      if (!answer.next_from) break;
      next = { from_date: answer.next_from, to_date: answer.to };
    }
  } catch (error) {
    rowError.value = error as ApiError;
  }
  if (total) said.value = describeOutcome(total, t, locale.value);
}

async function onAction({ actionId, row }: { actionId: string; row: RecurringOut }): Promise<void> {
  if (actionId === 'edit') {
    editing.value = row;
    formOpen.value = true;
  }
  if (actionId === 'materialize') await bookWindow(row);
  if (actionId === 'delete') {
    remove.error.value = null;
    deleting.value = row;
    deleteOpen.value = true;
  }
}

async function confirmDelete(): Promise<void> {
  if (!deleting.value) return;
  try {
    await remove.run({ id: deleting.value.id });
  } catch {
    return; // The dialog says why.
  }
  deleteOpen.value = false;
}

function openNew(): void {
  editing.value = null;
  formOpen.value = true;
}

function onCreated(outcome: MaterializeOut): void {
  said.value = describeOutcome(outcome, t, locale.value);
}

function onUpdated(outcome: RecurringUpdatedOut): void {
  said.value = {
    summary: t('appointment.series.outcome.updated', { moved: outcome.moved, cancelled: outcome.cancelled, locked: outcome.locked }),
    skipped: outcome.skipped.map((skip) => `${skip.occurrence_date}: ${skip.message}`),
    more: '',
  };
}
</script>

<template>
  <div class="series-list page-fill">
    <InlineFeedback
      v-if="said"
      tone="info"
      dismissible
      data-testid="appointment-series-outcome"
      :heading="said.summary"
      @dismiss="said = null"
    >
      <ul
        v-if="said.skipped.length"
        class="series-list__skipped"
      >
        <li
          v-for="line in said.skipped"
          :key="line"
        >
          {{ line }}
        </li>
      </ul>
      <p v-if="said.more">
        {{ said.more }}
      </p>
    </InlineFeedback>
    <InlineFeedback
      v-if="rowError"
      tone="danger"
      dismissible
      data-testid="appointment-series-error"
      :heading="$t('appointment.series.toggleError')"
      @dismiss="rowError = null"
    >
      {{ rowError.message }}
    </InlineFeedback>
    <DataTable
      testid="appointment-series"
      fill
      searchable
      :rows="list.rows.value"
      :columns="columns"
      :actions="actions"
      :page-size="100"
      :search-keys="['customer_name', 'service_names', 'staff_name']"
      :search-placeholder="$t('appointment.series.search')"
      :views="['table', 'cards']"
      :card-title="(row: RecurringOut) => `${row.customer_name || $t('appointment.list.erasedCustomer')} · ${pattern(row)}`"
      :card-icon="() => 'calendar-outline'"
      :entity-label="{ one: $t('appointment.series.entity.one'), many: $t('appointment.series.entity.many') }"
      :loading="list.status.value === 'loading'"
      :error="list.status.value === 'error' ? $t('appointment.series.loadError') : undefined"
      :addable="canAdd"
      :labels="{ add: $t('appointment.series.add'), loadError: $t('appointment.series.loadError'), retry: $t('appointment.retry') }"
      @action="onAction"
      @add="openNew"
      @retry="list.refresh()"
    >
      <template #active="{ row }">
        <ion-toggle
          :checked="(row as RecurringOut).is_active"
          :disabled="!canChange"
          :aria-label="$t('appointment.series.columns.active')"
          :data-testid="`appointment-series-toggle-${(row as RecurringOut).id}`"
          @ion-change="toggle(row as RecurringOut, $event.detail.checked)"
        />
      </template>
      <template #empty>
        <EmptyState
          data-testid="appointment-series-empty"
          icon="calendar-outline"
          :heading="$t('appointment.series.empty')"
        />
      </template>
    </DataTable>
    <SeriesFormModal
      v-model:open="formOpen"
      :series="editing"
      :business-today="businessToday"
      :own-staff="ownStaff"
      @outcome="onCreated"
      @updated="onUpdated"
    />
    <ConfirmDialog
      v-model:open="deleteOpen"
      testid="appointment-series-delete"
      tone="danger"
      :title="t('appointment.series.deleteDialog.title', { name: deleting?.customer_name || t('appointment.list.erasedCustomer') })"
      :message="t('appointment.series.deleteDialog.message')"
      :confirm-label="t('appointment.series.deleteDialog.confirm')"
      :cancel-label="t('appointment.cancelDialog.keep')"
      :pending="remove.pending.value"
      :error="remove.error.value"
      @confirm="confirmDelete"
      @cancel="deleteOpen = false"
    />
  </div>
</template>

<style scoped>
/* A `.page-fill` stack (polish.css): in AgendaPage's `fill` layout the series list takes the page's height. */
.series-list {
  gap: 12px;
}
.series-list__skipped {
  margin: 6px 0;
  padding-left: 18px;
}
</style>
