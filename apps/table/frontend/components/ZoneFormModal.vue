<script setup lang="ts">
// A zone's dialog (WORKBOOK «Zonas», «Plano de sala»; TABLE-F01, F06).
// - `full` (Zones): Name, Description (optional), Colour (Blue, Cyan, Purple, Green, Amber, Red, Grey) and
//   Order (empty = the last one), «Add zone»; editing adds «Active» and «Save changes», and sends only what
//   changed.
// - `plan` (the plan's pencil): «Edit zone» with Name and Description, «Delete zone» and «Save».
// «Delete zone» (whoever may) asks first, and with tables in the zone it is off and says why. A created or
// saved zone comes back in `saved` (the plan chooses a new one).
import { FormModal } from '@erplora/ui/components';
import { useCommand } from '@erplora/ui/sdk';
import { IonButton, IonInput, IonSelect, IonSelectOption, IonToggle } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import { useT } from '../composables/useT';
import type { ZoneColor, ZoneOut, ZonePatchIn } from '../operations';
import ZoneDeleteDialog from './ZoneDeleteDialog.vue';

const props = withDefaults(
  defineProps<{
    /** The zone being edited; `null` = «New zone». */
    zone: ZoneOut | null;
    variant?: 'full' | 'plan';
    canDelete?: boolean;
  }>(),
  { variant: 'full', canDelete: false },
);

const open = defineModel<boolean>('open', { default: false });
const emit = defineEmits<{ saved: [zone: ZoneOut] }>();

const COLORS: readonly ZoneColor[] = ['primary', 'secondary', 'tertiary', 'success', 'warning', 'danger', 'medium'];

interface Form {
  name: string;
  description: string;
  color: ZoneColor;
  order: string;
  active: boolean;
}

const t = useT();
const creation = useCommand('table.zone.create');
const update = useCommand('table.zone.update');
const pending = computed(() => creation.pending.value || update.pending.value);
const error = computed(() => (props.zone ? update.error.value : creation.error.value));
const full = computed(() => props.variant === 'full');
const confirmDelete = ref(false);

function fromZone(zone: ZoneOut | null): Form {
  if (!zone) return { name: '', description: '', color: 'primary', order: '', active: true };
  return { name: zone.name, description: zone.description, color: zone.color, order: String(zone.sort_order), active: zone.is_active };
}

const form = ref<Form>(fromZone(props.zone));
// Two sources, compared one by one: a live repaint of the same zone (a new row, same id) keeps what is
// being typed; opening the dialog or another zone starts over.
watch(
  [open, () => props.zone?.id],
  ([isOpen]) => {
    if (!isOpen) return;
    form.value = fromZone(props.zone);
    creation.error.value = null;
    update.error.value = null;
  },
  { immediate: true },
);

const text = (value: unknown): string => (value === null || value === undefined ? '' : String(value));
const invalid = (message: string | undefined) => ({ 'ion-invalid': !!message, 'ion-touched': !!message });
const whole = (value: string): number => (/^\d+$/.test(value.trim()) ? Number(value.trim()) : (value.trim() as unknown as number));
const title = computed(() => (props.zone ? t('table.zoneForm.titleEdit') : t('table.zoneForm.titleNew')));
const submitLabel = computed(() => {
  if (!props.zone) return t('table.zoneForm.create');
  return full.value ? t('table.zoneForm.save') : t('table.zoneForm.saveShort');
});

function set<K extends keyof Form>(field: K, value: Form[K]): void {
  form.value = { ...form.value, [field]: value };
}

function patch(zone: ZoneOut): ZonePatchIn {
  const f = form.value;
  const out: ZonePatchIn = { id: zone.id };
  if (f.name.trim() !== zone.name) out.name = f.name.trim();
  if (f.description.trim() !== zone.description) out.description = f.description.trim();
  if (full.value) {
    if (f.color !== zone.color) out.color = f.color;
    if (f.order.trim() !== String(zone.sort_order)) out.sort_order = whole(f.order);
    if (f.active !== zone.is_active) out.is_active = f.active;
  }
  return out;
}

