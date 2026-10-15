<script setup lang="ts">
// Schedules → Settings (SCHEDULE-F08, F09; WORKBOOK «Pantallas · Ajustes»): on top, read only, «Business
// timezone» with its name and the note (it is the Hub's: in phase 1, Madrid's); below, «Week starts»
// (Monday or Sunday; another stored day is offered too) and «Save» (`schedule.settings.update`) for
// whoever may change the settings. «Week starts» only shows once the settings were read: a value never
// read would be the default dressed as the business's choice. A refused save is said above the form.
import { InlineFeedback } from '@erplora/ui/components';
import { useCommand, useLive } from '@erplora/ui/sdk';
import { AppPage, useSession } from '@erplora/ui/shell';
import { IonButton, IonSelect, IonSelectOption } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import PageNotices, { blockingError } from '../components/PageNotices.vue';
import { scheduleTabs } from '../tabs';

const session = useSession();
const canManage = computed(() => session.can('schedule.manage_settings'));

const { data: settings, status, error, refresh } = useLive('schedule.settings.get', {});
const saving = useCommand('schedule.settings.update');

const blocked = computed(() => blockingError(error.value));
const loadFailed = computed(() => status.value === 'error' && !blocked.value && !settings.value);

/** «Week starts» as chosen on screen (ISO: 1 = Monday … 7 = Sunday). */
const weekStartsOn = ref<number | null>(null);
const saved = ref(false);

watch(
  settings,
  (now) => {
    if (now) weekStartsOn.value = now.week_starts_on;
  },
  { immediate: true },
);

/** Monday and Sunday, as the old screen; another stored day (from the API) stays offered. */
const options = computed(() => {
  const days = [1, 7];
  const stored = settings.value?.week_starts_on;
  if (stored && !days.includes(stored)) days.push(stored);
  return days;
});

function choose(value: unknown): void {
  weekStartsOn.value = Number(value);
  saved.value = false;
}

async function save(): Promise<void> {
  if (weekStartsOn.value === null || saving.pending.value) return;
  saved.value = false;
  try {
    await saving.run({ week_starts_on: weekStartsOn.value });
    saved.value = true;
  } catch {
    // The page paints the error; what was chosen stays.
  }
}

/** The day's name: ISO 1 = Monday … 7 = Sunday, the catalogue counts Monday = 0. */
const dayKey = (iso: number): string => `schedule.days.${iso - 1}`;
const saveError = computed(() => {
  const failure = saving.error.value;
  if (!failure) return '';
  return Object.values(failure.fields ?? {})[0] ?? failure.message;
});
</script>

<template>
  <AppPage
    :title="$t('schedule.title')"
    :tabs="scheduleTabs($t)"
    :tabs-label="$t('schedule.tabs.label')"
  >
    <PageNotices
      testid="schedule-settings"
      :status="status"
      :error="error"
    />
    <template v-if="!blocked">
      <InlineFeedback
        v-if="loadFailed"
        tone="danger"
        data-testid="schedule-settings-load-error"
        :heading="$t('schedule.settings.loadError')"
      >
        {{ error?.message }}
        <template #actions>
          <ion-button
            size="small"
            fill="outline"
            data-testid="schedule-settings-retry"
            @click="refresh()"
          >
            {{ $t('schedule.live.retry') }}
          </ion-button>
        </template>
      </InlineFeedback>
      <p
        v-else-if="!settings"
        class="schedule-settings__hint"
        data-testid="schedule-settings-loading"
      >
        {{ $t('schedule.loading') }}
      </p>
      <template v-else>
        <section
          class="schedule-settings__zone"
          data-testid="schedule-settings-timezone"
        >
          <div class="schedule-settings__kv">
            <span class="schedule-settings__key">{{ $t('schedule.settings.timezone') }}</span>
            <code>{{ settings.timezone }}</code>
          </div>
          <p class="schedule-settings__hint">
            {{ $t('schedule.settings.timezoneNote') }}
          </p>
        </section>
        <InlineFeedback
          v-if="saveError"
          tone="danger"
          data-testid="schedule-settings-save-error"
        >
          {{ saveError }}
        </InlineFeedback>
        <form
          class="schedule-settings__form"
          @submit.prevent="save"
        >
          <ion-select
            data-testid="schedule-settings-week-start"
            :value="weekStartsOn"
            :label="$t('schedule.settings.weekStarts')"
            label-placement="floating"
            fill="outline"
            mode="md"
            interface="popover"
            :disabled="!canManage"
            @ion-change="choose($event.detail.value)"
          >
            <ion-select-option
              v-for="day in options"
              :key="day"
              :value="day"
            >
              {{ $t(dayKey(day)) }}
            </ion-select-option>
          </ion-select>
          <ion-button
            v-if="canManage"
            data-testid="schedule-settings-submit"
            :disabled="saving.pending.value"
            @click="save"
          >
            {{ $t('schedule.save') }}
          </ion-button>
          <span
            v-if="saved"
            class="schedule-settings__saved"
            data-testid="schedule-settings-saved"
          >{{ $t('schedule.settings.saved') }}</span>
        </form>
      </template>
    </template>
  </AppPage>
</template>

<style scoped>
.schedule-settings__zone {
  display: grid;
  gap: 0.5rem;
  margin-bottom: 1rem;
}
.schedule-settings__kv {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  align-items: baseline;
}
.schedule-settings__key {
  font-weight: 600;
}
.schedule-settings__hint {
  margin: 0;
  color: var(--ion-color-medium-shade, #5f5f5f);
  font-size: 0.85rem;
}
.schedule-settings__form {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.75rem;
  max-width: 32rem;
}
.schedule-settings__form ion-select {
  flex: 1 1 12rem;
}
.schedule-settings__saved {
  color: var(--ion-color-success-shade, #2b8a3e);
  font-size: 0.85rem;
}
</style>
