<script setup lang="ts">
// The head of a kitchen card. Its row is the shortcut that marks every dish on screen; the pills under it are not.
import { StatusPill } from '@erplora/ui/components';
import { HubIcon } from '@erplora/ui/shell';
import { IonCardHeader, IonItem, IonLabel, IonNote, IonThumbnail } from '@ionic/vue';
import { computed } from 'vue';

import { useT } from '../composables/useT';
import { ORDER_TYPE_ICONS, PRIORITY_TONES, STATUS_TONES, waitOf } from '../lib/card';
import { formatElapsed, type Semaphore } from '../lib/format';
import type { SettingsOut, TicketOut } from '../operations';

const props = defineProps<{
  ticket: TicketOut;
  /** Milliseconds since the round was sent. */
  elapsed: number;
  settings: SettingsOut;
  sem: Semaphore;
  /** The row marks every dish on screen. */
  tappable: boolean;
}>();

const emit = defineEmits<{ bumpAll: [] }>();

const t = useT();
const id = computed(() => props.ticket.id);
const typeName = computed(() => t(`kitchen.orderType.${props.ticket.order_type}`));
const label = computed(() => props.ticket.label || typeName.value);
const wait = computed(() => waitOf(props.sem));
const priority = computed(() => (props.ticket.priority === 'normal' ? null : props.ticket.priority));

function bumpAll(): void {
  if (props.tappable) emit('bumpAll');
}
</script>

<template>
  <ion-card-header :class="['kds-head', `kds-head--${sem}`]">
    <ion-item
      class="kds-head__main"
      :button="tappable"
      :detail="false"
      lines="none"
      :data-testid="`kitchen-card-${id}-head`"
      :aria-disabled="tappable ? 'false' : 'true'"
      :title="tappable ? t('kitchen.card.bumpAll') : undefined"
      @click="bumpAll"
    >
      <ion-thumbnail
        slot="start"
        class="kds-head__icon"
      >
        <HubIcon
          :name="ORDER_TYPE_ICONS[ticket.order_type]"
          :label="ticket.label ? typeName : undefined"
        />
      </ion-thumbnail>
      <ion-label class="kds-head__title">
        <span
          class="kds-head__label"
          :data-testid="`kitchen-card-${id}-label`"
        >{{ label }}</span>
        <span
          v-if="ticket.waiter"
          class="kds-head__waiter"
          :data-testid="`kitchen-card-${id}-waiter`"
        >{{ t('kitchen.card.waiter', { name: ticket.waiter }) }}</span>
      </ion-label>
      <ion-note
        slot="end"
        class="kds-head__clock"
      >
        <span
          v-if="settings.show_timer"
          class="kds-head__timer"
          :data-testid="`kitchen-card-${id}-timer`"
        >{{ formatElapsed(elapsed) }}</span>
        <span
          v-if="wait"
          class="kds-head__wait"
          :data-testid="`kitchen-card-${id}-wait`"
        ><HubIcon :name="wait.icon" />{{ t(wait.key) }}</span>
        <span
          class="kds-head__num"
          :data-testid="`kitchen-card-${id}-number`"
        >#{{ ticket.short_number }}</span>
      </ion-note>
    </ion-item>
    <div class="kds-head__flags">
      <StatusPill
        class="kds-head__pill"
        :data-testid="`kitchen-card-${id}-status`"
        :tone="STATUS_TONES[ticket.status]"
        :label="t(`kitchen.status.${ticket.status}`)"
      />
      <StatusPill
        v-if="priority"
        class="kds-head__pill"
        :data-testid="`kitchen-card-${id}-priority`"
        :tone="PRIORITY_TONES[priority]"
        :label="t(`kitchen.priority.${priority}`)"
      />
      <StatusPill
        v-if="ticket.round_no > 1"
        class="kds-head__pill"
        :data-testid="`kitchen-card-${id}-round`"
        :label="t('kitchen.card.round', { n: ticket.round_no })"
      />
    </div>
  </ion-card-header>
</template>

<style scoped>
/* Ionic's card header stacks its children bottom-up in iOS mode: the head row comes first in both modes. */
.kds-head {
  flex-direction: column;
  padding: 0.5rem 0.5rem 0.75rem;
  border-bottom: 1px solid var(--ion-border-color);
  background: color-mix(in srgb, var(--ion-color-step-50) 60%, var(--ion-card-background));
}
.kds-head__main {
  --background: transparent;
  --color: var(--ion-text-color);
  --padding-start: 0.25rem;
  --inner-padding-end: 0.25rem;
  --padding-top: 0.25rem;
  --padding-bottom: 0.25rem;
  --min-height: 56px;
  --border-radius: var(--ep-radius);
  align-items: flex-start;
  user-select: none;
}
.kds-head__main.ion-focused::part(native) {
  outline: 3px solid var(--ion-color-primary);
  outline-offset: -3px;
}
.kds-head__icon {
  --size: 48px;
  --border-radius: 12px;
  display: grid;
  place-items: center;
  margin: 0 0.75rem 0 0;
  background: var(--ep-primary-tint);
  color: var(--ep-primary-text);
  font-size: 1.6rem;
}
.kds-head__title {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  margin: 0;
  min-width: 0;
  white-space: normal;
}
.kds-head__label {
  font-size: 1.45rem;
  line-height: 1.1;
  font-weight: 800;
  overflow-wrap: anywhere;
}
/* Who sent it is read whole (a name or, without one, an e-mail): it wraps on a narrow card, never cut. */
.kds-head__waiter {
  color: var(--ep-text-muted);
  font-size: 0.95rem;
  font-weight: 500;
  overflow-wrap: anywhere;
}
.kds-head__clock {
  --color: var(--ion-text-color);
  display: flex;
  flex: none;
  flex-direction: column;
  align-items: flex-end;
  gap: 0.2rem;
  margin: 0 0 0 0.5rem;
  text-align: right;
}
.kds-head__timer {
  font-size: 1.6rem;
  line-height: 1.05;
  font-weight: 800;
  font-variant-numeric: tabular-nums;
}
.kds-head__wait {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  color: var(--ep-text-muted);
  font-size: 0.85rem;
  font-weight: 700;
}
.kds-head__num {
  color: var(--ep-text-muted);
  font-size: 0.85rem;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
.kds-head--warning .kds-head__timer,
.kds-head--warning .kds-head__wait {
  color: var(--ep-warning-text);
}
.kds-head--critical .kds-head__timer,
.kds-head--critical .kds-head__wait {
  color: var(--ep-danger-text);
}
.kds-head__flags {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
  margin: 0.5rem 0.25rem 0;
}
.kds-head__pill {
  padding: 0.2rem 0.65rem;
  font-size: 0.85rem;
  font-weight: 700;
}
</style>
