<script setup lang="ts">
// Time clock → Records (WORKBOOK «Pantallas · Registros»; ATTENDANCE-F06, F07, F08, F09, F10, F11), the old
// `erp-attendance-records`: the working days of the chosen month in a server-side DataTable — Date,
// Person, Clock-in, Clock-out, Breaks (min), Worked, Status and Location —, list or cards, 50 a page,
// with «Correct» (whoever may correct) and «History» on each row and «Export CSV» above. The server
// limits an employee to their own days (no Person, no search); a manager sees the team, filters by
// Person (searched on the server), Month (the four years the law keeps) and Status, and «Clocked in
// now» on top. Times are the business's; the worked time of an open day runs on by the minute.
import {
  Combo,
  type ComboOption,
  type ComboSearch,
  DataTable,
  type DataTableAction,
  type DataTableColumn,
  type DataTableFilters,
  EmptyState,
  InlineFeedback,
  StatusPill,
  type StatusPillTone,
} from '@erplora/ui/components';
import { useLiveClient } from '@erplora/ui/sdk';
import { AppPage, HubIcon, useSession } from '@erplora/ui/shell';
import { IonButton, IonSelect, IonSelectOption } from '@ionic/vue';
import { computed, ref } from 'vue';

import CorrectionModal from '../components/CorrectionModal.vue';
import HistoryModal from '../components/HistoryModal.vue';
import PageNotices, { blockingError } from '../components/PageNotices.vue';
import PresenceCard from '../components/PresenceCard.vue';
import { useLiveList } from '../composables/useLiveList';
import { useServerNow } from '../composables/useServerNow';
import { useServerTable } from '../composables/useServerTable';
import { useLocale, useT } from '../composables/useT';
import { saveCsv } from '../lib/download';
import { formatDay, formatHm, liveSeconds, monthBounds, monthLabel, monthOf, recentMonths, timeOfDay } from '../lib/time';
import type { RecordListIn, RecordOut, RecordStatus } from '../operations';
import { attendanceTabs } from '../tabs';

const STATUSES: readonly RecordStatus[] = ['open', 'closed', 'needs_review'];
const TONE: Record<RecordStatus, StatusPillTone> = { open: 'info', closed: 'neutral', needs_review: 'warning' };
/** This month and the 48 before it: the four years the law keeps the record (RD-ley 8/2019). */
const MONTHS_OFFERED = 49;
/** People asked at once by the «Person» search: the manager narrows them by typing. */
const PEOPLE_PAGE = 20;

const session = useSession();
const client = useLiveClient();
const t = useT();
const locale = useLocale();
const team = computed(() => session.can('attendance.view_all'));
const canCorrect = computed(() => session.can('attendance.correct'));

const month = ref(monthOf(Date.now()));
const months = computed(() => {
  const offered = recentMonths(monthOf(Date.now()), MONTHS_OFFERED);
  return offered.includes(month.value) ? offered : [...offered, month.value];
});
const person = ref<ComboOption | null>(null);
const filters = ref<DataTableFilters>({});
const table = useServerTable({ sort: '-clock_in_at' });

/** What the list and the CSV share: the month, the person and the status. */
const query = computed<Partial<RecordListIn>>(() => ({
  ...monthBounds(month.value),
  ...(person.value ? { member_id: person.value.id } : {}),
  ...(filters.value.status ? { status: filters.value.status as RecordStatus } : {}),
}));

function narrowed(): boolean {
  return person.value !== null || !!filters.value.status;
}

function setMonth(value: unknown): void {
  if (typeof value !== 'string' || !value || value === month.value) return;
  month.value = value;
  table.restart({ narrowed: narrowed() });
}

function setPerson(option: ComboOption | null): void {
  person.value = option;
  table.restart({ narrowed: narrowed() });
}

function onFilters(next: DataTableFilters): void {
  filters.value = next;
  table.restart({ narrowed: narrowed() });
}

const { data: result, status, error, refresh } = useLiveList(
  'attendance.record.list',
  () => ({ ...query.value, ...table.query.value }),
  () => table.windows.value,
);
table.followResult(result);
// The server's clock (the rows' `as_of`), ticking by the minute: never the device's own.
const now = useServerNow(() => result.value?.rows[0]?.as_of, 60_000);
const blocked = computed(() => blockingError(error.value));

const searchPeople: ComboSearch = async (text) => {
  const found = await client.api.call('attendance.person.list', { ...(text.trim() ? { search: text.trim() } : {}), limit: PEOPLE_PAGE });
  return found.rows.map((row) => ({ id: row.id, label: row.name }));
};

const running = (row: RecordOut): boolean => row.status === 'open';
const worked = (row: RecordOut): number | null =>
  row.worked_seconds === null ? null : liveSeconds(row.worked_seconds, row.as_of, now.value, running(row) && !row.break_started_at);
const breakMinutes = (row: RecordOut): number =>
  Math.floor(liveSeconds(row.break_seconds, row.as_of, now.value, running(row) && !!row.break_started_at) / 60);

