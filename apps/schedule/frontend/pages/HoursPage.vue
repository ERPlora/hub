<script setup lang="ts">
// Schedules → Hours (SCHEDULE-F01, F02, F03; WORKBOOK «Pantallas · Horario»): the live
// `schedule.week.get` as seven fixed rows — Day, Hours («10:00–14:00 · 17:00–20:00», «Open 24 hours»,
// «Closed», «Not set») and Status — in the order of «Week starts» (the server folds and turns the week).
// No «+»: a day is edited, never added (Google Business Profile, Square, Fresha). «Edit» or the row opens
// «Edit hours — {day}» for whoever can change the hours. While the week is still the default one, the
// yellow notice with «Yes, these are my hours» (`schedule.week.confirm`); a refused confirmation is said
// above the table.
import { type DataTableAction, type DataTableColumn, DataTable, InlineFeedback } from '@erplora/ui/components';
import { useCommand, useLive } from '@erplora/ui/sdk';
import { AppPage, useSession } from '@erplora/ui/shell';
import { IonButton } from '@ionic/vue';
import { computed, ref } from 'vue';

import DayHoursModal from '../components/DayHoursModal.vue';
import PageNotices, { blockingError } from '../components/PageNotices.vue';
import { useLocale, useT } from '../composables/useT';
import { hoursSummary, statusOf } from '../lib/intervals';
import type { WeekDayOut } from '../operations';
import { scheduleTabs } from '../tabs';

const session = useSession();
const t = useT();
const locale = useLocale();
const canChange = computed(() => session.can('schedule.change'));

const { data: week, status, error, refresh } = useLive('schedule.week.get', {});
const blocked = computed(() => blockingError(error.value));
const tableError = computed(() => (status.value === 'error' && !blocked.value ? error.value?.message : undefined));
/** The default week nobody confirmed: the notice of the old screen (only over a week that is there). */
const unconfirmed = computed(() => !!week.value && !week.value.confirmed && week.value.days.some((d) => d.is_set));

const dayName = (weekday: number): string => t(`schedule.days.${weekday}`);

const columns = computed<DataTableColumn<WeekDayOut>[]>(() => [
  { key: 'weekday', label: t('schedule.hours.columns.day'), priority: 'high', format: (_, row) => dayName(row.weekday) },
  { key: 'hours', label: t('schedule.hours.columns.hours'), width: 'minmax(12rem,2fr)', format: (_, row) => hoursSummary(row, t, locale.value) },
  { key: 'status', label: t('schedule.hours.columns.status'), format: (_, row) => statusOf(row, t) },
]);

const actions = computed<DataTableAction<WeekDayOut>[]>(() =>
  canChange.value ? [{ id: 'edit', label: t('schedule.actions.edit'), icon: 'create-outline' }] : [],
);

const editing = ref<WeekDayOut | null>(null);
const formOpen = ref(false);
const pageError = ref('');
const confirmation = useCommand('schedule.week.confirm');

function edit(row: WeekDayOut): void {
  if (!canChange.value) return;
  pageError.value = '';
  editing.value = row;
  formOpen.value = true;
}

async function confirmWeek(): Promise<void> {
  if (confirmation.pending.value) return;
  pageError.value = '';
  try {
    await confirmation.run({});
  } catch (failure) {
    pageError.value = failure instanceof Error ? failure.message : String(failure);
  }
}
</script>

<template>
  <AppPage
    :title="$t('schedule.title')"
    :tabs="scheduleTabs($t)"
    :tabs-label="$t('schedule.tabs.label')"
  >
    <PageNotices
      testid="schedule-hours"
      :status="status"
      :error="error"
    />
    <InlineFeedback
      v-if="pageError"
      tone="danger"
      data-testid="schedule-hours-error"
    >
      {{ pageError }}
    </InlineFeedback>
    <InlineFeedback
      v-if="unconfirmed"
      tone="warning"
      data-testid="schedule-hours-default-week"
    >
      <span>{{ $t('schedule.hours.defaultWeek.message') }}</span>
      <template
        v-if="canChange"
        #actions
      >
        <ion-button
          size="small"
          data-testid="schedule-hours-confirm-week"
          :disabled="confirmation.pending.value"
          @click="confirmWeek"
        >
          {{ $t('schedule.hours.defaultWeek.confirm') }}
        </ion-button>
      </template>
    </InlineFeedback>
    <DataTable
      v-if="!blocked"
      testid="schedule-hours"
      :row-key="(row: WeekDayOut) => String(row.weekday)"
      :rows="week?.days ?? []"
      :page-size="7"
      :page-size-options="[]"
      :column-picker="false"
      :views="['table', 'cards']"
      :card-title="(row: WeekDayOut) => dayName(row.weekday)"
      :card-icon="() => 'time-outline'"
      card-title-column="weekday"
      :entity-label="{ one: $t('schedule.hours.entity.one'), many: $t('schedule.hours.entity.many') }"
      :loading="status === 'loading'"
      :error="tableError"
      :row-clickable="canChange"
      :actions="actions"
      :labels="{ loadError: $t('schedule.hours.loadError'), retry: $t('schedule.live.retry') }"
      :columns="columns"
      @action="({ row }) => edit(row)"
      @row-click="edit"
      @retry="refresh()"
    />
    <DayHoursModal
      v-if="canChange"
      v-model:open="formOpen"
      :day="editing"
    />
  </AppPage>
</template>
