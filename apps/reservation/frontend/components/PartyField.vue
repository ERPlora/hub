<script setup lang="ts">
// «Party» of a reservation (RESERVATION-F06, F08) and of a waitlist entry (RESERVATION-F14): how many people come, a
// whole number from 1 in an outlined md box, with its window's refusal under it. The host's hook, its name in the form
// (`name="party_size"`, hub#888) and `disabled` fall through to the field.
import { IonInput } from '@ionic/vue';

defineProps<{ errorText?: string }>();
/** What is typed, as text: the host reads it as the number it sends. */
const party = defineModel<string>({ required: true });
</script>

<template>
  <ion-input
    :value="party"
    type="number"
    inputmode="numeric"
    min="1"
    :label="$t('reservation.form.party')"
    label-placement="floating"
    fill="outline"
    mode="md"
    :error-text="errorText"
    :class="{ 'ion-invalid': !!errorText, 'ion-touched': !!errorText }"
    @ion-input="party = String($event.detail.value ?? '')"
  />
</template>
