<script setup lang="ts">
// A button of a page's bar whose icon says what it does by itself: in the bar, the icon alone, with its label as its
// accessible name and its title; listed in the bar's «⋮» on a phone, a row with its icon and its label, which acts
// once the menu has gone (a dialog opened while the menu leaves loses the keyboard to it).
import { HubIcon, useTopbarMenu } from '@erplora/ui/shell';
import { IonButton } from '@ionic/vue';

defineProps<{ testid: string; icon: string; label: string; color?: string }>();
const emit = defineEmits<{ press: [] }>();
const menu = useTopbarMenu();

function press(): void {
  if (menu) menu.closeThen(() => emit('press'));
  else emit('press');
}
</script>

<template>
  <ion-button
    :data-testid="testid"
    :color="color"
    :aria-label="label"
    :title="label"
    @click="press"
  >
    <template v-if="menu">
      <HubIcon
        slot="start"
        :name="icon"
      />
      {{ label }}
    </template>
    <HubIcon
      v-else
      slot="icon-only"
      :name="icon"
    />
  </ion-button>
</template>
