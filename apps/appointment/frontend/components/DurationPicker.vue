<script setup lang="ts">
import { IonInput } from '@ionic/vue';
import { nextTick, ref, useId, useTemplateRef, watch } from 'vue';

import ChoiceButton from './ChoiceButton.vue';

const PRESETS = [15, 30, 45, 60, 90, 120];

const props = withDefaults(
  defineProps<{
    /** The length the panel holds, in minutes (`''` before any service). */
    minutes: string;
    /** The services' sum, in minutes (`''` before any service). */
    sum: string;
    /** The person changed the length: it no longer follows the services. */
    touched: boolean;
    disabled?: boolean;
    errorText?: string;
    /** The form's key for the length, handed to its field. */
    name?: string;
  }>(),
  { disabled: false, errorText: undefined, name: undefined },
);
const emit = defineEmits<{ type: [minutes: string]; useSum: [] }>();

const labelId = useId();
const field = useTemplateRef<InstanceType<typeof IonInput>>('field');
/** «Other» is open: the length is typed. It stays open while the person types, even through a button's number. */
const other = ref(false);

const isCustom = (value: string): boolean => value !== '' && !PRESETS.includes(Number(value));

watch(
  () => props.minutes,
  (value) => {
    if (!props.touched) other.value = isCustom(value);
    else if (isCustom(value)) other.value = true;
  },
  { immediate: true },
);
watch(
  () => props.errorText,
  (reason) => {
    if (reason) other.value = true;
  },
  { immediate: true },
);

function choose(minutes: number): void {
  other.value = false;
  emit('type', String(minutes));
}

async function openOther(): Promise<void> {
  other.value = true;
  await nextTick();
  void (field.value?.$el as { setFocus?: () => Promise<void> } | undefined)?.setFocus?.();
}

function useSum(): void {
  other.value = false;
  emit('useSum');
}

const text = (value: unknown): string => (value === null || value === undefined ? '' : String(value));
</script>

<template>
  <div
    class="duration-picker"
    data-testid="appointment-form-duration"
  >
    <div class="duration-picker__head">
      <span
        :id="labelId"
        class="duration-picker__label"
      >{{ $t('appointment.form.minutes') }}</span>
      <span
        v-if="sum"
        class="duration-picker__sum"
      >
        <span data-testid="appointment-form-duration-sum">{{ $t('appointment.form.durationSum', { n: sum }) }}</span>
        <button
          v-if="minutes !== sum"
          type="button"
          class="duration-picker__use-sum"
          data-testid="appointment-form-duration-use-sum"
          :disabled="disabled"
          @click="useSum"
        >
          {{ $t('appointment.form.useSum') }}
        </button>
      </span>
    </div>
    <div
      class="duration-picker__choices"
      role="group"
      :aria-labelledby="labelId"
    >
      <ChoiceButton
        v-for="preset in PRESETS"
        :key="preset"
        :pressed="!other && Number(minutes) === preset"
        :disabled="disabled"
        :aria-label="$t('appointment.form.durationValue', { n: preset })"
        :data-testid="`appointment-form-duration-${preset}`"
        @click="choose(preset)"
      >
        {{ preset }}
      </ChoiceButton>
      <ChoiceButton
        :pressed="other"
        :disabled="disabled"
        :aria-label="$t('appointment.form.durationOtherLabel')"
        data-testid="appointment-form-duration-other"
        @click="openOther"
      >
        {{ $t('appointment.form.durationOther') }}
      </ChoiceButton>
    </div>
    <ion-input
      v-if="other"
      ref="field"
      data-testid="appointment-form-minutes"
      type="number"
      inputmode="numeric"
      min="1"
      :value="minutes"
      :label="$t('appointment.form.minutes')"
      label-placement="floating"
      fill="outline"
      mode="md"
      :disabled="disabled"
      :name="name"
      :error-text="errorText"
      :class="{ 'ion-invalid': !!errorText, 'ion-touched': !!errorText }"
      @ion-input="emit('type', text($event.detail.value))"
    />
  </div>
</template>

<style scoped>
.duration-picker {
  display: grid;
  gap: 8px;
  container-type: inline-size;
}
.duration-picker__head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0 8px;
  min-height: 24px;
}
.duration-picker__label {
  flex: 1 1 auto;
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--ep-text-muted, #646b78);
}
.duration-picker__sum {
  display: inline-flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: 0 8px;
  margin-inline-start: auto;
  font-size: 0.8rem;
  color: var(--ep-text-muted, #646b78);
  font-variant-numeric: tabular-nums;
}
/* A finger-sized target that does not push the buttons down. */
.duration-picker__use-sum {
  min-height: 44px;
  margin: -10px 0;
  padding: 0 4px;
  border: 0;
  background: transparent;
  color: var(--ep-primary-text, #0b5f8a);
  font: inherit;
  font-size: 0.8rem;
  font-weight: 600;
  text-decoration: underline;
  cursor: pointer;
}
.duration-picker__use-sum:focus-visible {
  outline: none;
  box-shadow: var(--ep-focus-ring);
}
.duration-picker__choices {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 6px;
}
/* All seven in a row only where «Other» fits whole beside the numbers. */
@container (min-width: 440px) {
  .duration-picker__choices {
    grid-template-columns: repeat(7, minmax(0, 1fr));
  }
}
</style>
