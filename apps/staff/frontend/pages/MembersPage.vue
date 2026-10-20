<script setup lang="ts">
// Staff → Staff (WORKBOOK «Pantallas · Personal»; STAFF-F01–F06, F08, F21): the live
// `staff.member.list` in a server-side DataTable — Name, Role, Email, Status and, for whoever may see
// the pay, Rate/h (`staff.member.compensation`, the same rows page by page); Phone starts hidden —, «Search
// member…», sort by any column, the old column filters behind the table's funnel, 50 a page. «+» opens «New»; a row or «Edit»
// opens «Edit · {name}»; «Deactivate» (confirmed) and «Terminate» (its dialog) for the owner and the
// admin. «My record» opens one's own record. Above the list, the figures of the old Home panels
// (STAFF-G02–G04). Nothing here refetches: changes come through the stream.
import {
  ConfirmDialog,
  type DataTableAction,
  type DataTableColumn,
  type DataTableFilterField,
  type DataTableFilters,
  DataTable,
  EmptyState,
  InlineFeedback,
  StatusPill,
} from '@erplora/ui/components';
import { useCommand, useLive, useLiveClient } from '@erplora/ui/sdk';
import { AppPage, HubIcon, useSession } from '@erplora/ui/shell';
import { IonButton } from '@ionic/vue';
import { computed, ref, shallowRef, watch } from 'vue';

import MemberFormModal from '../components/MemberFormModal.vue';
import MyRecordModal from '../components/MyRecordModal.vue';
import PageNotices, { blockingError } from '../components/PageNotices.vue';
import StaffFigures from '../components/StaffFigures.vue';
import TerminateDialog from '../components/TerminateDialog.vue';
import { useLiveList } from '../composables/useLiveList';
import { useServerTable } from '../composables/useServerTable';
import { useLocale, useT } from '../composables/useT';
import { MEMBER_STATUSES, memberStatusTone } from '../lib/enums';
import { formatMoney } from '../lib/format';
import { accountSearch, roleSearch } from '../lib/pickers';
import type { MemberListIn, MemberOut } from '../operations';
import { staffTabs } from '../tabs';

const session = useSession();
const t = useT();
const locale = useLocale();
const client = useLiveClient();

const canAdd = computed(() => session.can('staff.add_member'));
const canChange = computed(() => session.can('staff.change_member'));
const canDelete = computed(() => session.can('staff.delete_member'));
const canPay = session.can('staff.view_compensation');
const canLink = computed(() => canAdd.value || canChange.value);
const canSettings = computed(() => session.can('staff.manage_settings'));

// ── The list ───────────────────────────────────────────────────────────────────────────────────
const table = useServerTable({ sort: 'name' });
/** The table's filters (its funnel): a filter not in use is absent. */
const filters = ref<DataTableFilters>({});
watch(filters, (now) => table.restart({ narrowed: Object.keys(now).length > 0 }));

/** The filters as the query takes them: Bookable is a yes/no and the Hub user a number. */
function filterParams(values: DataTableFilters): Partial<MemberListIn> {
  const { is_bookable: bookable, user_id: user, ...rest } = values;
  return {
    ...rest,
    ...(bookable ? { is_bookable: bookable === 'true' } : {}),
    ...(user ? { user_id: Number(user) } : {}),
  } as Partial<MemberListIn>;
}

const {
  data: result,
  status,
  error,
  refresh,
} = useLiveList(
  'staff.member.list',
  () => ({ ...filterParams(filters.value), ...table.query.value }),
  () => table.windows.value,
);
table.followResult(result);
const blocked = computed(() => blockingError(error.value));

/** The pay of exactly the rows on screen (the Rate/h column): the same query, sort and windows as the
 *  directory, so it follows the list page by page; only for whoever may see it. */
const pay = canPay
  ? useLiveList('staff.member.compensation', () => ({ ...filterParams(filters.value), ...table.query.value }), () => table.windows.value).data
  : shallowRef(undefined);
const rates = computed(() => new Map((pay.value?.rows ?? []).map((row) => [row.id, row.hourly_rate])));
/** One's own record, for «My record» (STAFF-F08). */
const { data: mine } = useLive('staff.member.mine', {});

