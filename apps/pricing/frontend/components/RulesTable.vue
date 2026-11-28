<script setup lang="ts">
// Price Lists → «Discount rules» (WORKBOOK «Pantallas · Tarifas»; PRICING-F09 to F12): the live
// `pricing.rule.list` in a server-side DataTable — Code, Name, Type, Value (one column with its unit,
// neither sorted nor filtered, its units differ), Applies to (with the customer
// group), Validity, Priority and Status —, «Search code or name…», column filters behind the funnel (Status
// opens on the active ones), list or cards, 50 a page by name. Whoever manages gets «+» (New discount rule), Edit,
// Deactivate (asking first), Activate and Delete (asking first). An amount per unit is in the business's currency
// (its country's).
import {
  ConfirmDialog,
  DataTable,
  type DataTableAction,
  type DataTableColumn,
  type DataTableFilters,
  EmptyState,
  InlineFeedback,
  StatusPill,
} from '@erplora/ui/components';
import { type ApiError, useCommand } from '@erplora/ui/sdk';
import { useSession } from '@erplora/ui/shell';
import { computed, ref } from 'vue';

import { useLiveList } from '../composables/useLiveList';
import { useServerTable } from '../composables/useServerTable';
import { useLocale, useT } from '../composables/useT';
import { useBusinessMoney, validityLabel } from '../lib/format';
import { appliesToLabel, ruleValueLabel } from '../lib/rules';
import type { RuleListIn, RuleOut, RuleScope, RuleType, Status } from '../operations';
import PageNotices, { blockingError } from './PageNotices.vue';
import RuleFormModal from './RuleFormModal.vue';

const TYPES: readonly RuleType[] = ['percent', 'fixed', 'buy_x_get_y', 'tiered'];
const SCOPES: readonly RuleScope[] = ['all', 'products', 'services', 'category', 'product', 'service'];
// The active ones until the person picks another status; the table's own blank option («All») asks for
// every one, so there is no second «All» beside it that meant something else.
const STATUSES: readonly Status[] = ['active', 'inactive'];
const DEFAULT_STATUS = 'active';

const session = useSession();
const t = useT();
const locale = useLocale();
const money = useBusinessMoney();
const canManage = computed(() => session.can('pricing.manage'));

const table = useServerTable({ sort: 'name' });
const filters = ref<DataTableFilters>({ status: DEFAULT_STATUS });

const query = computed<Partial<RuleListIn>>(() => {
  const f = filters.value;
  return {
    ...(f.code ? { code: f.code } : {}),
    ...(f.name ? { name: f.name } : {}),
    ...(f.rule_type ? { rule_type: f.rule_type as RuleType } : {}),
    ...(f.applies_to ? { applies_to: f.applies_to as RuleScope } : {}),
    status: (f.status || 'all') as Status,
  };
});

function onFilters(now: DataTableFilters): void {
  filters.value = now;
  // The default status narrows nothing the person asked for: an empty answer is still «No discount rules.».
  table.restart({ narrowed: Object.entries(now).some(([key, value]) => value && !(key === 'status' && value === DEFAULT_STATUS)) });
}

const { data: result, status, error, refresh } = useLiveList(
  'pricing.rule.list',
  () => ({ ...query.value, ...table.query.value }) as RuleListIn,
  () => table.windows.value,
);
table.followResult(result);
const blocked = computed(() => blockingError(error.value));

const columns = computed<DataTableColumn<RuleOut>[]>(() => [
  { key: 'code', label: t('pricing.rules.columns.code'), sortable: true, filter: { type: 'text' } },
  { key: 'name', label: t('pricing.rules.columns.name'), sortable: true, priority: 'high', filter: { type: 'text' } },
  {
    key: 'rule_type',
    label: t('pricing.rules.columns.type'),
    sortable: true,
    format: (_, row) => t(`pricing.rules.type.${row.rule_type}`),
    filter: { type: 'select', options: TYPES.map((value) => ({ value, label: t(`pricing.rules.type.${value}`) })) },
  },
  { key: 'value', label: t('pricing.rules.columns.value'), align: 'right', format: (_, row) => ruleValueLabel(row, t, locale.value, money.value) },
  {
    key: 'applies_to',
    label: t('pricing.rules.columns.appliesTo'),
    format: (_, row) => appliesToLabel(row, t),
    filter: { type: 'select', options: SCOPES.map((value) => ({ value, label: t(`pricing.rules.scope.${value}`) })) },
  },
  {
    key: 'validity',
    label: t('pricing.rules.columns.validity'),
    priority: 'low',
    format: (_, row) => validityLabel(row.valid_from, row.valid_until, t, locale.value),
  },
  { key: 'priority', label: t('pricing.rules.columns.priority'), sortable: true, align: 'right', priority: 'low', format: (_, row) => String(row.priority) },
  {
    key: 'status',
    label: t('pricing.rules.columns.status'),
    cell: 'status',
    priority: 'low',
    format: (_, row) => t(row.is_active ? 'pricing.state.active' : 'pricing.state.inactive'),
    filter: { type: 'select', options: STATUSES.map((value) => ({ value, label: t(`pricing.status.${value}`) })) },
  },
]);

