<script setup lang="ts">
// «When this happens…» (WORKBOOK FLOW-F10; the old editor's trigger node): the first card of the column
// says in one sentence when the automation starts and opens to choose it. Something happens — one of
// the events of this business (`flow.catalog.read`), in words, grouped by app and searchable, with
// «Only when…» on what it brings —; a schedule (every day, week or month at a time, in the business's
// time zone); once at a date and time; or only by hand. The server's refusals show by their field.
import { Combo, type ComboOption } from '@erplora/ui/components';
import { IonInput, IonSelect, IonSelectOption } from '@ionic/vue';
import { computed } from 'vue';

import { usePhrasing } from '../composables/usePhrasing';
import type { DataChoice } from '../lib/document';
import { describeTrigger, eventLabel } from '../lib/phrasing';
import type { CatalogOut, Condition, Step, Trigger, TriggerKind } from '../operations';
import ConditionRows from './ConditionRows.vue';

const props = defineProps<{
  modelValue: Trigger;
  open: boolean;
  catalog: CatalogOut | null;
  /** What the event brings, for «Only when…» (from a real one). */
  choices: readonly DataChoice[];
  steps: readonly Step[];
  /** The server's refusals by field (`trigger.event`, `trigger.at`, `trigger.time`, `trigger`). */
  errors: Readonly<Record<string, string>>;
}>();
const emit = defineEmits<{ 'update:modelValue': [value: Trigger]; toggle: [] }>();
const phrasing = usePhrasing();

const KINDS: readonly TriggerKind[] = ['event', 'schedule', 'at', 'manual'];
const trigger = computed(() => props.modelValue);

const events = computed<ComboOption[]>(() =>
  [...(props.catalog?.events ?? [])]
    .map((event) => ({ id: event.name, label: eventLabel(event.name, props.catalog, phrasing.value), hint: `${event.app_name} · ${event.name}`, app: event.app_name }))
    .sort((a, b) => a.app.localeCompare(b.app, phrasing.value.locale) || a.label.localeCompare(b.label, phrasing.value.locale))
    .map(({ id, label, hint }) => ({ id, label, hint })),
);

const chosenEvent = computed<ComboOption | null>(() => {
  const value = trigger.value;
  if (value.kind !== 'event' || !value.event) return null;
  return events.value.find((option) => option.id === value.event) ?? { id: value.event, label: eventLabel(value.event, props.catalog, phrasing.value) };
});

function setKind(kind: TriggerKind): void {
  if (kind === trigger.value.kind) return;
  if (kind === 'event') emit('update:modelValue', { kind, event: '' });
  else if (kind === 'schedule') emit('update:modelValue', { kind, every: 'day', time: '09:00' });
  else if (kind === 'at') emit('update:modelValue', { kind, at: '' });
  else emit('update:modelValue', { kind: 'manual' });
}

function setEvent(option: ComboOption | null): void {
  const value = trigger.value;
  if (value.kind !== 'event') return;
  emit('update:modelValue', { ...value, event: option?.id ?? '' });
}

function setFilter(filter: Condition): void {
  const value = trigger.value;
  if (value.kind !== 'event') return;
  emit('update:modelValue', { ...value, filter });
}

function setSchedule(change: { every?: 'day' | 'week' | 'month'; weekday?: number; day?: number; time?: string }): void {
  const value = trigger.value;
  if (value.kind !== 'schedule') return;
  const every = change.every ?? value.every;
  const next: Trigger = { kind: 'schedule', every, time: change.time ?? value.time };
  if (every === 'week') next.weekday = change.weekday ?? value.weekday ?? 0;
  if (every === 'month') next.day = change.day ?? value.day ?? 1;
  emit('update:modelValue', next);
}

/** The ISO instant as the date and time box shows it (the device's local time). */
const atLocal = computed(() => {
  const value = trigger.value;
  if (value.kind !== 'at' || !value.at) return '';
  const date = new Date(value.at);
  if (Number.isNaN(date.getTime())) return '';
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
});

function setAt(raw: string): void {
  const date = raw ? new Date(raw) : null;
  emit('update:modelValue', { kind: 'at', at: date && !Number.isNaN(date.getTime()) ? date.toISOString() : '' });
}

const generalError = computed(() => props.errors['trigger.at'] ?? props.errors['trigger.time'] ?? props.errors['trigger.filter'] ?? props.errors.trigger ?? '');
</script>

