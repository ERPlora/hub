<script setup lang="ts">
// A station's dialog (WORKBOOK «Pantallas · Estaciones»; KITCHEN-F01, F02): Name («e.g. Grill»), Colour (the
// chip of the display), Destination (screen and paper, screen only, paper only), Printer function (Kitchen,
// Bar), Printer (optional: a printer of Printing by its name) and Active. «Create station»; editing,
// «Save» with only what changed. A refusal shows in the dialog and what was typed stays.
import { FormModal } from '@erplora/ui/components';
import { useCommand } from '@erplora/ui/sdk';
import { IonInput, IonSelect, IonSelectOption, IonToggle } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import { useT } from '../composables/useT';
import type { Destination, PrinterUsage, StationOut, StationPatchIn } from '../operations';

const props = defineProps<{
  /** The station being edited; `null` = «Add station». */
  station: StationOut | null;
}>();

const open = defineModel<boolean>('open', { default: false });
const emit = defineEmits<{ saved: [station: StationOut] }>();

/** The palette of the old module's chips; the first is the factory colour. */
const PALETTE: ReadonlyArray<[string, string]> = [
  ['#F97316', 'orange'],
  ['#E03131', 'red'],
  ['#F59F00', 'amber'],
  ['#2F9E44', 'green'],
  ['#0C8599', 'teal'],
  ['#1971C2', 'blue'],
  ['#7048E8', 'violet'],
  ['#868E96', 'grey'],
];
const DESTINATIONS: readonly Destination[] = ['both', 'display', 'printer'];
const USAGES: readonly PrinterUsage[] = ['kitchen', 'bar'];

interface Form {
  name: string;
  color: string;
  destination: Destination;
  printer_usage: PrinterUsage;
  printer_name: string;
  is_active: boolean;
}

const t = useT();
const creation = useCommand('kitchen.station.create');
const update = useCommand('kitchen.station.update');
const pending = computed(() => creation.pending.value || update.pending.value);
const error = computed(() => (props.station ? update.error.value : creation.error.value));

function fromStation(station: StationOut | null): Form {
  if (!station) return { name: '', color: PALETTE[0][0], destination: 'both', printer_usage: 'kitchen', printer_name: '', is_active: true };
  const { name, color, destination, printer_usage, printer_name, is_active } = station;
  return { name, color, destination, printer_usage, printer_name, is_active };
}

const form = ref<Form>(fromStation(props.station));
watch(
  () => [open.value, props.station?.id] as const,
  ([isOpen]) => {
    if (!isOpen) return;
    form.value = fromStation(props.station);
    creation.error.value = null;
    update.error.value = null;
  },
  { immediate: true },
);

const colors = computed(() => {
  const known = PALETTE.map(([hex, name]) => ({ hex, label: t(`kitchen.colors.${name}`) }));
  const current = form.value.color.toUpperCase();
  return known.some((color) => color.hex === current) ? known : [...known, { hex: form.value.color, label: t('kitchen.colors.custom', { hex: form.value.color }) }];
});
const title = computed(() => (props.station ? t('kitchen.stations.form.editTitle', { name: props.station.name }) : t('kitchen.stations.form.createTitle')));
const text = (value: unknown): string => (value === null || value === undefined ? '' : String(value));
const invalid = (message: string | undefined) => ({ 'ion-invalid': !!message, 'ion-touched': !!message });

function set<K extends keyof Form>(field: K, value: Form[K]): void {
  form.value = { ...form.value, [field]: value };
}

function patch(station: StationOut): StationPatchIn {
  const out: StationPatchIn = { station_id: station.id };
  const now = { ...form.value, name: form.value.name.trim(), printer_name: form.value.printer_name.trim() };
  for (const key of Object.keys(now) as (keyof Form)[]) {
    if (now[key] !== station[key]) (out as Record<string, unknown>)[key] = now[key];
  }
  return out;
}

async function save(): Promise<void> {
  let saved: StationOut;
  try {
    if (props.station) saved = await update.run(patch(props.station));
    else saved = await creation.run({ ...form.value, name: form.value.name.trim(), printer_name: form.value.printer_name.trim() });
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
    testid="kitchen-station-form"
    :title="title"
    :submit-label="station ? t('kitchen.stations.form.save') : t('kitchen.stations.form.create')"
    :pending="pending"
    :error="error"
    :submit-disabled="!form.name.trim()"
    @submit="save"
  >
    <template #default="{ fieldErrors }">
      <div class="kitchen-station-form">
        <ion-input
          data-testid="kitchen-station-form-name"
          :value="form.name"
          :label="t('kitchen.stations.form.name')"
          :placeholder="t('kitchen.stations.form.namePlaceholder')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :maxlength="80"
          :error-text="fieldErrors.name"
          :class="invalid(fieldErrors.name)"
          @ion-input="set('name', text($event.detail.value))"
        />
        <ion-select
          data-testid="kitchen-station-form-color"
          :value="form.color"
          :label="t('kitchen.stations.form.color')"
          label-placement="floating"
          fill="outline"
          mode="md"
          interface="popover"
          @ion-change="set('color', text($event.detail.value))"
        >
          <ion-select-option
            v-for="color in colors"
            :key="color.hex"
            :value="color.hex"
          >
            {{ color.label }}
          </ion-select-option>
        </ion-select>
        <ion-select
          data-testid="kitchen-station-form-destination"
          :value="form.destination"
          :label="t('kitchen.stations.form.destination')"
          label-placement="floating"
          fill="outline"
          mode="md"
          interface="popover"
          @ion-change="set('destination', $event.detail.value as Destination)"
        >
          <ion-select-option
            v-for="value in DESTINATIONS"
            :key="value"
            :value="value"
          >
            {{ t(`kitchen.destination.${value}`) }}
          </ion-select-option>
        </ion-select>
        <ion-select
          data-testid="kitchen-station-form-printer_usage"
          :value="form.printer_usage"
          :label="t('kitchen.stations.form.printerUsage')"
          label-placement="floating"
          fill="outline"
          mode="md"
          interface="popover"
          @ion-change="set('printer_usage', $event.detail.value as PrinterUsage)"
        >
          <ion-select-option
            v-for="value in USAGES"
            :key="value"
            :value="value"
          >
            {{ t(`kitchen.printerUsage.${value}`) }}
          </ion-select-option>
        </ion-select>
        <ion-input
          data-testid="kitchen-station-form-printer_name"
          :value="form.printer_name"
          :label="t('kitchen.stations.form.printerName')"
          :helper-text="t('kitchen.stations.form.printerNameHint')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :maxlength="100"
          :error-text="fieldErrors.printer_name"
          :class="invalid(fieldErrors.printer_name)"
          @ion-input="set('printer_name', text($event.detail.value))"
        />
        <ion-toggle
          data-testid="kitchen-station-form-is_active"
          label-placement="end"
          justify="start"
          :checked="form.is_active"
          @ion-change="set('is_active', $event.detail.checked)"
        >
          {{ t('kitchen.stations.form.active') }}
        </ion-toggle>
      </div>
    </template>
  </FormModal>
</template>

<style scoped>
.kitchen-station-form {
  display: grid;
  gap: 12px;
}
</style>
