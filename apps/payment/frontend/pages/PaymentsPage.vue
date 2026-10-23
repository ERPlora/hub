<script setup lang="ts">
// Payments → Payments (WORKBOOK «Pantallas · Pagos»; PAYMENT-F02 to F06): «Outgoing payments», the live
// `payment.payment.list` in a server-side DataTable with the old table's Reference, Date, Beneficiary,
// Amount and Status (Method in the column chooser), «Search reference or beneficiary…», the column
// filters behind the toolbar's funnel as in the old list (the date from / to), newest payment date
// first, 50 a page, list or cards. Each row offers the step it can take
// (Approve, Mark as sent, Mark as completed) and «Cancel payment» while it is not finished, only to
// whoever may; a refusal shows above the table. «New payment» opens the form; changes come back
// through the stream.
import {
  DataTable,
  type DataTableAction,
  type DataTableColumn,
  type DataTableFilters,
  EmptyState,
  InlineFeedback,
  StatusPill,
} from '@erplora/ui/components';
import { type ApiError, useCommand } from '@erplora/ui/sdk';
import { AppPage, useSession } from '@erplora/ui/shell';
import { computed, ref } from 'vue';

import CancelPaymentModal from '../components/CancelPaymentModal.vue';
import PageNotices, { blockingError } from '../components/PageNotices.vue';
import PaymentFormModal from '../components/PaymentFormModal.vue';
import { useLiveList } from '../composables/useLiveList';
import { useServerTable } from '../composables/useServerTable';
import { useLocale, useT } from '../composables/useT';
import { formatDay, formatMoney, STATUS_TONE } from '../lib/format';
import { parseMoney } from '../lib/money';
import type { PaymentListIn, PaymentOut, PaymentStatus } from '../operations';
import { paymentTabs } from '../tabs';

const STATUSES: readonly PaymentStatus[] = ['draft', 'approved', 'sent', 'completed', 'cancelled'];
type Step = 'approve' | 'mark_sent' | 'mark_completed';
/** The step each status can take, the key of its label and who may take it. */
const NEXT: Partial<Record<PaymentStatus, { step: Step; label: string; permission: string }>> = {
  draft: { step: 'approve', label: 'payment.payments.actions.approve', permission: 'payment.approve_payment' },
  approved: { step: 'mark_sent', label: 'payment.payments.actions.markSent', permission: 'payment.add_payment' },
  sent: { step: 'mark_completed', label: 'payment.payments.actions.markCompleted', permission: 'payment.add_payment' },
};
const FINISHED: readonly PaymentStatus[] = ['completed', 'cancelled'];

const session = useSession();
const t = useT();
const locale = useLocale();
const canAdd = computed(() => session.can('payment.add_payment'));
const canApprove = computed(() => session.can('payment.approve_payment'));

const table = useServerTable({ sort: '-payment_date' });
const filters = ref<DataTableFilters>({});

/** Cents of a typed amount bound; nothing when it is not an amount (never «from 0»). */
function cents(text: string | undefined): number | undefined {
  if (!text) return undefined;
  const read = parseMoney(text);
  return read.ok && read.cents !== null ? read.cents : undefined;
}

/** The table's filters as the query takes them: each end of the dates as sent, amounts in cents. */
const query = computed<Partial<PaymentListIn>>(() => {
  const f = filters.value;
  const out: Partial<PaymentListIn> = {
    ...(f.reference ? { reference: f.reference } : {}),
    ...(f.payment_date_from ? { payment_date_from: f.payment_date_from } : {}),
    ...(f.payment_date_to ? { payment_date_to: f.payment_date_to } : {}),
    ...(f.beneficiary_name ? { beneficiary_name: f.beneficiary_name } : {}),
  };
  const min = cents(f.amount_from);
  const max = cents(f.amount_to);
  if (min !== undefined) out.amount_min = min;
  if (max !== undefined) out.amount_max = max;
  if (f.status) out.status = f.status as PaymentStatus;
  return out;
});

function onFilters(now: DataTableFilters): void {
  filters.value = now;
  table.restart({ narrowed: Object.keys(now).length > 0 });
}

const { data: result, status, error, refresh } = useLiveList(
  'payment.payment.list',
  () => ({ ...query.value, ...table.query.value }),
  () => table.windows.value,
);
table.followResult(result);
const blocked = computed(() => blockingError(error.value));

const columns = computed<DataTableColumn<PaymentOut>[]>(() => [
  { key: 'reference', label: t('payment.payments.columns.reference'), sortable: true, priority: 'high', filter: { type: 'text' } },
  {
    key: 'payment_date',
    label: t('payment.payments.columns.date'),
    sortable: true,
    format: (_, row) => formatDay(row.payment_date, locale.value),
    filter: { type: 'daterange' },
  },
  { key: 'beneficiary_name', label: t('payment.payments.columns.beneficiary'), sortable: true, filter: { type: 'text' } },
  {
    key: 'amount',
    label: t('payment.payments.columns.amount'),
    sortable: true,
    align: 'right',
    format: (_, row) => formatMoney(row.amount, locale.value, row.currency),
    filter: { type: 'range' },
  },
  {
    key: 'status',
    label: t('payment.payments.columns.status'),
    sortable: true,
    cell: 'status',
    filter: { type: 'select', options: STATUSES.map((value) => ({ value, label: t(`payment.status.${value}`) })) },
  },
  { key: 'method_name', label: t('payment.payments.columns.method'), sortable: true, hidden: true },
]);

