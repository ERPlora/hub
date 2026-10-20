<script setup lang="ts">
// «Your automations» (WORKBOOK FLOW-F02, F03, F06, F07; `flow.flow.list`, live): the business's
// automations in the Hub's server-side DataTable. Each row says its name and when it starts in words,
// how its last run ended, and Active/Paused with its switch (saved at once). Search, «Showing»,
// «Starts with» and «Order» (the old screen's three) query the server again, with the count «Showing
// N of M». Several chosen are turned on or paused, one after another. A row is copied (paused, with no
// permission) or deleted (asked first); tapping it opens the editor. A refusal is said above the list.
import {
  DataTable,
  type DataTableAction,
  type DataTableColumn,
  EmptyState,
  InlineFeedback,
  StatusPill,
  useConfirm,
} from '@erplora/ui/components';
import { type ApiError, useCommand } from '@erplora/ui/sdk';
import { toastInfo, toastSuccess } from '@erplora/ui/shell';
import { IonButton, IonSelect, IonSelectOption, IonToggle } from '@ionic/vue';
import { computed, ref, shallowRef, watch } from 'vue';

import { useLiveList } from '../composables/useLiveList';
import { usePhrasing } from '../composables/usePhrasing';
import { wording } from '../lib/refusal';
import { useServerTable } from '../composables/useServerTable';
import { describeTrigger, runStatusPill, statePill } from '../lib/phrasing';
import type { CatalogOut, FlowListIn, FlowOut, TriggerKind } from '../operations';

defineProps<{ catalog: CatalogOut | null; /** Automations of the business, unfiltered. */ allTotal: number }>();
const emit = defineEmits<{ open: [flow: FlowOut]; ready: [] }>();
const phrasing = usePhrasing();
const { confirm } = useConfirm();

type StateFilter = '' | 'active' | 'paused';
type Order = 'updated' | 'name';
const table = useServerTable({ sort: '-updated_at' });
const state = ref<StateFilter>('');
const startsWith = ref<'' | TriggerKind>('');
const order = ref<Order>('updated');
watch([state, startsWith], () => table.restart({ narrowed: !!state.value || !!startsWith.value }));
watch(order, (now) => table.setSort(now === 'name' ? { sort: 'name', dir: 'asc' } : { sort: 'updated_at', dir: 'desc' }));

const query = computed<Omit<FlowListIn, 'limit' | 'offset'>>(() => ({
  ...table.query.value,
  sort: table.query.value.sort as FlowListIn['sort'],
  ...(state.value ? { enabled: state.value === 'active' } : {}),
  ...(startsWith.value ? { trigger_kind: startsWith.value } : {}),
}));
const { data: result, status, error: listError, refresh } = useLiveList('flow.flow.list', () => query.value, () => table.windows.value);
table.followResult(result);
// Its first page (or failure) is painted: the page opens a linked card of the gallery below only then.
let told = false;
watch(
  () => result.value ?? listError.value,
  (answer) => {
    if (answer && !told) {
      told = true;
      emit('ready');
    }
  },
  { immediate: true },
);

const selected = ref<string[]>([]);
const error = shallowRef<ApiError | null>(null);
const switching = useCommand('flow.flow.set_enabled');
const duplicating = useCommand('flow.flow.duplicate');
const deleting = useCommand('flow.flow.delete');

async function attempt(work: () => Promise<void>): Promise<void> {
  error.value = null;
  try {
    await work();
  } catch (failure) {
    error.value = failure as ApiError;
  }
}

async function setEnabled(flow: Pick<FlowOut, 'id'>, enabled: boolean): Promise<void> {
  const saved = await switching.run({ id: flow.id, enabled });
  if (saved.enabled && saved.missing_grants.length) void toastInfo(phrasing.value.t('flow.list.enabledMissing'));
}

function toggle(flow: FlowOut, enabled: boolean): void {
  if (enabled !== flow.enabled) void attempt(() => setEnabled(flow, enabled));
}

async function bulk(enabled: boolean): Promise<void> {
  const ids = [...selected.value];
  // Let go first: a second press on a bar that is still there would repeat the whole thing.
  selected.value = [];
  await attempt(async () => {
    for (const id of ids) await setEnabled({ id }, enabled);
  });
}

