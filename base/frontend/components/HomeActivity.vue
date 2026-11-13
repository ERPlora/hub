<script setup lang="ts">
// The Home's «Activity»: the last sales, read through Sales' own operation only while Sales is on in this hub. base
// does not require Sales, so without it the table is simply empty. A status this screen does not know reads «Other».
import { DataTable, formatDateTime, InlineFeedback, StatusPill } from '@erplora/ui/components';
import { useLive } from '@erplora/ui/sdk';
import { useSession } from '@erplora/ui/shell';
import { IonButton } from '@ionic/vue';
import { computed } from 'vue';

import { formatValue, saleStatus } from '../lib/home';
import { useBaseI18n } from '../lib/i18n';
import { useBusinessMoney } from '../lib/money';

/**
 * The fields «Activity» reads of a row of `sale.sale.list`. base is the platform and requires no module, so it keeps
 * its own type of the row instead of importing Sales' (`platform-boundary.test.ts`).
 */
interface ActivitySale {
  created_at: string;
  number: string;
  customer_name: string;
  payment_method_name: string;
  total: number;
  status: string;
}

const LIMIT = 100;
/** Rows per page: 15 first, and the chooser offers it too, so it never shows blank. */
const PAGE_SIZES = [15, 25, 50, 100];
/** The statuses the filter offers: the sales history's own. */
const SALE_STATUSES = ['completed', 'voided', 'refunded'] as const;

const { t, locale } = useBaseI18n();
const session = useSession();
const money = useBusinessMoney();
const salesOn = (session.me.value?.apps ?? []).some((app) => app.label === 'sale' && app.state === 'on');
const sales = salesOn
  ? useLive('sale.sale.list', { limit: LIMIT, offset: 0, sort: 'created_at', dir: 'desc' })
  : undefined;

const rows = computed<ActivitySale[]>(() => sales?.data.value?.rows ?? []);
/** The methods of the sales on screen, once each and sorted: what the method filter offers. */
const methods = computed(() => [...new Set(rows.value.map((row) => row.payment_method_name).filter(Boolean))].sort());
const loading = computed(() => !!sales && sales.data.value === undefined && sales.status.value !== 'error');
const failed = computed(() => sales?.status.value === 'error');

const columns = computed(() => [
  {
    key: 'created_at',
    label: t('base.activity.columns.date'),
    format: (value: unknown) => formatDateTime(value as string, locale.value),
    // The widest date and time the format prints («May 30, 2028, 10:44 AM», 158 px) whole, with room to spare.
    width: 'minmax(10.5rem, 1fr)',
  },
  { key: 'number', label: t('base.activity.columns.sale') },
  { key: 'customer_name', label: t('base.activity.columns.customer') },
  {
    key: 'payment_method_name',
    label: t('base.activity.columns.method'),
    filter: { type: 'select' as const, options: methods.value.map((name) => ({ value: name, label: name })) },
  },
  {
    key: 'total',
    label: t('base.activity.columns.amount'),
    align: 'right' as const,
    format: (value: unknown) => formatValue(value, 'currency', locale.value, money.value),
  },
  {
    key: 'status',
    label: t('base.activity.columns.status'),
    cell: 'status',
    filter: {
      type: 'select' as const,
      options: SALE_STATUSES.map((status) => ({ value: status, label: t(`base.activity.status.${status}`) })),
    },
  },
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
      filterable
      column-picker
      :search-keys="['number', 'customer_name', 'payment_method_name']"
      :search-placeholder="$t('base.activity.search')"
      :page-size="PAGE_SIZES[0]"
      :page-size-options="PAGE_SIZES"
      :views="['table', 'cards']"
      :rows="rows"
      :columns="columns"
      :loading="loading"
      :labels="{ loading: $t('base.activity.loading') }"
    >
      <template #status="{ row }">
        <StatusPill
          data-testid="home-activity-status"
          :tone="saleStatus((row as ActivitySale).status).tone"
          :label="$t(`base.activity.status.${saleStatus((row as ActivitySale).status).key}`)"
        />
      </template>
    </DataTable>
  </div>
</template>
