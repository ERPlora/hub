<script setup lang="ts">
// Online orders → Table QR codes (ONLINE_ORDER-F01, F02): every table in the floor plan's order (the server's), live,
// read whole because the sheet prints them all, with its zone, the address its QR opens and when it was generated.
// «Print sheet» prints one card per table with a QR; «Print QR» prints a row's own. «Regenerate QR» asks first,
// because the printed QR stops working at once; a table without a code gets its first one without asking, and
// «Generate the missing QR codes» gives one to each table still without, one after another.
import {
  DataTable,
  type DataTableAction,
  type DataTableActionEvent,
  type DataTableColumn,
  EmptyState,
  formatDateTime,
  InlineFeedback,
  useConfirm,
} from '@erplora/ui/components';
import { useCommand } from '@erplora/ui/sdk';
import { AppPage, toastError, toastSuccess, useSession } from '@erplora/ui/shell';
import { computed, nextTick, ref, watch } from 'vue';
import { useRouter } from 'vue-router';

import QrSheet from '../components/QrSheet.vue';
import { useQrImages } from '../composables/useQrImages';
import type { TableCodeOut } from '../operations';
import { useBaseI18n } from '../../../../base/frontend/lib/i18n';
import { useLiveAllRows } from '../../../../base/frontend/lib/live-all-rows';
import { printPaper } from '../../../../base/frontend/lib/print';
import { printRefusal, withReason } from '../../../../base/frontend/lib/print-paper';
import { useBusinessZone } from '../../../../base/frontend/lib/zone';

/** Where the tables of the room are added. */
const TABLES = '/table/tables';

const { t, locale } = useBaseI18n();
const router = useRouter();
const session = useSession();
const zone = useBusinessZone();
const { confirm } = useConfirm();
const canChange = computed(() => session.can('online_order.change_qr_code'));
const canAddTables = computed(() => session.can('table.add_table'));

const list = useLiveAllRows('online_order.qr_code.list');
const rows = list.rows;
const coded = computed(() => rows.value.filter((row) => row.url));
const missing = computed(() => rows.value.filter((row) => !row.code));
const { images, ready } = useQrImages(() => coded.value.map((row) => row.url!));

const columns = computed<DataTableColumn<TableCodeOut>[]>(() => [
  { key: 'number', label: t('online_order.qrCodes.columns.number'), priority: 'high' },
  { key: 'zone_name', label: t('online_order.qrCodes.columns.zone'), format: (_, row) => row.zone_name ?? t('online_order.qrCodes.noZone') },
  { key: 'url', label: t('online_order.qrCodes.columns.url'), priority: 'low', format: (_, row) => row.url ?? t('online_order.qrCodes.noCode') },
  {
    key: 'issued_at',
    label: t('online_order.qrCodes.columns.issuedAt'),
    format: (_, row) => (row.issued_at ? formatDateTime(row.issued_at, locale.value, { timeZone: zone.value }) : t('online_order.qrCodes.noCode')),
  },
]);

const withCode = (row: TableCodeOut) => Boolean(row.code);
const actions = computed<DataTableAction<TableCodeOut>[]>(() => [
  { id: 'print', label: t('online_order.qrCodes.actions.print'), icon: 'ion:qr-code-outline', pinned: true, hidden: (row) => !withCode(row) },
  ...(canChange.value
    ? [
        { id: 'regenerate', label: t('online_order.qrCodes.actions.regenerate'), icon: 'ion:refresh-outline', hidden: (row: TableCodeOut) => !withCode(row) },
        { id: 'generate', label: t('online_order.qrCodes.actions.generate'), icon: 'ion:qr-code-outline', hidden: withCode },
      ]
    : []),
]);

const regeneration = useCommand('online_order.qr_code.regenerate');
const failure = (error: unknown) => (error instanceof Error && error.message ? error.message : t('online_order.qrCodes.failed'));

async function regenerate(row: TableCodeOut): Promise<void> {
  if (row.code) {
    const yes = await confirm({
      title: t('online_order.qrCodes.regenerate.title', { table: row.table }),
      message: t('online_order.qrCodes.regenerate.message'),
      confirmLabel: t('online_order.qrCodes.regenerate.confirm'),
      tone: 'danger',
    });
    if (!yes) return;
  }
  try {
    await regeneration.run({ id: row.table_id });
  } catch (error) {
    toastError(failure(error));
    return;
  }
  toastSuccess(t(row.code ? 'online_order.qrCodes.regenerated' : 'online_order.qrCodes.generated', { table: row.table }));
}

