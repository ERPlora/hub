<script setup lang="ts">
// STAFF-G05: the old Home panel «Today's time off» (STAFF-F20) above the time-off list, as Attendance
// shows «Clocked in now» above its records, while the Hub's Home has no panels: who has an approved
// absence covering today in the business's day, whole days first and then by name (the server's order),
// with its type and, for part of the day, its hours — never the reason. Live (`staff.time_off.today`).
import { useLive } from '@erplora/ui/sdk';
import { IonSpinner } from '@ionic/vue';

import { useT } from '../composables/useT';
import { formatTime } from '../lib/format';
import type { TimeOffOut } from '../operations';

const t = useT();
const { data, status } = useLive('staff.time_off.today', { limit: 100 });

function when(row: TimeOffOut): string {
  return row.is_full_day ? t('staff.awayToday.allDay') : `${formatTime(row.start_time)}–${formatTime(row.end_time)}`;
}
</script>

<template>
  <section
    class="staff-away-today"
    data-testid="staff-away-today"
  >
    <header class="staff-away-today__header">
      <h2>{{ $t('staff.awayToday.title') }}</h2>
      <span
        v-if="data && data.total > 0"
        class="staff-away-today__count"
        data-testid="staff-away-today-count"
      >{{ $t('staff.awayToday.count', { n: data.total }, data.total) }}</span>
    </header>
    <p
      v-if="status === 'error' && !data"
      class="staff-away-today__state staff-away-today__state--error"
      role="alert"
      data-testid="staff-away-today-error"
    >
      {{ $t('staff.awayToday.loadError') }}
    </p>
    <p
      v-else-if="!data"
      class="staff-away-today__state"
    >
      <ion-spinner name="dots" />
    </p>
    <p
      v-else-if="data.rows.length === 0"
      class="staff-away-today__state"
      data-testid="staff-away-today-empty"
    >
      {{ $t('staff.awayToday.empty') }}
    </p>
    <ul
      v-else
      class="staff-away-today__list"
    >
      <li
        v-for="row in data.rows"
        :key="row.id"
        class="staff-away-today__row"
        data-testid="staff-away-today-row"
      >
        <strong>{{ row.member_name }}</strong>
        <!-- The leading space keeps the words apart for a screen reader, not only for the eye. -->
        <span class="staff-away-today__what">{{ ` ${$t(`staff.leaveType.${row.leave_type}`)} · ${when(row)}` }}</span>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.staff-away-today {
  margin-bottom: 12px;
  padding: 12px 16px;
  border: 1px solid var(--ion-border-color, rgba(0, 0, 0, 0.12));
  border-radius: 12px;
  background: var(--ion-card-background, var(--ion-background-color, #fff));
}
.staff-away-today__header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
}
.staff-away-today__header h2 {
  margin: 0;
  font-size: 1rem;
  font-weight: 600;
}
.staff-away-today__count {
  color: var(--ion-color-medium-shade, #5f5f5f);
  font-size: 0.875rem;
  white-space: nowrap;
}
.staff-away-today__state {
  margin: 8px 0 0;
  color: var(--ion-color-medium-shade, #5f5f5f);
  font-size: 0.875rem;
}
.staff-away-today__state--error {
  color: var(--ion-color-danger, #c5000f);
}
.staff-away-today__list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 20px;
  margin: 8px 0 0;
  padding: 0;
  list-style: none;
}
.staff-away-today__row {
  min-width: 0;
  overflow-wrap: anywhere;
}
.staff-away-today__what {
  color: var(--ion-color-medium-shade, #5f5f5f);
}
</style>
