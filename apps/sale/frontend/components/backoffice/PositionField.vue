<script setup lang="ts">
// The «Position» of the sale app's back-office lists (a section, SALE-F35; a quick note, SALE-F36): a whole number
// from 0, the server's `sort_order`, in an outlined md box under its host's label, with its window's refusal under it.
// The host's hook and its name in the form (`name="sort_order"`, hub#888) fall through to the field.
import { IonInput } from '@ionic/vue';

defineProps<{ label: string; errorText?: string }>();
/** What is typed, as text: the host reads it as the number it sends. */
const order = defineModel<string>({ required: true });
</script>

<template>
  <ion-input
    :value="order"
    type="number"
    inputmode="numeric"
    min="0"
    step="1"
    :label="label"
    label-placement="floating"
    fill="outline"
    mode="md"
    :error-text="errorText"
    :class="{ 'ion-invalid': !!errorText, 'ion-touched': !!errorText }"
    @ion-input="order = String($event.detail.value ?? '')"
  />
</template>