const generating = ref(false);
async function generateMissing(): Promise<void> {
  generating.value = true;
  const pending = [...missing.value];
  try {
    for (const row of pending) await regeneration.run({ id: row.table_id });
    toastSuccess(t('online_order.qrCodes.generatedMissing', { count: pending.length }));
  } catch (error) {
    toastError(failure(error));
  } finally {
    generating.value = false;
  }
}

// The sheet waits out of sight for what is printed: every table with a QR, or the one row asked for.
const holder = ref<HTMLElement | null>(null);
const sheetRows = ref<TableCodeOut[]>([]);
const printing = ref(false);
const canPrint = computed(() => list.complete.value && coded.value.length > 0 && !printing.value);

function drawn(): Promise<void> {
  if (ready.value) return Promise.resolve();
  return new Promise((resolve) => {
    const stop = watch(ready, (now) => {
      if (!now) return;
      stop();
      resolve();
    });
  });
}

async function print(only?: TableCodeOut): Promise<void> {
  printing.value = true;
  try {
    sheetRows.value = only ? [only] : coded.value;
    await drawn();
    await nextTick();
    const paper = holder.value?.firstElementChild as HTMLElement;
    await Promise.all([...paper.querySelectorAll('img')].map((img) => img.decode?.().catch(() => undefined)));
    await printPaper(paper, { title: t('online_order.sheet.title') });
  } catch (error) {
    toastError(withReason(t('online_order.qrCodes.printFailed'), printRefusal(error, t)));
  } finally {
    printing.value = false;
  }
}

function onAction({ actionId, row }: DataTableActionEvent<TableCodeOut>): void {
  if (actionId === 'print') void print(row);
  else void regenerate(row);
}
</script>

<template>
  <AppPage
    :title="$t('online_order.qrCodes.title')"
    content-layout="fill"
  >
    <template #actions>
      <ion-button
        data-testid="online-order-qr-print"
        :disabled="!canPrint"
        @click="print()"
      >
        {{ $t('online_order.qrCodes.print') }}
      </ion-button>
    </template>
    <InlineFeedback
      v-if="list.status.value === 'reconnecting'"
      tone="warning"
      data-testid="online-order-qr-reconnecting"
    >
      {{ $t('online_order.qrCodes.reconnecting') }}
    </InlineFeedback>
    <InlineFeedback
      v-if="list.complete.value && missing.length && rows.length"
      tone="info"
      data-testid="online-order-qr-missing"
    >
      {{ $t('online_order.qrCodes.missing', { count: missing.length }) }}
      <template
        v-if="canChange"
        #actions
      >
        <ion-button
          size="small"
          data-testid="online-order-qr-generate-missing"
          :disabled="generating"
          @click="generateMissing"
        >
          {{ $t('online_order.qrCodes.generateMissing') }}
        </ion-button>
      </template>
    </InlineFeedback>
    <DataTable
      testid="online-order-qr"
      fill
      :rows="rows"
      row-key="table_id"
      :columns="columns"
      :actions="actions"
      :views="['table', 'cards']"
      :card-title="(row: TableCodeOut) => $t('online_order.sheet.table', { number: row.number })"
      :card-icon="() => 'qr-code-outline'"
      :entity-label="{ one: $t('online_order.qrCodes.entity.one'), many: $t('online_order.qrCodes.entity.many') }"
      :loading="list.status.value === 'loading'"
      :error="list.status.value === 'error' ? (list.error.value?.message ?? $t('online_order.qrCodes.loadError')) : undefined"
      :labels="{ loadError: $t('online_order.qrCodes.loadError'), retry: $t('online_order.qrCodes.retry') }"
      @action="onAction"
      @retry="list.refresh()"
    >
      <template #empty>
        <EmptyState
          data-testid="online-order-qr-empty"
          icon="grid-outline"
          :heading="$t('online_order.qrCodes.empty')"
          :message="$t('online_order.qrCodes.emptyMessage')"
        >
          <template
            v-if="canAddTables"
            #action
          >
            <ion-button
              data-testid="online-order-qr-to-tables"
              @click="router.push(TABLES)"
            >
              {{ $t('online_order.qrCodes.goToTables') }}
            </ion-button>
          </template>
        </EmptyState>
      </template>
    </DataTable>
    <div
      ref="holder"
      hidden
    >
      <QrSheet
        :rows="sheetRows"
        :images="images"
      />
    </div>
  </AppPage>
</template>
