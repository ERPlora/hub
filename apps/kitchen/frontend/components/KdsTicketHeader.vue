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
const hasAllergy = computed(() => props.ticket.items.some((line) => line.allergy.length > 0));

function bumpAll(): void {
  if (props.tappable) emit('bumpAll');
}
</script>

<template>
  <ion-card-header class="ep-order-ticket__head">
    <ion-item
      class="ep-order-ticket__headline"
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
        class="ep-order-ticket__icon"
      >
        <HubIcon
          :name="ORDER_TYPE_ICONS[ticket.order_type]"
          :label="ticket.label ? typeName : undefined"
        />
      </ion-thumbnail>
      <ion-label class="ep-order-ticket__title">
        <span
          class="ep-order-ticket__label"
          :data-testid="`kitchen-card-${id}-label`"
        >{{ label }}</span>
        <span
          v-if="ticket.waiter"
          class="ep-order-ticket__waiter"
          :data-testid="`kitchen-card-${id}-waiter`"
        >{{ t('kitchen.card.waiter', { name: ticket.waiter }) }}</span>
      </ion-label>
      <ion-note
        slot="end"
        class="ep-order-ticket__clock"
      >
        <span
          v-if="settings.show_timer"
          class="ep-order-ticket__timer"
          :data-testid="`kitchen-card-${id}-timer`"
        >{{ formatElapsed(elapsed) }}</span>
        <span
          v-if="wait"
          class="ep-order-ticket__wait"
          :data-testid="`kitchen-card-${id}-wait`"
        ><HubIcon :name="wait.icon" />{{ t(wait.key) }}</span>
        <span
          class="ep-order-ticket__number"
          :data-testid="`kitchen-card-${id}-number`"
        >#{{ ticket.short_number }}</span>
      </ion-note>
    </ion-item>
    <div class="ep-order-ticket__flags">
      <StatusPill
        class="ep-order-ticket__pill"
        :data-testid="`kitchen-card-${id}-status`"
        :tone="STATUS_TONES[ticket.status]"
        :label="t(`kitchen.status.${ticket.status}`)"
      />
      <StatusPill
        v-if="priority"
        class="ep-order-ticket__pill"
        :data-testid="`kitchen-card-${id}-priority`"
        :tone="PRIORITY_TONES[priority]"
        :label="t(`kitchen.priority.${priority}`)"
      />
      <StatusPill
        v-if="hasAllergy"
        class="ep-order-ticket__pill"
        :data-testid="`kitchen-card-${id}-allergy`"
        tone="danger"
        :label="t('kitchen.card.allergy')"
      />
      <StatusPill
        v-if="ticket.round_no > 1"
        class="ep-order-ticket__pill"
        :data-testid="`kitchen-card-${id}-round`"
        :label="t('kitchen.card.round', { n: ticket.round_no })"
      />
    </div>
  </ion-card-header>
</template>

