<script setup lang="ts">
// A ticket on the kitchen display (WORKBOOK «Pantallas · Pantalla»; KITCHEN-F10 to F14): the card that holds its
// head, its dishes, its note and its foot, and decides what each may do from the ticket's state and the person's
// permissions. The stripe on top is green, amber or red by the minutes since the round was sent. No step asks for
// confirmation: recall is the undo. The card's name and data hooks live on the article, because Ionic's card moves
// an `aria-label` off its own element.
import { IonCard, IonCardContent } from '@ionic/vue';
import { computed } from 'vue';

import { useT } from '../composables/useT';
import { semaphore } from '../lib/format';
import type { SettingsOut } from '../operations/settings';
import type { TicketOut } from '../operations/tickets';
import KdsTicketActions from './KdsTicketActions.vue';
import KdsTicketHeader from './KdsTicketHeader.vue';
import KdsTicketLines from './KdsTicketLines.vue';

const props = defineProps<{
  ticket: TicketOut;
  now: Date;
  settings: SettingsOut;
  /** «All» (the pass): each dish says its station. */
  showStation: boolean;
  /** May mark, recall and rush (`kitchen.change_ticket`). */
  canChange: boolean;
  /** May hand it over (`kitchen.complete_ticket`). */
  canServe: boolean;
}>();

const emit = defineEmits<{
  /** Mark dishes ready: these ids, or `[]` for every dish on screen. */
  bump: [itemIds: string[]];
  /** Bring dishes back: these ids, or `[]` for every struck dish on screen. */
  recall: [itemIds: string[]];
  rush: [rush: boolean];
  serve: [];
}>();

const t = useT();
const cooking = computed(() => props.ticket.status === 'pending' || props.ticket.status === 'preparing');
const active = computed(() => cooking.value || props.ticket.status === 'ready');
const elapsed = computed(() => props.now.getTime() - new Date(props.ticket.received_at).getTime());
const sem = computed(() => semaphore(elapsed.value, props.settings));
const anyToDo = computed(() => props.ticket.items.some((line) => line.status === 'pending' || line.status === 'preparing'));
const headTappable = computed(() => props.canChange && cooking.value && anyToDo.value);
</script>

<template>
  <article
    class="ep-order-ticket"
    :data-testid="`kitchen-card-${ticket.id}`"
    :data-status="ticket.status"
    :data-sem="sem"
    :aria-label="t('kitchen.card.aria', { n: ticket.short_number })"
  >
    <ion-card class="ep-order-ticket__card ep-surface">
      <KdsTicketHeader
        :ticket="ticket"
        :elapsed="elapsed"
        :settings="settings"
        :sem="sem"
        :tappable="headTappable"
        @bump-all="emit('bump', [])"
      />
      <ion-card-content class="ep-order-ticket__body">
        <KdsTicketLines
          :items="ticket.items"
          :show-station="showStation"
          :can-tap="canChange && active"
          :can-bump-menus="canChange && cooking"
          @bump="emit('bump', $event)"
          @recall="emit('recall', $event)"
        />
        <p
          v-if="ticket.notes"
          class="ep-order-ticket__notes"
        >
          {{ ticket.notes }}
        </p>
      </ion-card-content>
      <KdsTicketActions
        :ticket="ticket"
        :can-change="canChange"
        :can-serve="canServe"
        @bump="emit('bump', [])"
        @recall="emit('recall', [])"
        @rush="emit('rush', $event)"
        @serve="emit('serve')"
      />
    </ion-card>
  </article>
</template>

