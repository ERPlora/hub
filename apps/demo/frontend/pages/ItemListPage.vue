<script setup lang="ts">
// Demo items (DEMO-F01, F05, F06): the live list of `demo.item.list` in a server-side DataTable —
// search, status filter (behind the table's funnel), page and page size are the server's — with
// every state of the screen, the «Updated» column (shared formatter) and, for whoever can manage,
// the live figures above it.
// Nothing here refetches: a write anywhere in this business re-runs the queries on the server and
// the new results arrive through the stream. On a phone «Load more» grows ONE live window from the
// first row (a bigger `limit`, `offset` 0), so every row on screen stays live; a desk pages one
// page at a time.
import { DataTable, EmptyState, formatDateTime, InlineFeedback } from '@erplora/ui/components';
import { type InputOf, type OutputOf, useLive } from '@erplora/ui/sdk';
import { AppPage, useSession } from '@erplora/ui/shell';
import { IonBadge } from '@ionic/vue';
import { computed, ref, watch } from 'vue';
import { useRouter } from 'vue-router';

import ItemStats from '../components/ItemStats.vue';

type Row = OutputOf<'demo.item.list'>['rows'][number];
/** «All» is no `status` at all. */
type StatusFilter = NonNullable<InputOf<'demo.item.list'>['status']> | 'all';

const PAGE_SIZES = [10, 25, 50, 100];

const router = useRouter();
const session = useSession();
const canManage = computed(() => session.can('demo.manage'));

const search = ref('');
const statusFilter = ref<StatusFilter>('all');
/** 0-based, as the table counts. */
const page = ref(0);
const pageSize = ref(50);
/** Pages the live window holds from `page` on: 1 on a desk; each «Load more» on a phone adds one. */
const windowPages = ref(1);

/** Shows `n` alone (the desk pager, a new search or page size, a crossed breakpoint). */
function goToPage(n: number): void {
  page.value = n;
  windowPages.value = 1;
}
/** `v-model:search` of the table: a new search starts from the first page. */
const query = computed({
  get: () => search.value,
  set: (value: string) => {
    search.value = value;
    goToPage(0);
  },
});
/** The status filter lives behind the table's funnel (`filterable`, the `status` column's filter). */
const tableFilters = computed((): Record<string, string> => (statusFilter.value === 'all' ? {} : { status: statusFilter.value }));
/** A new filter starts from the first page, as a search does; a status the query does not know is «All». */
function onFilters(filters: Record<string, string>): void {
  statusFilter.value = filters.status === 'open' || filters.status === 'done' ? filters.status : 'all';
  goToPage(0);
}
const filtered = computed(() => search.value.trim() !== '' || statusFilter.value !== 'all');

const {
  data: result,
  status,
  error,
  refresh,
} = useLive('demo.item.list', () => ({
  search: search.value.trim() || undefined,
  status: statusFilter.value === 'all' ? undefined : statusFilter.value,
  limit: pageSize.value * windowPages.value,
  offset: page.value * pageSize.value,
}));

const inactive = computed(() => error.value?.code === 'app_inactive');

// A page emptied by deletions elsewhere steps back to the last page that still has rows.
watch(result, (now) => {
  if (now && now.rows.length === 0 && now.total > 0 && now.offset >= now.total) {
    goToPage(Math.ceil(now.total / pageSize.value) - 1);
  }
});

function setPageSize(size: number): void {
  pageSize.value = size;
  goToPage(0);
}

const open = (row: Row) => router.push(`/demo/items/${row.id}`);
</script>

<template>
  <AppPage
    :title="$t('demo.items.title')"
    content-layout="fill"
  >
    <InlineFeedback
      v-if="status === 'reconnecting'"
      tone="warning"
      data-testid="demo-items-reconnecting"
    >
      {{ $t('demo.live.reconnecting') }}
    </InlineFeedback>

    <InlineFeedback
      v-if="inactive"
      tone="warning"
      data-testid="demo-items-inactive"
      :heading="$t('demo.live.appInactive')"
    >
      {{ error?.message }}
    </InlineFeedback>
    <template v-else>
      <ItemStats v-if="canManage" />
      <DataTable
        v-model:search="query"
        testid="demo-items"
        server-side
        searchable
        fill
        filterable
        :filters="tableFilters"
        row-clickable
        :rows="result?.rows ?? []"
        :total="result?.total ?? 0"
        :page="page"
        :page-size="pageSize"
        :page-size-options="PAGE_SIZES"
        :views="['table', 'cards']"
        :loading="status === 'loading'"
        :error="status === 'error' ? error?.message : undefined"
        :addable="canManage"
        :search-placeholder="$t('demo.items.search')"
        :labels="{ add: $t('demo.items.new'), loadError: $t('demo.items.loadError'), retry: $t('demo.live.retry') }"
        :columns="[
          { key: 'name', label: $t('demo.items.columns.name'), cell: 'name' },
          {
            key: 'status',
            label: $t('demo.items.columns.status'),
            cell: 'status',
            filter: {
              type: 'select',
              options: [
                { value: 'open', label: $t('demo.status.open') },
                { value: 'done', label: $t('demo.status.done') },
              ],
            },
          },
          { key: 'line_count', label: $t('demo.items.columns.lines'), cell: 'lines' },
          { key: 'updated_at', label: $t('demo.items.columns.updated'), cell: 'updated' },
        ]"
        @page-change="goToPage"
        @load-more="windowPages += 1"
        @page-size-change="setPageSize"
        @row-click="open"
        @add="router.push('/demo/items/new')"
        @retry="refresh()"
        @filters-change="onFilters"
      >
        <template #name="{ row }">
          <span
            data-testid="demo-item-name"
            :title="row.name"
          >{{ row.name }}</span>
        </template>
        <template #status="{ row }">
          <ion-badge
            data-testid="demo-item-status"
            :color="row.status === 'done' ? 'success' : 'primary'"
          >
            {{ row.status === 'done' ? $t('demo.status.done') : $t('demo.status.open') }}
          </ion-badge>
        </template>
        <template #lines="{ row }">
          <span data-testid="demo-item-lines">{{ $t('demo.items.lineCount', row.line_count) }}</span>
        </template>
        <template #updated="{ row }">
          <span data-testid="demo-item-updated">{{ formatDateTime(row.updated_at, $i18n.locale) }}</span>
        </template>
        <template #empty>
          <EmptyState
            data-testid="demo-items-empty"
            icon="cube-outline"
            :heading="filtered ? $t('demo.items.noResultsHeading') : $t('demo.items.emptyHeading')"
            :message="
              filtered ? $t('demo.items.noResultsMessage') : canManage ? $t('demo.items.emptyMessage') : undefined
            "
          />
        </template>
      </DataTable>
    </template>
  </AppPage>
</template>
