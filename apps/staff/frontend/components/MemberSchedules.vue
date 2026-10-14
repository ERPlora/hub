<script setup lang="ts">
// The schedules of one member (WORKBOOK «Pantallas · Horarios»; STAFF-F13–F15): the live
// `staff.schedule.list` of that member — Schedule, Default, From, To, Active and Hours (the week at a
// glance) —, the default first. A member has a handful: they come in one page of the server's cap (100)
// and the table pages them itself. Whoever manages schedules adds, edits (a row or «Edit»), toggles at
// once and deletes after confirming; a refused action is said above the table.
import { ConfirmDialog, type DataTableAction, type DataTableColumn, DataTable, EmptyState, InlineFeedback } from '@erplora/ui/components';
import { useCommand, useLive } from '@erplora/ui/sdk';
import { useSession } from '@erplora/ui/shell';
import { computed, ref } from 'vue';

import { useLocale, useT } from '../composables/useT';
import { formatDate, hoursSummary } from '../lib/format';
import type { ScheduleOut } from '../operations';
import PageNotices, { blockingError } from './PageNotices.vue';
import ScheduleFormModal from './ScheduleFormModal.vue';

const props = defineProps<{
  memberId: string;
}>();

const session = useSession();
const t = useT();
const locale = useLocale();
const canManage = computed(() => session.can('staff.manage_settings'));

const { data: result, status, error, refresh } = useLive('staff.schedule.list', () => ({ member_id: props.memberId, limit: 100 }));
const blocked = computed(() => blockingError(error.value));
/** Whether the member has a default schedule: a new one is not proposed as «Default» then. */
const hasDefault = computed(() => (result.value?.rows ?? []).some((schedule) => schedule.is_default));

const columns = computed<DataTableColumn<ScheduleOut>[]>(() => [
  { key: 'name', label: t('staff.schedules.columns.name'), priority: 'high' },
  { key: 'is_default', label: t('staff.schedules.columns.default'), format: (_, row) => (row.is_default ? t('staff.yes') : '—') },
  { key: 'effective_from', label: t('staff.schedules.columns.from'), format: (_, row) => formatDate(row.effective_from, locale.value) },
  { key: 'effective_until', label: t('staff.schedules.columns.to'), format: (_, row) => formatDate(row.effective_until, locale.value) },
  { key: 'is_active', label: t('staff.schedules.columns.active'), format: (_, row) => (row.is_active ? t('staff.yes') : t('staff.no')) },
  {
    key: 'hours',
    label: t('staff.schedules.columns.hours'),
    width: 'minmax(12rem,2fr)',
    sortable: false,
    format: (_, row) => hoursSummary(row.days, (weekday) => t(`staff.days.short.${weekday}`)),
  },
]);

const pageError = ref('');
const busy = ref<string | null>(null);

const actions = computed<DataTableAction<ScheduleOut>[]>(() =>
  canManage.value
    ? [
        { id: 'edit', label: t('staff.schedules.actions.edit'), icon: 'create-outline' },
        { id: 'toggle', label: t('staff.schedules.actions.toggle'), icon: 'sync-outline', loading: (row) => busy.value === row.id },
        { id: 'delete', label: t('staff.schedules.actions.delete'), icon: 'trash-outline', color: 'danger' },
      ]
    : [],
);

const editing = ref<ScheduleOut | null>(null);
const formOpen = ref(false);
const deleting = ref<ScheduleOut | null>(null);
const deleteOpen = ref(false);
const activation = useCommand('staff.schedule.set_active');
const removal = useCommand('staff.schedule.delete');

const failed = (failure: unknown): string => (failure instanceof Error ? failure.message : String(failure));

function openForm(schedule: ScheduleOut | null): void {
  if (!canManage.value) return;
  pageError.value = '';
  editing.value = schedule;
  formOpen.value = true;
}

async function toggle(row: ScheduleOut): Promise<void> {
  busy.value = row.id;
  try {
    await activation.run({ id: row.id, is_active: !row.is_active });
  } catch (failure) {
    pageError.value = failed(failure);
  } finally {
    busy.value = null;
  }
}

function onAction({ actionId, row }: { actionId: string; row: ScheduleOut }): void {
  if (!canManage.value) return;
  pageError.value = '';
  if (actionId === 'edit') openForm(row);
  else if (actionId === 'toggle') void toggle(row);
  else if (actionId === 'delete') {
    deleting.value = row;
    deleteOpen.value = true;
  }
}

async function remove(): Promise<void> {
  const row = deleting.value;
  if (!row) return;
  try {
    await removal.run({ id: row.id });
  } catch (failure) {
    pageError.value = failed(failure);
  } finally {
    deleteOpen.value = false;
  }
}
</script>

<template>
  <PageNotices
    testid="staff-schedules"
    :status="status"
    :error="error"
  />
  <InlineFeedback
    v-if="pageError"
    tone="danger"
    data-testid="staff-schedules-error"
  >
    {{ pageError }}
  </InlineFeedback>
  <DataTable
    v-if="!blocked"
    testid="staff-schedules"
    :rows="result?.rows ?? []"
    :views="['table', 'cards']"
    :card-title="(row: ScheduleOut) => row.name"
    :card-icon="() => 'time-outline'"
    :entity-label="{ one: $t('staff.schedules.entity.one'), many: $t('staff.schedules.entity.many') }"
    :loading="status === 'loading'"
    :error="status === 'error' && !blocked ? error?.message : undefined"
    :addable="canManage"
    :row-clickable="canManage"
    :actions="actions"
    :labels="{ add: $t('staff.add'), loadError: $t('staff.schedules.loadError'), retry: $t('staff.live.retry') }"
    :columns="columns"
    @action="onAction"
    @row-click="openForm"
    @add="openForm(null)"
    @retry="refresh()"
  >
    <template #empty>
      <EmptyState
        data-testid="staff-schedules-empty"
        icon="time-outline"
        :heading="$t('staff.schedules.empty')"
      />
    </template>
  </DataTable>
  <template v-if="canManage">
    <ScheduleFormModal
      v-model:open="formOpen"
      :member-id="memberId"
      :schedule="editing"
      :propose-default="!hasDefault"
    />
    <ConfirmDialog
      v-model:open="deleteOpen"
      testid="staff-schedule-delete"
      tone="danger"
      confirm-icon="ion:trash-outline"
      :title="$t('staff.schedules.delete.title')"
      :message="$t('staff.schedules.delete.message', { name: deleting?.name ?? '' })"
      :confirm-label="$t('staff.schedules.delete.confirm')"
      :pending="removal.pending.value"
      @confirm="remove"
    />
  </template>
</template>
