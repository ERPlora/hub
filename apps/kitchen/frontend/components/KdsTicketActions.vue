<script setup lang="ts">
// The foot of a kitchen card: one main step across it and the rest behind «⋮», so the step a cook takes most is the
// biggest target. No step asks for confirmation: recall is the undo.
import { HubIcon } from '@erplora/ui/shell';
import { IonButton, IonItem, IonLabel, IonList, IonPopover } from '@ionic/vue';
import { computed, shallowRef } from 'vue';

import { useT } from '../composables/useT';
import type { TicketOut } from '../operations/tickets';

type Secondary = 'rush' | 'recall';

const props = defineProps<{
  ticket: TicketOut;
  /** May mark, recall and rush (`kitchen.change_ticket`). */
  canChange: boolean;
  /** May hand it over (`kitchen.complete_ticket`). */
  canServe: boolean;
}>();

const emit = defineEmits<{
  bump: [];
  recall: [];
  rush: [rush: boolean];
  serve: [];
}>();

const t = useT();
const id = computed(() => props.ticket.id);
const cooking = computed(() => props.ticket.status === 'pending' || props.ticket.status === 'preparing');
const anyToDo = computed(() => props.ticket.items.some((line) => line.status === 'pending' || line.status === 'preparing'));
const anyReady = computed(() => props.ticket.items.some((line) => line.status === 'ready'));
const rushed = computed(() => props.ticket.priority === 'rush');

const primary = computed<'bump' | 'serve' | null>(() => {
  if (props.canChange && cooking.value && anyToDo.value) return 'bump';
  if (props.canServe && props.ticket.status === 'ready') return 'serve';
  return null;
});

const secondary = computed(() => {
  const steps: Array<{ id: Secondary; label: string; icon: string }> = [];
  if (!props.canChange) return steps;
  if (cooking.value && props.ticket.priority !== 'vip') {
    steps.push({ id: 'rush', label: t(rushed.value ? 'kitchen.card.clearRush' : 'kitchen.card.markRush'), icon: 'ion:speedometer-outline' });
  }
  if (props.ticket.status === 'ready' || (cooking.value && anyReady.value)) {
    steps.push({ id: 'recall', label: t('kitchen.card.recall'), icon: 'ion:arrow-undo-outline' });
  }
  return steps;
});

const open = shallowRef(false);
const anchor = shallowRef<Event>();

function present(event: Event): void {
  anchor.value = event;
  open.value = true;
}

function choose(step: Secondary): void {
  open.value = false;
  if (step === 'rush') emit('rush', !rushed.value);
  else emit('recall');
}
</script>

<template>
  <footer
    v-if="primary || secondary.length"
    class="ep-order-ticket__foot"
    :data-testid="`kitchen-card-${id}-foot`"
  >
    <ion-button
      v-if="primary === 'bump'"
      class="ep-order-ticket__step"
      color="success"
      :data-testid="`kitchen-card-${id}-bump`"
      @click="emit('bump')"
    >
      <HubIcon
        slot="start"
        name="ion:checkmark-done-outline"
      />
      {{ t('kitchen.card.bump') }}
    </ion-button>
    <ion-button
      v-else-if="primary === 'serve'"
      class="ep-order-ticket__step"
      color="success"
      :data-testid="`kitchen-card-${id}-served`"
      @click="emit('serve')"
    >
      <HubIcon
        slot="start"
        name="ion:checkmark-outline"
      />
      {{ t('kitchen.card.served') }}
    </ion-button>
    <ion-button
      v-if="secondary.length"
      class="ep-order-ticket__more"
      fill="outline"
      color="medium"
      :data-testid="`kitchen-card-${id}-more`"
      :aria-label="t('kitchen.card.moreActions')"
      :title="t('kitchen.card.moreActions')"
      aria-haspopup="menu"
      :aria-expanded="open ? 'true' : 'false'"
      @click="present"
    >
      <HubIcon
        slot="icon-only"
        name="ion:ellipsis-vertical"
      />
    </ion-button>
    <ion-popover
      class="ep-order-ticket-steps"
      :is-open="open"
      :event="anchor"
      alignment="end"
      :dismiss-on-select="true"
      @did-dismiss="open = false"
    >
      <ion-list
        class="ep-order-ticket-steps__list"
        lines="none"
        :data-testid="`kitchen-card-${id}-menu`"
      >
        <ion-item
          v-for="step in secondary"
          :key="step.id"
          button
          :detail="false"
          :data-testid="`kitchen-card-${id}-${step.id}`"
          @click="choose(step.id)"
        >
          <HubIcon
            slot="start"
            :name="step.icon"
          />
          <ion-label>{{ step.label }}</ion-label>
        </ion-item>
      </ion-list>
    </ion-popover>
  </footer>
</template>

