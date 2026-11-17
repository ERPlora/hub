<script setup lang="ts">
// One dish of a kitchen card. The row is the dish's only target, so its state is said by the icon at its end and
// never by a second button.
import { HubIcon } from '@erplora/ui/shell';
import { IonItem, IonLabel, IonText } from '@ionic/vue';
import { computed } from 'vue';

import { useLocale, useT } from '../composables/useT';
import { ITEM_STATUS_ICONS } from '../lib/card';
import { formatQuantity } from '../lib/format';
import type { ItemOut } from '../operations';

const props = defineProps<{
  line: ItemOut;
  /** «All» (the pass): the dish says its station. */
  showStation: boolean;
  /** The card lets this dish be marked or recalled. */
  tappable: boolean;
  /** One of a menu's dishes, hung from the menu's header. */
  inMenu: boolean;
}>();

const emit = defineEmits<{ tap: [] }>();

const t = useT();
const locale = useLocale();
const toDo = computed(() => props.line.status === 'pending' || props.line.status === 'preparing');
const hint = computed(() => (props.tappable ? t(toDo.value ? 'kitchen.card.tapToBump' : 'kitchen.card.tapToRecall') : undefined));

function tap(): void {
  if (props.tappable) emit('tap');
}
</script>

<template>
  <ion-item
    :class="['kds-line', { 'kds-line--menu': inMenu }]"
    :button="tappable"
    :detail="false"
    lines="full"
    :data-testid="`kitchen-line-${line.id}`"
    :data-status="line.status"
    :data-menu="line.menu_line_id ?? undefined"
    :aria-disabled="tappable ? 'false' : 'true'"
    :title="hint"
    @click="tap"
  >
    <ion-text
      slot="start"
      class="kds-line__qty"
    >
      {{ formatQuantity(line.quantity, locale) }}×
    </ion-text>
    <ion-label class="kds-line__body">
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
        v-if="showStation || line.destination === 'printer'"
        class="kds-line__meta"
      >
        <span
          v-if="showStation"
          :data-testid="`kitchen-line-${line.id}-station`"
        ><i
          v-if="line.station_color"
          class="kds-line__dot"
          :style="{ background: line.station_color }"
        />{{ line.station_name || t('kitchen.display.stationNone') }}</span>
        <span
          v-if="line.destination === 'printer'"
          :data-testid="`kitchen-line-${line.id}-paper`"
        ><HubIcon name="ion:receipt-outline" />{{ t('kitchen.card.paperOnly') }}</span>
      </span>
    </ion-label>
    <HubIcon
      slot="end"
      class="kds-line__state"
      :name="ITEM_STATUS_ICONS[line.status]"
      :label="t(`kitchen.itemStatus.${line.status}`)"
      :data-testid="`kitchen-line-${line.id}-state`"
    />
  </ion-item>
</template>

<style scoped>
.kds-line {
  --background: transparent;
  --color: var(--ion-text-color);
  --border-color: var(--ion-border-color);
  --padding-start: 0.75rem;
  --inner-padding-end: 0.75rem;
  --padding-top: 0.6rem;
  --padding-bottom: 0.6rem;
  --min-height: 64px;
  align-items: flex-start;
  user-select: none;
}
.kds-line.ion-focused::part(native) {
  outline: 3px solid var(--ion-color-primary);
  outline-offset: -3px;
}
/* The dishes of a menu hang from its header along a rule inside the row: each keeps the full width for its name. */
.kds-line--menu {
  --padding-start: 0.5rem;
  margin-inline-start: 0.5rem;
  border-inline-start: 3px solid var(--ep-primary-text);
}
.kds-line__qty {
  flex: none;
  min-width: 2.6ch;
  margin: 0.1rem 0.75rem 0 0;
  text-align: right;
  font-size: 1.75rem;
  line-height: 1;
  font-weight: 800;
  font-variant-numeric: tabular-nums;
}
.kds-line__body {
  margin: 0;
  min-width: 0;
  white-space: normal;
}
.kds-line__name {
  display: block;
  font-size: 1.3rem;
  line-height: 1.2;
  font-weight: 700;
  overflow-wrap: break-word;
}
.kds-line__mods {
  display: block;
  margin-top: 0.25rem;
  font-size: 1.05rem;
  line-height: 1.25;
  font-weight: 800;
  overflow-wrap: anywhere;
}
.kds-line__note {
  display: block;
  margin-top: 0.2rem;
  color: var(--ep-text-muted);
  font-size: 1rem;
  line-height: 1.3;
  font-style: italic;
  overflow-wrap: anywhere;
}
.kds-line__void {
  display: flex;
  flex-wrap: wrap;
  gap: 0.2rem 0.5rem;
  margin-top: 0.3rem;
  color: var(--ep-danger-text);
  font-size: 1rem;
}
.kds-line__void strong {
  font-weight: 800;
}
.kds-line__void em {
  overflow-wrap: anywhere;
}
.kds-line__meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.3rem 0.75rem;
  margin-top: 0.35rem;
  color: var(--ep-text-muted);
  font-size: 0.9rem;
  font-weight: 600;
}
.kds-line__meta > span {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
}
.kds-line__dot {
  flex: none;
  width: 0.65rem;
  height: 0.65rem;
  border-radius: 50%;
}
.kds-line__state {
  flex: none;
  margin: 0.1rem 0 0 0.5rem;
  font-size: 1.6rem;
  color: var(--ep-text-muted);
}
.kds-line[data-status='ready'] .kds-line__name,
.kds-line[data-status='served'] .kds-line__name,
.kds-line[data-status='voided'] .kds-line__name,
.kds-line[data-status='cancelled'] .kds-line__name {
  text-decoration: line-through;
  color: var(--ep-text-muted);
}
.kds-line[data-status='ready'] .kds-line__qty,
.kds-line[data-status='served'] .kds-line__qty,
.kds-line[data-status='voided'] .kds-line__qty,
.kds-line[data-status='cancelled'] .kds-line__qty {
  color: var(--ep-text-muted);
}
.kds-line[data-status='ready'] .kds-line__state,
.kds-line[data-status='served'] .kds-line__state {
  color: var(--ep-success-text);
}
.kds-line[data-status='voided'] .kds-line__state,
.kds-line[data-status='cancelled'] .kds-line__state {
  color: var(--ep-danger-text);
}
</style>