/** Role (every one, by name) and Hub user filters search the server: there may be more than 100. */
const findRoles = roleSearch(client, { activeOnly: false, by: 'name' });
const findAccounts = accountSearch(client);

/** The filters with no column of their own, after the columns' (the old table's order otherwise). */
const filterFields = computed<DataTableFilterField[]>(() => [
  { type: 'text', key: 'first_name', label: t('staff.members.filters.firstName') },
  { type: 'text', key: 'last_name', label: t('staff.members.filters.lastName') },
  { type: 'boolean', key: 'is_bookable', label: t('staff.members.filters.bookable') },
  { type: 'daterange', key: 'hire_date', label: t('staff.members.filters.hireDate'), keys: ['hire_date_from', 'hire_date_to'] },
  { type: 'text', key: 'color', label: t('staff.members.filters.color') },
  ...(canLink.value ? [{ type: 'lookup' as const, key: 'user_id', label: t('staff.members.filters.user'), load: findAccounts }] : []),
]);

const dash = (value: unknown): string => (value === null || value === undefined || value === '' ? '—' : String(value));

const columns = computed<DataTableColumn<MemberOut>[]>(() => [
  { key: 'name', label: t('staff.members.columns.name'), sortable: true, priority: 'high', format: (_, row) => row.full_name },
  { key: 'role_name', label: t('staff.members.columns.role'), sortable: true, format: dash, filter: { type: 'lookup', load: findRoles } },
  { key: 'email', label: t('staff.members.columns.email'), sortable: true, priority: 'low', format: dash, filter: { type: 'text' } },
  { key: 'phone', label: t('staff.members.columns.phone'), sortable: true, hidden: true, format: dash, filter: { type: 'text' } },
  {
    key: 'status',
    label: t('staff.members.columns.status'),
    sortable: true,
    cell: 'status',
    format: (_, row) => t(`staff.memberStatus.${row.status}`),
    filter: { type: 'select', options: MEMBER_STATUSES.map((value) => ({ value, label: t(`staff.memberStatus.${value}`) })) },
  },
  ...(canPay
    ? [
        {
          key: 'hourly_rate',
          label: t('staff.members.columns.hourlyRate'),
          align: 'right' as const,
          format: (_: unknown, row: MemberOut) => {
            const cents = rates.value.get(row.id);
            return cents === undefined ? '—' : formatMoney(cents, locale.value);
          },
        },
      ]
    : []),
]);

// ── Row actions ────────────────────────────────────────────────────────────────────────────────
/** What a row action was refused: above the table (a form's refusal stays in its dialog). */
const pageError = ref('');

const actions = computed<DataTableAction<MemberOut>[]>(() => [
  ...(canChange.value ? [{ id: 'edit', label: t('staff.members.actions.edit'), icon: 'create-outline' }] : []),
  ...(canDelete.value
    ? [
        {
          id: 'deactivate',
          label: t('staff.members.actions.deactivate'),
          icon: 'ban-outline',
          disabled: (row: MemberOut) => row.status !== 'active' && row.status !== 'on_leave',
        },
        { id: 'terminate', label: t('staff.members.actions.terminate'), icon: 'person-remove-outline', color: 'danger' },
      ]
    : []),
]);

const editing = ref<MemberOut | null>(null);
const formOpen = ref(false);
const terminating = ref<MemberOut | null>(null);
const terminateOpen = ref(false);
const deactivating = ref<MemberOut | null>(null);
const deactivateOpen = ref(false);
const deactivation = useCommand('staff.member.deactivate');
const recordOpen = ref(false);

function openForm(member: MemberOut | null): void {
  pageError.value = '';
  editing.value = member;
  formOpen.value = true;
}

function onAction({ actionId, row }: { actionId: string; row: MemberOut }): void {
  pageError.value = '';
  if (actionId === 'edit' && canChange.value) openForm(row);
  else if (actionId === 'deactivate' && canDelete.value) {
    deactivating.value = row;
    deactivateOpen.value = true;
  } else if (actionId === 'terminate' && canDelete.value) {
    terminating.value = row;
    terminateOpen.value = true;
  }
}

function onRowClick(row: MemberOut): void {
  if (canChange.value) openForm(row);
}

