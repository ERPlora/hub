<script setup lang="ts">
// One row of a Settings card, as the old hub's: icon, name, the line that says what it is for and, at the end, its
// value (read-only) or — with `to` — a chevron that opens another screen. Business and Printing (APP-BASE-6) use it.
import { HubIcon } from '@erplora/ui/shell';
import { IonItem, IonLabel, IonNote } from '@ionic/vue';
import { useRouter } from 'vue-router';

const props = defineProps<{
  icon: string;
  title: string;
  hint: string;
  value?: string;
  /** A screen of the hub: the row becomes a button that opens it. */
  to?: string;
}>();

const router = useRouter();

function open(): void {
  if (props.to) void router.push(props.to);
}
</script>

<template>
  <ion-item
    lines="none"
    class="settings-row"
    :button="to ? true : undefined"
    :detail="to ? true : undefined"
    @click="open"
  >
    <HubIcon
      slot="start"
      :name="icon"
      aria-hidden="true"
    />
    <ion-label class="ion-text-wrap">
      <h3 data-testid="settings-row-title">
        {{ title }}
      </h3>
      <p data-testid="settings-row-hint">
        {{ hint }}
      </p>
    </ion-label>
    <ion-note
      v-if="!to && value !== undefined"
      slot="end"
      class="settings-row__value"
      data-testid="settings-row-value"
    >
      {{ value }}
    </ion-note>
  </ion-item>
</template>

<style scoped>
.settings-row__value {
  max-width: 55%;
  color: var(--ion-text-color);
  font-size: 1rem;
  text-align: end;
  overflow-wrap: anywhere;
}
</style>
