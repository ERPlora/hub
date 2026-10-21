<script setup lang="ts">
// A ticket on the kitchen display (WORKBOOK «Pantallas · Pantalla»; KITCHEN-F10 to F14), as the old card:
// the label (or the type) and «Waiter: …», the Rush/VIP, «Round N» and «Ready» marks, the clock and
// «#0012»; each dish with its quantity large, the options chosen under its name (KITCHEN-F07), its note in
// italics and, in «All», its station; the dishes of a menu indented under the menu's header with how many
// there are (KITCHEN-F06, kitchen#57); a dish voided in the till struck with «Voided» and its reason, which
// does not answer to a tap. The top border is green, amber or red by the minutes since the round was sent.
// One tap marks a dish ready; a tap on a struck one recalls it; a menu's header marks its dishes on screen;
// the card's header or «Ready» every dish on screen. No confirmation anywhere: recall is the undo.
import { HubIcon } from '@erplora/ui/shell';
import { IonButton } from '@ionic/vue';
import { computed } from 'vue';

import { useLocale, useT } from '../composables/useT';
import { type DishGroup, groupMenus } from '../lib/board';
import { formatElapsed, formatQuantity, semaphore } from '../lib/format';
import type { ItemOut, SettingsOut, TicketOut } from '../operations';

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
const locale = useLocale();

const id = computed(() => props.ticket.id);
const cooking = computed(() => props.ticket.status === 'pending' || props.ticket.status === 'preparing');
const active = computed(() => cooking.value || props.ticket.status === 'ready');
const label = computed(() => props.ticket.label || t(`kitchen.orderType.${props.ticket.order_type}`));
const elapsed = computed(() => props.now.getTime() - new Date(props.ticket.received_at).getTime());
const sem = computed(() => semaphore(elapsed.value, props.settings));
const toDo = (item: ItemOut) => item.status === 'pending' || item.status === 'preparing';
const struck = (item: ItemOut) => item.status === 'voided' || item.status === 'cancelled';
const anyToDo = computed(() => props.ticket.items.some(toDo));
const anyReady = computed(() => props.ticket.items.some((item) => item.status === 'ready'));
const tappable = (item: ItemOut) => props.canChange && active.value && !struck(item) && item.status !== 'served';
const headerTappable = computed(() => props.canChange && cooking.value && anyToDo.value);
const showFoot = computed(() => (props.canChange && active.value) || (props.canServe && props.ticket.status === 'ready'));
const groups = computed(() => groupMenus(props.ticket.items));
const menuToDo = (group: DishGroup) => group.items.filter(toDo).map((item) => item.id);
const menuTappable = (group: DishGroup) => props.canChange && cooking.value && menuToDo(group).length > 0;

function tap(item: ItemOut): void {
  if (!tappable(item)) return;
  if (toDo(item)) emit('bump', [item.id]);
  else if (item.status === 'ready') emit('recall', [item.id]);
}

function bumpAll(): void {
  if (headerTappable.value) emit('bump', []);
}

function bumpMenu(group: DishGroup): void {
  if (menuTappable(group)) emit('bump', menuToDo(group));
}
</script>