async function onAction({ actionId, row }: { actionId: string; row: FlowOut }): Promise<void> {
  const t = phrasing.value.t;
  if (actionId === 'duplicate') {
    await attempt(async () => {
      await duplicating.run({ id: row.id });
      void toastSuccess(t('flow.list.copied'));
    });
    return;
  }
  const yes = await confirm({
    title: t('flow.list.deleteTitle', { name: row.name }),
    message: t('flow.list.deleteMessage'),
    tone: 'danger',
    confirmLabel: t('flow.list.deleteYes'),
    cancelLabel: t('flow.list.deleteNo'),
  });
  if (!yes) return;
  await attempt(async () => {
    await deleting.run({ id: row.id });
    void toastSuccess(t('flow.list.deleted'));
  });
}

function clearFilters(): void {
  state.value = '';
  startsWith.value = '';
  table.search.value = '';
}

function when(iso: string): string {
  return new Intl.DateTimeFormat(phrasing.value.locale, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(iso));
}

const columns = computed<DataTableColumn<FlowOut>[]>(() => [
  { key: 'name', label: phrasing.value.t('flow.list.columns.name'), cell: 'name', priority: 'high', width: 'minmax(12rem,2fr)' },
  { key: 'last_run', label: phrasing.value.t('flow.list.columns.lastRun'), cell: 'lastRun', priority: 'low' },
  { key: 'enabled', label: phrasing.value.t('flow.list.columns.state'), cell: 'state', width: '11rem' },
]);

const actions = computed<DataTableAction<FlowOut>[]>(() => [
  { id: 'duplicate', label: phrasing.value.t('flow.list.duplicate'), icon: 'ion:copy-outline' },
  { id: 'delete', label: phrasing.value.t('flow.list.delete'), icon: 'ion:trash-outline', color: 'danger' },
]);

const tableError = computed(() => (status.value === 'error' && listError.value ? wording(listError.value, phrasing.value.t('flow.errors.read')) : undefined));
</script>

