<script setup lang="ts">
// «New printer» / «Edit printer» (PRINTING-F03, F04; the old «Add printer by IP», widened to every
// connection the app reaches): «Name», «Connection» (Network, USB, Bluetooth, System printer (A4)), its
// address — «IP address or name» and «Port» (9100) for a network one, «Bluetooth MAC», «USB queue name»,
// none for the system printer —, «Paper width» (80 or 58 mm, kept with it: the app prints 32 characters a
// line for now, and the window says so; not for the system printer), «Role» (the
// system printer prints receipts and A4 documents only) and «Active». «Save» adds it or saves it and says
// so; a refusal is said at its field in the server's words (an address no printer can have, a taken name).
import { FormModal, type FormModalError } from '@erplora/ui/components';
import { useCommand } from '@erplora/ui/sdk';
import { toastSuccess } from '@erplora/ui/shell';
import { IonInput, IonItem, IonLabel, IonNote, IonSelect, IonSelectOption, IonToggle } from '@ionic/vue';
import { computed, shallowRef, watch } from 'vue';

import { useT } from '../composables/useT';
import { refusal } from '../lib/refusal';
import type { PaperWidth, PrinterKind, PrinterOut, Usage } from '../operations';

const props = defineProps<{ printer: PrinterOut | null }>();

const open = defineModel<boolean>('open', { required: true });

const KINDS: readonly PrinterKind[] = ['network', 'usb', 'bluetooth', 'system'];
const USAGES: readonly Usage[] = ['receipt', 'kitchen', 'bar', 'label'];
const PAPERS: readonly PaperWidth[] = [80, 58];
const DEFAULT_PORT = '9100';
const ADDRESS_LABEL: Record<Exclude<PrinterKind, 'system'>, string> = {
  network: 'printing.modal.host',
  bluetooth: 'printing.modal.mac',
  usb: 'printing.modal.queue',
};

const t = useT();
const create = useCommand('printing.printer.create');
const update = useCommand('printing.printer.update');

const name = shallowRef('');
const kind = shallowRef<PrinterKind>('network');
const address = shallowRef('');
const port = shallowRef(DEFAULT_PORT);
const paper = shallowRef<PaperWidth>(80);
const usage = shallowRef<Usage>('receipt');
const active = shallowRef(true);
const missing = shallowRef(false);

watch(
  open,
  (now) => {
    if (!now) return;
    const p = props.printer;
    name.value = p?.name ?? '';
    kind.value = p?.kind ?? 'network';
    address.value = p?.address ?? '';
    port.value = p?.port != null ? String(p.port) : DEFAULT_PORT;
    paper.value = (p?.paper_width as PaperWidth | undefined) ?? 80;
    usage.value = p?.usage ?? 'receipt';
    active.value = p?.is_active ?? true;
    missing.value = false;
    create.error.value = null;
    update.error.value = null;
  },
  { immediate: true },
);

const isSystem = computed(() => kind.value === 'system');
const isNetwork = computed(() => kind.value === 'network');
// The computer's own printer prints A4 pages: the receipt role only (the server says so too).
watch(isSystem, (system) => {
  if (system) usage.value = 'receipt';
});

const pending = computed(() => create.pending.value || update.pending.value);
const error = computed<FormModalError | null>(() => refusal(create.error.value ?? update.error.value, t('printing.modal.failed')));
const fieldError = (field: string) => error.value?.fields?.[field] ?? null;
const nameError = computed(() => (missing.value ? t('printing.modal.required') : fieldError('name')));

function body() {
  const typedPort = Number.parseInt(port.value, 10);
  return {
    name: name.value.trim(),
    kind: kind.value,
    address: isSystem.value ? '' : address.value.trim(),
    port: isNetwork.value ? (Number.isNaN(typedPort) ? null : typedPort) : null,
    paper_width: paper.value,
    usage: usage.value,
    is_active: active.value,
  };
}

async function confirm(): Promise<void> {
  missing.value = !name.value.trim();
  if (missing.value) return;
  try {
    if (props.printer) await update.run({ printer_id: props.printer.id, ...body() });
    else await create.run(body());
  } catch {
    return; // The window shows the refusal.
  }
  void toastSuccess(t(props.printer ? 'printing.modal.saved' : 'printing.modal.created'));
  open.value = false;
}
</script>