<template>
  <article
    class="kds-card"
    :data-testid="`kitchen-card-${id}`"
    :data-status="ticket.status"
    :data-sem="sem"
    :aria-label="t('kitchen.card.aria', { n: ticket.short_number })"
  >
    <header
      class="kds-card__head"
      :data-testid="`kitchen-card-${id}-head`"
      role="button"
      :tabindex="headerTappable ? 0 : -1"
      :aria-disabled="headerTappable ? 'false' : 'true'"
      :title="headerTappable ? t('kitchen.card.bumpAll') : undefined"
      @click="bumpAll"
      @keydown.enter.prevent="bumpAll"
    >
      <span class="kds-card__title">
        <span
          class="kds-card__label"
          :data-testid="`kitchen-card-${id}-label`"
        >{{ label }}</span>
        <span
          v-if="ticket.waiter"
          class="kds-card__waiter"
          :data-testid="`kitchen-card-${id}-waiter`"
        >{{ t('kitchen.card.waiter', { name: ticket.waiter }) }}</span>
      </span>
      <span
        v-if="ticket.priority !== 'normal'"
        :class="['kds-pill', `kds-pill--${ticket.priority}`]"
        :data-testid="`kitchen-card-${id}-priority`"
      >{{ t(`kitchen.priority.${ticket.priority}`) }}</span>
      <span
        v-if="ticket.round_no > 1"
        class="kds-pill kds-pill--round"
        :data-testid="`kitchen-card-${id}-round`"
      >{{ t('kitchen.card.round', { n: ticket.round_no }) }}</span>
      <span
        v-if="ticket.status === 'ready'"
        class="kds-pill kds-pill--ready"
        :data-testid="`kitchen-card-${id}-status`"
      >{{ t('kitchen.card.ready') }}</span>
      <span
        v-if="settings.show_timer"
        class="kds-card__timer"
        :data-testid="`kitchen-card-${id}-timer`"
      >{{ formatElapsed(elapsed) }}</span>
      <span
        class="kds-card__num"
        :data-testid="`kitchen-card-${id}-number`"
      >#{{ ticket.short_number }}</span>
    </header>
    <ul class="kds-card__lines">
      <template
        v-for="group in groups"
        :key="group.menu?.lineId ?? group.items[0].id"
      >
        <li
          v-if="group.menu"
          class="kds-menu"
          :data-testid="`kitchen-menu-${group.menu.lineId}`"
          role="button"
          :tabindex="menuTappable(group) ? 0 : -1"
          :aria-disabled="menuTappable(group) ? 'false' : 'true'"
          :title="menuTappable(group) ? t('kitchen.card.bumpMenu') : undefined"
          @click="bumpMenu(group)"
          @keydown.enter.prevent="bumpMenu(group)"
        >
          <span class="kds-menu__name">{{ group.menu.name }}</span>
          <span class="kds-menu__count">{{ $t('kitchen.card.menuDishes', group.items.length) }}</span>
        </li>
        <li
          v-for="line in group.items"
          :key="line.id"
          :class="['kds-line', { 'kds-line--menu': group.menu }]"
          :data-testid="`kitchen-line-${line.id}`"
          :data-status="line.status"
          :data-menu="line.menu_line_id ?? undefined"
          role="button"
          :tabindex="tappable(line) ? 0 : -1"
          :aria-disabled="tappable(line) ? 'false' : 'true'"
          :title="tappable(line) ? t(toDo(line) ? 'kitchen.card.tapToBump' : 'kitchen.card.tapToRecall') : undefined"
          @click="tap(line)"
          @keydown.enter.prevent="tap(line)"
        >
          <span class="kds-line__qty">{{ formatQuantity(line.quantity, locale) }}</span>
          <span class="kds-line__body">
            <span class="kds-line__name">{{ line.name }}</span>
            <span
              v-if="line.modifiers.length"
              class="kds-line__mods"
              :data-testid="`kitchen-line-${line.id}-modifiers`"
            >{{ line.modifiers.join(', ') }}</span>
            <span
              v-if="line.notes"
              class="kds-line__note"
            >{{ line.notes }}</span>
            <span
              v-if="line.status === 'voided'"
              class="kds-line__void"
            >
              <strong>{{ t('kitchen.card.voided') }}</strong>
              <em v-if="line.void_reason">{{ line.void_reason }}</em>
            </span>
            <span
              v-if="(showStation) || line.destination === 'printer'"
              class="kds-line__meta"
            >
              <span
                v-if="showStation"
                class="kds-line__station"
                :data-testid="`kitchen-line-${line.id}-station`"
              ><i
                v-if="line.station_color"
                class="kds-line__dot"
                :style="{ background: line.station_color }"
              />{{ line.station_name || t('kitchen.display.stationNone') }}</span>
              <HubIcon
                v-if="line.destination === 'printer'"
                name="ion:receipt-outline"
                :label="t('kitchen.card.paperOnly')"
                :data-testid="`kitchen-line-${line.id}-paper`"
              />
            </span>
          </span>
          <span
            v-if="line.status === 'ready' || line.status === 'served'"
            class="kds-line__tick"
            aria-hidden="true"
          >✓</span>
        </li>
      </template>
    </ul>
    <div
      v-if="ticket.notes"
      class="kds-card__notes"
    >
      {{ ticket.notes }}
    </div>
    <footer
      v-if="showFoot"
      class="kds-card__foot"
      :data-testid="`kitchen-card-${id}-foot`"
    >
      <ion-button
        v-if="canChange && cooking && anyToDo"
        class="kds-card__bump"
        color="success"
        :data-testid="`kitchen-card-${id}-bump`"
        @click="emit('bump', [])"
      >
        {{ t('kitchen.card.bump') }}
      </ion-button>
      <ion-button
        v-if="canChange && cooking && ticket.priority !== 'vip'"
        fill="outline"
        :color="ticket.priority === 'rush' ? 'medium' : 'danger'"
        :data-testid="`kitchen-card-${id}-rush`"
        @click="emit('rush', ticket.priority !== 'rush')"
      >
        {{ ticket.priority === 'rush' ? t('kitchen.card.clearRush') : t('kitchen.card.markRush') }}
      </ion-button>
      <ion-button
        v-if="canChange && (ticket.status === 'ready' || (cooking && anyReady))"
        fill="outline"
        :data-testid="`kitchen-card-${id}-recall`"
        @click="emit('recall', [])"
      >
        {{ t('kitchen.card.recall') }}
      </ion-button>
      <ion-button
        v-if="canServe && ticket.status === 'ready'"
        fill="outline"
        color="success"
        :data-testid="`kitchen-card-${id}-served`"
        @click="emit('serve')"
      >
        {{ t('kitchen.card.served') }}
      </ion-button>
    </footer>
  </article>