const columns = computed<DataTableColumn<RecordOut>[]>(() => [
  { key: 'work_date', label: t('attendance.records.columns.date'), sortable: true, priority: 'high', format: (_, row) => formatDay(row.work_date, locale.value) },
  ...(team.value
    ? [{ key: 'member_name', label: t('attendance.records.columns.person'), sortable: true, priority: 'high' } as DataTableColumn<RecordOut>]
    : []),
  { key: 'clock_in_at', label: t('attendance.records.columns.in'), sortable: true, format: (_, row) => timeOfDay(row.clock_in_at, row.work_date, locale.value) },
  { key: 'clock_out_at', label: t('attendance.records.columns.out'), sortable: true, format: (_, row) => timeOfDay(row.clock_out_at, row.work_date, locale.value) },
  { key: 'break_minutes', label: t('attendance.records.columns.breaks'), align: 'right', format: (_, row) => String(breakMinutes(row)) },
  { key: 'worked', label: t('attendance.records.columns.worked'), align: 'right', cell: 'worked' },
  {
    key: 'status',
    label: t('attendance.records.columns.status'),
    sortable: true,
    cell: 'status',
    filter: { type: 'select', options: STATUSES.map((value) => ({ value, label: t(`attendance.status.${value}`) })) },
  },
  { key: 'location', label: t('attendance.records.columns.location'), cell: 'location', priority: 'low' },
]);

const actions = computed<DataTableAction<RecordOut>[]>(() => [
  ...(canCorrect.value ? [{ id: 'correct', label: t('attendance.records.actions.correct'), icon: 'create-outline', showLabel: true }] : []),
  { id: 'history', label: t('attendance.records.actions.history'), icon: 'time-outline', showLabel: true },
]);

// Dialogs
const correcting = ref<RecordOut | null>(null);
const correctOpen = ref(false);
const historyOf = ref<RecordOut | null>(null);
const historyOpen = ref(false);
const corrected = ref(false);

function onAction({ actionId, row }: { actionId: string; row: RecordOut }): void {
  if (actionId === 'correct') {
    correcting.value = row;
    correctOpen.value = true;
  }
  if (actionId === 'history') {
    historyOf.value = row;
    historyOpen.value = true;
  }
}

function onCorrected(): void {
  corrected.value = true;
}

// CSV (ATTENDANCE-F10): every row of the filter, written by the server.
const exporting = ref(false);
const exportNotice = ref<{ tone: 'info' | 'danger'; text: string } | null>(null);

async function exportCsv(): Promise<void> {
  if (exporting.value) return;
  exporting.value = true;
  exportNotice.value = null;
  try {
    const search = table.query.value.search;
    const file = await client.api.call('attendance.record.export', { ...query.value, sort: table.query.value.sort, ...(search ? { search } : {}) });
    saveCsv(file.filename, file.csv);
    if (file.rows === 0) exportNotice.value = { tone: 'info', text: t('attendance.records.exportEmpty') };
  } catch {
    exportNotice.value = { tone: 'danger', text: t('attendance.records.exportFailed') };
  } finally {
    exporting.value = false;
  }
}

const cardTitle = (row: RecordOut): string => {
  const day = formatDay(row.work_date, locale.value);
  return team.value ? `${day} · ${row.member_name}` : day;
};
</script>

