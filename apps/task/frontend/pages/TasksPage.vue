<script setup lang="ts">
// Tasks → Tasks (WORKBOOK «Pantallas · Tareas»; TASK-F01 to F07). «All»: the live `task.task.list` in a
// server-side DataTable — No., Title, Status, Priority (a coloured chip with its name), Due (red
// «Overdue», amber «Due today»; a closed task is never late), Assignee and Project (hidden) —, the
// newest first, «Search no. or title…», column filters, list or cards, 50 a page. «My tasks», only for
// whoever has a staff record: the live `task.task.mine`, dated first; a task completed from its card
// stays in its slot, as done, until the person leaves the tab (tasks#45). A row offers Detail, Start
// and Complete where they apply; Start and Complete confirm with a short notice; the row and Detail open
// the task's sheet; «+» opens «New task». A refused row action is said above the table.
import {
  DataTable,
  type DataTableAction,
  type DataTableColumn,
  type DataTableFilters,
  EmptyState,
  InlineFeedback,
  StatusPill,
} from '@erplora/ui/components';
import { type ApiError, useCommand, useLive } from '@erplora/ui/sdk';
import { AppPage, toastSuccess, useSession } from '@erplora/ui/shell';
import { IonLabel, IonSegment, IonSegmentButton } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import PageNotices, { blockingError } from '../components/PageNotices.vue';
import TaskFormModal from '../components/TaskFormModal.vue';
import TaskSheet from '../components/TaskSheet.vue';
import { useLiveList } from '../composables/useLiveList';
import { useServerTable } from '../composables/useServerTable';
import { useLocale, useT } from '../composables/useT';
import { dueTone, formatDay, isClosed, PRIORITY_TONE, STATUS_TONE } from '../lib/format';
import { keepCompletedInPlace } from '../lib/mine';
import type { TaskListIn, TaskOut, TaskPriority, TaskSort, TaskStatus } from '../operations';
import { taskTabs } from '../tabs';

const STATUSES: readonly TaskStatus[] = ['todo', 'in_progress', 'blocked', 'done', 'cancelled'];
const PRIORITIES: readonly TaskPriority[] = ['low', 'medium', 'high', 'urgent'];

const session = useSession();
const t = useT();
const locale = useLocale();
const canAdd = computed(() => session.can('task.add'));

// «All» and «My tasks»
const view = ref<'all' | 'mine'>('all');
const me = useLive('staff.member.mine', {});
const hasRecord = computed(() => !!me.data.value?.member);

const table = useServerTable({ sort: '-created_at' });
const filters = ref<DataTableFilters>({});

/** The table's filters as the query takes them: a due day is a range of one day. */
const query = computed<Partial<TaskListIn>>(() => {
  const f = filters.value;
  return {
    ...(f.number ? { number: f.number } : {}),
    ...(f.title ? { title: f.title } : {}),
    ...(f.status ? { status: f.status as TaskStatus } : {}),
    ...(f.priority ? { priority: f.priority as TaskPriority } : {}),
    ...(f.due_date ? { due_from: f.due_date, due_to: f.due_date } : {}),
    ...(f.assignee_name ? { assignee: f.assignee_name } : {}),
    ...(f.project_id ? { project_id: f.project_id } : {}),
  };
});

function onFilters(now: DataTableFilters): void {
  filters.value = now;
  table.restart({ narrowed: Object.keys(now).length > 0 });
}

const all = useLiveList('task.task.list', () => ({ ...query.value, ...(table.query.value as { search?: string; sort: TaskSort }) }), () => table.windows.value);
table.followResult(all.data);

// «My tasks»: its own pages and search; the order is the server's (dated first).
const mineTable = useServerTable({ sort: 'due_date' });
const mine = useLiveList(
  'task.task.mine',
  () => (mineTable.query.value.search ? { search: mineTable.query.value.search } : {}),
  () => mineTable.windows.value,
);
mineTable.followResult(mine.data);
/** tasks#45: the tasks completed from «My tasks» during this visit to the tab. */
let keptDone = new Map<string, TaskOut>();
const mineRows = ref<TaskOut[]>([]);
watch(
  () => mine.data.value?.rows,
  (fresh) => {
    mineRows.value = keepCompletedInPlace(mineRows.value, fresh ?? [], keptDone);
  },
  { immediate: true },
);

function setView(next: 'all' | 'mine'): void {
  view.value = next;
  // Leaving the tab (or coming back to it) is when the completed ones are let go.
  keptDone = new Map();
  mineRows.value = [...(mine.data.value?.rows ?? [])];
}

const live = computed(() => (view.value === 'mine' ? mine : all));
const blocked = computed(() => blockingError(live.value.error.value));

// The project filter offers the business's projects (a salon has a handful).
const { data: projects } = useLive('task.project.list', { limit: 100, sort: 'name' });

