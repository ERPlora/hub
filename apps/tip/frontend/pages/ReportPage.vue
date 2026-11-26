<script setup lang="ts">
// Tips → Report (TIP-F13; WORKBOOK «Pantallas · Informe»): the team's tips of the period — «Today» to begin with, «7
// days» or «30 days» — live (`tip.report.get`), by person or by working day clocked in Time clock: the period's figures
// above, and a line per person or per working day with how many and how much by card, in cash and other ways. «Export»
// saves the lines on screen as CSV.
import { DataTable, type DataTableColumn, EmptyState } from '@erplora/ui/components';
import { useLive } from '@erplora/ui/sdk';
import { AppPage, HubIcon } from '@erplora/ui/shell';
import { IonButton, IonSelect, IonSelectOption } from '@ionic/vue';
import { computed, shallowRef } from 'vue';

import ListNotices, { blockingError } from '../../../sale/frontend/components/backoffice/ListNotices.vue';
import { useLocale, useT } from '../../../sale/frontend/composables/useT';
import { formatMoney } from '../../../sale/frontend/lib/format';
import { useAppTabs } from '../../../../base/frontend/lib/app-tabs';
import { saveCsv } from '../../../../base/frontend/lib/download';
import { useBusinessMoney } from '../../../../base/frontend/lib/money';
import { useBusinessZone } from '../../../../base/frontend/lib/zone';
import PeriodSelect from '../components/PeriodSelect.vue';
import TipFigures from '../components/TipFigures.vue';
import { usePeriod } from '../composables/usePeriod';
import { lineName, reportCsv, reportFilename, shiftText } from '../lib/report';
import type { ReportBy, ReportIn, ReportRowOut } from '../operations';

type Line = ReportRowOut & { key: string };
type Amount = 'card' | 'cash' | 'other' | 'total';

const VIEWS: readonly ReportBy[] = ['person', 'shift'];

const tabs = useAppTabs('tip');
const t = useT();
const locale = useLocale();
const money = useBusinessMoney();
const zone = useBusinessZone();

const { period, bounds, pick } = usePeriod();
const by = shallowRef<ReportBy>('person');
function pickView(value: unknown): void {
  if (VIEWS.includes(value as ReportBy)) by.value = value as ReportBy;
}

const params = computed<ReportIn>(() => ({ by: by.value, ...bounds.value }));
const { data, status, error, refresh } = useLive('tip.report.get', params);
const blocked = computed(() => blockingError(error.value));
const tableError = computed(() => (status.value === 'error' ? error.value?.message : undefined));

/** The view of the report on screen, which may lag behind the one just picked until the server answers. */
const shown = computed<ReportBy>(() => data.value?.by ?? by.value);
const noShifts = computed(() => data.value?.by === 'shift' && !data.value.shifts_available);
const lines = computed<Line[]>(() => (data.value?.rows ?? []).map((row) => ({ ...row, key: row.shift_id ?? row.member_id ?? 'nobody' })));

const amount = (key: Amount): DataTableColumn<Line> => ({
  key,
  label: t(`tip.report.columns.${key}`),
  align: 'right',
  format: (_, row) => formatMoney(row[key], locale.value, money.value),
});

const columns = computed<DataTableColumn<Line>[]>(() => [
  { key: 'member_name', label: t('tip.report.columns.person'), priority: 'high', format: (_, row) => lineName(row, shown.value, t) },
  ...(shown.value === 'shift'
    ? [{ key: 'clock_in_at', label: t('tip.report.columns.shift'), format: (_: unknown, row: Line) => shiftText(row, { t, locale: locale.value, zone: zone.value }) }]
    : []),
  { key: 'count', label: t('tip.report.columns.count'), align: 'right', format: (_, row) => String(row.count) },
  amount('card'),
  amount('cash'),
  amount('other'),
  { ...amount('total'), priority: 'high' },
]);

const exporting = shallowRef(false);
const canExport = computed(() => Boolean(data.value && money.value) && !exporting.value);

async function exportCsv(): Promise<void> {
  const report = data.value;
  const inMoney = money.value;
  if (!report || !inMoney || exporting.value) return;
  exporting.value = true;
  try {
    await saveCsv(reportFilename(report), reportCsv(report, { t, locale: locale.value, zone: zone.value, money: inMoney }), t);
  } finally {
    exporting.value = false;
  }
}
</script>

<template>
  <AppPage
    :title="$t('tip.title')"
    content-layout="fill"
    :tabs="tabs"
    :tabs-label="$t('tip.tabs.label')"
  >
    <ListNotices
      testid="tip-report"
      :status="status"
      :error="error"
    />
    <template v-if="!blocked">
      <TipFigures
        class="ion-margin-bottom"
        testid="tip-report-figures"
        :figures="data?.totals"
      />
      <DataTable
        testid="tip-report"
        fill
        :rows="lines"
        row-key="key"
        :page-size="100"
        :page-size-chooser="false"
        :views="['table', 'cards']"
        :card-title="(row: Line) => lineName(row, shown, t)"
        :card-icon="() => 'wallet-outline'"
        :entity-label="{ one: $t('tip.report.entity.one'), many: $t('tip.report.entity.many') }"
        :loading="status === 'loading'"
        :error="tableError"
        :labels="{ loading: $t('tip.report.loading'), loadError: $t('tip.report.loadError'), retry: $t('sale.live.retry') }"
        :columns="columns"
        @retry="refresh()"
      >
        <template #toolbar>
          <PeriodSelect
            testid="tip-report-period"
            :value="period"
            @pick="pick"
          />
          <ion-select
            data-testid="tip-report-by"
            interface="popover"
            :value="by"
            :aria-label="$t('tip.report.by.label')"
            @ion-change="pickView($event.detail.value)"
          >
            <ion-select-option
              v-for="view in VIEWS"
              :key="view"
              :value="view"
            >
              {{ $t(`tip.report.by.${view}`) }}
            </ion-select-option>
          </ion-select>
          <ion-button
            size="small"
            fill="outline"
            data-testid="tip-report-export"
            :disabled="!canExport"
            @click="exportCsv"
          >
            <HubIcon
              slot="start"
              name="ion:download-outline"
            />
            {{ $t('tip.report.export') }}
          </ion-button>
        </template>
        <template #empty>
          <EmptyState
            v-if="noShifts"
            data-testid="tip-report-no-shifts"
            icon="time-outline"
            :heading="$t('tip.report.noShifts.heading')"
            :message="$t('tip.report.noShifts.message')"
          />
          <EmptyState
            v-else
            data-testid="tip-report-empty"
            icon="wallet-outline"
            :heading="$t('tip.report.empty')"
            :message="$t('tip.report.emptyMessage')"
          />
        </template>
      </DataTable>
    </template>
  </AppPage>
</template>
