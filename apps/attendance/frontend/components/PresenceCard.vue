<script setup lang="ts">
// ATTENDANCE-F11: «Clocked in now» above the team's records: how many people have their day open and who,
// since when and whether they are on a break; the Home's panel of the same name counts them (apps.py `widgets`).
// Live (`attendance.presence.list`); a day waiting for review does not count (the server leaves it out).
import { StatusPill } from '@erplora/ui/components';
import { useLive } from '@erplora/ui/sdk';
import { IonSpinner } from '@ionic/vue';

import { formatTime } from '../lib/time';

const { data, status } = useLive('attendance.presence.list', { limit: 100 });
</script>

<template>
  <section
    class="attendance-presence"
    data-testid="attendance-presence"
  >
    <header class="attendance-presence__header">
      <h2>{{ $t('attendance.presence.title') }}</h2>
      <span
        v-if="data"
        class="attendance-presence__count"
        data-testid="attendance-presence-count"
      >{{ $t('attendance.presence.count', { n: data.total }) }}</span>
    </header>
    <p
      v-if="status === 'error' && !data"
      class="attendance-presence__state attendance-presence__state--error"
      role="alert"
      data-testid="attendance-presence-error"
    >
      {{ $t('attendance.presence.loadError') }}
    </p>
    <p
      v-else-if="!data"
      class="attendance-presence__state"
    >
      <ion-spinner name="dots" />
    </p>
    <p
      v-else-if="data.rows.length === 0"
      class="attendance-presence__state"
      data-testid="attendance-presence-empty"
    >
      {{ $t('attendance.presence.empty') }}
    </p>
    <ul
      v-else
      class="attendance-presence__list"
    >
      <li
        v-for="row in data.rows"
        :key="row.record_id"
        class="attendance-presence__row"
        data-testid="attendance-presence-row"
      >
        <strong>{{ row.member_name }}</strong>
        <!-- The leading spaces keep the words apart for a screen reader, not only for the eye. -->
        <span class="attendance-presence__since">{{ ` ${$t('attendance.presence.since', { time: formatTime(row.clock_in_at) })}` }}</span>
        <template v-if="row.break_started_at">
          {{ ' ' }}<StatusPill
            size="sm"
            tone="warning"
            :label="$t('attendance.presence.onBreak')"
          />
        </template>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.attendance-presence {
  margin-bottom: 12px;
  padding: 12px 16px;
  border: 1px solid var(--ion-border-color, rgba(0, 0, 0, 0.12));
  border-radius: 12px;
  background: var(--ion-card-background, var(--ion-background-color, #fff));
}
.attendance-presence__header {
  display: flex;
  align-items: baseline;
  gap: 12px;
}
.attendance-presence__header h2 {
  margin: 0;
  font-size: 1rem;
}
.attendance-presence__count {
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}
.attendance-presence__state {
  margin: 8px 0 0;
  color: var(--ion-color-medium-shade, #5f5f5f);
}
.attendance-presence__state--error {
  color: var(--ion-color-danger, #c5000f);
}
.attendance-presence__list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  list-style: none;
  margin: 8px 0 0;
  padding: 0;
}
.attendance-presence__row {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--ion-color-success, #2dd36f) 10%, transparent);
  font-size: 0.9rem;
}
.attendance-presence__since {
  color: var(--ion-color-medium-shade, #5f5f5f);
  font-variant-numeric: tabular-nums;
}
</style>
