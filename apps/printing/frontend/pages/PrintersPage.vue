<script setup lang="ts">
// Printing → Printers (WORKBOOK «Pantallas · Impresoras»; the old «Printers» screen): the intro, the print
// queue's summary by role (PRINTING-F01) and the business's printers, live, by name (PRINTING-F03, F04,
// F19) — Name, Role, Connection, Address, Paper, Status (with the last error) and Active —, list or cards.
// Whoever manages the settings adds one («Add printer»), edits it and deactivates or activates it (a printer
// is never deleted: the queue names it); whoever prints sends it a test page (PRINTING-F05), active ones only.
// Every change comes back through the stream by itself.
import { DataTable, type DataTableAction, type DataTableColumn, EmptyState, InlineFeedback, StatusPill } from '@erplora/ui/components';
import { useCommand, useLive } from '@erplora/ui/sdk';
import { AppPage, toastError, toastSuccess, useSession } from '@erplora/ui/shell';
import { computed, shallowRef } from 'vue';

import PrinterModal from '../components/PrinterModal.vue';
import QueueSummary from '../components/QueueSummary.vue';
import { useNow } from '../composables/useNow';
import { useT } from '../composables/useT';
import { printerAddress, printerPaper, printerState, STATE_TONE } from '../lib/format';
import { refusal } from '../lib/refusal';
import type { PrinterOut } from '../operations';
import { printingTabs } from '../tabs';

const session = useSession();
const canManage = computed(() => session.can('printing.manage_settings'));
const canPrint = computed(() => session.can('printing.print'));
const t = useT();
/** «Waiting» comes from the clock: it turns by itself, without another result. */
const now = useNow();

const list = useLive('printing.printer.list', { limit: 100 });
const update = useCommand('printing.printer.update');
const test = useCommand('printing.printer.test');

const rows = computed(() => list.data.value?.rows ?? []);
const blocked = computed(() => {
  const code = list.error.value?.code;
  return code === 'app_inactive' || code === 'permission_denied' ? code : null;
});
const tableError = computed(() => (list.status.value === 'error' && !blocked.value ? t('printing.printers.loadError') : undefined));

const columns = computed<DataTableColumn<PrinterOut>[]>(() => [
  { key: 'name', label: t('printing.printers.columns.name'), priority: 'high' },
  { key: 'usage', label: t('printing.printers.columns.usage'), format: (_, row) => t(`printing.usage.${row.usage}`) },
  { key: 'kind', label: t('printing.printers.columns.kind'), format: (_, row) => t(`printing.kind.${row.kind}`) },
  { key: 'address', label: t('printing.printers.columns.address'), priority: 'low', format: (_, row) => printerAddress(row) },
  { key: 'paper_width', label: t('printing.printers.columns.paper'), priority: 'low', format: (_, row) => printerPaper(row, t) },
  { key: 'state', label: t('printing.printers.columns.state'), cell: 'state', format: (_, row) => t(`printing.state.${printerState(row, now.value)}`) },
  {
    key: 'is_active',
    label: t('printing.printers.columns.active'),
    format: (_, row) => (row.is_active ? t('printing.printers.yes') : t('printing.printers.no')),
  },
]);

const actions = computed<DataTableAction<PrinterOut>[]>(() => [
  ...(canManage.value ? [{ id: 'edit', label: t('printing.printers.actions.edit'), icon: 'create-outline' }] : []),
  ...(canPrint.value
    ? [
        {
          id: 'test',
          label: t('printing.printers.actions.test'),
          icon: 'lucide:receipt',
          showLabel: true,
          hidden: (row: PrinterOut) => !row.is_active,
          loading: (row: PrinterOut) => testing.value === row.id,
        },
      ]
    : []),
  ...(canManage.value
    ? [
        {
          id: 'toggle',
          label: (row: PrinterOut) => (row.is_active ? t('printing.printers.actions.deactivate') : t('printing.printers.actions.activate')),
          icon: 'swap-horizontal-outline',
          loading: (row: PrinterOut) => toggling.value === row.id,
        },
      ]
    : []),
]);

const editing = shallowRef(false);
const target = shallowRef<PrinterOut | null>(null);
const testing = shallowRef<string | null>(null);
const toggling = shallowRef<string | null>(null);

function add(): void {
  target.value = null;
  editing.value = true;
}

