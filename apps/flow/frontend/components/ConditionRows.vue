<script setup lang="ts">
// The comparisons of «Only continue if…» and of the trigger's «Only when…» (WORKBOOK FLOW-F10, F11): one
// row per comparison — Data, Is, Value — and every one must hold. The data are chosen from what the
// automation has (`choices`), never typed; «present» asks yes or no; «one of» takes values separated
// by commas; a number or a yes/no typed is sent as one. A row without its data does not count yet.
import { HubIcon } from '@erplora/ui/shell';
import { IonButton, IonInput, IonSelect, IonSelectOption } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import { usePhrasing } from '../composables/usePhrasing';
import { type ConditionRow, conditionRows, type DataChoice, OPERATORS, partsToValue, rowsToCondition } from '../lib/document';
import { pathLabel } from '../lib/phrasing';
import type { CatalogOut, Condition, Operator, Step } from '../operations';

const props = defineProps<{
  modelValue: Condition | undefined;
  choices: readonly DataChoice[];
  steps: readonly Step[];
  catalog: CatalogOut | null;
  /** Prefix of the hooks: `<testid>-row-<n>`, `-path-<n>`, `-op-<n>`, `-value-<n>`, `-remove-<n>`, `-add`. */
  testid: string;
}>();
const emit = defineEmits<{ 'update:modelValue': [value: Condition] }>();
const phrasing = usePhrasing();

const rows = ref<ConditionRow[]>(conditionRows(props.modelValue));
watch(
  () => props.modelValue,
  (now) => {
    if (JSON.stringify(now ?? {}) !== JSON.stringify(rowsToCondition(rows.value))) rows.value = conditionRows(now);
  },
);

/** The data offered: the choices, and the one a row already reads if it is not among them. */
const paths = computed(() => {
  const offered = props.choices.map((choice) => choice.path);
  for (const row of rows.value) if (row.path && !offered.includes(row.path)) offered.push(row.path);
  return offered;
});

function scalar(text: string): unknown {
  return partsToValue([{ kind: 'text', text }]);
}

function send(next: ConditionRow[]): void {
  rows.value = next;
  emit('update:modelValue', rowsToCondition(next));
}

function patch(index: number, change: Partial<ConditionRow>): void {
  send(rows.value.map((row, i) => (i === index ? { ...row, ...change } : row)));
}

function setOp(index: number, op: Operator): void {
  const row = rows.value[index];
  let value = row.value;
  if (op === 'exists') value = true;
  else if (row.op === 'exists') value = '';
  else if (op === 'in' && !Array.isArray(value)) value = value === '' ? [] : [value];
  else if (op !== 'in' && Array.isArray(value)) value = value[0] ?? '';
  patch(index, { op, value });
}

function setText(index: number, text: string): void {
  const row = rows.value[index];
  const value = row.op === 'in' ? text.split(',').map((part) => part.trim()).filter(Boolean).map(scalar) : scalar(text);
  patch(index, { value });
}

function shown(row: ConditionRow): string {
  if (Array.isArray(row.value)) return row.value.join(', ');
  return row.value === undefined || row.value === null ? '' : String(row.value);
}

function add(): void {
  rows.value = [...rows.value, { path: '', op: 'eq', value: '' }];
}

function remove(index: number): void {
  send(rows.value.filter((_, i) => i !== index));
}
</script>

<template>
  <div class="flow-conditions">
    <div
      v-for="(row, index) in rows"
      :key="index"
      class="flow-conditions__row"
      :data-testid="`${testid}-row-${index}`"
    >
      <IonSelect
        :data-testid="`${testid}-path-${index}`"
        :value="row.path"
        :label="$t('flow.steps.data')"
        label-placement="floating"
        fill="outline"
        mode="md"
        interface="popover"
        @ion-change="patch(index, { path: String($event.detail.value) })"
      >
        <IonSelectOption
          v-for="path in paths"
          :key="path"
          :value="path"
        >
          {{ pathLabel(path, steps, catalog, phrasing) }}
        </IonSelectOption>
      </IonSelect>
      <IonSelect
        :data-testid="`${testid}-op-${index}`"
        :value="row.op"
        :label="$t('flow.steps.is')"
        label-placement="floating"
        fill="outline"
        mode="md"
        interface="popover"
        @ion-change="setOp(index, $event.detail.value as Operator)"
      >
        <IonSelectOption
          v-for="op in OPERATORS"
          :key="op"
          :value="op"
        >
          {{ $t(`flow.steps.operators.${op}`) }}
        </IonSelectOption>
      </IonSelect>
      <div class="flow-conditions__value">
        <IonSelect
          v-if="row.op === 'exists'"
          :data-testid="`${testid}-value-${index}`"
          :value="String(row.value)"
          :label="$t('flow.steps.value')"
          label-placement="floating"
          fill="outline"
          mode="md"
          interface="popover"
          @ion-change="patch(index, { value: $event.detail.value === 'true' })"
        >
          <IonSelectOption value="true">
            {{ $t('flow.steps.yes') }}
          </IonSelectOption>
          <IonSelectOption value="false">
            {{ $t('flow.steps.no') }}
          </IonSelectOption>
        </IonSelect>
        <IonInput
          v-else
          :data-testid="`${testid}-value-${index}`"
          :value="shown(row)"
          :label="$t('flow.steps.value')"
          label-placement="floating"
          fill="outline"
          mode="md"
          @ion-input="setText(index, String($event.detail.value ?? ''))"
        />
        <span
          v-if="row.op === 'in'"
          class="flow-conditions__hint"
          :data-testid="`${testid}-hint-${index}`"
        >{{ $t('flow.steps.inHint') }}</span>
      </div>
      <IonButton
        fill="clear"
        color="medium"
        :data-testid="`${testid}-remove-${index}`"
        @click="remove(index)"
      >
        <HubIcon
          name="ion:close-outline"
          :label="$t('flow.steps.removeCondition')"
        />
      </IonButton>
    </div>
    <IonButton
      size="small"
      fill="outline"
      mode="md"
      :data-testid="`${testid}-add`"
      @click="add"
    >
      <HubIcon name="ion:add-outline" />{{ $t('flow.steps.addCondition') }}
    </IonButton>
  </div>
</template>

<style scoped>
.flow-conditions {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  align-items: stretch;
}
.flow-conditions > ion-button {
  align-self: flex-start;
}
.flow-conditions__row {
  display: grid;
  grid-template-columns: 1fr;
  gap: 0.4rem;
  align-items: start;
  padding-bottom: 0.5rem;
  border-bottom: 1px solid var(--ep-border-soft, rgba(0, 0, 0, 0.06));
}
@media (min-width: 560px) {
  .flow-conditions__row {
    grid-template-columns: 1.2fr 0.9fr 1.2fr auto;
  }
}
.flow-conditions__value {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}
.flow-conditions__hint {
  font-size: 0.78rem;
  color: var(--ep-muted, var(--ion-color-medium));
}
</style>
