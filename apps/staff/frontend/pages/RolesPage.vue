<script setup lang="ts">
// Staff → Roles (WORKBOOK «Pantallas · Roles»; STAFF-F04, F23): the live `staff.role.list` in a
// server-side DataTable — Role (its colour, and «Retired» on a retired one), Description and Members
// (the active people who hold it) —, «Search role…», sort by any column, filters, 50 a page. Whoever
// manages roles adds («New») and opens a row («Edit · {name}», where a role is also retired). Changes
// come back through the stream.
import { type DataTableColumn, DataTable, EmptyState, StatusPill } from '@erplora/ui/components';
import { AppPage, useSession } from '@erplora/ui/shell';
import { computed, ref, watch } from 'vue';

import FilterPanel, { type FilterSpec, type FilterValues } from '../components/FilterPanel.vue';
import PageNotices, { blockingError } from '../components/PageNotices.vue';
import RoleFormModal from '../components/RoleFormModal.vue';
import { useLiveList } from '../composables/useLiveList';
import { useServerTable } from '../composables/useServerTable';
import { useT } from '../composables/useT';
import type { RoleListIn, RoleOut } from '../operations';
import { staffTabs } from '../tabs';

const session = useSession();
const t = useT();
const canManage = computed(() => session.can('staff.manage_settings'));

const table = useServerTable({ sort: 'name' });
const filters = ref<FilterValues>({});
watch(filters, (now) => table.restart({ narrowed: Object.keys(now).length > 0 }));

/** The filters as the query takes them: status is a yes/no, members are whole numbers. */
function filterParams(values: FilterValues): Partial<RoleListIn> {
  const { is_active: active, member_count_min: min, member_count_max: max, ...rest } = values;
  return {
    ...rest,
    ...(active ? { is_active: active === 'true' } : {}),
    ...(min ? { member_count_min: Number(min) } : {}),
    ...(max ? { member_count_max: Number(max) } : {}),
  };
}

const {
  data: result,
  status,
  error,
  refresh,
} = useLiveList(
  'staff.role.list',
  () => ({ ...filterParams(filters.value), ...table.query.value }),
  () => table.windows.value,
);
table.followResult(result);
const blocked = computed(() => blockingError(error.value));

const filterSpecs = computed<FilterSpec[]>(() => [
  {
    kind: 'select',
    key: 'is_active',
    label: t('staff.roles.filters.state'),
    options: [
      { value: 'true', label: t('staff.roles.filters.active') },
      { value: 'false', label: t('staff.roles.filters.retired') },
    ],
  },
  { kind: 'text', key: 'color', label: t('staff.roles.filters.color') },
  { kind: 'range', key: 'member_count', label: t('staff.roles.filters.members'), keys: ['member_count_min', 'member_count_max'] },
]);

const columns = computed<DataTableColumn<RoleOut>[]>(() => [
  { key: 'name', label: t('staff.roles.columns.name'), sortable: true, priority: 'high', cell: 'name' },
  {
    key: 'description',
    label: t('staff.roles.columns.description'),
    sortable: true,
    format: (_, row) => row.description.trim() || '—',
  },
  { key: 'member_count', label: t('staff.roles.columns.members'), sortable: true, align: 'right', format: (_, row) => String(row.member_count) },
]);

const editing = ref<RoleOut | null>(null);
const formOpen = ref(false);

function openForm(role: RoleOut | null): void {
  if (!canManage.value) return;
  editing.value = role;
  formOpen.value = true;
}
</script>

<template>
  <AppPage
    :title="$t('staff.title')"
    :tabs="staffTabs($t, { settings: canManage })"
    :tabs-label="$t('staff.tabs.label')"
  >
    <PageNotices
      testid="staff-roles"
      :status="status"
      :error="error"
    />
    <DataTable
      v-if="!blocked"
      v-model:search="table.search.value"
      testid="staff-roles"
      server-side
      searchable
      :rows="result?.rows ?? []"
      :total="result?.total ?? 0"
      :page="table.page.value"
      :page-size="table.pageSize.value"
      :sort="table.sort.value"
      :sort-dir="table.dir.value"
      :views="['table', 'cards']"
      :card-title="(row: RoleOut) => row.name"
      :card-icon="() => 'shield-outline'"
      :entity-label="{ one: $t('staff.roles.entity.one'), many: $t('staff.roles.entity.many') }"
      :loading="status === 'loading'"
      :error="status === 'error' && !blocked ? error?.message : undefined"
      :addable="canManage"
      :row-clickable="canManage"
      :search-placeholder="$t('staff.roles.search')"
      :labels="{ add: $t('staff.add'), loadError: $t('staff.roles.loadError'), retry: $t('staff.live.retry') }"
      :columns="columns"
      @page-change="table.goToPage"
      @load-more="table.loadMore"
      @page-size-change="table.setPageSize"
      @sort-change="table.setSort"
      @row-click="openForm"
      @add="openForm(null)"
      @retry="refresh()"
    >
      <template #filters>
        <FilterPanel
          v-model="filters"
          testid="staff-roles"
          :filters="filterSpecs"
        />
      </template>
      <template #name="{ row }">
        <span class="staff-role">
          <span
            v-if="row.color"
            class="staff-role__dot"
            :style="{ background: row.color }"
            aria-hidden="true"
          />
          <span>{{ row.name }}</span>
          <StatusPill
            v-if="!row.is_active"
            size="sm"
            tone="neutral"
            data-testid="staff-roles-retired"
            :label="$t('staff.roles.retired')"
          />
        </span>
      </template>
      <template #empty>
        <EmptyState
          data-testid="staff-roles-empty"
          icon="shield-outline"
          :heading="table.filtered.value ? $t('staff.noResults') : $t('staff.roles.empty')"
          :message="table.filtered.value ? $t('staff.noResultsMessage') : undefined"
        />
      </template>
    </DataTable>
    <RoleFormModal
      v-if="canManage"
      v-model:open="formOpen"
      :role="editing"
    />
  </AppPage>
</template>

<style scoped>
.staff-role {
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
  min-width: 0;
}
.staff-role__dot {
  flex: none;
  width: 0.7rem;
  height: 0.7rem;
  border-radius: 50%;
}
</style>
