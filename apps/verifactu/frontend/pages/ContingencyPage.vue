<script setup lang="ts">
// VeriFactu → Contingency (VERIFACTU-F20–F22; the old `erp-verifactu-contingency`): «Contingency queue» and «Process
// queue» («Processing…» while it works; for whoever may send). The live `verifactu.contingency.list`: the records
// that are not in the AEAT yet — Invoice (its number, not an internal id), Environment, Attempts, Status (translated),
// Next attempt and Last error —, in the order they go out, with «Retry» (out with the next pass) and «View». The
// result of a pass is said under the button. There is no «Cancel»: a record generated is never discarded.
import { type DataTableAction, type DataTableColumn, DataTable, EmptyState, formatDateTime, InlineFeedback, StatusPill } from '@erplora/ui/components';
import { useCommand } from '@erplora/ui/sdk';
import { AppPage, toastSuccess, useSession } from '@erplora/ui/shell';
import { IonButton } from '@ionic/vue';
import { computed, shallowRef } from 'vue';
import { useRouter } from 'vue-router';

import PageNotices, { blockingError } from '../components/PageNotices.vue';
import { useServerTable } from '../composables/useServerTable';
import { useLocale, useT } from '../composables/useT';
import { statusTone } from '../lib/record';
import { refusal } from '../lib/refusal';
import type { QueueRowOut } from '../operations';
import { verifactuTabs } from '../tabs';

const router = useRouter();
const session = useSession();
const canSend = computed(() => session.can('verifactu.transmit_record'));
const t = useT();
const locale = useLocale();

const table = useServerTable('verifactu.contingency.list', { sort: 'next_attempt_at', dir: 'asc', maxSearch: 120 });
const { data: result, status, error, refresh } = table;
const blocked = computed(() => blockingError(error.value));
const tableError = computed(() => (status.value === 'error' ? error.value?.message : undefined));

const process = useCommand('verifactu.contingency.process');
const retry = useCommand('verifactu.contingency.retry');
const outcome = shallowRef<{ tone: 'success' | 'warning' | 'danger'; text: string } | null>(null);

const columns = computed<DataTableColumn<QueueRowOut>[]>(() => [
  { key: 'invoice_number', label: t('verifactu.contingency.columns.invoice'), sortable: true, priority: 'high', width: 'minmax(9rem, 11rem)' },
  { key: 'environment', label: t('verifactu.contingency.columns.environment'), width: 'minmax(7rem, 9rem)', format: (_, row) => t(`verifactu.env.${row.environment}`) },
  { key: 'attempts', label: t('verifactu.contingency.columns.attempts'), sortable: true, align: 'right', width: 'minmax(5rem, 6rem)' },
  { key: 'status', label: t('verifactu.contingency.columns.status'), sortable: true, cell: 'status', width: 'minmax(7rem, 10rem)', format: (_, row) => t(`verifactu.status.${row.status}`) },
  { key: 'next_attempt_at', label: t('verifactu.contingency.columns.nextAttempt'), sortable: true, width: 'minmax(9rem, 11rem)', format: (_, row) => formatDateTime(row.next_attempt_at, locale.value) },
  { key: 'last_error', label: t('verifactu.contingency.columns.lastError'), priority: 'low', width: 'minmax(10rem, 1fr)', format: (_, row) => row.last_error || '—' },
]);

const actions = computed<DataTableAction<QueueRowOut>[]>(() => [
  ...(canSend.value ? [{ id: 'retry', label: t('verifactu.contingency.actions.retry'), icon: 'ion:refresh-outline' }] : []),
  { id: 'view', label: t('verifactu.contingency.actions.view'), icon: 'lucide:eye', pinned: true },
]);