<template>
  <AppPage
    :title="$t('attendance.title')"
    content-layout="fill"
    :tabs="attendanceTabs($t)"
    :tabs-label="$t('attendance.tabs.label')"
  >
    <PageNotices
      testid="attendance-records"
      :status="status"
      :error="error"
    />
    <PresenceCard v-if="team && !blocked" />
    <InlineFeedback
      v-if="corrected"
      tone="success"
      dismissible
      data-testid="attendance-records-corrected"
      @dismiss="corrected = false"
    >
      {{ $t('attendance.correct.corrected') }}
    </InlineFeedback>
    <InlineFeedback
      v-if="exportNotice"
      :tone="exportNotice.tone"
      dismissible
      data-testid="attendance-records-export-notice"
      @dismiss="exportNotice = null"
    >
      {{ exportNotice.text }}
    </InlineFeedback>
    <DataTable
      v-if="!blocked"
      v-model:search="table.search.value"
      testid="attendance-records"
      fill
      server-side
      :searchable="team"
      :filters="filters"
      :rows="result?.rows ?? []"
      :total="result?.total ?? 0"
      :page="table.page.value"
      :page-size="table.pageSize.value"
      :sort="table.sort.value"
      :sort-dir="table.dir.value"
      :views="['table', 'cards']"
      :card-title="cardTitle"
      :card-icon="() => 'time-outline'"
      :entity-label="{ one: $t('attendance.records.entity.one'), many: $t('attendance.records.entity.many') }"
      :loading="status === 'loading'"
      :error="status === 'error' && !blocked ? $t('attendance.records.loadError') : undefined"
      :actions="actions"
      :search-placeholder="$t('attendance.records.search')"
      :labels="{ loadError: $t('attendance.records.loadError'), retry: $t('attendance.live.retry'), loading: $t('attendance.records.loading') }"
      :columns="columns"
      @filters-change="onFilters"
      @page-change="table.goToPage"
      @load-more="table.loadMore"
      @page-size-change="table.setPageSize"
      @sort-change="table.setSort"
      @action="onAction"
      @retry="refresh()"
    >
      <template #filters>
        <div class="attendance-records__filters">
          <ion-select
            class="attendance-records__month"
            data-testid="attendance-records-month"
            interface="popover"
            mode="md"
            fill="outline"
            label-placement="floating"
            :label="$t('attendance.records.month')"
            :value="month"
            @ion-change="setMonth($event.detail.value)"
          >
            <ion-select-option
              v-for="value in months"
              :key="value"
              :value="value"
            >
              {{ monthLabel(value, locale) }}
            </ion-select-option>
          </ion-select>
          <Combo
            v-if="team"
            class="attendance-records__person"
            testid="attendance-records-person"
            :model-value="person"
            :search="searchPeople"
            :label="$t('attendance.records.person')"
            :placeholder="$t('attendance.records.personAll')"
            @update:model-value="setPerson"
          />
        </div>
      </template>
      <template #toolbar>
        <ion-button
          size="small"
          fill="outline"
          data-testid="attendance-export-csv"
          :disabled="exporting"
          @click="exportCsv"
        >
          <HubIcon
            slot="start"
            name="ion:download-outline"
          />
          {{ exporting ? $t('attendance.records.exporting') : $t('attendance.records.exportCsv') }}
        </ion-button>
      </template>
      <template #worked="{ row }">
        <span class="attendance-records__worked">
          <template v-if="worked(row) === null">—</template>
          <template v-else>{{ formatHm(worked(row) ?? 0) }}</template>
          <StatusPill
            v-if="row.status === 'open'"
            size="sm"
            tone="info"
            :label="t('attendance.records.inProgress')"
          />
        </span>
      </template>
      <template #status="{ row }">
        <StatusPill
          size="sm"
          :tone="TONE[row.status as RecordStatus]"
          :label="t(`attendance.status.${row.status}`)"
        />
      </template>
      <template #location="{ row }">
        <span
          v-if="row.in_within_radius === null && row.out_within_radius === null"
          :title="t('attendance.records.radius.none')"
          :aria-label="t('attendance.records.radius.none')"
        >—</span>
        <span
          v-else
          class="attendance-records__location"
        >
          <HubIcon
            v-if="row.in_within_radius !== null"
            data-testid="attendance-records-location-in"
            :class="row.in_within_radius ? 'attendance-records__inside' : 'attendance-records__outside'"
            :name="row.in_within_radius ? 'ion:checkmark-circle-outline' : 'ion:alert-circle-outline'"
            :label="t(row.in_within_radius ? 'attendance.records.radius.inInside' : 'attendance.records.radius.inOutside')"
          />
          <HubIcon
            v-if="row.out_within_radius !== null"
            data-testid="attendance-records-location-out"
            :class="row.out_within_radius ? 'attendance-records__inside' : 'attendance-records__outside'"
            :name="row.out_within_radius ? 'ion:checkmark-circle-outline' : 'ion:alert-circle-outline'"
            :label="t(row.out_within_radius ? 'attendance.records.radius.outInside' : 'attendance.records.radius.outOutside')"
          />
        </span>
      </template>
      <template #empty>
        <EmptyState
          data-testid="attendance-records-empty"
          icon="time-outline"
          :heading="table.filtered.value ? $t('attendance.noResults') : $t('attendance.records.empty')"
          :message="table.filtered.value ? $t('attendance.noResultsMessage') : undefined"
        />
      </template>
    </DataTable>
    <CorrectionModal
      v-model:open="correctOpen"
      :record="correcting"
      :team="team"
      @corrected="onCorrected"
    />
    <HistoryModal
      v-model:open="historyOpen"
      :record="historyOf"
    />
  </AppPage>
</template>

<style scoped>
/* Month and Person side by side in the toolbar; each on its own line on a phone. */
.attendance-records__filters {
  display: flex;
  flex: 0 1 30rem;
  gap: 8px;
  align-items: center;
}
.attendance-records__month,
.attendance-records__person {
  flex: 1 1 0;
  min-width: 10rem;
}
@media (max-width: 640px) {
  .attendance-records__filters {
    flex-basis: 100%;
    flex-wrap: wrap;
  }
  .attendance-records__month,
  .attendance-records__person {
    flex-basis: 100%;
  }
}
.attendance-records__worked {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  flex-wrap: wrap;
  justify-content: flex-end;
  font-variant-numeric: tabular-nums;
}
.attendance-records__location {
  display: inline-flex;
  gap: 0.25rem;
  font-size: 1.1rem;
}
.attendance-records__inside {
  color: var(--ion-color-success, #2dd36f);
}
.attendance-records__outside {
  color: var(--ion-color-danger, #c5000f);
}
</style>