async function deactivate(): Promise<void> {
  const row = deactivating.value;
  if (!row) return;
  try {
    await deactivation.run({ id: row.id });
  } catch (failure) {
    pageError.value = failure instanceof Error ? failure.message : String(failure);
  } finally {
    deactivateOpen.value = false;
  }
}
</script>

<template>
  <AppPage
    :title="$t('staff.title')"
    content-layout="fill"
    :tabs="staffTabs($t, { settings: canSettings })"
    :tabs-label="$t('staff.tabs.label')"
  >
    <PageNotices
      testid="staff-members"
      :status="status"
      :error="error"
    />
    <InlineFeedback
      v-if="pageError"
      tone="danger"
      data-testid="staff-members-error"
    >
      {{ pageError }}
    </InlineFeedback>
    <StaffFigures v-if="!blocked" />
    <DataTable
      v-if="!blocked"
      v-model:search="table.search.value"
      v-model:filters="filters"
      testid="staff-members"
      fill
      server-side
      searchable
      filterable
      :filter-fields="filterFields"
      :rows="result?.rows ?? []"
      :total="result?.total ?? 0"
      :page="table.page.value"
      :page-size="table.pageSize.value"
      :sort="table.sort.value"
      :sort-dir="table.dir.value"
      :views="['table', 'cards']"
      :card-title="(row: MemberOut) => row.full_name"
      :card-icon="() => 'person-outline'"
      :entity-label="{ one: $t('staff.members.entity.one'), many: $t('staff.members.entity.many') }"
      :loading="status === 'loading'"
      :error="status === 'error' && !blocked ? error?.message : undefined"
      :addable="canAdd"
      :row-clickable="canChange"
      :actions="actions"
      :search-placeholder="$t('staff.members.search')"
      :labels="{ add: $t('staff.add'), loadError: $t('staff.members.loadError'), retry: $t('staff.live.retry') }"
      :columns="columns"
      @page-change="table.goToPage"
      @load-more="table.loadMore"
      @page-size-change="table.setPageSize"
      @sort-change="table.setSort"
      @action="onAction"
      @row-click="onRowClick"
      @add="openForm(null)"
      @retry="refresh()"
    >
      <template #toolbar>
        <ion-button
          v-if="mine?.member"
          class="staff-members__mine"
          fill="outline"
          color="medium"
          data-testid="staff-members-mine"
          @click="recordOpen = true"
        >
          <HubIcon
            slot="start"
            name="ion:person-circle-outline"
          />
          {{ $t('staff.members.mine.button') }}
        </ion-button>
      </template>
      <template #status="{ row }">
        <StatusPill
          size="sm"
          :tone="memberStatusTone(row.status)"
          :label="$t(`staff.memberStatus.${row.status}`)"
        />
      </template>
      <template #empty>
        <EmptyState
          data-testid="staff-members-empty"
          icon="people-outline"
          :heading="table.filtered.value ? $t('staff.noResults') : $t('staff.members.empty')"
          :message="table.filtered.value ? $t('staff.noResultsMessage') : undefined"
        />
      </template>
    </DataTable>
    <MemberFormModal
      v-if="canAdd || canChange"
      v-model:open="formOpen"
      :member="editing"
    />
    <template v-if="canDelete">
      <TerminateDialog
        v-model:open="terminateOpen"
        :member="terminating"
      />
      <ConfirmDialog
        v-model:open="deactivateOpen"
        testid="staff-member-deactivate"
        tone="warning"
        confirm-icon="ion:ban-outline"
        :title="$t('staff.members.deactivate.title')"
        :message="$t('staff.members.deactivate.message', { name: deactivating?.full_name ?? '' })"
        :confirm-label="$t('staff.members.deactivate.confirm')"
        :pending="deactivation.pending.value"
        @confirm="deactivate"
      />
    </template>
    <MyRecordModal
      v-model:open="recordOpen"
      :record="mine?.member ?? null"
    />
  </AppPage>
</template>

<style scoped>
/* Boxed like the table's own toolbar buttons (38 px, radius 10). */
.staff-members__mine {
  min-height: 38px;
  margin: 0;
  --border-radius: 10px;
  --padding-start: 0.7rem;
  --padding-end: 0.7rem;
  font-size: 13px;
  text-transform: none;
}
</style>
