<script setup lang="ts">
// «Activity» on the Home (BASE-G129): the last 100 sales of Sales, newest first, read by its own operation
// (`sale.sale.list`, live: a sale anywhere in the business brings the new list) only while Sales is on in this
// hub — base does not require Sales, so without it the table is simply empty. Searched, sorted and paged in the
// browser (15 a page). The status speaks the sales history's words; one this screen does not know is «Other».
import { DataTable, formatDateTime, InlineFeedback, StatusPill } from '@erplora/ui/components';
import { useLive } from '@erplora/ui/sdk';
import { useSession } from '@erplora/ui/shell';
import { IonButton } from '@ionic/vue';
import { computed } from 'vue';

import type { SaleRow } from '../../../apps/sale/frontend/operations';
import { formatValue, saleStatus } from '../lib/home';
import { useBaseI18n } from '../lib/i18n';

const LIMIT = 100;

const { t, locale } = useBaseI18n();
const session = useSession();
const salesOn = (session.me.value?.apps ?? []).some((app) => app.label === 'sale' && app.state === 'on');
const sales = salesOn
  ? useLive('sale.sale.list', { limit: LIMIT, offset: 0, sort: 'created_at', dir: 'desc' })
  : undefined;

const rows = computed<SaleRow[]>(() => sales?.data.value?.rows ?? []);
const loading = computed(() => !!sales && sales.data.value === undefined && sales.status.value !== 'error');
const failed = computed(() => sales?.status.value === 'error');

const columns = computed(() => [
  {
    key: 'created_at',
    label: t('base.activity.columns.date'),
    format: (value: unknown) => formatDateTime(value as string, locale.value),
    width: 'minmax(9.5rem, 1fr)',
  },
  { key: 'number', label: t('base.activity.columns.sale') },
  { key: 'customer_name', label: t('base.activity.columns.customer') },
  { key: 'payment_method_name', label: t('base.activity.columns.method') },
  {
    key: 'total',
    label: t('base.activity.columns.amount'),
    align: 'right' as const,
    format: (value: unknown) => formatValue(value, 'currency', locale.value),
  },
  { key: 'status', label: t('base.activity.columns.status'), cell: 'status' },
]);
</script>

<template>
  <div class="page-fill home-activity">
    <InlineFeedback
      v-if="failed"
      tone="warning"
      data-testid="home-activity-error"
      :heading="$t('base.activity.loadError')"
    >
      {{ $t('base.activity.loadErrorBody') }}
      <template #actions>
        <ion-button
          size="small"
          fill="outline"
          data-testid="home-activity-retry"
          @click="sales?.refresh()"
        >
          {{ $t('base.activity.retry') }}
        </ion-button>
      </template>
    </InlineFeedback>
    <DataTable
      v-if="!failed || rows.length > 0"
      testid="home-activity"
      fill
      searchable
      column-picker
      :search-keys="['number', 'customer_name', 'payment_method_name']"
      :search-placeholder="$t('base.activity.search')"
      :page-size="15"
      :views="['table', 'cards']"
      :rows="rows"
      :columns="columns"
      :loading="loading"
      :labels="{ loading: $t('base.activity.loading') }"
    >
      <template #status="{ row }">
        <StatusPill
          data-testid="home-activity-status"
          :tone="saleStatus((row as SaleRow).status).tone"
          :label="$t(`base.activity.status.${saleStatus((row as SaleRow).status).key}`)"
        />
      </template>
    </DataTable>
  </div>
</template>
