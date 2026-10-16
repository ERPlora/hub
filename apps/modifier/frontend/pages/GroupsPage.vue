<script setup lang="ts">
// Modifiers (WORKBOOK «Pantallas · Suplementos»; MODIFIER-F01 to F03): the live `modifier.group.list` in a
// server-side DataTable with the old screen's columns — Name (sorted and filtered), «On the kitchen
// ticket» (the name when empty, Toast's rule), Choice (the rule, filtered by required or optional) and
// Order — plus Options and «Applies to»; «Search…» (name and kitchen name), by order then name, 50 a page.
// «New group» and Edit (whoever may manage) open the form; Delete asks first, saying how many options go
// and where it stops applying. A row opens the group's sheet (its options and what it applies to), to
// everyone. Changes come back through the stream.
import {
  ConfirmDialog,
  DataTable,
  type DataTableAction,
  type DataTableColumn,
  type DataTableFilters,
  EmptyState,
} from '@erplora/ui/components';
import { useCommand } from '@erplora/ui/sdk';
import { AppPage, useSession } from '@erplora/ui/shell';
import { computed, ref } from 'vue';

import GroupFormModal from '../components/GroupFormModal.vue';
import GroupSheet from '../components/GroupSheet.vue';
import PageNotices, { blockingError } from '../components/PageNotices.vue';
import { useLiveList } from '../composables/useLiveList';
import { useServerTable } from '../composables/useServerTable';
import { useT } from '../composables/useT';
import { choiceRule } from '../lib/format';
import type { GroupListIn, GroupOut, GroupSort } from '../operations';

const session = useSession();
const t = useT();
const canManage = computed(() => session.can('modifier.manage'));

const table = useServerTable({ sort: 'sort_order' });
const filters = ref<DataTableFilters>({});

/** The table's filters as the query takes them. */
const query = computed<Partial<GroupListIn>>(() => {
  const f = filters.value;
  return {
    ...(f.name ? { name: f.name } : {}),
    ...(f.required ? { required: f.required === 'true' } : {}),
  };
});

function onFilters(now: DataTableFilters): void {
  filters.value = now;
  table.restart({ narrowed: Object.keys(now).length > 0 });
}

const { data: result, status, error, refresh } = useLiveList(
  'modifier.group.list',
  () => ({ ...query.value, ...table.query.value, sort: table.query.value.sort as GroupSort }),
  () => table.windows.value,
);
table.followResult(result);
const blocked = computed(() => blockingError(error.value));

const columns = computed<DataTableColumn<GroupOut>[]>(() => [
  { key: 'name', label: t('modifier.groups.columns.name'), sortable: true, priority: 'high', filter: { type: 'text' } },
  { key: 'kitchen_name', label: t('modifier.groups.columns.kitchen'), format: (_, row) => row.kitchen_name || row.name },
  {
    key: 'min_choices',
    label: t('modifier.groups.columns.choice'),
    sortable: true,
    format: (_, row) => choiceRule(row, t),
    filter: {
      type: 'select',
      key: 'required',
      options: [
        { value: 'true', label: t('modifier.groups.required.yes') },
        { value: 'false', label: t('modifier.groups.required.no') },
      ],
    },
  },
  { key: 'option_count', label: t('modifier.groups.columns.options'), sortable: true, align: 'right', format: (_, row) => String(row.option_count) },
  { key: 'link_count', label: t('modifier.groups.columns.links'), sortable: true, align: 'right', format: (_, row) => String(row.link_count) },
  { key: 'sort_order', label: t('modifier.groups.columns.order'), sortable: true, align: 'right', format: (_, row) => String(row.sort_order) },
]);

const actions = computed<DataTableAction<GroupOut>[]>(() =>
  canManage.value
    ? [
        { id: 'edit', label: t('modifier.groups.actions.edit'), icon: 'create-outline' },
        { id: 'delete', label: t('modifier.groups.actions.delete'), icon: 'trash-outline', color: 'danger' },
      ]
    : [],
);