<template>
  <section
    class="flow-list"
    data-testid="flow-list-section"
  >
    <h2 class="flow-section">
      {{ $t('flow.list.heading') }}
    </h2>
    <InlineFeedback
      v-if="error"
      tone="danger"
      data-testid="flow-list-error"
    >
      {{ wording(error, $t('flow.errors.action')) }}
    </InlineFeedback>
    <DataTable
      v-model:search="table.search.value"
      v-model:selected="selected"
      testid="flow-list"
      server-side
      searchable
      selectable
      row-clickable
      row-key="id"
      :rows="result?.rows ?? []"
      :total="result?.total ?? 0"
      :page="table.page.value"
      :page-size="table.pageSize.value"
      :views="['table', 'cards']"
      :card-title="(row: FlowOut) => row.name"
      :entity-label="{ one: $t('flow.list.entity.one'), many: $t('flow.list.entity.many') }"
      :loading="status === 'loading'"
      :error="tableError"
      :search-placeholder="$t('flow.list.search')"
      :labels="{ loadError: $t('flow.list.loadError'), retry: $t('flow.live.retry') }"
      :columns="columns"
      :actions="actions"
      @page-change="table.goToPage"
      @load-more="table.loadMore"
      @page-size-change="table.setPageSize"
      @row-click="emit('open', $event)"
      @action="onAction"
      @retry="refresh()"
    >
      <template #filters>
        <div class="flow-list__filters">
          <IonSelect
            data-testid="flow-list-state"
            :value="state"
            :label="$t('flow.list.filterState')"
            label-placement="floating"
            fill="outline"
            mode="md"
            interface="popover"
            @ion-change="state = $event.detail.value"
          >
            <IonSelectOption value="">
              {{ $t('flow.list.stateAll') }}
            </IonSelectOption>
            <IonSelectOption value="active">
              {{ $t('flow.list.stateActive') }}
            </IonSelectOption>
            <IonSelectOption value="paused">
              {{ $t('flow.list.statePaused') }}
            </IonSelectOption>
          </IonSelect>
          <IonSelect
            data-testid="flow-list-trigger"
            :value="startsWith"
            :label="$t('flow.list.filterTrigger')"
            label-placement="floating"
            fill="outline"
            mode="md"
            interface="popover"
            @ion-change="startsWith = $event.detail.value"
          >
            <IonSelectOption value="">
              {{ $t('flow.list.triggerAny') }}
            </IonSelectOption>
            <IonSelectOption value="event">
              {{ $t('flow.list.triggerEvent') }}
            </IonSelectOption>
            <IonSelectOption value="schedule">
              {{ $t('flow.list.triggerSchedule') }}
            </IonSelectOption>
            <IonSelectOption value="at">
              {{ $t('flow.list.triggerAt') }}
            </IonSelectOption>
            <IonSelectOption value="manual">
              {{ $t('flow.list.triggerManual') }}
            </IonSelectOption>
          </IonSelect>
          <IonSelect
            data-testid="flow-list-sort"
            :value="order"
            :label="$t('flow.list.sortLabel')"
            label-placement="floating"
            fill="outline"
            mode="md"
            interface="popover"
            @ion-change="order = $event.detail.value"
          >
            <IonSelectOption value="updated">
              {{ $t('flow.list.sortUpdated') }}
            </IonSelectOption>
            <IonSelectOption value="name">
              {{ $t('flow.list.sortName') }}
            </IonSelectOption>
          </IonSelect>
          <span
            class="flow-list__count"
            data-testid="flow-list-count"
          >{{ $t('flow.list.count', { shown: result?.total ?? 0, total: allTotal }) }}</span>
        </div>
      </template>
      <template #toolbar>
        <div
          v-if="selected.length"
          class="flow-list__bulk"
        >
          <IonButton
            size="small"
            fill="outline"
            mode="md"
            data-testid="flow-list-bulk-enable"
            @click="bulk(true)"
          >
            {{ $t('flow.list.bulkEnable') }}
          </IonButton>
          <IonButton
            size="small"
            fill="outline"
            mode="md"
            data-testid="flow-list-bulk-pause"
            @click="bulk(false)"
          >
            {{ $t('flow.list.bulkPause') }}
          </IonButton>
        </div>
      </template>
      <template #name="{ row }">
        <span class="flow-list__name">
          <strong>{{ row.name }}</strong>
          <span class="flow-list__when">{{ describeTrigger(row.trigger, catalog, phrasing) }}</span>
        </span>
      </template>
      <template #lastRun="{ row }">
        <span
          v-if="row.last_run"
          class="flow-list__run"
        >
          <StatusPill
            size="sm"
            v-bind="runStatusPill(row.last_run.status, phrasing)"
          />
          <span class="flow-list__when">{{ when(row.last_run.started_at) }}</span>
        </span>
        <span
          v-else
          class="flow-list__when"
        >{{ $t('flow.list.neverRan') }}</span>
      </template>
      <template #state="{ row }">
        <span
          class="flow-list__state"
          @click.stop
        >
          <StatusPill v-bind="statePill(row, phrasing)" />
          <IonToggle
            :checked="row.enabled"
            :aria-label="$t('flow.list.enable', { name: row.name })"
            :data-testid="`flow-list-toggle-${row.id}`"
            @ion-change="toggle(row, $event.detail.checked)"
          />
        </span>
      </template>
      <template #empty>
        <div data-testid="flow-list-nomatch">
          <EmptyState
            icon="search-outline"
            :heading="$t('flow.list.noMatch')"
          />
          <IonButton
            size="small"
            fill="outline"
            mode="md"
            data-testid="flow-list-clear"
            @click="clearFilters"
          >
            {{ $t('flow.list.clear') }}
          </IonButton>
        </div>
      </template>
    </DataTable>
  </section>
</template>

<style scoped>
.flow-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.flow-section {
  margin: 0.5rem 0 0;
  font-size: 1.05rem;
  font-weight: 600;
}
.flow-list__filters {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
}
.flow-list__filters ion-select {
  min-width: 11rem;
}
.flow-list__count,
.flow-list__when {
  font-size: 0.82rem;
  color: var(--ep-muted, var(--ion-color-medium));
}
.flow-list__bulk {
  display: flex;
  gap: 0.4rem;
}
.flow-list__name,
.flow-list__run {
  display: flex;
  flex-direction: column;
  gap: 0.1rem;
  min-width: 0;
}
.flow-list__state {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
}
</style>