const pill = (row: TaskOut) => row;
const columns = computed<DataTableColumn<TaskOut>[]>(() => [
  { key: 'number', label: t('task.columns.number'), sortable: true, width: '11rem', filter: { type: 'text' } },
  { key: 'title', label: t('task.columns.title'), sortable: true, priority: 'high', width: 'minmax(10rem,2fr)', filter: { type: 'text' } },
  {
    key: 'status',
    label: t('task.columns.status'),
    sortable: true,
    cell: 'status',
    format: (_, row) => t(`task.status.${row.status}`),
    filter: { type: 'select', options: STATUSES.map((value) => ({ value, label: t(`task.status.${value}`) })) },
  },
  {
    key: 'priority',
    label: t('task.columns.priority'),
    sortable: true,
    cell: 'priority',
    format: (_, row) => t(`task.priority.${row.priority}`),
    filter: { type: 'select', options: PRIORITIES.map((value) => ({ value, label: t(`task.priority.${value}`) })) },
  },
  {
    key: 'due_date',
    label: t('task.columns.due'),
    sortable: true,
    cell: 'due',
    format: (_, row) => formatDay(row.due_date, locale.value),
    filter: { type: 'date' },
  },
  {
    key: 'assignee_name',
    label: t('task.columns.assignee'),
    sortable: true,
    priority: 'low',
    format: (_, row) => row.assignee_name ?? '—',
    filter: { type: 'text' },
  },
  {
    key: 'project_name',
    label: t('task.columns.project'),
    sortable: true,
    hidden: true,
    format: (_, row) => row.project_name ?? '—',
    filter: { type: 'select', key: 'project_id', options: (projects.value?.rows ?? []).map((p) => ({ value: p.id, label: p.name })) },
  },
]);
/** «My tasks» has no column filters: it is a short list of one person's open work. */
const mineColumns = computed(() => columns.value.map((column) => ({ ...column, filter: undefined, sortable: false })));

const actions = computed<DataTableAction<TaskOut>[]>(() => [
  { id: 'detail', label: t('task.actions.detail'), icon: 'chevron-forward-outline', color: 'primary', pinned: true },
  {
    id: 'start',
    label: t('task.actions.start'),
    icon: 'time-outline',
    color: 'primary',
    hidden: (row) => !row.can_change || row.status === 'in_progress' || isClosed(row.status),
  },
  {
    id: 'complete',
    label: t('task.actions.complete'),
    icon: 'checkmark-circle-outline',
    color: 'success',
    hidden: (row) => !row.can_change || isClosed(row.status),
  },
]);

// The sheet and the form
const sheetTaskId = ref<string | null>(null);
const sheetOpen = ref(false);
const formOpen = ref(false);

function openSheet(row: TaskOut): void {
  sheetTaskId.value = row.id;
  sheetOpen.value = true;
}

// Row actions
const setStatus = useCommand('task.task.set_status');
const complete = useCommand('task.task.complete');
const rowError = ref<ApiError | null>(null);

async function onAction({ actionId, row }: { actionId: string; row: TaskOut }): Promise<void> {
  rowError.value = null;
  if (actionId === 'detail') return openSheet(row);
  try {
    if (actionId === 'start') {
      await setStatus.run({ id: row.id, status: 'in_progress' });
      void toastSuccess(t('task.tasks.started'));
    }
    if (actionId === 'complete') {
      await complete.run({ id: row.id });
      if (view.value === 'mine') keptDone.set(row.id, { ...row, status: 'done' });
      void toastSuccess(t('task.tasks.completed'));
    }
  } catch (error) {
    rowError.value = (actionId === 'start' ? setStatus.error.value : complete.error.value) ?? (error as ApiError);
  }
}

const dueLabel = (row: TaskOut): string | undefined => {
  const tone = dueTone(row.due_date, row.status);
  return tone === 'none' ? undefined : t(tone === 'overdue' ? 'task.due.overdue' : 'task.due.today');
};
</script>

