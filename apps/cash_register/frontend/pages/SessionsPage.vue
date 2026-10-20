<script setup lang="ts">
// Cash register → the sessions (WORKBOOK «Pantallas · Caja»; the old `erp-cashregister-dashboard`): the title
// «Cash register» and «Open session» (off while a session is open, saying why; on again when the open one
// is past its daily cut-off, which opening the next one closes), and the live `cash_register.session.list`
// newest first in a server-side DataTable — Session, Opened on, Status, Opening, Expected (live while open,
// empty when a blind count hides it from this person), Counted, Difference with its sign — with search by
// number, the filters behind the table's funnel (Session, Status and the four amounts on their columns,
// the amounts typed in euros), table or cards and 50 a page. «Detail» on every row (the row opens it too) and, on
// the open session, «Movement», «Count» and «Close», each by its permission; a closing count opens the
// close. The cash charged with no session open is said, with its list. Above the table, the drawer's figures
// (CASH_REGISTER-F12: the open session's expected cash and the recent discrepancies). Every action comes back
// through the stream by itself: nothing here refetches.
import {
  type DataTableAction,
  type DataTableColumn,
  type DataTableFilters,
  DataTable,
  EmptyState,
  formatDateTime,
  InlineFeedback,
} from '@erplora/ui/components';
import { useLive } from '@erplora/ui/sdk';
import { AppPage, useSession } from '@erplora/ui/shell';
import { IonButton } from '@ionic/vue';
import { computed, ref, shallowRef } from 'vue';
import { useRouter } from 'vue-router';

import CashFigures from '../components/CashFigures.vue';
import CloseSessionModal from '../components/CloseSessionModal.vue';
import CountModal from '../components/CountModal.vue';
import MovementModal from '../components/MovementModal.vue';
import OpenSessionModal from '../components/OpenSessionModal.vue';
import UnassignedModal from '../components/UnassignedModal.vue';
import { useServerTable } from '../composables/useServerTable';
import { useLocale, useT } from '../composables/useT';
import { formatMoney, formatSignedMoney } from '../lib/money';
import { AMOUNT_RANGES, filterParams, filtersInUse, SESSION_STATUSES, unreadableAmounts } from '../lib/sessionFilters';
import type { CountType, SessionRow } from '../operations';
import { cashRegisterTabs } from '../tabs';

const session = useSession();
const can = (permission: string) => computed(() => session.can(permission));
const canOpen = can('cash_register.add_session');
const canMove = can('cash_register.add_movement');
const canCount = can('cash_register.add_count');
const canClose = can('cash_register.close_session');
const t = useT();
const locale = useLocale();
const router = useRouter();

const current = useLive('cash_register.session.current', {});
/** The table's filters (its funnel), as typed: the amounts in euros. A filter not in use is absent. */
const filters = ref<DataTableFilters>({});
const table = useServerTable('cash_register.session.list', {
  sort: 'opened_at',
  dir: 'desc',
  maxSearch: 24,
  filters: () => filterParams(filters.value),
  // Only the filters that really apply narrow the list (an amount it cannot read does not).
  narrowed: () => filtersInUse(filters.value) > 0,
});
const { data: result, status, error, refresh } = table;

/** The failures that replace the list with a notice: the app is off here, or the person may not look. */
const blocked = computed(() => (error.value?.code === 'app_inactive' || error.value?.code === 'permission_denied' ? error.value.code : null));
/** What the server refused (a 422 of the list) and the amounts it cannot read, under each filter: the rows stay. */
const filterErrors = computed<Record<string, string>>(() => ({
  ...(error.value?.fields ?? {}),
  ...Object.fromEntries(unreadableAmounts(filters.value).map((name) => [name, t('cash_register.filters.amountInvalid')])),
}));
const tableError = computed(() =>
  status.value === 'error' && !Object.keys(error.value?.fields ?? {}).length ? (error.value?.message ?? t('cash_register.sessions.loadError')) : undefined,
);

// ── The open session ─────────────────────────────────────────────────────────────────────────────
const openSession = computed(() => current.data.value?.session ?? null);
/** One session open at a time; a forgotten one past its cut-off closes when the next one opens. */
const openBlocked = computed(() => !!openSession.value && !openSession.value.auto_close_due);
const dueAt = computed(() => {
  const at = current.data.value?.auto_close_at;
  return at ? new Intl.DateTimeFormat(locale.value, { timeStyle: 'short' }).format(new Date(at)) : '';
});
const unassignedCount = computed(() => current.data.value?.unassigned_count ?? 0);
const unassignedCash = computed(() => current.data.value?.unassigned_cash ?? 0);

