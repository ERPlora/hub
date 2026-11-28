<script setup lang="ts">
// One value composed of text the owner types and data they pick (WORKBOOK FLOW-F11; the old module's
// `erp-flows-value`). A picked datum is a pill with the words it was chosen by — the path that makes it
// work exists only in the value —; every piece of text is its own box, so a typo in the middle of a
// sentence is fixed without rebuilding the line; there is no expression mode. «Insert data» asks the
// editor's one picker (`pick`) and adds what it answers at the end. A datum that takes a closed list (a task's
// priority, `options`) is chosen by the words of its values instead, or is one datum inserted in its place.
import { HubIcon } from '@erplora/ui/shell';
import { IonSelect, IonSelectOption } from '@ionic/vue';
import { computed } from 'vue';

import { usePhrasing } from '../composables/usePhrasing';
import { partsToValue, type ValuePart, valueToParts } from '../lib/document';
import { pathLabel } from '../lib/phrasing';
import type { CatalogOut, Step } from '../operations';

const props = defineProps<{
  modelValue: unknown;
  label: string;
  /** Prefix of the hooks: `<testid>-label`, `-text-<n>`, `-pill-<i>`, `-unpill-<i>`, `-insert`, `-error`. */
  testid: string;
  steps: readonly Step[];
  catalog: CatalogOut | null;
  /** Opens the picker; the chosen path, or `null` when it was closed. */
  pick: () => Promise<string | null>;
  helper?: string;
  errorText?: string;
  required?: boolean;
  /** The values of a closed list, with their words: chosen, never typed. */
  options?: readonly { value: string; label: string }[];
}>();

const emit = defineEmits<{ 'update:modelValue': [value: unknown] }>();
const phrasing = usePhrasing();

/** A closed list that is empty or holds one of its values is chosen; a datum inserted, or a value it does not
 *  have (to be corrected), is a value as any other. */
const choosing = computed(
  () => !!props.options?.length && (props.modelValue === '' || props.modelValue == null || props.options.some((option) => option.value === String(props.modelValue))),
);

/** Text, pill, text, pill, …, text: a box before, between and after every pill. */
const segments = computed<ValuePart[]>(() => {
  const out: ValuePart[] = [];
  for (const part of valueToParts(props.modelValue)) {
    if (part.kind === 'field' && out.at(-1)?.kind !== 'text') out.push({ kind: 'text', text: '' });
    out.push(part);
  }
  if (out.at(-1)?.kind !== 'text') out.push({ kind: 'text', text: '' });
  return out;
});

/** The position of each text box among the text boxes (its hook). */
const textIndex = computed(() => {
  let n = 0;
  return segments.value.map((part) => (part.kind === 'text' ? n++ : -1));
});

function send(parts: ValuePart[]): void {
  const kept: ValuePart[] = [];
  for (const part of parts) {
    if (part.kind === 'text' && kept.at(-1)?.kind === 'text') {
      kept[kept.length - 1] = { kind: 'text', text: (kept.at(-1) as { text: string }).text + part.text };
    } else kept.push(part);
  }
  emit('update:modelValue', partsToValue(kept.filter((part) => part.kind === 'field' || part.text !== '')));
}

function type(index: number, text: string): void {
  send(segments.value.map((part, i) => (i === index ? { kind: 'text', text } : part)));
}

function unpill(index: number): void {
  send(segments.value.filter((_, i) => i !== index));
}

async function insert(): Promise<void> {
  const path = await props.pick();
  if (path) send(choosing.value ? [{ kind: 'field', path }] : [...segments.value, { kind: 'field', path }]);
}
</script>

