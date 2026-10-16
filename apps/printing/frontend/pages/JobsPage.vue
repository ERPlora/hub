<script setup lang="ts">
// Printing → Queue (WORKBOOK «Pantallas · Cola»; the old screen's queue list): «Print queue», the live
// `printing.job.list` newest first in a server-side DataTable — Document («Receipt T-000123»), Role,
// Printer, Status, Attempts, Asked on and Detail (the last error, no answer, who sent it again or cancelled
// it and why) —, «Search document…», a filter per column (status, role, printer), 50 a page, list or cards.
// Whoever manages the queue (PRINTING-F14) sees «Try again» on a failed or unanswered job and «Cancel» on a
// queued, failed or unanswered one; nothing is ever deleted. Every change comes back through the stream.
import {
  DataTable,
  type DataTableAction,
  type DataTableColumn,
  type DataTableFilters,
  EmptyState,
  formatDateTime,
  InlineFeedback,
  StatusPill,
} from '@erplora/ui/components';
import { useCommand, useLive } from '@erplora/ui/sdk';
import { AppPage, toastError, toastSuccess, useSession } from '@erplora/ui/shell';
import { computed, ref, shallowRef } from 'vue';

import CancelJobModal from '../components/CancelJobModal.vue';
import { useNow } from '../composables/useNow';
import { useServerTable } from '../composables/useServerTable';
import { useLocale, useT } from '../composables/useT';
import { JOB_TONE, jobDetail, jobFlags, jobTitle } from '../lib/format';
import { refusal } from '../lib/refusal';
import type { JobListIn, JobOut, JobStatus, Usage } from '../operations';
import { printingTabs } from '../tabs';

const STATUSES: readonly JobStatus[] = ['pending', 'sent', 'done', 'failed', 'cancelled'];
const USAGES: readonly Usage[] = ['receipt', 'kitchen', 'bar', 'label'];

const session = useSession();
const canManage = computed(() => session.can('printing.manage_jobs'));
const t = useT();
const locale = useLocale();
/** A sent job past its lease turns «no answer» by the clock, without another result. */
const now = useNow();

const filters = ref<DataTableFilters>({});
/** The table's filters as the list takes them. */
const query = computed<Partial<JobListIn>>(() => {
  const f = filters.value;
  return {
    ...(f.status ? { status: f.status as JobStatus } : {}),
    ...(f.usage ? { usage: f.usage as Usage } : {}),
    ...(f.printer_id ? { printer_id: f.printer_id } : {}),
  };
});
const table = useServerTable('printing.job.list', {
  sort: 'created_at',
  dir: 'desc',
  maxSearch: 64,
  filters: () => query.value,
  narrowed: () => Object.keys(filters.value).length > 0,
});
const { data: result, status, error, refresh } = table;
const printers = useLive('printing.printer.list', { limit: 100 });
const retry = useCommand('printing.job.retry');

const blocked = computed(() => (error.value?.code === 'app_inactive' || error.value?.code === 'permission_denied' ? error.value.code : null));
const tableError = computed(() => (status.value === 'error' && !blocked.value ? t('printing.jobs.loadError') : undefined));

const columns = computed<DataTableColumn<JobOut>[]>(() => [
  { key: 'document', label: t('printing.jobs.columns.document'), priority: 'high', format: (_, row) => jobTitle(row, t, locale.value) },
  {
    key: 'usage',
    label: t('printing.jobs.columns.usage'),
    sortable: true,
    format: (_, row) => t(`printing.usage.${row.usage}`),
    filter: { type: 'select', options: USAGES.map((value) => ({ value, label: t(`printing.usage.${value}`) })) },
  },
  {
    key: 'printer_id',
    label: t('printing.jobs.columns.printer'),
    format: (_, row) => row.printer_name ?? t('printing.jobs.noPrinter'),
    filter: { type: 'select', options: (printers.data.value?.rows ?? []).map((p) => ({ value: p.id, label: p.name })) },
  },
  {
    key: 'status',
    label: t('printing.jobs.columns.status'),
    sortable: true,
    cell: 'status',
    format: (_, row) => t(`printing.status.${row.status}`),
    filter: { type: 'select', options: STATUSES.map((value) => ({ value, label: t(`printing.status.${value}`) })) },
  },
  { key: 'attempts', label: t('printing.jobs.columns.attempts'), sortable: true, align: 'right' },
  { key: 'created_at', label: t('printing.jobs.columns.created'), sortable: true, format: (_, row) => formatDateTime(row.created_at, locale.value) },
  { key: 'detail', label: t('printing.jobs.columns.detail'), priority: 'low', format: (_, row) => jobDetail(row, t, now.value) },
]);