// ── Columns ──────────────────────────────────────────────────────────────────────────────────────
const money = (cents: number | null): string => formatMoney(cents, locale.value);
/** An amount column's filter: from–to, typed in euros (`AMOUNT_RANGES`). */
const amountFilter = (range: keyof typeof AMOUNT_RANGES) => ({ type: 'range' as const, amount: true, keys: AMOUNT_RANGES[range] });

const columns = computed<DataTableColumn<SessionRow>[]>(() => [
  {
    key: 'number',
    label: t('cash_register.sessions.columns.number'),
    sortable: true,
    priority: 'high',
    width: 'minmax(7rem,1fr)',
    filter: { type: 'text', maxlength: 24 },
  },
  { key: 'opened_at', label: t('cash_register.sessions.columns.openedAt'), sortable: true, format: (_, row) => formatDateTime(row.opened_at, locale.value) },
  {
    key: 'status',
    label: t('cash_register.sessions.columns.status'),
    sortable: true,
    format: (_, row) => t(`cash_register.status.${row.status}`),
    filter: { type: 'select', options: SESSION_STATUSES.map((value) => ({ value, label: t(`cash_register.status.${value}`) })) },
  },
  {
    key: 'opening_balance',
    label: t('cash_register.sessions.columns.opening'),
    sortable: true,
    align: 'right',
    format: (_, row) => money(row.opening_balance),
    filter: amountFilter('opening'),
  },
  {
    key: 'expected_balance',
    label: t('cash_register.sessions.columns.expected'),
    sortable: true,
    align: 'right',
    format: (_, row) => money(row.expected_balance),
    filter: amountFilter('expected'),
  },
  {
    key: 'closing_balance',
    label: t('cash_register.sessions.columns.counted'),
    sortable: true,
    align: 'right',
    format: (_, row) => money(row.closing_balance),
    filter: amountFilter('counted'),
  },
  {
    key: 'difference',
    label: t('cash_register.sessions.columns.difference'),
    sortable: true,
    align: 'right',
    format: (_, row) => formatSignedMoney(row.difference, locale.value),
    filter: amountFilter('difference'),
  },
]);

// ── Row actions ──────────────────────────────────────────────────────────────────────────────────
const closed = (row: SessionRow): boolean => row.status !== 'open';
/** Closed, or open past its daily cut-off (the server takes nothing more on it): only «Detail». */
const finished = (row: SessionRow): boolean => closed(row) || row.auto_close_due;

const actions = computed<DataTableAction<SessionRow>[]>(() => [
  { id: 'detail', label: t('cash_register.sessions.actions.detail'), icon: 'list-outline' },
  ...(canMove.value ? [{ id: 'movement', label: t('cash_register.sessions.actions.movement'), icon: 'swap-vertical-outline', hidden: finished }] : []),
  ...(canCount.value ? [{ id: 'count', label: t('cash_register.sessions.actions.count'), icon: 'keypad-outline', hidden: finished }] : []),
  ...(canClose.value
    ? [{ id: 'close', label: t('cash_register.sessions.actions.close'), icon: 'lock-closed-outline', color: 'danger', hidden: finished }]
    : []),
]);

const opening = shallowRef(false);
const listing = shallowRef(false);
const moving = shallowRef(false);
const counting = shallowRef(false);
const closing = shallowRef(false);
const target = shallowRef<SessionRow | null>(null);

function openDetail(row: SessionRow): void {
  void router.push(`/cash_register/sessions/${row.id}`);
}

function onAction({ actionId, row }: { actionId: string; row: SessionRow }): void {
  if (actionId === 'detail') return openDetail(row);
  if (finished(row)) return;
  target.value = row;
  if (actionId === 'movement' && canMove.value) moving.value = true;
  else if (actionId === 'count' && canCount.value) counting.value = true;
  else if (actionId === 'close' && canClose.value) closing.value = true;
}

/** A closing count leads to the close, with its count (Square, Toast, Lightspeed): it closes nothing itself. */
function onCounted(count: { type: CountType; total: number }): void {
  if (count.type === 'closing' && canClose.value) closing.value = true;
}
</script>

