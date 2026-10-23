<script setup lang="ts">
// Tasks → Projects (WORKBOOK «Pantallas · Proyectos»; TASK-F12 to F14): the live `task.project.list` in a
// server-side DataTable — Code, Name, Color (with its swatch) and Active (Yes / No, a list filter) —, the
// newest first, «Search code or name…», column filters behind the toolbar funnel, list or cards, 50 a
// page. A row and its «Open» open the project's sheet (tasks#43); «+», for whoever manages projects, opens
// «New project».
import {
  DataTable,
  type DataTableAction,
  type DataTableColumn,
  type DataTableFilters,
  EmptyState,
} from '@erplora/ui/components';
import { AppPage, useSession } from '@erplora/ui/shell';
import { computed, ref } from 'vue';

import PageNotices, { blockingError } from '../components/PageNotices.vue';
import ProjectFormModal from '../components/ProjectFormModal.vue';
import ProjectSheet from '../components/ProjectSheet.vue';
import { useLiveList } from '../composables/useLiveList';
import { useServerTable } from '../composables/useServerTable';
import { useT } from '../composables/useT';
import type { ProjectListIn, ProjectOut, ProjectSort } from '../operations';
import { taskTabs } from '../tabs';

const session = useSession();
const t = useT();
const canManage = computed(() => session.can('task.manage_project'));

const table = useServerTable({ sort: '-created_at' });
const filters = ref<DataTableFilters>({});

const query = computed<Partial<ProjectListIn>>(() => {
  const f = filters.value;
  return {
    ...(f.code ? { code: f.code } : {}),
    ...(f.name ? { name: f.name } : {}),
    ...(f.color ? { color: f.color } : {}),
    ...(f.is_active ? { is_active: f.is_active === 'true' } : {}),
  };
});

function onFilters(now: DataTableFilters): void {
  filters.value = now;
  table.restart({ narrowed: Object.keys(now).length > 0 });
}

const { data: result, status, error, refresh } = useLiveList(
  'task.project.list',
  () => ({ ...query.value, ...(table.query.value as { search?: string; sort: ProjectSort }) }),
  () => table.windows.value,
);
table.followResult(result);
const blocked = computed(() => blockingError(error.value));

const columns = computed<DataTableColumn<ProjectOut>[]>(() => [
  { key: 'code', label: t('task.projects.columns.code'), sortable: true, filter: { type: 'text' } },
  { key: 'name', label: t('task.projects.columns.name'), sortable: true, priority: 'high', filter: { type: 'text' } },
  {
    key: 'color',
    label: t('task.projects.columns.color'),
    sortable: true,
    cell: 'color',
    format: (_, row) => row.color || '—',
    filter: { type: 'text' },
  },
  {
    key: 'is_active',
    label: t('task.projects.columns.active'),
    sortable: true,
    format: (_, row) => (row.is_active ? t('task.yes') : t('task.no')),
    filter: {
      type: 'select',
      options: [
        { value: 'true', label: t('task.yes') },
        { value: 'false', label: t('task.no') },
      ],
    },
  },
]);

const actions = computed<DataTableAction<ProjectOut>[]>(() => [
  { id: 'open', label: t('task.actions.open'), icon: 'open-outline', color: 'primary', showLabel: true, pinned: true },
]);

const sheetProjectId = ref<string | null>(null);
const sheetOpen = ref(false);
const formOpen = ref(false);

function openSheet(row: ProjectOut): void {
  sheetProjectId.value = row.id;
  sheetOpen.value = true;
}

const swatch = (row: unknown) => (row as ProjectOut).color;
</script>

<template>
  <AppPage
    :title="$t('task.title')"
    content-layout="fill"
    :tabs="taskTabs($t)"
    :tabs-label="$t('task.tabs.label')"
  >
    <PageNotices
      testid="task-projects"
      :status="status"
      :error="error"
    />
    <DataTable
      v-if="!blocked"
      v-model:search="table.search.value"
      testid="task-projects"
      fill
      server-side
      searchable
      filterable
      :filters="filters"
      :rows="result?.rows ?? []"
      :total="result?.total ?? 0"
      :page="table.page.value"
      :page-size="table.pageSize.value"
      :sort="table.sort.value"
      :sort-dir="table.dir.value"
      :views="['table', 'cards']"
      :card-title="(row: ProjectOut) => row.name"
      :card-icon="() => 'folder-outline'"
      :entity-label="{ one: $t('task.projects.entity.one'), many: $t('task.projects.entity.many') }"
      :loading="status === 'loading'"
      :error="status === 'error' && !blocked ? $t('task.projects.loadError') : undefined"
      :addable="canManage"
      row-clickable
      :actions="actions"
      :search-placeholder="$t('task.projects.search')"
      :labels="{ add: $t('task.projects.new'), loadError: $t('task.projects.loadError'), retry: $t('task.live.retry') }"
      :columns="columns"
      @filters-change="onFilters"
      @page-change="table.goToPage"
      @load-more="table.loadMore"
      @page-size-change="table.setPageSize"
      @sort-change="table.setSort"
      @row-click="openSheet"
      @add="formOpen = true"
      @action="({ row }) => openSheet(row)"
      @retry="refresh()"
    >
      <template #color="{ row }">
        <span class="task-projects__color">
          <span
            v-if="swatch(row)"
            class="task-projects__swatch"
            :style="{ background: swatch(row) }"
          />
          {{ swatch(row) || '—' }}
        </span>
      </template>
      <template #empty>
        <EmptyState
          data-testid="task-projects-empty"
          icon="folder-outline"
          :heading="table.filtered.value ? $t('task.noResults') : $t('task.projects.empty')"
          :message="table.filtered.value ? $t('task.noResultsMessage') : undefined"
        />
      </template>
    </DataTable>
    <ProjectFormModal v-model:open="formOpen" />
    <ProjectSheet
      v-if="sheetProjectId"
      v-model:open="sheetOpen"
      :project-id="sheetProjectId"
    />
  </AppPage>
</template>

<style scoped>
.task-projects__color {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.task-projects__swatch {
  width: 0.8rem;
  height: 0.8rem;
  border-radius: 50%;
  border: 1px solid var(--ion-border-color, #e7e2d6);
  flex: none;
}
</style>
