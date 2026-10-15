<script setup lang="ts">
// The one money field of the drawer: an outlined md `ion-input` with the decimal pad. What is typed goes up
// as it is (`v-model`); the parent reads it with `readMoney` and passes the reason it is not an amount,
// which the field says under itself (Ionic shows `error-text` on an invalid, touched field).
import { IonInput } from '@ionic/vue';
import { computed } from 'vue';

const props = withDefaults(
  defineProps<{
    label: string;
    /** Prefix of the field's `data-testid`. */
    testid: string;
    /** Why what was typed cannot be sent. */
    error?: string | null;
    placeholder?: string;
  }>(),
  { error: null, placeholder: undefined },
);

const model = defineModel<string>({ required: true });

const invalid = computed(() => ({ 'ion-invalid': !!props.error, 'ion-touched': !!props.error }));
</script>

<template>
  <ion-input
    :data-testid="testid"
    :value="model"
    :label="label"
    label-placement="stacked"
    type="text"
    inputmode="decimal"
    autocomplete="off"
    fill="outline"
    mode="md"
    :placeholder="placeholder"
    :error-text="error ?? undefined"
    :class="invalid"
    @ion-input="model = String($event.detail.value ?? '')"
  />
</template>