const actions = computed<DataTableAction<PaymentOut>[]>(() => [
  {
    id: 'advance',
    label: (row) => (NEXT[row.status] ? t(NEXT[row.status]!.label) : ''),
    icon: 'chevron-forward-outline',
    color: 'primary',
    showLabel: true,
    pinned: true,
    loading: (row) => busy.value === row.id,
    hidden: (row) => !NEXT[row.status] || !session.can(NEXT[row.status]!.permission),
  },
  {
    id: 'cancel',
    label: t('payment.payments.actions.cancel'),
    icon: 'close-outline',
    color: 'danger',
    hidden: (row) => FINISHED.includes(row.status) || !canApprove.value,
  },
]);

// The form
const formOpen = ref(false);

// Row actions
const commands = {
  approve: useCommand('payment.payment.approve'),
  mark_sent: useCommand('payment.payment.mark_sent'),
  mark_completed: useCommand('payment.payment.mark_completed'),
};
const rowError = ref<ApiError | null>(null);
/** The row whose step is running: a second tap meanwhile does nothing (one command per tap). */
const busy = ref<string | null>(null);
const cancelling = ref<PaymentOut | null>(null);
const cancelOpen = ref(false);

async function onAction({ actionId, row }: { actionId: string; row: PaymentOut }): Promise<void> {
  rowError.value = null;
  if (actionId === 'cancel') {
    cancelling.value = row;
    cancelOpen.value = true;
    return;
  }
  const next = NEXT[row.status];
  if (actionId !== 'advance' || !next || busy.value) return;
  const command = commands[next.step];
  busy.value = row.id;
  try {
    await command.run({ id: row.id });
  } catch {
    rowError.value = command.error.value;
  } finally {
    busy.value = null;
  }
}

/** A new payment heads the first page (newest first): the search, the filters and the order stay. */
function onCreated(): void {
  table.goToPage(0);
}
</script>

<template>
  <AppPage
    :title="$t('payment.title')"
    content-layout="fill"
    :tabs="paymentTabs($t)"
    :tabs-label="$t('payment.tabs.label')"
  >
    <PageNotices
      testid="payment-payments"
      :status="status"
      :error="error"
    />
    <InlineFeedback
      v-if="rowError"
      tone="danger"
      dismissible
      data-testid="payment-payments-row-error"
      :heading="t('payment.payments.actionError')"
      @dismiss="rowError = null"
    >
      {{ rowError.message }}
    </InlineFeedback>
    <DataTable
      v-if="!blocked"
      v-model:search="table.search.value"
      testid="payment-payments"
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
      :card-title="(row: PaymentOut) => row.reference"
      :card-icon="() => 'receipt-outline'"
      :entity-label="{ one: $t('payment.payments.entity.one'), many: $t('payment.payments.entity.many') }"
      :loading="status === 'loading'"
      :error="status === 'error' && !blocked ? $t('payment.payments.loadError') : undefined"
      :addable="canAdd"
      :actions="actions"
      :search-placeholder="$t('payment.payments.search')"
      :labels="{ add: $t('payment.payments.new'), loadError: $t('payment.payments.loadError'), retry: $t('payment.live.retry') }"
      :columns="columns"
      @filters-change="onFilters"
      @page-change="table.goToPage"
      @load-more="table.loadMore"
      @page-size-change="table.setPageSize"
      @sort-change="table.setSort"
      @add="formOpen = true"
      @action="onAction"
      @retry="refresh()"
    >
      <template #status="{ row }">
        <span class="payment-status">
          <StatusPill
            size="sm"
            :tone="STATUS_TONE[row.status]"
            :label="t(`payment.status.${row.status}`)"
          />
          <small
            v-if="row.status === 'cancelled' && row.cancel_reason"
            class="payment-status__reason"
          >{{ t('payment.payments.cancelReason', { reason: row.cancel_reason }) }}</small>
          <small
            v-else-if="row.approved_by"
            class="payment-status__reason"
          >{{ t('payment.payments.approvedBy', { name: row.approved_by }) }}</small>
        </span>
      </template>
      <template #empty>
        <EmptyState
          data-testid="payment-payments-empty"
          icon="receipt-outline"
          :heading="table.filtered.value ? $t('payment.noResults') : $t('payment.payments.empty')"
          :message="table.filtered.value ? $t('payment.noResultsMessage') : undefined"
        />
      </template>
    </DataTable>
    <PaymentFormModal
      v-model:open="formOpen"
      @created="onCreated"
    />
    <CancelPaymentModal
      v-model:open="cancelOpen"
      :payment="cancelling"
    />
  </AppPage>
</template>

<style scoped>
.payment-status {
  display: inline-flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
}

.payment-status__reason {
  color: var(--ion-color-medium);
  font-size: 0.8em;
}
</style>