<template>
  <AppPage
    :title="$t('task.title')"
    :tabs="taskTabs($t)"
    :tabs-label="$t('task.tabs.label')"
  >
    <div class="task-tasks__views">
      <ion-segment
        data-testid="task-views"
        :value="view"
        :aria-label="t('task.views.label')"
        @ion-change="setView($event.detail.value as 'all' | 'mine')"
      >
        <ion-segment-button
          value="all"
          data-testid="task-view-all"
        >
          <ion-label>{{ t('task.views.all') }}</ion-label>
        </ion-segment-button>
        <ion-segment-button
          v-if="hasRecord"
          value="mine"
          data-testid="task-view-mine"
        >
          <ion-label>{{ t('task.views.mine') }}</ion-label>
        </ion-segment-button>
      </ion-segment>
    </div>
    <PageNotices
      testid="task-tasks"
      :status="live.status.value"
      :error="live.error.value"
    />
    <InlineFeedback
      v-if="rowError"
      tone="danger"
      dismissible
      data-testid="task-tasks-row-error"
      :heading="t('task.tasks.rowError')"
      @dismiss="rowError = null"
    >
      {{ rowError.message }}
    </InlineFeedback>
    <DataTable
      v-if="!blocked && view === 'all'"
      v-model:search="table.search.value"
      testid="task-tasks"
      server-side
      searchable
      :filters="filters"
      :rows="all.data.value?.rows ?? []"
      :total="all.data.value?.total ?? 0"
      :page="table.page.value"
      :page-size="table.pageSize.value"
      :sort="table.sort.value"
      :sort-dir="table.dir.value"
      :views="['table', 'cards']"
      :card-title="(row: TaskOut) => row.title"
      :card-icon="() => 'checkmark-circle-outline'"
      :entity-label="{ one: $t('task.tasks.entity.one'), many: $t('task.tasks.entity.many') }"
      :loading="all.status.value === 'loading'"
      :error="all.status.value === 'error' && !blocked ? $t('task.tasks.loadError') : undefined"
      :addable="canAdd"
      row-clickable
      :actions="actions"
      :search-placeholder="$t('task.tasks.search')"
      :labels="{ add: $t('task.tasks.new'), loadError: $t('task.tasks.loadError'), retry: $t('task.live.retry') }"
      :columns="columns"
      @filters-change="onFilters"
      @page-change="table.goToPage"
      @load-more="table.loadMore"
      @page-size-change="table.setPageSize"
      @sort-change="table.setSort"
      @row-click="openSheet"
      @add="formOpen = true"
      @action="onAction"
      @retry="all.refresh()"
    >
      <template #status="{ row }">
        <StatusPill
          size="sm"
          :tone="STATUS_TONE[pill(row).status]"
          :label="t(`task.status.${pill(row).status}`)"
        />
      </template>
      <template #priority="{ row }">
        <StatusPill
          size="sm"
          :dot="false"
          :tone="PRIORITY_TONE[pill(row).priority]"
          :label="t(`task.priority.${pill(row).priority}`)"
        />
      </template>
      <template #due="{ row }">
        <span
          data-testid="task-due"
          :class="`task-due task-due--${dueTone(pill(row).due_date, pill(row).status)}`"
          :aria-label="dueLabel(pill(row))"
          :title="dueLabel(pill(row))"
        >{{ formatDay(pill(row).due_date, locale) }}</span>
      </template>
      <template #empty>
        <EmptyState
          data-testid="task-tasks-empty"
          icon="checkmark-circle-outline"
          :heading="table.filtered.value ? $t('task.noResults') : $t('task.tasks.empty')"
          :message="table.filtered.value ? $t('task.noResultsMessage') : undefined"
        />
      </template>
    </DataTable>
    <DataTable
      v-if="!blocked && view === 'mine'"
      v-model:search="mineTable.search.value"
      testid="task-mine"
      server-side
      searchable
      :rows="mineRows"
      :total="Math.max(mine.data.value?.total ?? 0, mineRows.length)"
      :page="mineTable.page.value"
      :page-size="mineTable.pageSize.value"
      :views="['table', 'cards']"
      :card-title="(row: TaskOut) => row.title"
      :card-icon="() => 'checkmark-circle-outline'"
      :entity-label="{ one: $t('task.tasks.entity.one'), many: $t('task.tasks.entity.many') }"
      :loading="mine.status.value === 'loading'"
      :error="mine.status.value === 'error' && !blocked ? $t('task.tasks.loadError') : undefined"
      row-clickable
      :actions="actions"
      :search-placeholder="$t('task.tasks.search')"
      :labels="{ loadError: $t('task.tasks.loadError'), retry: $t('task.live.retry') }"
      :columns="mineColumns"
      @page-change="mineTable.goToPage"
      @load-more="mineTable.loadMore"
      @page-size-change="mineTable.setPageSize"
      @row-click="openSheet"
      @action="onAction"
      @retry="mine.refresh()"
    >
      <template #status="{ row }">
        <StatusPill
          size="sm"
          :tone="STATUS_TONE[pill(row).status]"
          :label="t(`task.status.${pill(row).status}`)"
        />
      </template>
      <template #priority="{ row }">
        <StatusPill
          size="sm"
          :dot="false"
          :tone="PRIORITY_TONE[pill(row).priority]"
          :label="t(`task.priority.${pill(row).priority}`)"
        />
      </template>
      <template #due="{ row }">
        <span
          data-testid="task-due"
          :class="`task-due task-due--${dueTone(pill(row).due_date, pill(row).status)}`"
          :aria-label="dueLabel(pill(row))"
          :title="dueLabel(pill(row))"
        >{{ formatDay(pill(row).due_date, locale) }}</span>
      </template>
      <template #empty>
        <EmptyState
          data-testid="task-mine-empty"
          icon="checkmark-circle-outline"
          :heading="mineTable.filtered.value ? $t('task.noResults') : $t('task.tasks.emptyMine')"
        />
      </template>
    </DataTable>
    <TaskFormModal
      v-model:open="formOpen"
      :task="null"
    />
    <TaskSheet
      v-if="sheetTaskId"
      v-model:open="sheetOpen"
      :task-id="sheetTaskId"
    />
  </AppPage>
</template>

<style scoped>
.task-tasks__views {
  max-width: 22rem;
  padding: 0 0 8px;
}
.task-due--overdue {
  color: var(--ion-color-danger, #c5000f);
  font-weight: 600;
}
.task-due--today {
  color: var(--ion-color-warning-shade, #b37400);
  font-weight: 600;
}
</style>