// The form (new or edit) and the sheet (a row).
const editing = ref<GroupOut | null>(null);
const formOpen = ref(false);
function openForm(group: GroupOut | null): void {
  editing.value = group;
  formOpen.value = true;
}
const viewing = ref<GroupOut | null>(null);
const sheetOpen = ref(false);
function openSheet(group: GroupOut): void {
  viewing.value = group;
  sheetOpen.value = true;
}

// Deleting, after its confirmation.
const remove = useCommand('modifier.group.delete');
const deleting = ref<GroupOut | null>(null);
const deleteOpen = ref(false);
const consequences = computed(() => {
  const group = deleting.value;
  if (!group) return [];
  return [
    ...(group.option_count > 0 ? [t('modifier.groups.delete.options', { count: group.option_count })] : []),
    ...(group.link_count > 0 ? [t('modifier.groups.delete.links', { count: group.link_count })] : []),
  ];
});

async function confirmDelete(): Promise<void> {
  if (!deleting.value) return;
  try {
    await remove.run({ id: deleting.value.id });
  } catch {
    return; // The dialog says why.
  }
  deleteOpen.value = false;
}

function onAction({ actionId, row }: { actionId: string; row: GroupOut }): void {
  if (actionId === 'edit') openForm(row);
  if (actionId === 'delete') {
    remove.error.value = null;
    deleting.value = row;
    deleteOpen.value = true;
  }
}
</script>

<template>
  <AppPage :title="$t('modifier.title')">
    <PageNotices
      testid="modifier-groups"
      :status="status"
      :error="error"
    />
    <DataTable
      v-if="!blocked"
      v-model:search="table.search.value"
      testid="modifier-groups"
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
      :card-title="(row: GroupOut) => row.name"
      :card-icon="() => 'lucide:sliders-horizontal'"
      :entity-label="{ one: $t('modifier.groups.entity.one'), many: $t('modifier.groups.entity.many') }"
      :loading="status === 'loading'"
      :error="status === 'error' && !blocked ? $t('modifier.groups.loadError') : undefined"
      :addable="canManage"
      :actions="actions"
      :search-placeholder="$t('modifier.groups.search')"
      :labels="{ add: $t('modifier.groups.new'), loadError: $t('modifier.groups.loadError'), retry: $t('modifier.live.retry') }"
      :columns="columns"
      @filters-change="onFilters"
      @page-change="table.goToPage"
      @load-more="table.loadMore"
      @page-size-change="table.setPageSize"
      @sort-change="table.setSort"
      @row-click="openSheet"
      @add="openForm(null)"
      @action="onAction"
      @retry="refresh()"
    >
      <template #empty>
        <EmptyState
          data-testid="modifier-groups-empty"
          icon="lucide:sliders-horizontal"
          :heading="table.filtered.value ? $t('modifier.noResults') : $t('modifier.groups.empty')"
          :message="table.filtered.value ? $t('modifier.noResultsMessage') : undefined"
        />
      </template>
    </DataTable>
    <GroupFormModal
      v-model:open="formOpen"
      :group="editing"
    />
    <GroupSheet
      v-if="viewing"
      v-model:open="sheetOpen"
      :group="viewing"
      @closed="viewing = null"
    />
    <ConfirmDialog
      v-model:open="deleteOpen"
      testid="modifier-groups-delete"
      tone="danger"
      :title="t('modifier.groups.delete.title')"
      :message="deleting ? t('modifier.groups.delete.message', { name: deleting.name }) : ''"
      :consequences="consequences"
      :confirm-label="t('modifier.groups.delete.confirm')"
      :cancel-label="t('modifier.cancel')"
      :pending="remove.pending.value"
      :error="remove.error.value"
      @confirm="confirmDelete"
      @cancel="deleteOpen = false"
    />
  </AppPage>
</template>