async function sendTest(row: PrinterOut): Promise<void> {
  testing.value = row.id;
  try {
    await test.run({ printer_id: row.id });
    void toastSuccess(t('printing.printers.tested', { name: row.name }));
  } catch {
    void toastError(refusal(test.error.value, t('printing.printers.testFailed'))?.message ?? t('printing.printers.testFailed'));
  } finally {
    testing.value = null;
  }
}

async function toggle(row: PrinterOut): Promise<void> {
  toggling.value = row.id;
  try {
    await update.run({ printer_id: row.id, is_active: !row.is_active });
    void toastSuccess(t(row.is_active ? 'printing.printers.deactivated' : 'printing.printers.activated'));
  } catch {
    void toastError(refusal(update.error.value, t('printing.printers.toggleFailed'))?.message ?? t('printing.printers.toggleFailed'));
  } finally {
    toggling.value = null;
  }
}

function onAction({ actionId, row }: { actionId: string; row: PrinterOut }): void {
  if (actionId === 'edit' && canManage.value) {
    target.value = row;
    editing.value = true;
  } else if (actionId === 'test' && canPrint.value && row.is_active && !testing.value) void sendTest(row);
  else if (actionId === 'toggle' && canManage.value && !toggling.value) void toggle(row);
}
</script>

<template>
  <AppPage
    :title="$t('printing.title')"
    :tabs="printingTabs($t)"
    :tabs-label="$t('printing.tabs.label')"
  >
    <div class="printing-printers">
      <p
        class="printing-printers__intro"
        data-testid="printing-printers-intro"
      >
        {{ $t('printing.printers.intro') }}
      </p>

      <QueueSummary />

      <section class="printing-printers__list">
        <h2
          class="printing-printers__heading"
          data-testid="printing-printers-heading"
        >
          {{ $t('printing.printers.heading') }}
        </h2>
        <InlineFeedback
          tone="info"
          icon="information-circle-outline"
          data-testid="printing-printers-app-note"
        >
          {{ $t('printing.printers.appNote') }}
        </InlineFeedback>
        <InlineFeedback
          v-if="blocked"
          tone="warning"
          data-testid="printing-printers-blocked"
          :heading="blocked === 'app_inactive' ? $t('printing.live.appInactive') : $t('printing.live.noPermission')"
        />
        <DataTable
          v-else
          testid="printing-printers"
          :rows="rows"
          :page-size="100"
          :page-size-options="[]"
          :column-picker="false"
          :views="['table', 'cards']"
          :card-title="(row: PrinterOut) => row.name"
          card-title-column="name"
          :card-icon="() => 'lucide:receipt'"
          :loading="list.status.value === 'loading'"
          :error="tableError"
          :addable="canManage"
          :actions="actions"
          :max-inline-actions="3"
          :entity-label="{ one: $t('printing.printers.entity.one'), many: $t('printing.printers.entity.many') }"
          :labels="{ add: $t('printing.printers.add'), loading: $t('printing.printers.loading'), retry: $t('printing.live.retry') }"
          :columns="columns"
          @add="add"
          @action="onAction"
          @retry="list.refresh()"
        >
          <template #state="{ row }">
            <span
              class="printing-printers__state"
              :data-testid="`printing-printers-state-${row.id}`"
            >
              <StatusPill
                size="sm"
                :tone="STATE_TONE[printerState(row as PrinterOut, now)]"
                :label="t(`printing.state.${printerState(row as PrinterOut, now)}`)"
              />
              <small v-if="row.last_error && printerState(row as PrinterOut, now) === 'failing'">{{
                t('printing.printers.lastError', { error: row.last_error })
              }}</small>
            </span>
          </template>
          <template #empty>
            <EmptyState
              data-testid="printing-printers-empty"
              icon="file-tray-outline"
              :heading="$t('printing.printers.empty')"
            />
          </template>
        </DataTable>
      </section>
    </div>

    <PrinterModal
      v-if="canManage"
      v-model:open="editing"
      :printer="target"
    />
  </AppPage>
</template>

<style scoped>
.printing-printers {
  display: grid;
  gap: 1.5rem;
}
.printing-printers__intro {
  margin: 0;
  padding-inline: 0.25rem;
  color: var(--ion-color-medium-shade, var(--ion-color-medium));
}
.printing-printers__list {
  display: grid;
  gap: 8px;
}
.printing-printers__heading {
  margin: 0;
  padding-inline: 0.25rem;
  font-size: 1.05rem;
  font-weight: 600;
}
.printing-printers__state {
  display: inline-grid;
  gap: 2px;
  justify-items: start;
}
.printing-printers__state small {
  color: var(--ion-color-danger-shade, var(--ion-color-danger));
}
</style>
