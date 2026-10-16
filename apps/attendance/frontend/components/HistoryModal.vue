<script setup lang="ts">
// ATTENDANCE-F09: «Correction history» of a working day, the old history dialog. Every correction,
// newest first: who (or «System», for the one a termination makes), when, «Before» → «After» with the
// statuses and the «Reason». Read once when it opens (`attendance.correction.list`); nothing here can be
// edited or deleted.
import { FormModal } from '@erplora/ui/components';
import { useLiveClient } from '@erplora/ui/sdk';
import { IonButton, IonSpinner } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import { useLocale, useT } from '../composables/useT';
import { formatDay, localDateTime } from '../lib/time';
import type { CorrectionOut, RecordOut, RecordStatus } from '../operations';

const props = defineProps<{
  /** The day whose history is shown; `null` while no row asked. */
  record: RecordOut | null;
}>();

const open = defineModel<boolean>('open', { default: false });

const client = useLiveClient();
const t = useT();
const locale = useLocale();

const items = ref<CorrectionOut[]>([]);
const loading = ref(false);
const failed = ref(false);

watch(
  open,
  async (isOpen) => {
    const day = props.record;
    if (!isOpen || !day) return;
    items.value = [];
    failed.value = false;
    loading.value = true;
    try {
      const page = await client.api.call('attendance.correction.list', { record_id: day.id, limit: 100 });
      if (!Array.isArray(page?.rows)) throw new Error('attendance.correction.list answered without rows');
      if (props.record?.id === day.id) items.value = page.rows;
    } catch {
      failed.value = true;
    } finally {
      loading.value = false;
    }
  },
  { immediate: true },
);

const heading = computed(() => (props.record ? `${props.record.member_name} · ${formatDay(props.record.work_date, locale.value)}` : ''));

function span(start: string | null, end: string | null, status: RecordStatus): string {
  return `${localDateTime(start)} → ${localDateTime(end)} (${t(`attendance.status.${status}`)})`;
}
</script>

<template>
  <FormModal
    v-model:open="open"
    testid="attendance-history"
    :title="$t('attendance.history.title')"
  >
    <p class="attendance-history__day">
      {{ heading }}
    </p>
    <p
      v-if="loading"
      class="attendance-history__state"
      data-testid="attendance-history-loading"
    >
      <ion-spinner name="dots" />
      {{ $t('attendance.history.loading') }}
    </p>
    <p
      v-else-if="failed"
      class="attendance-history__state attendance-history__state--error"
      role="alert"
      data-testid="attendance-history-load-error"
    >
      {{ $t('attendance.history.loadError') }}
    </p>
    <p
      v-else-if="items.length === 0"
      class="attendance-history__state"
      data-testid="attendance-history-empty"
    >
      {{ $t('attendance.history.empty') }}
    </p>
    <ul
      v-else
      class="attendance-history__list"
      data-testid="attendance-history-list"
    >
      <li
        v-for="item in items"
        :key="item.id"
        data-testid="attendance-history-item"
      >
        <h3>
          {{ item.is_system ? $t('attendance.history.system') : item.created_by_name }} · {{ localDateTime(item.created_at) }}
        </h3>
        <p>{{ $t('attendance.history.before') }}: {{ span(item.old_clock_in_at, item.old_clock_out_at, item.old_status) }}</p>
        <p>{{ $t('attendance.history.after') }}: {{ span(item.new_clock_in_at, item.new_clock_out_at, item.new_status) }}</p>
        <p>{{ $t('attendance.history.reason') }}: {{ item.reason }}</p>
      </li>
    </ul>
    <template #footer="{ cancel }">
      <ion-button
        fill="outline"
        data-testid="attendance-history-close-button"
        @click="cancel"
      >
        {{ $t('attendance.history.close') }}
      </ion-button>
    </template>
  </FormModal>
</template>

<style scoped>
.attendance-history__day {
  margin: 0 0 12px;
  font-weight: 600;
}
.attendance-history__state {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  color: var(--ion-color-medium-shade, #5f5f5f);
}
.attendance-history__state--error {
  color: var(--ion-color-danger, #c5000f);
  font-weight: 600;
}
.attendance-history__list {
  list-style: none;
  margin: 0;
  padding: 0;
}
.attendance-history__list li {
  padding: 10px 0;
  border-bottom: 1px solid var(--ion-border-color, rgba(0, 0, 0, 0.08));
}
.attendance-history__list h3 {
  margin: 0 0 4px;
  font-size: 0.95rem;
}
.attendance-history__list p {
  margin: 2px 0;
  font-size: 0.9rem;
  font-variant-numeric: tabular-nums;
}
</style>
