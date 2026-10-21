<script setup lang="ts">
// «Print from this device» / «Edit device» (PRINTING-F18; the old hub's print host, hub#342): the device's name
// and the active printers it reaches, one check each. A new one is the device the page runs on (the SDK names it
// to the server with X-Device-Id; its id is never shown); an edited one is any device of the list. «Save» says
// so; what is missing is said before anything is sent, and a refusal at its field in the server's words.
import { FormModal, type FormModalError } from '@erplora/ui/components';
import { useCommand } from '@erplora/ui/sdk';
import { toastSuccess } from '@erplora/ui/shell';
import { IonCheckbox, IonInput, IonNote } from '@ionic/vue';
import { computed, shallowRef, watch } from 'vue';

import { useT } from '../composables/useT';
import { refusal } from '../lib/refusal';
import type { DeviceOut, PrinterOut } from '../operations';

// `printers`: the business's active printers, the ones a device may print for.
const props = defineProps<{ device: DeviceOut | null; printers: readonly Pick<PrinterOut, 'id' | 'name' | 'usage'>[] }>();

const open = defineModel<boolean>('open', { required: true });

const t = useT();
const register = useCommand('printing.device.register');
const update = useCommand('printing.device.update');

const name = shallowRef('');
const chosen = shallowRef<ReadonlySet<string>>(new Set());
const missingName = shallowRef(false);
const missingPrinters = shallowRef(false);

watch(
  open,
  (now) => {
    if (!now) return;
    name.value = props.device?.name ?? '';
    chosen.value = new Set(props.device?.printers.map((printer) => printer.id) ?? []);
    missingName.value = false;
    missingPrinters.value = false;
    register.error.value = null;
    update.error.value = null;
  },
  { immediate: true },
);

const pending = computed(() => register.pending.value || update.pending.value);
const error = computed<FormModalError | null>(() => refusal(register.error.value ?? update.error.value, t('printing.devices.modal.failed')));
const fieldError = (field: string) => error.value?.fields?.[field] ?? null;
const nameError = computed(() => (missingName.value ? t('printing.devices.modal.required') : fieldError('name')));
const printersError = computed(() => (missingPrinters.value ? t('printing.devices.modal.choosePrinters') : fieldError('printers')));

function toggle(id: string, on: boolean): void {
  const next = new Set(chosen.value);
  if (on) next.add(id);
  else next.delete(id);
  chosen.value = next;
  if (next.size) missingPrinters.value = false;
}

async function confirm(): Promise<void> {
  // The order of the business's printers, not the order they were ticked.
  const printers = props.printers.filter((printer) => chosen.value.has(printer.id)).map((printer) => printer.id);
  missingName.value = !name.value.trim();
  missingPrinters.value = printers.length === 0;
  if (missingName.value || missingPrinters.value) return;
  const body = { name: name.value.trim(), printers };
  try {
    if (props.device) await update.run({ device_id: props.device.id, ...body });
    else await register.run(body);
  } catch {
    return; // The window shows the refusal.
  }
  void toastSuccess(t(props.device ? 'printing.devices.modal.saved' : 'printing.devices.modal.created'));
  open.value = false;
}
</script>

<template>
  <FormModal
    v-model:open="open"
    testid="printing-device"
    :title="device ? $t('printing.devices.modal.edit') : $t('printing.devices.modal.create')"
    :submit-label="$t('printing.devices.modal.save')"
    :cancel-label="$t('printing.devices.modal.cancel')"
    :pending="pending"
    :error="error"
    @submit="confirm"
  >
    <div class="printing-device">
      <p
        class="printing-device__hint"
        data-testid="printing-device-hint"
      >
        {{ $t('printing.devices.modal.hint') }}
      </p>
      <ion-input
        data-testid="printing-device-name"
        :label="$t('printing.devices.modal.name')"
        :placeholder="$t('printing.devices.modal.namePlaceholder')"
        label-placement="stacked"
        fill="outline"
        mode="md"
        :maxlength="100"
        :value="name"
        :error-text="nameError ?? undefined"
        :class="{ 'ion-invalid': !!nameError, 'ion-touched': !!nameError }"
        @ion-input="name = String($event.detail.value ?? '')"
      />
      <fieldset class="printing-device__printers">
        <legend>{{ $t('printing.devices.modal.printers') }}</legend>
        <p
          v-if="printers.length === 0"
          class="printing-device__hint"
          data-testid="printing-device-no-printers"
        >
          {{ $t('printing.devices.modal.noPrinters') }}
        </p>
        <ion-checkbox
          v-for="printer in printers"
          :key="printer.id"
          :data-testid="`printing-device-printer-${printer.id}`"
          label-placement="end"
          justify="start"
          :checked="chosen.has(printer.id)"
          @ion-change="toggle(printer.id, !!$event.detail.checked)"
        >
          <span :data-testid="`printing-device-printer-label-${printer.id}`">{{
            $t('printing.devices.modal.printer', { name: printer.name, usage: $t(`printing.usage.${printer.usage}`) })
          }}</span>
        </ion-checkbox>
        <ion-note
          v-if="printersError"
          color="danger"
          data-testid="printing-device-printers-error"
        >
          {{ printersError }}
        </ion-note>
      </fieldset>
    </div>
  </FormModal>
</template>

<style scoped>
.printing-device {
  display: grid;
  gap: 12px;
}
.printing-device__hint {
  margin: 0;
  font-size: 0.875rem;
  color: var(--ion-color-medium-shade, var(--ion-color-medium));
}
.printing-device__printers {
  display: grid;
  gap: 10px;
  margin: 0;
  padding: 0;
  border: 0;
  min-width: 0;
}
.printing-device__printers legend {
  padding: 0;
  margin-bottom: 6px;
  font-weight: 600;
}
.printing-device__printers ion-checkbox {
  overflow-wrap: anywhere;
}
</style>
