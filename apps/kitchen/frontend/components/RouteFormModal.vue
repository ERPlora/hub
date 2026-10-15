<script setup lang="ts">
// «Route to a station» (WORKBOOK «Pantallas · Estaciones»; KITCHEN-F04): the station (the active ones;
// «Route» in a station's row leaves it chosen), whether a product or a category goes there, the product or
// the category of the catalogue (Inventory, searched as the person types) and «Save routing». It replaces
// where that product or category went before. A refusal shows in the dialog.
import { Combo, type ComboOption, FormModal } from '@erplora/ui/components';
import { useCommand, useLiveClient } from '@erplora/ui/sdk';
import { IonSegment, IonSegmentButton, IonLabel, IonSelect, IonSelectOption } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import { useT } from '../composables/useT';
import { searchCategories, searchProducts } from '../lib/pickers';
import type { RouteOut, StationOut } from '../operations';

const props = withDefaults(
  defineProps<{
    stations: readonly StationOut[];
    /** The station chosen when it opens (its row's «Route»). */
    station?: string | null;
  }>(),
  { station: null },
);

const open = defineModel<boolean>('open', { default: false });
const emit = defineEmits<{ saved: [route: RouteOut] }>();

type Kind = 'product' | 'category';

const t = useT();
const client = useLiveClient();
const command = useCommand('kitchen.routing.set');
const active = computed(() => props.stations.filter((station) => station.is_active));
const stationId = ref<string | null>(props.station);
const kind = ref<Kind>('product');
const target = ref<ComboOption | null>(null);
const findProducts = searchProducts(client);
const findCategories = searchCategories(client);

watch(
  open,
  (isOpen) => {
    if (!isOpen) return;
    stationId.value = props.station;
    kind.value = 'product';
    target.value = null;
    command.error.value = null;
  },
  { immediate: true },
);

function onKind(event: CustomEvent<{ value?: string | number }>): void {
  const value = String(event.detail.value ?? 'product') as Kind;
  if (value === kind.value) return;
  kind.value = value;
  target.value = null;
}

async function save(): Promise<void> {
  if (!stationId.value || !target.value) return;
  const what = kind.value === 'product' ? { product_id: target.value.id } : { category_id: target.value.id };
  let saved: RouteOut;
  try {
    saved = await command.run({ station_id: stationId.value, ...what });
  } catch {
    return; // The dialog paints the error.
  }
  emit('saved', saved);
  open.value = false;
}
</script>

<template>
  <FormModal
    v-model:open="open"
    testid="kitchen-route-form"
    :title="t('kitchen.routing.form.title')"
    :submit-label="t('kitchen.routing.submit')"
    :pending="command.pending.value"
    :error="command.error.value"
    :submit-disabled="!stationId || !target"
    @submit="save"
  >
    <div class="kitchen-route-form">
      <ion-select
        data-testid="kitchen-route-form-station"
        :value="stationId"
        :label="t('kitchen.routing.form.station')"
        label-placement="floating"
        fill="outline"
        mode="md"
        interface="popover"
        @ion-change="stationId = $event.detail.value ?? null"
      >
        <ion-select-option
          v-for="choice in active"
          :key="choice.id"
          :value="choice.id"
        >
          {{ choice.name }}
        </ion-select-option>
      </ion-select>
      <ion-segment
        data-testid="kitchen-route-form-kind"
        :value="kind"
        :aria-label="t('kitchen.routing.form.kind')"
        @ion-change="onKind"
      >
        <ion-segment-button value="product">
          <ion-label>{{ t('kitchen.routing.form.product') }}</ion-label>
        </ion-segment-button>
        <ion-segment-button value="category">
          <ion-label>{{ t('kitchen.routing.form.category') }}</ion-label>
        </ion-segment-button>
      </ion-segment>
      <Combo
        v-if="kind === 'product'"
        v-model="target"
        testid="kitchen-route-form-product"
        :search="findProducts"
        :label="t('kitchen.routing.form.product')"
        clearable
      />
      <Combo
        v-else
        v-model="target"
        testid="kitchen-route-form-category"
        :search="findCategories"
        :label="t('kitchen.routing.form.category')"
        clearable
      />
    </div>
  </FormModal>
</template>

<style scoped>
.kitchen-route-form {
  display: grid;
  gap: 12px;
}
</style>
