<script setup lang="ts">
// The «Name» of a printer or a device. 100 is the length the server keeps. The host's hook and its `name="name"`
// fall through to the field: the window tells by that name which refused field a person corrected.
import { IonInput } from '@ionic/vue';

defineProps<{ label: string; placeholder?: string; errorText?: string }>();
const name = defineModel<string>({ required: true });
</script>

<template>
  <ion-input
    :value="name"
    :label="label"
    :placeholder="placeholder"
    label-placement="stacked"
    fill="outline"
    mode="md"
    :maxlength="100"
    :error-text="errorText"
    :class="{ 'ion-invalid': !!errorText, 'ion-touched': !!errorText }"
    @ion-input="name = String($event.detail.value ?? '')"
  />
</template>
