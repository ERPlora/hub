<script setup lang="ts">
// The three suggestions of one payment method on the Settings screen (TIP-F01), under its name: each one «%» or
// «Amount» and its value — a whole percentage, or an amount in the platform's money field — with what is wrong with it
// said under it. It edits a copy: every change gives the method back whole (`update:method`).
import { MoneyInput } from '@erplora/ui/components';
import { IonCol, IonGrid, IonInput, IonRow, IonSelect, IonSelectOption } from '@ionic/vue';

import { useBusinessMoney } from '../../../../base/frontend/lib/money';
import type { MethodFields, SuggestionField, SuggestionKind } from '../lib/suggestions';

const props = defineProps<{
  method: MethodFields;
  /** What is wrong, by `<method_id>.<position>`: a key of the catalogue. */
  errors: Readonly<Record<string, string>>;
  disabled: boolean;
}>();

const emit = defineEmits<{ 'update:method': [method: MethodFields] }>();

const KINDS: readonly SuggestionKind[] = ['percent', 'amount'];
const money = useBusinessMoney();

function change(index: number, next: Partial<SuggestionField>): void {
  const suggestions = props.method.suggestions.map((field, at) => (at === index ? { ...field, ...next } : field));
  emit('update:method', { ...props.method, suggestions });
}

const errorOf = (index: number): string | undefined => props.errors[`${props.method.method_id}.${index}`];
const testid = (index: number, part: string): string => `tip-settings-${props.method.method_id}-${index}-${part}`;
</script>

<template>
  <section
    class="settings-card__field"
    :data-testid="`tip-settings-method-${method.method_id}`"
  >
    <p class="settings-card__label">
      {{ method.method_name }}
    </p>
    <ion-grid class="ion-no-padding">
      <ion-row
        v-for="(field, index) in method.suggestions"
        :key="index"
        class="ion-align-items-start ion-margin-bottom"
      >
        <ion-col
          size="4"
          class="ion-padding-end"
        >
          <ion-select
            :data-testid="testid(index, 'kind')"
            :label="$t('tip.settings.kind.short')"
            label-placement="stacked"
            :aria-label="$t('tip.settings.kind.label', { n: index + 1 })"
            fill="outline"
            mode="md"
            interface="popover"
            :value="field.kind"
            :disabled="disabled"
            @ion-change="change(index, { kind: $event.detail.value === 'amount' ? 'amount' : 'percent' })"
          >
            <ion-select-option
              v-for="kind in KINDS"
              :key="kind"
              :value="kind"
            >
              {{ $t(`tip.settings.kind.${kind}`) }}
            </ion-select-option>
          </ion-select>
        </ion-col>
        <ion-col size="8">
          <ion-input
            v-if="field.kind === 'percent'"
            :data-testid="testid(index, 'value')"
            :label="$t('tip.settings.suggestion', { n: index + 1 })"
            label-placement="stacked"
            fill="outline"
            mode="md"
            inputmode="numeric"
            :value="field.text"
            :disabled="disabled"
            :error-text="errorOf(index) ? $t(errorOf(index) as string) : undefined"
            :class="{ 'ion-invalid': !!errorOf(index), 'ion-touched': !!errorOf(index) }"
            @ion-input="change(index, { text: String($event.detail.value ?? '') })"
          />
          <MoneyInput
            v-else
            :model-value="field.text"
            :testid="testid(index, 'value')"
            :label="$t('tip.settings.suggestion', { n: index + 1 })"
            :money="money"
            :disabled="disabled"
            :error-text="errorOf(index) ? $t(errorOf(index) as string) : undefined"
            :show-error="!!errorOf(index)"
            @update:model-value="change(index, { text: $event })"
          />
        </ion-col>
      </ion-row>
    </ion-grid>
  </section>
</template>
