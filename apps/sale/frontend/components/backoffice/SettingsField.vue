<script setup lang="ts">
// One row of the till settings (SALE-F34), as the old generated settings screen painted it: an `ion-item`
// with the setting's name and explanation and its control — a switch or the document choice at the end
// of the row; a number, a text or a multi-line text (the receipt header: name, then address) in an
// outlined md box under the name. Blocked, nothing can be changed. A refusal of the server for this field
// is said at it. The value travels as the form keeps it: a boolean for a switch, text for the rest.
import { HubIcon } from '@erplora/ui/shell';
import { IonInput, IonItem, IonLabel, IonSelect, IonSelectOption, IonTextarea, IonToggle } from '@ionic/vue';
import { computed } from 'vue';

import { useT } from '../../composables/useT';
import type { SettingsField } from './settingsFields';

const props = withDefaults(
  defineProps<{
    field: SettingsField;
    /** String before boolean: Vue casts an empty string to `true` when Boolean comes first. */
    value: string | boolean;
    disabled: boolean;
    /** The server's refusal for this field. */
    error?: string;
    /** An icon at the start of the row (the old screen put its own on the first one). */
    icon?: string;
    /** The business territory's tax («VAT», «IGIC», «IPSI»), read once by the form for every row. */
    taxName: string;
  }>(),
  { error: undefined, icon: undefined },
);

const emit = defineEmits<{ 'update:value': [value: string | boolean] }>();

const t = useT();
// «Prices include VAT» names the business territory's tax («IGIC», «IPSI»); the other names ignore it.
const label = computed(() => t(`sale.settings.fields.${props.field.key}.label`, { tax: props.taxName }));
const description = computed(() => (props.field.described ? t(`sale.settings.fields.${props.field.key}.description`) : undefined));
const testid = computed(() => `sale-settings-field-${props.field.key}`);
/** A switch or a choice says its refusal under the name; a box, under itself. */
const inline = computed(() => props.field.control === 'toggle' || props.field.control === 'select');
const invalid = computed(() => ({ 'ion-invalid': !!props.error, 'ion-touched': !!props.error }));

const text = (value: unknown): string => (value === null || value === undefined ? '' : String(value));
</script>

<template>
  <ion-item
    lines="none"
    class="sale-setting"
  >
    <HubIcon
      v-if="icon"
      slot="start"
      :name="icon"
    />
    <div class="sale-setting__entry">
      <ion-label>
        <h2>{{ label }}</h2>
        <p v-if="description">
          {{ description }}
        </p>
        <p
          v-if="error && inline"
          class="sale-setting__invalid"
          :data-testid="`sale-settings-invalid-${field.key}`"
        >
          {{ error }}
        </p>
      </ion-label>
      <ion-input
        v-if="field.control === 'number'"
        class="sale-setting__input sale-setting__input--number"
        :data-testid="testid"
        :value="text(value)"
        type="number"
        inputmode="numeric"
        :min="field.min"
        :max="field.max"
        step="1"
        fill="outline"
        mode="md"
        :aria-label="label"
        :disabled="disabled"
        :error-text="error"
        :class="invalid"
        @ion-input="emit('update:value', text($event.detail.value))"
      />
      <ion-input
        v-else-if="field.control === 'text'"
        class="sale-setting__input"
        :data-testid="testid"
        :value="text(value)"
        :type="field.type"
        :maxlength="field.maxlength"
        :placeholder="t('sale.settings.textPlaceholder')"
        fill="outline"
        mode="md"
        :aria-label="label"
        :disabled="disabled"
        :error-text="error"
        :class="invalid"
        @ion-input="emit('update:value', text($event.detail.value))"
      />
      <ion-textarea
        v-else-if="field.control === 'textarea'"
        class="sale-setting__input"
        :data-testid="testid"
        :value="text(value)"
        :maxlength="field.maxlength"
        :placeholder="t('sale.settings.textPlaceholder')"
        :auto-grow="true"
        :rows="2"
        fill="outline"
        mode="md"
        :aria-label="label"
        :disabled="disabled"
        :error-text="error"
        :class="invalid"
        @ion-input="emit('update:value', text($event.detail.value))"
      />
    </div>
    <ion-toggle
      v-if="field.control === 'toggle'"
      slot="end"
      :data-testid="testid"
      :checked="value === true"
      :aria-label="label"
      :disabled="disabled"
      @ion-change="emit('update:value', $event.detail.checked)"
    />
    <ion-select
      v-else-if="field.control === 'select'"
      slot="end"
      interface="popover"
      :data-testid="testid"
      :value="value"
      :aria-label="label"
      :disabled="disabled"
      @ion-change="emit('update:value', text($event.detail.value))"
    >
      <ion-select-option
        v-for="option in field.options"
        :key="option"
        :value="option"
      >
        {{ t(`sale.settings.documentType.${option}`) }}
      </ion-select-option>
    </ion-select>
  </ion-item>
</template>

<style scoped>
/* The body of a row: its name and, for a box, the box. Side by side when the row is wide, the box under
   its name when it is not (the old screen's container query). */
.sale-setting__entry {
  flex: 1;
  min-width: 0;
  container-type: inline-size;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  column-gap: 1rem;
}

.sale-setting__entry > ion-label {
  flex: 1 1 0;
  min-width: 0;
  margin: 10px 0;
}

.sale-setting__input {
  flex: 1 1 100%;
  margin-bottom: 10px;
}

@container (min-width: 30rem) {
  .sale-setting__input {
    flex: 0 1 18rem;
    margin-bottom: 0;
  }

  .sale-setting__input--number {
    flex-basis: 8rem;
  }
}

.sale-setting__invalid {
  color: var(--ion-color-danger, #c5000f);
}
</style>
