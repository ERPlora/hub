<script setup lang="ts">
// Sales & POS → Quick notes (SALE-F36; WORKBOOK «Pantallas · Notas rápidas»): the old intro, then the live
// `sale.quick_note.list` in a server-side DataTable — Note and Position —, «Search a note…», 50 a page
// sorted by position. Whoever may change the till settings gets «+», «Edit» (also a tap on the row) and
// «Delete» (confirmed with the old «Delete quick note»); anyone else sees the list read-only. New, changed
// and deleted notes arrive through the stream (no refetch).
import { type DataTableAction, type DataTableColumn, DataTable, EmptyState, useConfirm } from '@erplora/ui/components';
import { useCommand } from '@erplora/ui/sdk';
import { AppPage, useSession } from '@erplora/ui/shell';
import { computed, ref } from 'vue';

import ListNotices, { blockingError, type ListRefusal } from '../components/backoffice/ListNotices.vue';
import QuickNoteFormModal from '../components/backoffice/QuickNoteFormModal.vue';
import { refusal } from '../lib/refusal';
import { useServerTable } from '../composables/useServerTable';
import { useT } from '../composables/useT';
import type { QuickNoteOut } from '../operations';
import { saleTabs } from '../tabs';

const session = useSession();
const canManage = computed(() => session.can('sale.manage_settings'));
const t = useT();
const { confirm } = useConfirm();

// `search` of QuickNoteListIn takes 80 characters.
const table = useServerTable('sale.quick_note.list', { sort: 'sort_order', maxSearch: 80 });
const { data: result, status, error } = table;

const blocked = computed(() => blockingError(error.value));
const tableError = computed(() => (status.value === 'error' ? error.value?.message : undefined));

const columns = computed<DataTableColumn<QuickNoteOut>[]>(() => [
  { key: 'text', label: t('sale.quickNotes.columns.text'), sortable: true, priority: 'high' },
  { key: 'sort_order', label: t('sale.quickNotes.columns.sortOrder'), sortable: true, align: 'right' },
]);

// ── Add, edit, delete ─────────────────────────────────────────────────────────────────────────────
const formOpen = ref(false);
const editing = ref<QuickNoteOut | null>(null);
const removal = useCommand('sale.quick_note.delete');
const removing = ref<string | null>(null);
const refused = ref<ListRefusal | null>(null);

const actions = computed<DataTableAction<QuickNoteOut>[]>(() =>
  canManage.value
    ? [
        { id: 'edit', label: t('sale.quickNotes.edit'), icon: 'ion:create-outline' },
        { id: 'delete', label: t('sale.quickNotes.delete'), icon: 'ion:trash-outline', color: 'danger', loading: (row) => removing.value === row.id },
      ]
    : [],
);

function edit(note: QuickNoteOut | null): void {
  if (!canManage.value) return;
  refused.value = null;
  editing.value = note;
  formOpen.value = true;
}

async function remove(note: QuickNoteOut): Promise<void> {
  refused.value = null;
  const yes = await confirm({
    title: t('sale.quickNotes.deleteTitle'),
    message: t('sale.quickNotes.deleteMessage', { text: note.text }),
    confirmLabel: t('sale.quickNotes.delete'),
    cancelLabel: t('sale.quickNotes.deleteCancel'),
    confirmIcon: 'ion:trash-outline',
    tone: 'danger',
  });
  if (!yes) return;
  removing.value = note.id;
  try {
    await removal.run({ id: note.id });
  } catch {
    refused.value = { heading: t('sale.quickNotes.deleteFailed'), message: refusal(removal.error.value, '')?.message };
  } finally {
    removing.value = null;
  }
}

function onAction({ actionId, row }: { actionId: string; row: QuickNoteOut }): void {
  // The server checks the permission on every command; the page does not offer what it would refuse.
  if (!canManage.value) return;
  if (actionId === 'edit') edit(row);
  else if (actionId === 'delete') void remove(row);
}

const cardTitle = (row: QuickNoteOut): string => row.text;
</script>

<template>
  <AppPage
    :title="$t('sale.title')"
    content-layout="fill"
    :tabs="saleTabs($t)"
    :tabs-label="$t('sale.tabs.label')"
  >
    <p
      class="sale-backoffice-intro"
      data-testid="sale-quick-notes-intro"
    >
      {{ $t('sale.quickNotes.intro') }}
    </p>
    <ListNotices
      testid="sale-quick-notes"
      :status="status"
      :error="error"
      :refused="refused"
    />
    <DataTable
      v-if="!blocked"
      v-model:search="table.search.value"
      testid="sale-quick-notes"
      fill
      server-side
      searchable
      :rows="result?.rows ?? []"
      :total="result?.total ?? 0"
      :page="table.page.value"
      :page-size="table.pageSize.value"
      :sort="table.sort.value"
      :sort-dir="table.dir.value"
      :views="['table', 'cards']"
      :card-title="cardTitle"
      :entity-label="{ one: $t('sale.quickNotes.entity.one'), many: $t('sale.quickNotes.entity.many') }"
      :loading="status === 'loading'"
      :error="tableError"
      :addable="canManage"
      :row-clickable="canManage"
      :actions="actions"
      :search-placeholder="$t('sale.quickNotes.search')"
      :labels="{
        add: $t('sale.quickNotes.add'),
        loading: $t('sale.quickNotes.loading'),
        loadError: $t('sale.quickNotes.loadError'),
        retry: $t('sale.live.retry'),
      }"
      :columns="columns"
      @page-change="table.goToPage"
      @load-more="table.loadMore"
      @page-size-change="table.setPageSize"
      @sort-change="table.setSort"
      @add="edit(null)"
      @row-click="edit"
      @action="onAction"
      @retry="table.refresh()"
    >
      <template #empty>
        <EmptyState
          data-testid="sale-quick-notes-empty"
          icon="chatbubbles-outline"
          :heading="table.filtered.value ? $t('sale.quickNotes.noResults') : $t('sale.quickNotes.empty')"
          :message="table.filtered.value ? $t('sale.quickNotes.noResultsMessage') : undefined"
        />
      </template>
    </DataTable>
    <QuickNoteFormModal
      v-if="canManage"
      v-model:open="formOpen"
      :note="editing"
    />
  </AppPage>
</template>

<style scoped>
.sale-backoffice-intro {
  margin: 0 0 12px;
  color: var(--ion-color-medium-shade, #5f5f5f);
}
</style>
