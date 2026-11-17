<script setup lang="ts">
// The dishes of a kitchen card, the dishes of a menu under its header. Which dish answers a tap, and what it asks for,
// is decided here; how a dish looks, in KdsTicketLine.
import { HubIcon } from '@erplora/ui/shell';
import { IonItem, IonLabel, IonList } from '@ionic/vue';
import { computed } from 'vue';

import { useT } from '../composables/useT';
import { type DishGroup, groupMenus } from '../lib/board';
import type { ItemOut } from '../operations';
import KdsTicketLine from './KdsTicketLine.vue';

const props = defineProps<{
  items: ItemOut[];
  /** «All» (the pass): each dish says its station. */
  showStation: boolean;
  /** Dishes may be marked and recalled: leave to change tickets, on a ticket still on the board. */
  canTap: boolean;
  /** A menu's header may mark its dishes: leave to change tickets, on a ticket that cooks. */
  canBumpMenus: boolean;
}>();

const emit = defineEmits<{
  bump: [itemIds: string[]];
  recall: [itemIds: string[]];
}>();

const t = useT();
const groups = computed(() => groupMenus(props.items));
const toDo = (line: ItemOut) => line.status === 'pending' || line.status === 'preparing';
const struck = (line: ItemOut) => line.status === 'voided' || line.status === 'cancelled';
const tappable = (line: ItemOut) => props.canTap && !struck(line) && line.status !== 'served';
const menuToDo = (group: DishGroup) => group.items.filter(toDo).map((line) => line.id);
const menuTappable = (group: DishGroup) => props.canBumpMenus && menuToDo(group).length > 0;

function tap(line: ItemOut): void {
  if (toDo(line)) emit('bump', [line.id]);
  else if (line.status === 'ready') emit('recall', [line.id]);
}

function bumpMenu(group: DishGroup): void {
  if (menuTappable(group)) emit('bump', menuToDo(group));
}
</script>

<template>
  <ion-list
    class="kds-lines"
    lines="none"
  >
    <template
      v-for="group in groups"
      :key="group.menu?.lineId ?? group.items[0].id"
    >
      <ion-item
        v-if="group.menu"
        class="kds-menu"
        :button="menuTappable(group)"
        :detail="false"
        lines="full"
        :data-testid="`kitchen-menu-${group.menu.lineId}`"
        :aria-disabled="menuTappable(group) ? 'false' : 'true'"
        :title="menuTappable(group) ? t('kitchen.card.bumpMenu') : undefined"
        @click="bumpMenu(group)"
      >
        <HubIcon
          slot="start"
          class="kds-menu__icon"
          name="ion:list-outline"
        />
        <ion-label class="kds-menu__label">
          <span class="kds-menu__name">{{ group.menu.name }}</span>
          <span class="kds-menu__count">{{ $t('kitchen.card.menuDishes', group.items.length) }}</span>
        </ion-label>
      </ion-item>
      <KdsTicketLine
        v-for="line in group.items"
        :key="line.id"
        :line="line"
        :show-station="showStation"
        :tappable="tappable(line)"
        :in-menu="!!group.menu"
        @tap="tap(line)"
      />
    </template>
  </ion-list>
</template>

<style scoped>
.kds-lines {
  padding: 0;
  background: transparent;
}
.kds-menu {
  --background: color-mix(in srgb, var(--ep-primary-tint) 55%, transparent);
  --color: var(--ion-text-color);
  --border-color: var(--ion-border-color);
  --padding-start: 0.75rem;
  --inner-padding-end: 0.75rem;
  --min-height: 52px;
  user-select: none;
}
.kds-menu.ion-focused::part(native) {
  outline: 3px solid var(--ion-color-primary);
  outline-offset: -3px;
}
.kds-menu__icon {
  margin-inline-end: 0.6rem;
  color: var(--ep-primary-text);
  font-size: 1.3rem;
}
.kds-menu__label {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.25rem 0.75rem;
  margin: 0;
  white-space: normal;
}
.kds-menu__name {
  font-size: 1.05rem;
  font-weight: 800;
  overflow-wrap: anywhere;
}
.kds-menu__count {
  color: var(--ep-text-muted);
  font-size: 0.95rem;
  font-weight: 600;
}
</style>