<template>
  <AppPage
    :title="$t('cash_register.title')"
    content-layout="fill"
    :tabs="cashRegisterTabs($t)"
    :tabs-label="$t('cash_register.tabs.label')"
  >
    <header class="cash-sessions__header">
      <h2 data-testid="cash-register-sessions-title">
        {{ $t('cash_register.sessions.title') }}
      </h2>
      <ion-button
        v-if="canOpen"
        data-testid="cash-register-new-session"
        :disabled="openBlocked"
        :title="openBlocked ? $t('cash_register.sessions.alreadyOpen') : undefined"
        @click="opening = true"
      >
        {{ $t('cash_register.sessions.open') }}
      </ion-button>
    </header>

    <CashFigures v-if="!blocked" />

    <InlineFeedback
      v-if="status === 'reconnecting'"
      class="cash-sessions__notice"
      tone="warning"
      data-testid="cash-register-sessions-reconnecting"
    >
      {{ $t('cash_register.live.reconnecting') }}
    </InlineFeedback>
    <InlineFeedback
      v-if="openSession?.auto_close_due"
      class="cash-sessions__notice"
      tone="warning"
      icon="time-outline"
      data-testid="cash-register-auto-close-due"
      :heading="$t('cash_register.sessions.autoCloseDue.heading', { number: openSession.number, time: dueAt })"
    >
      {{ $t('cash_register.sessions.autoCloseDue.body') }}
    </InlineFeedback>
    <InlineFeedback
      v-if="unassignedCount > 0"
      class="cash-sessions__notice"
      tone="warning"
      icon="cash-outline"
      data-testid="cash-register-unassigned"
      :heading="$t('cash_register.sessions.unassigned.heading')"
    >
      {{ $t('cash_register.sessions.unassigned.body', { count: unassignedCount, cash: formatMoney(unassignedCash, locale) }, unassignedCount) }}
      <template #actions>
        <ion-button
          size="small"
          fill="outline"
          data-testid="cash-register-unassigned-view"
          @click="listing = true"
        >
          {{ $t('cash_register.sessions.unassigned.view') }}
        </ion-button>
      </template>
    </InlineFeedback>

    <InlineFeedback
      v-if="blocked"
      tone="warning"
      :data-testid="blocked === 'app_inactive' ? 'cash-register-sessions-inactive' : 'cash-register-sessions-forbidden'"
      :heading="blocked === 'app_inactive' ? $t('cash_register.live.appInactive') : $t('cash_register.live.noPermission')"
    >
      {{ error?.message }}
    </InlineFeedback>
    <DataTable
      v-else
      v-model:search="table.search.value"
      v-model:filters="filters"
      testid="cash-register-sessions"
      fill
      server-side
      searchable
      filterable
      :filter-errors="filterErrors"
      row-clickable
      :rows="result?.rows ?? []"
      :total="result?.total ?? 0"
      :page="table.page.value"
      :page-size="table.pageSize.value"
      :page-size-chooser="false"
      :sort="table.sort.value"
      :sort-dir="table.dir.value"
      :views="['table', 'cards']"
      :card-title="(row: SessionRow) => row.number"
      card-title-column="number"
      :card-icon="() => 'cash-outline'"
      :entity-label="{ one: $t('cash_register.sessions.entity.one'), many: $t('cash_register.sessions.entity.many') }"
      :loading="status === 'loading'"
      :error="tableError"
      :actions="actions"
      :max-inline-actions="4"
      :search-placeholder="$t('cash_register.sessions.search')"
      :labels="{ loading: $t('cash_register.sessions.loading'), loadError: $t('cash_register.sessions.loadError'), retry: $t('cash_register.live.retry') }"
      :columns="columns"
      @page-change="table.goToPage"
      @load-more="table.loadMore"
      @sort-change="table.setSort"
      @row-click="openDetail"
      @action="onAction"
      @retry="refresh()"
    >
      <template #empty>
        <EmptyState
          data-testid="cash-register-sessions-empty"
          icon="cash-outline"
          :heading="table.filtered.value ? $t('cash_register.sessions.noMatches') : $t('cash_register.sessions.empty')"
        />
      </template>
    </DataTable>

    <OpenSessionModal
      v-if="canOpen"
      v-model:open="opening"
      :unassigned-cash="unassignedCash"
    />
    <MovementModal
      v-if="canMove"
      v-model:open="moving"
      :session="target"
    />
    <CountModal
      v-if="canCount"
      v-model:open="counting"
      :session="target"
      @counted="onCounted"
    />
    <CloseSessionModal
      v-if="canClose"
      v-model:open="closing"
      :session="target"
    />
    <UnassignedModal v-model:open="listing" />
  </AppPage>
</template>

<style scoped>
.cash-sessions__header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.75rem;
}
.cash-sessions__header h2 {
  flex: 1;
  margin: 0;
  font-size: 1.15rem;
}
/* A finger needs 44 × 44 (WCAG 2.5.5). */
.cash-sessions__header ion-button {
  min-height: 44px;
  margin: 0;
}
.cash-sessions__notice {
  margin-bottom: 0.75rem;
}
</style>