async function processQueue(): Promise<void> {
  if (process.pending.value) return;
  outcome.value = null;
  try {
    const answer = await process.run({});
    outcome.value = answer.reason
      ? { tone: 'warning', text: answer.message }
      : {
          tone: 'success',
          text: t('verifactu.contingency.processed', {
            sent: answer.sent,
            accepted: answer.accepted + answer.accepted_with_errors,
            rejected: answer.rejected,
            waiting: answer.waiting,
          }),
        };
  } catch {
    outcome.value = { tone: 'danger', text: refusal(process.error.value, t('verifactu.contingency.processFailed'))?.message ?? t('verifactu.contingency.processFailed') };
  }
}

async function onAction({ actionId, row }: { actionId: string; row: QueueRowOut }): Promise<void> {
  if (actionId === 'view') {
    void router.push(`/verifactu/records/${row.id}`);
    return;
  }
  if (actionId !== 'retry' || !canSend.value) return;
  outcome.value = null;
  try {
    await retry.run({ record_id: row.id });
  } catch {
    outcome.value = { tone: 'danger', text: refusal(retry.error.value, t('verifactu.contingency.retryFailed'))?.message ?? t('verifactu.contingency.retryFailed') };
    return;
  }
  void toastSuccess(t('verifactu.contingency.retried', { number: row.invoice_number }));
}
</script>

<template>
  <AppPage
    :title="$t('verifactu.contingency.title')"
    :tabs="verifactuTabs($t)"
    :tabs-label="$t('verifactu.tabs.label')"
  >
    <PageNotices
      testid="verifactu-queue"
      :status="status"
      :error="error"
    />
    <div
      v-if="canSend && !blocked"
      class="verifactu-queue__bar"
    >
      <ion-button
        data-testid="verifactu-queue-process"
        :disabled="process.pending.value"
        @click="processQueue"
      >
        {{ process.pending.value || retry.pending.value ? $t('verifactu.contingency.processing') : $t('verifactu.contingency.process') }}
      </ion-button>
    </div>
    <InlineFeedback
      v-if="outcome"
      :tone="outcome.tone"
      data-testid="verifactu-queue-result"
    >
      {{ outcome.text }}
    </InlineFeedback>
    <DataTable
      v-if="!blocked"
      v-model:search="table.search.value"
      testid="verifactu-queue"
      server-side
      searchable
      row-clickable
      :rows="result?.rows ?? []"
      :total="result?.total ?? 0"
      :page="table.page.value"
      :page-size="table.pageSize.value"
      :sort="table.sort.value"
      :sort-dir="table.dir.value"
      :views="['table', 'cards']"
      :card-title="(row: QueueRowOut) => row.invoice_number"
      :card-icon="() => 'warning-outline'"
      :entity-label="{ one: $t('verifactu.contingency.entity.one'), many: $t('verifactu.contingency.entity.many') }"
      :loading="status === 'loading'"
      :error="tableError"
      :actions="actions"
      :search-placeholder="$t('verifactu.contingency.search')"
      :labels="{ loading: $t('verifactu.contingency.loading'), loadError: $t('verifactu.contingency.loadError'), retry: $t('verifactu.live.retry') }"
      :columns="columns"
      @page-change="table.goToPage"
      @load-more="table.loadMore"
      @page-size-change="table.setPageSize"
      @sort-change="table.setSort"
      @row-click="(row: QueueRowOut) => onAction({ actionId: 'view', row })"
      @action="onAction"
      @retry="refresh()"
    >
      <template #status="{ row }">
        <StatusPill
          size="sm"
          :tone="statusTone(row.status)"
          :label="$t(`verifactu.status.${row.status}`)"
        />
      </template>
      <template #empty>
        <EmptyState
          data-testid="verifactu-queue-empty"
          icon="checkmark-circle-outline"
          :heading="table.filtered.value ? $t('verifactu.records.noResults') : $t('verifactu.contingency.empty')"
        />
      </template>
    </DataTable>
  </AppPage>
</template>

<style scoped>
.verifactu-queue__bar {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 0.75rem;
}
</style>