async function save(): Promise<void> {
  const f = form.value;
  let saved: ZoneOut;
  try {
    if (props.zone) saved = await update.run(patch(props.zone));
    else {
      saved = await creation.run({
        name: f.name.trim(),
        ...(full.value ? { description: f.description.trim(), color: f.color } : {}),
        ...(full.value && f.order.trim() ? { sort_order: whole(f.order) } : {}),
      });
    }
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
    testid="table-zone-form"
    :title="title"
    :pending="pending"
    :error="error"
    :submit-disabled="!form.name.trim()"
    @submit="save"
  >
    <template #default="{ fieldErrors }">
      <div class="table-zone-form">
        <ion-input
          data-testid="table-zone-form-name"
          :value="form.name"
          :label="$t('table.zoneForm.name')"
          :placeholder="zone ? undefined : $t('table.add.zonePlaceholder')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :maxlength="100"
          :error-text="fieldErrors.name"
          :class="invalid(fieldErrors.name)"
          @ion-input="set('name', text($event.detail.value))"
        />
        <ion-input
          data-testid="table-zone-form-description"
          :value="form.description"
          :label="$t('table.zoneForm.description')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :maxlength="500"
          :error-text="fieldErrors.description"
          :class="invalid(fieldErrors.description)"
          @ion-input="set('description', text($event.detail.value))"
        />
        <template v-if="full">
          <ion-select
            data-testid="table-zone-form-color"
            :value="form.color"
            :label="$t('table.zoneForm.color')"
            label-placement="floating"
            fill="outline"
            mode="md"
            interface="popover"
            @ion-change="set('color', $event.detail.value)"
          >
            <ion-select-option
              v-for="color in COLORS"
              :key="color"
              :value="color"
            >
              {{ t(`table.color.${color}`) }}
            </ion-select-option>
          </ion-select>
          <ion-input
            data-testid="table-zone-form-sort_order"
            type="number"
            inputmode="numeric"
            min="0"
            :value="form.order"
            :label="$t('table.zoneForm.order')"
            label-placement="floating"
            fill="outline"
            mode="md"
            :error-text="fieldErrors.sort_order"
            :class="invalid(fieldErrors.sort_order)"
            @ion-input="set('order', text($event.detail.value))"
          />
          <ion-toggle
            v-if="zone"
            data-testid="table-zone-form-active"
            label-placement="end"
            justify="start"
            :checked="form.active"
            @ion-change="set('active', $event.detail.checked)"
          >
            {{ $t('table.zoneForm.active') }}
          </ion-toggle>
        </template>
      </div>
    </template>
    <template #footer="{ cancel, submit }">
      <ion-button
        v-if="zone && canDelete"
        class="table-zone-form__delete"
        fill="outline"
        color="danger"
        data-testid="table-zone-form-delete"
        :disabled="pending"
        @click="confirmDelete = true"
      >
        {{ $t('table.zoneForm.delete') }}
      </ion-button>
      <ion-button
        fill="clear"
        data-testid="table-zone-form-cancel"
        :disabled="pending"
        @click="cancel"
      >
        {{ $t('table.cancel') }}
      </ion-button>
      <ion-button
        data-testid="table-zone-form-submit"
        :disabled="pending || !form.name.trim()"
        @click="submit"
      >
        {{ submitLabel }}
      </ion-button>
    </template>
  </FormModal>
  <ZoneDeleteDialog
    v-if="zone"
    v-model:open="confirmDelete"
    testid="table-zone-form-delete-confirm"
    :zone="zone"
    @deleted="open = false"
  />
</template>

<style scoped>
.table-zone-form {
  display: grid;
  gap: 14px;
}
.table-zone-form__delete {
  margin-inline-end: auto;
}
</style>