const retrying = shallowRef<string | null>(null);
const actions = computed<DataTableAction<JobOut>[]>(() =>
  canManage.value
    ? [
        {
          id: 'retry',
          label: t('printing.jobs.actions.retry'),
          icon: 'refresh-outline',
          showLabel: true,
          hidden: (row) => !jobFlags(row, now.value).retryable,
          loading: (row) => retrying.value === row.id,
        },
        {
          id: 'cancel',
          label: t('printing.jobs.actions.cancel'),
          icon: 'close-circle-outline',
          color: 'danger',
          hidden: (row) => !jobFlags(row, now.value).cancellable,
        },
      ]
    : [],
);

const cancelling = shallowRef(false);
const target = shallowRef<JobOut | null>(null);

async function sendBack(row: JobOut): Promise<void> {
  retrying.value = row.id;
  try {
    await retry.run({ job_id: row.id });
    void toastSuccess(t('printing.jobs.retried'));
  } catch {
    void toastError(refusal(retry.error.value, t('printing.jobs.retryFailed'))?.message ?? t('printing.jobs.retryFailed'));
  } finally {
    retrying.value = null;
  }
}

function onAction({ actionId, row }: { actionId: string; row: JobOut }): void {
  if (!canManage.value) return;
  const flags = jobFlags(row, now.value);
  if (actionId === 'retry' && flags.retryable && !retrying.value) void sendBack(row);
  else if (actionId === 'cancel' && flags.cancellable) {
    target.value = row;
    cancelling.value = true;
  }
}
</script>

<template>
  <AppPage
    :title="$t('printing.title')"
    content-layout="fill"
    :tabs="printingTabs($t)"
    :tabs-label="$t('printing.tabs.label')"
  >
    <h2
      class="printing-jobs__heading"
      data-testid="printing-jobs-heading"
    >
      {{ $t('printing.jobs.heading') }}
    </h2>
    <InlineFeedback
      v-if="blocked"
      tone="warning"
      :data-testid="blocked === 'app_inactive' ? 'printing-jobs-inactive' : 'printing-jobs-forbidden'"
      :heading="blocked === 'app_inactive' ? $t('printing.live.appInactive') : $t('printing.live.noPermission')"
    >
      {{ error?.message }}
    </InlineFeedback>
    <DataTable
      v-else
      v-model:search="table.search.value"
      v-model:filters="filters"
      testid="printing-jobs"
      fill
      server-side
      searchable
      :rows="result?.rows ?? []"
      :total="result?.total ?? 0"
      :page="table.page.value"
      :page-size="table.pageSize.value"
      :page-size-chooser="false"
      :sort="table.sort.value"
      :sort-dir="table.dir.value"
      :views="['table', 'cards']"
      :card-title="(row: JobOut) => jobTitle(row, t, locale)"
      card-title-column="document"
      :card-icon="() => 'list-outline'"
      :entity-label="{ one: $t('printing.jobs.entity.one'), many: $t('printing.jobs.entity.many') }"
      :loading="status === 'loading'"
      :error="tableError"
      :actions="actions"
      :max-inline-actions="2"
      :search-placeholder="$t('printing.jobs.search')"
      :labels="{ loading: $t('printing.jobs.loading'), loadError: $t('printing.jobs.loadError'), retry: $t('printing.live.retry') }"
      :columns="columns"
      @page-change="table.goToPage"
      @load-more="table.loadMore"
      @sort-change="table.setSort"
      @action="onAction"
      @retry="refresh()"
    >
      <template #status="{ row }">
        <span :data-testid="`printing-jobs-status-${row.id}`">
          <StatusPill
            size="sm"
            :tone="JOB_TONE[row.status as JobStatus]"
            :busy="row.status === 'sent' && !jobFlags(row as JobOut, now).stale"
            :label="t(`printing.status.${row.status}`)"
          />
        </span>
      </template>
      <template #empty>
        <EmptyState
          data-testid="printing-jobs-empty"
          icon="file-tray-outline"
          :heading="table.filtered.value ? $t('printing.jobs.noMatches') : $t('printing.jobs.empty')"
        />
      </template>
    </DataTable>

    <CancelJobModal
      v-if="canManage"
      v-model:open="cancelling"
      :job="target"
    />
  </AppPage>
</template>

<style scoped>
.printing-jobs__heading {
  margin: 0 0 8px;
  padding-inline: 0.25rem;
  font-size: 1.05rem;
  font-weight: 600;
}
</style>
