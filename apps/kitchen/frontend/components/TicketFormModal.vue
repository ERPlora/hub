<script setup lang="ts">
// «New ticket» (WORKBOOK «Pantallas · Comandas»; KITCHEN-F23): Type (it starts at the settings' default),
// Destination and Notes (optional) and its dishes — a product of the catalogue (searched as the person
// types) or the dish written by hand, its quantity and a note — with «Add dish» and «Remove dish».
// «Create ticket» only with a dish; each dish goes to its station on the server. A refusal shows here.
import { Combo, type ComboOption, FormModal } from '@erplora/ui/components';
import { useCommand, useLiveClient } from '@erplora/ui/sdk';
import { HubIcon } from '@erplora/ui/shell';
import { IonButton, IonInput, IonSelect, IonSelectOption, IonTextarea } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import { useT } from '../composables/useT';
import { searchProducts } from '../lib/pickers';
import type { ManualItemIn, OrderType, TicketOut } from '../operations';

const props = withDefaults(defineProps<{ defaultType?: OrderType }>(), { defaultType: 'dine_in' });

const open = defineModel<boolean>('open', { default: false });
const emit = defineEmits<{ saved: [ticket: TicketOut] }>();

const TYPES: readonly OrderType[] = ['dine_in', 'takeaway', 'delivery'];

interface Dish {
  key: number;
  product: ComboOption | null;
  name: string;
  quantity: string;
  notes: string;
}

const t = useT();
const client = useLiveClient();
const findProducts = searchProducts(client);
const command = useCommand('kitchen.ticket.create');

let next = 0;
const dish = (): Dish => ({ key: next++, product: null, name: '', quantity: '1', notes: '' });
const type = ref<OrderType>(props.defaultType);
const label = ref('');
const notes = ref('');
const dishes = ref<Dish[]>([dish()]);

watch(
  open,
  (isOpen) => {
    if (!isOpen) return;
    type.value = props.defaultType;
    label.value = '';
    notes.value = '';
    dishes.value = [dish()];
    command.error.value = null;
  },
  { immediate: true },
);

const named = (entry: Dish) => entry.product !== null || entry.name.trim() !== '';
const ready = computed(() => dishes.value.some(named));
const text = (value: unknown): string => (value === null || value === undefined ? '' : String(value));

function update(index: number, change: Partial<Dish>): void {
  dishes.value = dishes.value.map((entry, i) => (i === index ? { ...entry, ...change } : entry));
}

function remove(index: number): void {
  dishes.value = dishes.value.filter((_, i) => i !== index);
  if (!dishes.value.length) dishes.value = [dish()];
}

function item(entry: Dish): ManualItemIn {
  const what = entry.product ? { product_id: entry.product.id } : { name: entry.name.trim() };
  return { ...what, quantity: entry.quantity.trim() || '1', notes: entry.notes.trim() };
}

async function save(): Promise<void> {
  let saved: TicketOut;
  try {
    saved = await command.run({
      order_type: type.value,
      label: label.value.trim(),
      notes: notes.value.trim(),
      items: dishes.value.filter(named).map(item),
    });
  } catch {
    return; // The dialog paints the error; what was typed stays.
  }
  emit('saved', saved);
  open.value = false;
}
</script>

<template>
  <FormModal
    v-model:open="open"
    testid="kitchen-ticket-form"
    size="md"
    :title="t('kitchen.form.title')"
    :submit-label="t('kitchen.form.submit')"
    :pending="command.pending.value"
    :error="command.error.value"
    :submit-disabled="!ready"
    @submit="save"
  >
    <div class="kitchen-ticket-form">
      <ion-select
        data-testid="kitchen-ticket-form-type"
        :value="type"
        :label="t('kitchen.form.type')"
        label-placement="floating"
        fill="outline"
        mode="md"
        interface="popover"
        @ion-change="type = $event.detail.value"
      >
        <ion-select-option
          v-for="value in TYPES"
          :key="value"
          :value="value"
        >
          {{ t(`kitchen.orderType.${value}`) }}
        </ion-select-option>
      </ion-select>
      <ion-input
        data-testid="kitchen-ticket-form-label"
        :value="label"
        :label="t('kitchen.form.label')"
        :placeholder="t('kitchen.form.labelPlaceholder')"
        label-placement="floating"
        fill="outline"
        mode="md"
        :maxlength="120"
        @ion-input="label = text($event.detail.value)"
      />
      <ion-textarea
        data-testid="kitchen-ticket-form-notes"
        :value="notes"
        :label="t('kitchen.form.notes')"
        label-placement="floating"
        fill="outline"
        mode="md"
        :maxlength="2000"
        :auto-grow="true"
        @ion-input="notes = text($event.detail.value)"
      />
      <h3 class="kitchen-ticket-form__title">
        {{ t('kitchen.form.dishes') }}
      </h3>
      <div
        v-for="(entry, index) in dishes"
        :key="entry.key"
        class="kitchen-ticket-form__dish"
        :data-testid="`kitchen-ticket-form-dish-${index}`"
      >
        <Combo
          :model-value="entry.product"
          :testid="`kitchen-ticket-form-dish-${index}-product`"
          :search="findProducts"
          :label="t('kitchen.form.product')"
          clearable
          @update:model-value="update(index, { product: $event })"
        />
        <ion-input
          v-if="!entry.product"
          :data-testid="`kitchen-ticket-form-dish-${index}-name`"
          :value="entry.name"
          :label="t('kitchen.form.name')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :maxlength="200"
          @ion-input="update(index, { name: text($event.detail.value) })"
        />
        <div class="kitchen-ticket-form__row">
          <ion-input
            :data-testid="`kitchen-ticket-form-dish-${index}-quantity`"
            :value="entry.quantity"
            type="number"
            inputmode="decimal"
            min="0"
            :label="t('kitchen.form.quantity')"
            label-placement="floating"
            fill="outline"
            mode="md"
            @ion-input="update(index, { quantity: text($event.detail.value) })"
          />
          <ion-input
            :data-testid="`kitchen-ticket-form-dish-${index}-notes`"
            :value="entry.notes"
            :label="t('kitchen.form.note')"
            label-placement="floating"
            fill="outline"
            mode="md"
            :maxlength="255"
            @ion-input="update(index, { notes: text($event.detail.value) })"
          />
          <ion-button
            fill="clear"
            color="medium"
            :data-testid="`kitchen-ticket-form-dish-${index}-remove`"
            :aria-label="t('kitchen.form.removeDish')"
            :title="t('kitchen.form.removeDish')"
            @click="remove(index)"
          >
            <HubIcon name="ion:trash-outline" />
          </ion-button>
        </div>
      </div>
      <ion-button
        fill="outline"
        data-testid="kitchen-ticket-form-add-dish"
        @click="dishes = [...dishes, dish()]"
      >
        <HubIcon
          slot="start"
          name="ion:add-outline"
        />
        {{ t('kitchen.form.addDish') }}
      </ion-button>
    </div>
  </FormModal>
</template>

<style scoped>
.kitchen-ticket-form {
  display: grid;
  gap: 12px;
}
.kitchen-ticket-form__title {
  margin: 4px 0 0;
  font-size: 1rem;
}
.kitchen-ticket-form__dish {
  display: grid;
  gap: 8px;
  padding: 10px;
  border: 1px solid var(--ion-border-color, #e7e2d6);
  border-radius: 10px;
}
.kitchen-ticket-form__row {
  display: grid;
  grid-template-columns: 7rem 1fr auto;
  gap: 8px;
  align-items: center;
}
</style>
