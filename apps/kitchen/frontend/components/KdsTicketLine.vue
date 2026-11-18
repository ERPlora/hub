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
    :class="['ep-order-ticket__dish', { 'ep-order-ticket__dish--menu': inMenu }]"
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
      class="ep-order-ticket__qty"
    >
      {{ formatQuantity(line.quantity, locale) }}×
    </ion-text>
    <ion-label class="ep-order-ticket__dish-body">
      <span class="ep-order-ticket__name">{{ line.name }}</span>
      <span
        v-if="line.modifiers.length"
        class="ep-order-ticket__modifiers"
        :data-testid="`kitchen-line-${line.id}-modifiers`"
      >{{ line.modifiers.join(', ') }}</span>
      <span
        v-if="line.notes"
        class="ep-order-ticket__dish-note"
      >{{ line.notes }}</span>
      <span
        v-if="line.status === 'voided'"
        class="ep-order-ticket__void"
      >
        <strong>{{ t('kitchen.card.voided') }}</strong>
        <em v-if="line.void_reason">{{ line.void_reason }}</em>
      </span>
      <span
        v-if="showStation || line.destination === 'printer'"
        class="ep-order-ticket__meta"
      >
        <span
          v-if="showStation"
          :data-testid="`kitchen-line-${line.id}-station`"
        ><i
          v-if="line.station_color"
          class="ep-station-dot"
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
      class="ep-order-ticket__state"
      :name="ITEM_STATUS_ICONS[line.status]"
      :label="t(`kitchen.itemStatus.${line.status}`)"
      :data-testid="`kitchen-line-${line.id}-state`"
    />
  </ion-item>
</template>