<template>
  <FormModal
    v-model:open="open"
    testid="printing-printer"
    :title="printer ? $t('printing.modal.edit') : $t('printing.modal.create')"
    :submit-label="$t('printing.modal.save')"
    :cancel-label="$t('printing.modal.cancel')"
    :pending="pending"
    :error="error"
    @submit="confirm"
  >
    <div class="printing-printer">
      <ion-input
        data-testid="printing-printer-name"
        :label="$t('printing.modal.name')"
        label-placement="stacked"
        fill="outline"
        mode="md"
        :maxlength="100"
        :value="name"
        :error-text="nameError ?? undefined"
        :class="{ 'ion-invalid': !!nameError, 'ion-touched': !!nameError }"
        @ion-input="name = String($event.detail.value ?? '')"
      />
      <ion-select
        data-testid="printing-printer-kind"
        :label="$t('printing.modal.kind')"
        label-placement="stacked"
        fill="outline"
        mode="md"
        interface="popover"
        :value="kind"
        @ion-change="kind = $event.detail.value as PrinterKind"
      >
        <ion-select-option
          v-for="option in KINDS"
          :key="option"
          :value="option"
        >
          {{ $t(`printing.kind.${option}`) }}
        </ion-select-option>
      </ion-select>
      <p
        v-if="isSystem"
        class="printing-printer__hint"
        data-testid="printing-printer-system-hint"
      >
        {{ $t('printing.modal.systemHint') }}
      </p>
      <div
        v-else
        class="printing-printer__address"
      >
        <ion-input
          data-testid="printing-printer-address"
          :label="t(ADDRESS_LABEL[kind as Exclude<PrinterKind, 'system'>])"
          label-placement="stacked"
          fill="outline"
          mode="md"
          :maxlength="255"
          :value="address"
          :helper-text="isNetwork ? $t('printing.modal.ipHint') : undefined"
          :error-text="fieldError('address') ?? undefined"
          :class="{ 'ion-invalid': !!fieldError('address'), 'ion-touched': !!fieldError('address') }"
          @ion-input="address = String($event.detail.value ?? '')"
        />
        <ion-input
          v-if="isNetwork"
          data-testid="printing-printer-port"
          class="printing-printer__port"
          type="number"
          inputmode="numeric"
          :label="$t('printing.modal.port')"
          label-placement="stacked"
          fill="outline"
          mode="md"
          :min="1"
          :max="65535"
          :value="port"
          :error-text="fieldError('port') ?? undefined"
          :class="{ 'ion-invalid': !!fieldError('port'), 'ion-touched': !!fieldError('port') }"
          @ion-input="port = String($event.detail.value ?? '')"
        />
      </div>
      <ion-select
        v-if="!isSystem"
        data-testid="printing-printer-paper"
        :label="$t('printing.modal.paper')"
        label-placement="stacked"
        fill="outline"
        mode="md"
        interface="popover"
        :value="paper"
        @ion-change="paper = Number($event.detail.value) as PaperWidth"
      >
        <ion-select-option
          v-for="option in PAPERS"
          :key="option"
          :value="option"
        >
          {{ $t('printing.printers.paper', { n: option }) }}
        </ion-select-option>
      </ion-select>
      <p
        v-if="!isSystem"
        class="printing-printer__hint"
        data-testid="printing-printer-paper-hint"
      >
        {{ $t('printing.modal.paperHint') }}
      </p>
      <ion-select
        data-testid="printing-printer-usage"
        :label="$t('printing.modal.usage')"
        label-placement="stacked"
        fill="outline"
        mode="md"
        interface="popover"
        :value="usage"
        :disabled="isSystem"
        @ion-change="usage = $event.detail.value as Usage"
      >
        <ion-select-option
          v-for="option in USAGES"
          :key="option"
          :value="option"
        >
          {{ $t(`printing.usage.${option}`) }}
        </ion-select-option>
      </ion-select>
      <ion-note
        v-if="fieldError('usage')"
        color="danger"
        data-testid="printing-printer-usage-error"
      >
        {{ fieldError('usage') }}
      </ion-note>
      <ion-item lines="none">
        <ion-label>{{ $t('printing.modal.active') }}</ion-label>
        <ion-toggle
          slot="end"
          data-testid="printing-printer-active"
          :checked="active"
          :aria-label="$t('printing.modal.active')"
          @ion-change="active = !!$event.detail.checked"
        />
      </ion-item>
    </div>
  </FormModal>
</template>

<style scoped>
.printing-printer {
  display: grid;
  gap: 12px;
}
.printing-printer__address {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 12px;
}
.printing-printer__port {
  width: 7rem;
}
.printing-printer__hint {
  margin: 0;
  font-size: 0.875rem;
  color: var(--ion-color-medium-shade, var(--ion-color-medium));
}
</style>
