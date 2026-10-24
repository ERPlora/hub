<script setup lang="ts">
// System › Logs (BASE-G90, G24; the old hub's SystemPage `#logs`, HUB_SHELL-F144), for who runs the business (the
// tab exists for no one else): the live `base.event.list` — the last 50 events between the hub's apps, newest first —
// in a table of Time, Level and Event: its name, the app that recorded it and what happened to it, in the person's
// language (the error itself stays in Failed events; the content of an event, never). Searchable, filtered by level
// and paged by 20, the old hub's. On a phone each event is a card headed by its time (three columns do not fit a phone:
// the event went past the screen's edge). It re-runs when a failed event appears, is resent or discarded; what new
// events bring shows when the tab opens again.
import { DataTable, type DataTableColumn, StatusPill, type StatusPillTone } from '@erplora/ui/components';
import { useLive } from '@erplora/ui/sdk';
import { computed } from 'vue';

import { useBaseI18n } from '../lib/i18n';
import type { EventLogEntry } from '../operations';

const LEVELS = ['info', 'warning', 'error'] as const;
const TONE: Record<EventLogEntry['level'], StatusPillTone> = { info: 'neutral', warning: 'warning', error: 'danger' };

const { t, locale } = useBaseI18n();

const { data, status, refresh } = useLive('base.event.list', {});

const rows = computed<EventLogEntry[]>(() => data.value?.entries ?? []);
const failed = computed(() => status.value === 'error' && data.value === undefined);

const when = (iso: string) =>
  new Intl.DateTimeFormat(locale.value, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(iso));

const columns = computed<DataTableColumn<EventLogEntry>[]>(() => [
  { key: 'at', label: t('base.system.log.columns.at'), format: (_, row) => when(row.at), width: '11rem' },
  {
    key: 'level',
    label: t('base.system.log.columns.level'),
    cell: 'level',
    width: '8rem',
    sortValue: (row) => LEVELS.indexOf(row.level),
    filter: { type: 'select', options: LEVELS.map((value) => ({ value, label: t(`base.system.log.levels.${value}`) })) },
  },
  { key: 'event', label: t('base.system.log.columns.event'), cell: 'event', width: 'minmax(14rem,3fr)', sortable: false },
]);
</script>

<template>
  <section class="system-log">
    <h2>{{ t('base.system.log.heading') }}</h2>
    <DataTable
      :columns="columns"
      :rows="rows"
      :page-size="20"
      :page-size-options="[]"
      :views="['table', 'cards']"
      :card-title="(row: EventLogEntry) => when(row.at)"
      card-title-column="at"
      :search-keys="['name', 'app_name', 'detail']"
      :search-placeholder="t('base.system.log.search')"
      :empty-message="t('base.system.log.empty')"
      :loading="data === undefined && !failed"
      :error="failed ? t('base.system.log.error') : undefined"
      @retry="refresh()"
    >
      <template #level="{ row }">
        <StatusPill
          data-testid="system-log-level"
          size="sm"
          :tone="TONE[(row as EventLogEntry).level]"
          :label="t(`base.system.log.levels.${(row as EventLogEntry).level}`)"
        />
      </template>
      <template #event="{ row }">
        <div class="system-log-event">
          <span><code>{{ (row as EventLogEntry).name }}</code> · {{ (row as EventLogEntry).app_name }}</span>
          <span class="system-log-detail">{{ (row as EventLogEntry).detail }}</span>
        </div>
      </template>
    </DataTable>
  </section>
</template>

<style scoped>
.system-log {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.system-log h2 {
  margin: 0;
  font-size: 1.25rem;
  font-weight: 700;
}

.system-log-event {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  overflow-wrap: anywhere;
}

.system-log-detail {
  color: var(--ion-color-medium-shade, #555);
  font-size: 0.875rem;
}
</style>