<template>
  <div
    class="flow-node flow-node--trigger"
    data-node="trigger"
  >
    <div class="flow-card">
      <button
        type="button"
        class="flow-card__open"
        :aria-expanded="open ? 'true' : 'false'"
        data-testid="flow-trigger-open"
        @click="emit('toggle')"
      >
        <span class="flow-card__eyebrow">{{ $t('flow.trigger.when') }}</span>
        <span class="flow-card__title">{{ describeTrigger(trigger, catalog, phrasing) }}</span>
      </button>
      <div
        v-if="open"
        class="flow-card__panel"
        data-testid="flow-trigger-panel"
      >
        <IonSelect
          data-testid="flow-trigger-kind"
          :value="trigger.kind"
          :label="$t('flow.trigger.kind')"
          label-placement="floating"
          fill="outline"
          mode="md"
          interface="popover"
          @ion-change="setKind($event.detail.value as TriggerKind)"
        >
          <IonSelectOption
            v-for="kind in KINDS"
            :key="kind"
            :value="kind"
          >
            {{ $t(`flow.trigger.kinds.${kind}`) }}
          </IonSelectOption>
        </IonSelect>

        <template v-if="trigger.kind === 'event'">
          <Combo
            testid="flow-trigger-event"
            :model-value="chosenEvent"
            :options="events"
            :label="$t('flow.trigger.chooseEvent')"
            :placeholder="$t('flow.trigger.searchEvent')"
            :error-text="errors['trigger.event']"
            :clearable="false"
            @update:model-value="setEvent"
          />
          <div class="flow-card__field">
            <span class="flow-card__label">{{ $t('flow.trigger.onlyWhen') }}</span>
            <span class="flow-card__hint">{{ $t('flow.trigger.onlyWhenHint') }}</span>
            <ConditionRows
              testid="flow-trigger-filter"
              :model-value="trigger.filter"
              :choices="choices"
              :steps="steps"
              :catalog="catalog"
              @update:model-value="setFilter"
            />
          </div>
        </template>

        <template v-else-if="trigger.kind === 'schedule'">
          <IonSelect
            data-testid="flow-trigger-every"
            :value="trigger.every"
            :label="$t('flow.trigger.every')"
            label-placement="floating"
            fill="outline"
            mode="md"
            interface="popover"
            @ion-change="setSchedule({ every: $event.detail.value })"
          >
            <IonSelectOption value="day">
              {{ $t('flow.trigger.everyDay') }}
            </IonSelectOption>
            <IonSelectOption value="week">
              {{ $t('flow.trigger.everyWeek') }}
            </IonSelectOption>
            <IonSelectOption value="month">
              {{ $t('flow.trigger.everyMonth') }}
            </IonSelectOption>
          </IonSelect>
          <IonSelect
            v-if="trigger.every === 'week'"
            data-testid="flow-trigger-weekday"
            :value="trigger.weekday ?? 0"
            :label="$t('flow.trigger.weekday')"
            label-placement="floating"
            fill="outline"
            mode="md"
            interface="popover"
            @ion-change="setSchedule({ weekday: Number($event.detail.value) })"
          >
            <IonSelectOption
              v-for="n in 7"
              :key="n"
              :value="n - 1"
            >
              {{ $t(`flow.trigger.weekdays.${n - 1}`) }}
            </IonSelectOption>
          </IonSelect>
          <IonInput
            v-if="trigger.every === 'month'"
            data-testid="flow-trigger-day"
            type="number"
            :min="1"
            :max="31"
            :value="trigger.day ?? 1"
            :label="$t('flow.trigger.monthDay')"
            :helper-text="$t('flow.trigger.monthDayHint')"
            label-placement="floating"
            fill="outline"
            mode="md"
            @ion-input="setSchedule({ day: Number($event.detail.value) || 1 })"
          />
          <IonInput
            data-testid="flow-trigger-time"
            type="time"
            :value="trigger.time"
            :label="$t('flow.trigger.time')"
            label-placement="floating"
            fill="outline"
            mode="md"
            @ion-input="setSchedule({ time: String($event.detail.value ?? '') })"
          />
        </template>

        <IonInput
          v-else-if="trigger.kind === 'at'"
          data-testid="flow-trigger-at"
          type="datetime-local"
          :value="atLocal"
          :label="$t('flow.trigger.at')"
          label-placement="floating"
          fill="outline"
          mode="md"
          @ion-input="setAt(String($event.detail.value ?? ''))"
        />

        <span
          v-if="generalError"
          class="flow-card__error"
          data-testid="flow-trigger-error"
        >{{ generalError }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped src="./spine.css"></style>