<template>
  <div
    class="flow-value"
    :data-testid="testid"
  >
    <span
      class="flow-value__label"
      :data-testid="`${testid}-label`"
    >{{ label }}<span
      v-if="required"
      class="flow-value__required"
    > · {{ $t('flow.steps.required') }}</span></span>
    <div
      class="flow-value__box"
      :class="{ 'flow-value__box--invalid': !!errorText }"
    >
      <IonSelect
        v-if="choosing"
        class="flow-value__choice"
        :data-testid="`${testid}-choice`"
        :value="modelValue == null ? '' : String(modelValue)"
        :aria-label="label"
        :placeholder="$t('flow.steps.chooseValue')"
        interface="popover"
        @ion-change="emit('update:modelValue', String($event.detail.value))"
      >
        <IonSelectOption
          v-for="option in options"
          :key="option.value"
          :value="option.value"
        >
          {{ option.label }}
        </IonSelectOption>
      </IonSelect>
      <template
        v-for="(part, index) in choosing ? [] : segments"
        :key="index"
      >
        <input
          v-if="part.kind === 'text'"
          class="flow-value__text"
          type="text"
          :aria-label="label"
          :data-testid="`${testid}-text-${textIndex[index]}`"
          :value="part.text"
          @input="type(index, ($event.target as HTMLInputElement).value)"
        >
        <span
          v-else
          class="flow-value__pill"
        >
          <span :data-testid="`${testid}-pill-${index}`">{{ pathLabel(part.path, steps, catalog, phrasing) }}</span>
          <button
            type="button"
            class="flow-value__unpill"
            :aria-label="$t('flow.steps.removeData')"
            :data-testid="`${testid}-unpill-${index}`"
            @click="unpill(index)"
          >
            <HubIcon name="ion:close-outline" />
          </button>
        </span>
      </template>
    </div>
    <div class="flow-value__foot">
      <button
        type="button"
        class="flow-value__insert"
        :data-testid="`${testid}-insert`"
        @click="insert"
      >
        <HubIcon name="ion:add-outline" />{{ $t('flow.steps.insert') }}
      </button>
      <span
        v-if="helper"
        class="flow-value__helper"
      >{{ helper }}</span>
    </div>
    <span
      v-if="errorText"
      class="flow-value__error"
      :data-testid="`${testid}-error`"
    >{{ errorText }}</span>
  </div>
</template>

<style scoped>
.flow-value {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  min-width: 0;
}
.flow-value__label {
  font-size: 0.78rem;
  color: var(--ep-muted, var(--ion-color-medium));
}
.flow-value__required {
  font-style: italic;
}
.flow-value__box {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.3rem;
  min-height: 2.6rem;
  padding: 0.3rem 0.45rem;
  border: 1px solid var(--ep-border, var(--ion-border-color, #d7d5cc));
  border-radius: 10px;
  background: var(--ep-surface, var(--ion-card-background, #fff));
}
.flow-value__box:focus-within {
  border-color: var(--ion-color-primary);
}
.flow-value__box--invalid {
  border-color: var(--ion-color-danger);
}
.flow-value__choice {
  flex: 1 1 10rem;
  min-width: 6rem;
  min-height: 2rem;
}
.flow-value__text {
  flex: 1 1 10rem;
  min-width: 6rem;
  border: 0;
  outline: none;
  background: transparent;
  font: inherit;
  color: inherit;
  padding: 0.25rem 0;
}
.flow-value__pill {
  display: inline-flex;
  align-items: center;
  gap: 0.2rem;
  max-width: 100%;
  padding: 0.15rem 0.2rem 0.15rem 0.6rem;
  border-radius: 999px;
  background: color-mix(in srgb, var(--ion-color-primary) 14%, transparent);
  color: var(--ion-color-primary-shade, var(--ion-color-primary));
  font-size: 0.85rem;
  font-weight: 600;
}
.flow-value__unpill,
.flow-value__insert {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  border: 0;
  background: transparent;
  color: inherit;
  font: inherit;
  cursor: pointer;
  min-height: 2rem;
}
.flow-value__unpill {
  min-width: 2rem;
  justify-content: center;
  border-radius: 999px;
}
.flow-value__foot {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
}
.flow-value__insert {
  font-size: 0.82rem;
  color: var(--ion-color-primary);
  padding: 0 0.2rem;
}
.flow-value__helper {
  font-size: 0.78rem;
  color: var(--ep-muted, var(--ion-color-medium));
}
.flow-value__error {
  font-size: 0.78rem;
  color: var(--ion-color-danger);
}
</style>