const actions = computed<DataTableAction<RuleOut>[]>(() =>
  canManage.value
    ? [
        { id: 'edit', label: t('pricing.rules.actions.edit'), icon: 'create-outline' },
        {
          id: 'deactivate',
          label: t('pricing.rules.actions.deactivate'),
          icon: 'ban-outline',
          color: 'danger',
          hidden: (row: RuleOut) => !row.is_active,
        },
        {
          id: 'activate',
          label: t('pricing.rules.actions.activate'),
          icon: 'arrow-undo-outline',
          color: 'success',
          hidden: (row: RuleOut) => row.is_active,
        },
        { id: 'delete', label: t('pricing.rules.actions.delete'), icon: 'trash-outline', color: 'danger', menuOnly: true },
      ]
    : [],
);

// The form, the confirmations and the row actions
type Confirmed = 'deactivate' | 'delete';
const CONFIRMS = [
  { id: 'deactivate', texts: 'deactivateConfirm' },
  { id: 'delete', texts: 'deleteConfirm' },
] as const;
const editing = ref<RuleOut | null>(null);
const formOpen = ref(false);
const confirming = ref<RuleOut | null>(null);
const confirmAction = ref<Confirmed | null>(null);
const commands = { deactivate: useCommand('pricing.rule.deactivate'), delete: useCommand('pricing.rule.delete') };
const activate = useCommand('pricing.rule.activate');
const rowError = ref<ApiError | null>(null);

function openForm(row: RuleOut | null): void {
  editing.value = row;
  formOpen.value = true;
}

function ask(action: Confirmed, row: RuleOut): void {
  commands[action].error.value = null;
  confirming.value = row;
  confirmAction.value = action;
}

async function confirm(): Promise<void> {
  const chosen = confirmAction.value;
  if (!confirming.value || !chosen) return;
  try {
    await commands[chosen].run({ id: confirming.value.id });
  } catch {
    return; // The dialog says why.
  }
  confirmAction.value = null;
}

async function onAction({ actionId, row }: { actionId: string; row: RuleOut }): Promise<void> {
  rowError.value = null;
  if (actionId === 'edit') openForm(row);
  if (actionId === 'deactivate' || actionId === 'delete') ask(actionId, row);
  if (actionId === 'activate') {
    try {
      await activate.run({ id: row.id });
    } catch {
      rowError.value = activate.error.value;
    }
  }
}
</script>

<template>
  <section class="pricing-section">
    <PageNotices
      testid="pricing-rules"
      :status="status"
      :error="error"
    />
    <InlineFeedback
      v-if="rowError"
      tone="danger"
      dismissible
      data-testid="pricing-rules-row-error"
      :heading="t('pricing.lists.rowError')"
      @dismiss="rowError = null"
    >
      {{ rowError.message }}
    </InlineFeedback>
    <DataTable
      v-if="!blocked"
      v-model:search="table.search.value"
      testid="pricing-rules"
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
      :card-title="(row: RuleOut) => row.name"
      :card-icon="() => 'pricetag-outline'"
      :entity-label="{ one: $t('pricing.rules.entity.one'), many: $t('pricing.rules.entity.many') }"
      :loading="status === 'loading'"
      :error="status === 'error' && !blocked ? $t('pricing.rules.loadError') : undefined"
      :addable="canManage"
      :row-clickable="canManage"
      :actions="actions"
      :search-placeholder="$t('pricing.rules.search')"
      :labels="{ add: $t('pricing.rules.new'), loadError: $t('pricing.rules.loadError'), retry: $t('pricing.live.retry') }"
      :columns="columns"
      @filters-change="onFilters"
      @page-change="table.goToPage"
      @load-more="table.loadMore"
      @page-size-change="table.setPageSize"
      @sort-change="table.setSort"
      @row-click="openForm"
      @add="openForm(null)"
      @action="onAction"
      @retry="refresh()"
    >
      <template #status="{ row }">
        <StatusPill
          size="sm"
          :tone="row.is_active ? 'success' : 'neutral'"
          :label="t(row.is_active ? 'pricing.state.active' : 'pricing.state.inactive')"
        />
      </template>
      <template #empty>
        <EmptyState
          data-testid="pricing-rules-empty"
          icon="pricetag-outline"
          :heading="table.filtered.value ? $t('pricing.noResults') : $t('pricing.rules.empty')"
          :message="table.filtered.value ? $t('pricing.noResultsMessage') : undefined"
        />
      </template>
    </DataTable>
    <RuleFormModal
      v-if="canManage"
      v-model:open="formOpen"
      :rule="editing"
    />
    <template v-if="canManage">
      <ConfirmDialog
        v-for="dialog in CONFIRMS"
        :key="dialog.id"
        :open="confirmAction === dialog.id"
        :testid="`pricing-rules-${dialog.id}`"
        tone="danger"
        :title="confirming ? t(`pricing.rules.${dialog.texts}.title`, { name: confirming.name }) : ''"
        :message="confirming ? t(`pricing.rules.${dialog.texts}.message`, { name: confirming.name }) : ''"
        :confirm-label="t(`pricing.rules.${dialog.texts}.confirm`)"
        :cancel-label="t('pricing.cancel')"
        :pending="commands[dialog.id].pending.value"
        :error="commands[dialog.id].error.value"
        @update:open="(open: boolean) => { if (!open) confirmAction = null }"
        @confirm="confirm"
        @cancel="confirmAction = null"
      />
    </template>
  </section>
</template>

<style scoped>
.pricing-section {
  display: grid;
  gap: 8px;
}
</style>