</template>

<style scoped>
.kds-card {
  border: 1px solid var(--ion-border-color, #e7e2d6);
  border-top-width: 6px;
  border-radius: 10px;
  background: var(--ion-item-background, var(--ion-background-color, #fff));
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.kds-card[data-sem='ok'] {
  border-top-color: var(--ion-color-success, #2dd36f);
}
.kds-card[data-sem='warning'] {
  border-top-color: var(--ion-color-warning, #ffc409);
}
.kds-card[data-sem='critical'] {
  border-top-color: var(--ion-color-danger, #eb445a);
}
.kds-card[data-sem='off'] {
  border-top-color: var(--ion-border-color, #e7e2d6);
}
.kds-card[data-sem='warning'] .kds-card__timer {
  color: var(--ion-color-warning-shade, #e0ac08);
}
.kds-card[data-sem='critical'] .kds-card__timer {
  color: var(--ion-color-danger, #eb445a);
}
.kds-card[data-status='ready'] {
  opacity: 0.85;
}
.kds-card__head {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.35rem 0.5rem;
  padding: 0.6rem 0.75rem;
  min-height: 44px;
  cursor: pointer;
  user-select: none;
  background: var(--ion-color-step-50, rgba(24, 24, 27, 0.04));
}
.kds-card__head[aria-disabled='true'] {
  cursor: default;
}
.kds-card__title {
  flex: 1 1 60%;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.05rem;
}
.kds-card__label {
  font-weight: 700;
  font-size: 1.3rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.kds-card__waiter {
  font-size: 0.95rem;
  font-weight: 500;
  opacity: 0.72;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.kds-card__num {
  font-variant-numeric: tabular-nums;
  font-size: 0.9rem;
  opacity: 0.75;
}
.kds-card__timer {
  font-variant-numeric: tabular-nums;
  font-weight: 700;
  font-size: 1.25rem;
}
.kds-pill {
  display: inline-block;
  padding: 0.1rem 0.5rem;
  border-radius: 999px;
  font-size: 0.75rem;
  font-weight: 700;
  text-transform: uppercase;
}
.kds-pill--rush {
  background: var(--ion-color-danger, #eb445a);
  color: #fff;
}
.kds-pill--vip {
  background: var(--ion-color-tertiary, #6030ff);
  color: #fff;
}
.kds-pill--round {
  background: rgba(0, 0, 0, 0.06);
}
.kds-pill--ready {
  background: var(--ion-color-success, #2dd36f);
  color: #fff;
}
.kds-card__lines {
  list-style: none;
  margin: 0;
  padding: 0;
}
.kds-line {
  display: flex;
  gap: 0.6rem;
  align-items: flex-start;
  padding: 0.55rem 0.75rem;
  min-height: 44px;
  border-top: 1px solid var(--ion-border-color, #e7e2d6);
  cursor: pointer;
  user-select: none;
  -webkit-tap-highlight-color: transparent;
}
.kds-line[aria-disabled='true'] {
  cursor: default;
}
.kds-line:active {
  background: rgba(0, 0, 0, 0.05);
}
.kds-line__qty {
  font-weight: 800;
  font-size: 1.6rem;
  min-width: 2ch;
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.kds-line__body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}
.kds-line__name {
  font-weight: 600;
  font-size: 1.4rem;
}
.kds-line__mods {
  font-size: 1.1rem;
  font-weight: 700;
  overflow-wrap: anywhere;
}
.kds-line__note {
  font-size: 1.05rem;
  opacity: 0.85;
  font-style: italic;
}
.kds-menu {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 0.25rem 0.6rem;
  padding: 0.45rem 0.75rem 0.2rem;
  min-height: 44px;
  border-top: 1px solid var(--ion-border-color, #e7e2d6);
  cursor: pointer;
  user-select: none;
  -webkit-tap-highlight-color: transparent;
}
.kds-menu[aria-disabled='true'] {
  cursor: default;
}
.kds-menu:active {
  background: rgba(0, 0, 0, 0.05);
}
.kds-menu__name {
  font-size: 1.05rem;
  font-weight: 600;
  overflow-wrap: anywhere;
}
.kds-menu__count {
  font-size: 0.95rem;
  opacity: 0.7;
}
.kds-line--menu {
  border-top: none;
  margin-left: 0.75rem;
  padding-left: 0.6rem;
  border-left: 3px solid var(--ion-border-color, #e7e2d6);
}
.kds-line__meta {
  font-size: 1rem;
  opacity: 0.7;
  display: flex;
  gap: 0.5rem;
  align-items: center;
}
.kds-line__dot {
  display: inline-block;
  width: 0.6rem;
  height: 0.6rem;
  border-radius: 50%;
  margin-right: 0.3rem;
}
.kds-line[data-status='ready'] .kds-line__name,
.kds-line[data-status='ready'] .kds-line__qty,
.kds-line[data-status='served'] .kds-line__name,
.kds-line[data-status='served'] .kds-line__qty {
  text-decoration: line-through;
  opacity: 0.55;
}
.kds-line[data-status='voided'] .kds-line__name,
.kds-line[data-status='voided'] .kds-line__qty,
.kds-line[data-status='cancelled'] .kds-line__name,
.kds-line[data-status='cancelled'] .kds-line__qty {
  text-decoration: line-through;
  opacity: 0.6;
}
.kds-line__void {
  font-size: 1rem;
  font-weight: 700;
  color: var(--ion-color-danger, #c5000f);
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem 0.5rem;
}
.kds-line__void em {
  font-weight: 400;
  overflow-wrap: anywhere;
}
.kds-line__tick {
  font-size: 1.4rem;
  line-height: 1;
  color: var(--ion-color-success, #2dd36f);
}
.kds-card__notes {
  padding: 0.5rem 0.75rem;
  border-top: 1px solid var(--ion-border-color, #e7e2d6);
  font-style: italic;
}
.kds-card__foot {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  padding: 0.5rem 0.75rem;
  border-top: 1px solid var(--ion-border-color, #e7e2d6);
}
.kds-card__foot ion-button {
  flex: 1;
  min-height: 44px;
  margin: 0;
}
</style>
